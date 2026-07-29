#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
브릿지포 — 부산 외국인 구직자용 공고 진단 서비스 (Streamlit)

두 축을 한 화면에서 보여준다.
  [ML]  적정 임금 80% 구간 + 신뢰도 등급 + 최저임금 경고   (로컬 추론, 비용 0원)
  [LLM] 근로조건 7종 미기재/모호 판정 + 모국어 확인 질문

탭 구성
  1. 공고 물어보기  공고를 붙여넣고 아무 언어로 질문한다. 질문한 언어로 답한다.
  2. 수집 공고      이미 진단해 둔 5,168건. 진단은 사전 계산본이라 비용이 없다.
  3. 모델 성능      성공기준 3종 지표와 한계.

화면 언어
  사이드바에서 고른 언어로 화면 전체가 바뀐다 (bridge4_i18n_app.APP).
  일부러 한국어로 남기는 것 — 고용주에게 보여줄 질문 문장, 공고 인용 원문,
  그리고 '모델 성능' 탭(팀·심사용).

로컬 실행
    streamlit run streamlit_app.py

Streamlit Cloud 배포
    python prepare_deploy.py 로 deploy/ 를 만들어 GitHub 에 올린다.
    OPENAI_API_KEY 는 .env 가 아니라 Streamlit Secrets 에 넣는다.
    (.env 를 저장소에 올리면 키가 공개된다)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from bridge4_i18n_app import a as T
from bridge4_charts import t as CH_TXT
from bridge4_charts import (distribution_chart, percentile_of,
                            position_chart, similar_postings)
from bridge4_i18n_app import (man_range, reliability, suggest, value_label,
                              won)
from bridge4_report import build_questions_only, build_report
from llm_prompts import (LABELS, LANGUAGES, build_chat_context,
                         lang_directive)
from wage_parser import parse_wage

try:                       # 링크 수집기는 선택 의존성. 없으면 링크 입력칸을 숨긴다
    from crawler_interface import fetch_posting, validate as validate_fetch
    CRAWLER = True
except Exception:
    CRAWLER = False

st.set_page_config(page_title="브릿지포 — 공고 진단", page_icon="🧭", layout="wide")

ROOT = Path(__file__).parent
MODEL_DIR = ROOT / "models"
DATA_DIR = ROOT / "data"
LLM_DIR = ROOT / "reports" / "llm"
REPORT_DIR = ROOT / "reports"

NO_INFO = "정보없음"




def txt(v, default: str = NO_INFO) -> str:
    s = "" if v is None else str(v).strip()
    return default if s in ("", "nan", "None") else s


# ─────────────────────────────────────────────────────────────────────────────
# 로딩 (캐시)
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner="임금 예측 모델 로딩…")
def load_model():
    import lightgbm as lgb

    meta = json.loads((MODEL_DIR / "meta.json").read_text(encoding="utf-8"))
    # model_file 대신 model_str 을 쓴다. LightGBM 의 C 라이브러리는 Windows 에서
    # 비ASCII 경로(예: 'OneDrive - 부산외국어대학교')를 열지 못한다.
    # 파일 읽기는 Python 이 하고 모델 문자열만 넘기면 경로 문제가 사라진다.
    boosters = {q: lgb.Booster(model_str=(MODEL_DIR / f"lgbm_q{q}.txt")
                               .read_text(encoding="utf-8"))
                for q in (10, 50, 90)}
    want = meta["numeric_features"] + meta["categorical_features"]
    if boosters[50].feature_name() != want:
        raise RuntimeError("모델과 meta.json 의 피처 순서가 다릅니다.")
    return meta, boosters


@st.cache_data(show_spinner="공고 데이터 로딩…")
def load_postings() -> pd.DataFrame:
    """결측(NaN)을 그대로 유지한다.

    fillna("") 를 하면 뒤에서 '정보없음' 으로 매핑되는데, 학습은 CSV 의 NaN 을
    결측으로, 문자열 '정보없음' 을 별개 범주로 구분해서 다뤘다.
    채워버리면 학습이 본 적 없는 값이 들어가 예측이 조용히 달라진다.
    """
    pq = DATA_DIR / "postings.parquet"
    if pq.exists():
        return pd.read_parquet(pq)
    csv = DATA_DIR / "team_merged.csv"
    if csv.exists():
        return pd.read_csv(csv, encoding="utf-8-sig", dtype=str, low_memory=False)
    return pd.DataFrame()


@st.cache_data(show_spinner=False)
def load_llm() -> tuple[pd.DataFrame | None, dict[str, pd.DataFrame]]:
    det = None
    p = LLM_DIR / "detect_predictions.csv"
    if p.exists():
        det = pd.read_csv(p, encoding="utf-8-sig", dtype=str).fillna("")
    chk: dict[str, pd.DataFrame] = {}
    for f in sorted(LLM_DIR.glob("checklist_*.csv")):
        q = pd.read_csv(f, encoding="utf-8-sig", dtype=str).fillna("")
        if "한국어질문" in q.columns:
            q = q[q["한국어질문"].str.strip() != ""]
            if len(q):
                chk[f.stem.replace("checklist_", "")] = q
    return det, chk


@st.cache_data(show_spinner=False)
def load_reports() -> dict[str, pd.DataFrame]:
    out = {}
    for name, p in {
        "metrics": REPORT_DIR / "metrics.csv",
        "reliability": REPORT_DIR / "reliability_breakdown.csv",
        "importance": REPORT_DIR / "feature_importance.csv",
        "f1": LLM_DIR / "eval_f1.csv",
        "backtrans_zh": LLM_DIR / "backtrans_zh.csv",
    }.items():
        if p.exists():
            try:
                out[name] = pd.read_csv(p, encoding="utf-8-sig")
            except Exception:
                pass
    return out


# ─────────────────────────────────────────────────────────────────────────────
# 예측
# ─────────────────────────────────────────────────────────────────────────────

def predict(rows: pd.DataFrame, meta: dict, boosters: dict) -> pd.DataFrame:
    """학습 시 build_xy 와 동일하게 만들고 CQR 보정을 적용한다."""
    num, cat, cats = (meta["numeric_features"], meta["categorical_features"],
                      meta["categories"])
    X = pd.DataFrame(index=rows.index)
    for c in num:
        X[c] = pd.to_numeric(rows[c], errors="coerce") if c in rows.columns else np.nan
    for c in cat:
        s = (rows[c].astype(str).str.strip()
             .replace({"": NO_INFO, "nan": NO_INFO, "None": NO_INFO})
             if c in rows.columns else pd.Series(NO_INFO, index=rows.index))
        # 학습에 없던 값은 결측으로 넘겨 LightGBM 이 결측으로 처리하게 한다.
        # pd.Categorical 에 미등록 값을 그대로 주면 pandas 4 에서 예외가 되므로
        # 여기서 먼저 NaN 으로 바꾼다.
        s = s.where(s.isin(cats[c]), other=None)
        X[c] = pd.Categorical(s, categories=cats[c])
    X = X[num + cat]

    w = float(meta["cqr_widen_log"])          # CQR 보정폭 (log 공간)
    raw = {q: boosters[q].predict(X) for q in (10, 50, 90)}
    st_ = np.sort(np.vstack([np.expm1(raw[10] - w),
                            np.expm1(raw[50]),
                            np.expm1(raw[90] + w)]), axis=0)
    lo, mid, hi = st_[0], st_[1], st_[2]
    width = hi - lo

    mw = int(meta["minimum_wage_2026"])
    ratio = mid / mw
    rel = np.full(len(mid), "보통", dtype=object)
    rel[ratio <= 1.16] = "높음"
    rel[(ratio > 1.45) & (ratio <= 1.94)] = "낮음"
    rel[ratio > 1.94] = "매우낮음"
    rel[width > 8000] = "매우낮음"
    return pd.DataFrame({"lo": lo.round(0), "mid": mid.round(0), "hi": hi.round(0),
                         "width": width.round(0), "rel": rel}, index=rows.index)


# ─────────────────────────────────────────────────────────────────────────────
# 렌더링
# ─────────────────────────────────────────────────────────────────────────────

def det_from_row(r: pd.Series) -> dict:
    return {
        "status": r.get("status", ""),
        "labels": {l: {"flag": (int(float(r[f"pred_{l}"]))
                               if str(r.get(f"pred_{l}", "")).strip() not in ("", "nan")
                               else None),
                       "evidence": r.get(f"ev_{l}", "")} for l in LABELS},
        "기타": [x for x in str(r.get("기타_확인필요", "")).split(" | ") if x],
    }


# ─────────────────────────────────────────────────────────────────────────────
# 앱
# ─────────────────────────────────────────────────────────────────────────────

def api_key() -> str | None:
    """키 우선순위: 화면 입력 -> Secrets -> 환경변수.

    화면 입력값은 st.session_state 에만 둔다. 파일로 쓰지 않는다.
    """
    k = (st.session_state.get("user_key") or "").strip()
    if k:
        return k
    try:
        v = st.secrets.get("OPENAI_API_KEY")
        if v:
            return str(v)
    except Exception:
        pass
    if not os.getenv("OPENAI_API_KEY"):
        try:                       # 로컬 실행 편의 — 배포본에는 .env 가 없다
            from dotenv import load_dotenv
            load_dotenv()
        except (ModuleNotFoundError, Exception):
            pass
    return os.getenv("OPENAI_API_KEY")


def key_source() -> str:
    if (st.session_state.get("user_key") or "").strip():
        return "직접 입력"
    try:
        if st.secrets.get("OPENAI_API_KEY"):
            return "Secrets"
    except Exception:
        pass
    return "환경변수" if os.getenv("OPENAI_API_KEY") else "없음"


def openai_client():
    key = api_key()
    if not key:
        return None
    from openai import OpenAI
    return OpenAI(api_key=key, timeout=120.0, max_retries=1)


def friendly_error(e: Exception) -> str:
    m = str(e)
    if "insufficient_quota" in m or "current quota" in m:
        return ("이 API 키는 OpenAI 사용 한도를 초과했습니다. "
                "크레딧을 충전하거나 다른 키를 넣어 주세요.")
    if "invalid_api_key" in m or "Incorrect API key" in m:
        return "API 키가 올바르지 않습니다. 다시 확인해 주세요."
    if "model_not_found" in m or "does not exist" in m:
        return "이 키로는 해당 모델을 쓸 수 없습니다. 다른 키를 쓰거나 모델을 바꿔 주세요."
    return f"{type(e).__name__}: {m[:220]}"


# ── 조건 입력 ────────────────────────────────────────────────────────

def cond_form(meta: dict, prefix: str, lang: str) -> dict:
    """임금 예측에 필요한 조건. 아는 것만 채우면 된다."""
    cats = meta["categories"]

    def opts(c):
        return [NO_INFO] + [v for v in cats.get(c, []) if v != NO_INFO]

    def fmt(v):
        # 데이터 값은 모델의 학습 범주라 번역하면 예측이 깨진다.
        # 표시만 바꾸고 값은 그대로 둔다.
        return T(lang, "no_info") if v == NO_INFO else v

    def fmt_of(field):
        # ksco_code 는 '1.0' 같은 코드라 그대로 보여주면 무엇인지 알 수 없다.
        # 기업규모구간도 한국어 값이라 다른 언어 사용자가 읽지 못한다.
        return lambda v: value_label(lang, field, v)

    a = st.columns(3)
    gu = a[0].selectbox(T(lang, "c_gu"), opts("sigungu"), format_func=fmt, key=prefix + "gu")
    weekly = a[1].number_input(T(lang, "c_weekly"), 0.0, 80.0, 40.0, 1.0, key=prefix + "wk")
    days = a[2].number_input(T(lang, "c_days"), 0.0, 7.0, 5.0, 1.0, key=prefix + "dy")

    b = st.columns(3)
    ksco = b[0].selectbox(T(lang, "c_ksco"), opts("ksco_code"),
                          format_func=fmt_of("ksco_code"), key=prefix + "ks")
    emp = b[1].number_input(T(lang, "c_emp"), 0, 50000, 0, 10, key=prefix + "em",
                            help=T(lang, "c_emp_help"))
    size = b[2].selectbox(T(lang, "c_size"), opts("기업규모구간"),
                         format_func=fmt_of("기업규모구간"), key=prefix + "sz")

    with st.expander(T(lang, "c_more")):
        c = st.columns(2)
        industry = c[0].selectbox(T(lang, "c_ind"), opts("industry"), format_func=fmt, key=prefix + "in")
        jobcat = c[1].selectbox(T(lang, "c_job"), opts("job_category"), format_func=fmt, key=prefix + "jc")
        d = st.columns(3)
        career = d[0].selectbox(T(lang, "c_career"), opts("career"), format_func=fmt, key=prefix + "ca")
        edu = d[1].selectbox(T(lang, "c_edu"), opts("education"), format_func=fmt, key=prefix + "ed")
        employ = d[2].selectbox(T(lang, "c_type"), opts("employ_type"), format_func=fmt, key=prefix + "et")

    return {
        "weekly_hours_final": weekly or np.nan,
        "work_days": days or np.nan,
        "employees": emp or np.nan,
        "founded": np.nan, "revenue": np.nan, "hire_count": np.nan,
        "sigungu": gu, "ksco_code": ksco, "기업규모구간": size,
        "industry": industry, "job_category": jobcat,
        "career": career, "education": edu, "employ_type": employ,
        "severance": NO_INFO, "insurance": NO_INFO, "work_form": NO_INFO,
        "기업형태": NO_INFO,
        "is_fulltime": "True" if weekly >= 35 else "False",
    }


def wage_inputs(prefix: str, lang: str):
    c = st.columns([1, 2])
    KMAP = {"미표기": "k_none", "월급": "k_month", "시급": "k_hour",
            "연봉": "k_year", "일급": "k_day"}
    kind = c[0].selectbox(T(lang, "wage_kind"), list(KMAP),
                          format_func=lambda k: T(lang, KMAP[k]),
                          key=prefix + "sk")
    if kind == "미표기":
        return "", None
    unit = {"월급": "만원", "시급": "원", "연봉": "만원", "일급": "만원"}[kind]
    step = {"월급": 10.0, "시급": 100.0, "연봉": 100.0, "일급": 1.0}[kind]
    dflt = {"월급": 220.0, "시급": 11000.0, "연봉": 2800.0, "일급": 10.0}[kind]
    v = c[1].number_input(T(lang, "wage_amt") + " (" + unit + ")",
                          0.0, 100000.0, dflt, step, key=prefix + "sv")
    if not v:
        return kind, None
    return kind, float(v * 10000 if unit == "만원" else v)


def hourly_from(kind: str, won, weekly: float, days: float):
    """주휴 포함 시급 환산. wage_interval_model 의 타깃 정의와 같아야 한다."""
    if won is None or not kind:
        return None
    mh = (weekly or 40) * 4.345 * 1.2
    if kind == "시급":
        return won
    if kind == "월급":
        return won / mh if mh else None
    if kind == "연봉":
        return won / 12 / mh if mh else None
    if kind == "일급":
        daily = (weekly / days) if days else 8.0
        return won / daily if daily else None
    return None


# ── 채팅 ─────────────────────────────────────────────────────────────

def chat_panel(ctx: str, key_ns: str, lang: str) -> None:
    """공고 컨텍스트를 근거로 자유 질의응답. 답변 언어는 질문 언어를 따른다."""
    from llm_prompts import CHAT_SYSTEM
    import llm_diagnose as L

    hist_key = key_ns + "_hist"
    if hist_key not in st.session_state:
        st.session_state[hist_key] = []
    hist = st.session_state[hist_key]

    st.markdown("#### " + T(lang, "chat_hdr"))
    st.caption(T(lang, "chat_note"))

    if not hist:
        sg = suggest(lang)
        cols = st.columns(len(sg))
        for i, q0 in enumerate(sg):
            if cols[i].button(q0, key=f"{key_ns}_sg{i}", use_container_width=True):
                st.session_state[key_ns + "_pending"] = q0
                st.rerun()

    for m in hist:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    q = st.chat_input(T(lang, "chat_ph"), key=key_ns + "_in")
    pending = st.session_state.pop(key_ns + "_pending", None)
    q = q or pending
    if not q:
        return

    cli = openai_client()
    if cli is None:
        st.error(T(lang, "chat_needkey"), icon="🔑")
        return

    hist.append({"role": "user", "content": q})
    with st.chat_message("user"):
        st.markdown(q)

    # 정적인 system + 공고 컨텍스트를 앞에 고정해 프롬프트 캐시가 붙게 한다
    # 자료가 한국어라 한국어로 답해버리는 일이 있었다. 최신 지시가 더 잘 지켜지므로
    # 대화 이력 뒤에 언어 지시를 한 번 더 둔다.
    msgs = ([{"role": "system", "content": CHAT_SYSTEM},
             {"role": "system", "content": ctx}] + hist
            + [{"role": "system",
                "content": lang_directive(LANGUAGES.get(lang, lang))}])

    with st.chat_message("assistant"):
        try:
            stream = cli.chat.completions.create(
                model=L.MODEL_CHECKLIST,
                reasoning_effort="low",
                messages=msgs,
                max_completion_tokens=1400,
                prompt_cache_key="bridge4-chat-v1",
                stream=True,
            )
            def gen():
                for ch in stream:
                    if ch.choices and ch.choices[0].delta.content:
                        yield ch.choices[0].delta.content
            answer = st.write_stream(gen)
        except Exception as e:
            answer = None
            st.error(friendly_error(e), icon="⚠️")

    if answer:
        hist.append({"role": "assistant", "content": answer})
    else:
        hist.pop()


def wage_ctx(p, rec) -> dict:
    posted = ""
    amt = pd.to_numeric(pd.Series([rec.get("sal_min_won")]), errors="coerce").iloc[0]
    kind = txt(rec.get("sal_type"), "")
    if pd.notna(amt) and kind:
        posted = f"{kind} {amt:,.0f}원"
    h = pd.to_numeric(pd.Series([rec.get("hourly_wage")]), errors="coerce").iloc[0]
    return {"lo": float(p["lo"]), "mid": float(p["mid"]), "hi": float(p["hi"]),
            "rel": str(p["rel"]), "posted": posted,
            "hourly": float(h) if pd.notna(h) else None}


# ── 메인 ─────────────────────────────────────────────────────────────

def url_panel(lang: str) -> None:
    """링크로 공고를 불러와 아래 폼을 채운다.

    crawl_alba() 가 아직 구현되지 않았으면 그 사실을 사용자 언어로 알리고
    직접 붙여넣기로 안내한다. 링크가 실패해도 기존 경로는 그대로 동작한다.
    """
    if not CRAWLER:
        return
    st.markdown("**" + T(lang, "url_hdr") + "**")
    st.caption(T(lang, "url_note"))
    c = st.columns([4, 1])
    url = c[0].text_input(T(lang, "url_lbl"), key="p_url",
                          placeholder=T(lang, "url_ph"),
                          label_visibility="collapsed")
    if not c[1].button(T(lang, "url_btn"), key="p_url_go",
                       use_container_width=True):
        return
    if not (url or "").strip():
        return

    with st.spinner(T(lang, "url_btn")):
        try:
            r = fetch_posting(url)
        except Exception as e:      # 수집기 예외가 앱을 죽이지 않게
            st.error(T(lang, "url_fail"), icon="🔗")
            st.caption(f"{type(e).__name__}: {str(e)[:160]}")
            return

    if not r.ok:
        # 미구현과 수집 실패를 구분해서 안내한다
        todo = "구현되지 않았" in (r.error or "")
        st.warning(T(lang, "url_todo" if todo else "url_fail"), icon="🔗")
        if not todo:
            st.caption(r.error[:200])
        return

    # 폼 위젯의 세션 값을 직접 채운다. 위젯 키와 이름이 같아야 반영된다.
    st.session_state["p_body"] = r.body or ""
    if r.wage_kind and r.wage_amount:
        st.session_state["p_sk"] = r.wage_kind
        st.session_state["p_sv"] = (r.wage_amount / 10000
                                    if r.wage_kind in ("월급", "연봉", "일급")
                                    else r.wage_amount)
    for key, val in (("p_gu", r.sigungu), ("p_ks", r.ksco_code),
                     ("p_et", r.employ_type), ("p_ca", r.career),
                     ("p_ed", r.education), ("p_sz", r.company_size)):
        if val:
            st.session_state[key] = val
    if r.weekly_hours:
        st.session_state["p_wk"] = float(r.weekly_hours)
    if r.work_days:
        st.session_state["p_dy"] = float(r.work_days)
    if r.employees:
        st.session_state["p_em"] = int(r.employees)

    st.success(T(lang, "url_ok"), icon="🔗")
    # 학습 범주와 어긋난 값이 있으면 알린다 (조용히 결측 처리되는 것을 막는다)
    for w in validate_fetch(r):
        st.caption("⚠️ " + w)
    st.session_state["p_ready"] = False        # 폼을 펼쳐 확인하게 한다


def show_metrics(p, kind: str, posted, real, lang: str) -> None:
    """지표 4개.

    이전에는 '공고 임금' 칸에 환산 시급(10,759원)을 넣어, 월급 2,326,840원짜리
    공고가 마치 시급 1만원짜리로 보였다. 표기 그대로를 값으로 두고 환산은 따로 낸다.
    """
    c = st.columns(4)
    rel = str(p["rel"])
    if rel == "매우낮음":
        c[0].metric(T(lang, "m_range_short"), T(lang, "m_hold"))
    else:
        # 단위를 라벨로 올리고 값은 숫자만 둔다. 값에 단위까지 넣으면 잘린다.
        c[0].metric(T(lang, "m_range_short") + " (80%)",
                    f"{int(p['lo']):,} ~ {int(p['hi']):,}")
    c[1].metric(T(lang, "m_month"), man_range(lang, p["lo"], p["hi"]))

    if posted and pd.notna(posted):
        c[2].metric(T(lang, "m_posted"), won(lang, posted),
                    (T(lang, "m_hourly") + " " + won(lang, real)) if real else None,
                    delta_color="off")
    else:
        c[2].metric(T(lang, "m_posted"), T(lang, "m_notposted"))
    c[3].metric(T(lang, "m_reliab"), reliability(lang, rel))


def show_charts(p, real, cond: dict, posts, lang: str) -> None:
    """판정 근거를 그림으로. 숫자만 보여주면 믿을 근거가 없다."""
    with st.expander(T(lang, "viz_hdr"), expanded=True):
        mw = 10320
        st.altair_chart(
            position_chart(p["lo"], p["mid"], p["hi"], real, mw, lang),
            use_container_width=True)

        sample = similar_postings(posts, cond.get("ksco_code"), cond.get("sigungu"))
        ch = distribution_chart(sample, real, p["lo"], p["hi"], lang)
        if ch is None:
            st.caption(CH_TXT(lang, "nodata"))
            return
        st.altair_chart(ch, use_container_width=True)
        n = len(sample)
        st.caption(CH_TXT(lang, "few" if n < 30 else "n").format(n=n))
        pct = percentile_of(sample, real)
        if pct is not None:
            st.caption(T(lang, "pct").format(p=pct))


def main() -> None:
    # 언어를 가장 먼저 정한다. 제목·부제부터 이 값에 의존하기 때문이다.
    # 사이드바는 코드 순서대로 실행되므로 여기서 한 번 열고, 나머지는 아래에서 잇는다.
    with st.sidebar:
        st.markdown("### 🌐 Language · 语言 · 言語")
        codes = list(LANGUAGES)
        lang = st.selectbox("Language", codes,
                            index=codes.index("zh") if "zh" in codes else 0,
                            format_func=lambda c: LANGUAGES[c],
                            label_visibility="collapsed")
        st.divider()

    st.title("🧭 브릿지포")
    st.markdown(T(lang, "subtitle"))

    if not (MODEL_DIR / "meta.json").exists():
        st.error("models/meta.json 이 없습니다. "
                 "`python wage_interval_model.py` 를 먼저 실행하세요.")
        st.stop()

    meta, boosters = load_model()
    posts = load_postings()
    det_df, chk = load_llm()
    reports = load_reports()

    with st.sidebar:
        st.markdown("### " + T(lang, "sb_key"))
        st.text_input(T(lang, "key_lbl"), type="password", key="user_key",
                      placeholder=T(lang, "key_ph"), help=T(lang, "key_help"))
        src = key_source()
        if src == "없음":
            st.warning(T(lang, "key_none"), icon="🔑")
        else:
            st.success(T(lang, "key_ok") + " (" + src + ")", icon="🔑")
        st.caption(T(lang, "key_note"))
        st.divider()

        with st.expander(T(lang, "sb_perf")):
            m = reports.get("metrics")
            if m is not None and len(m):
                r = m.iloc[0]
                st.metric("임금 구간 커버리지", f"{r['coverage_pct']}%",
                          f"목표 80% · 보정 전 {r['coverage_before_cqr_pct']}%")
            f1 = reports.get("f1")
            if f1 is not None and "대표지표포함" in f1.columns:
                core = f1[f1["대표지표포함"] == "Y"]
                if len(core):
                    tp, fp, fn = (core[k].sum() for k in ("TP", "FP", "FN"))
                    st.metric("근로조건 탐지 F1", f"{2 * tp / (2 * tp + fp + fn):.3f}",
                              f"목표 0.80 · 대표 {len(core)}라벨")
            bz = reports.get("backtrans_zh")
            if bz is not None and "원문용어수" in bz.columns:
                o = pd.to_numeric(bz["원문용어수"], errors="coerce").sum()
                k = pd.to_numeric(bz["보존용어수"], errors="coerce").sum()
                if o:
                    st.metric("용어 보존율", f"{k / o * 100:.1f}%",
                              f"목표 90% · {int(o)}회")

    t1, t2, t3 = st.tabs([T(lang, "tab_chat"), T(lang, "tab_db"), T(lang, "tab_perf")])

    # ── 탭 1: 붙여넣고 대화 ─────────────────────────────────────
    with t1:
        with st.expander(T(lang, "step1"), expanded=not st.session_state.get("p_ready")):
            url_panel(lang)
            if CRAWLER:
                st.markdown("**" + T(lang, "url_or") + "**")
            body = st.text_area(
                T(lang, "body_lbl"), height=150, key="p_body",
                placeholder=T(lang, "body_ph"))
            st.markdown("**" + T(lang, "wage_hdr") + "**")
            auto = parse_wage(st.session_state.get("p_body", ""))
            if auto:
                st.caption("🔍 " + T(lang, "auto_found").format(
                    raw=auto["raw"], kind=auto["kind"]))
            kind, won_ = wage_inputs("p_", lang)
            st.markdown("**" + T(lang, "cond_hdr") + "**")
            cond = cond_form(meta, "p_", lang)
            if st.button(T(lang, "btn_start"), type="primary", key="p_go"):
                st.session_state["p_ready"] = True
                st.session_state.pop("t1_hist", None)
                st.rerun()

        if st.session_state.get("p_ready"):
            body = st.session_state.get("p_body", "")
            kind = st.session_state.get("p_sk", "미표기")
            # 지역변수 이름을 won 으로 두면 임포트한 won() 포맷 함수를 가린다
            posted = None
            if kind != "미표기":
                posted = float(st.session_state.get("p_sv", 0) or 0)
                posted = posted * 10000 if kind in ("월급", "연봉", "일급") else posted
            else:
                # 폼을 비워 두었으면 본문에서 읽어낸 값을 쓴다.
                # 이걸 안 하면 `월급 2,326,840원` 이 적힌 공고도 '미표기' 로 나온다.
                auto = parse_wage(body)
                if auto:
                    kind, posted = auto["kind"], auto["amount"]
            weekly = float(st.session_state.get("p_wk", 40) or 40)
            days = float(st.session_state.get("p_dy", 5) or 5)
            real = hourly_from("" if kind == "미표기" else kind, posted, weekly, days)

            cond = {
                "weekly_hours_final": weekly, "work_days": days,
                "employees": float(st.session_state.get("p_em", 0) or 0) or np.nan,
                "founded": np.nan, "revenue": np.nan, "hire_count": np.nan,
                "sigungu": st.session_state.get("p_gu", NO_INFO),
                "ksco_code": st.session_state.get("p_ks", NO_INFO),
                "기업규모구간": st.session_state.get("p_sz", NO_INFO),
                "industry": st.session_state.get("p_in", NO_INFO),
                "job_category": st.session_state.get("p_jc", NO_INFO),
                "career": st.session_state.get("p_ca", NO_INFO),
                "education": st.session_state.get("p_ed", NO_INFO),
                "employ_type": st.session_state.get("p_et", NO_INFO),
                "severance": NO_INFO, "insurance": NO_INFO, "work_form": NO_INFO,
                "기업형태": NO_INFO,
                "is_fulltime": "True" if weekly >= 35 else "False",
            }
            p = predict(pd.DataFrame([cond]), meta, boosters).iloc[0]
            rec = pd.Series({
                "company": "붙여넣은 공고", "title": "",
                "sigungu": cond["sigungu"] if cond["sigungu"] != NO_INFO else "",
                "ksco_name": "", "sal_type": "" if kind == "미표기" else kind,
                "sal_min_won": posted, "hourly_wage": real,
            })

            show_metrics(p, kind, posted, real, lang)
            show_charts(p, real, cond, posts, lang)

            det = None
            if body.strip():
                if st.session_state.get("t1_det_body") != body:
                    cli = openai_client()
                    if cli:
                        with st.spinner(T(lang, "spinner")):
                            try:
                                d_, items_ = run_live(body, lang)
                                st.session_state["t1_det"] = d_
                                st.session_state["t1_items"] = items_
                                st.session_state["t1_det_body"] = body
                            except Exception as e:
                                st.warning(friendly_error(e), icon="⚠️")
                det = st.session_state.get("t1_det")
                items = st.session_state.get("t1_items") or []
            else:
                items = []

            if det:
                with st.expander(T(lang, "rep_open")):
                    st.markdown(build_report(rec, p, det, items, LANGUAGES[lang], meta),
                                unsafe_allow_html=True)

            st.divider()
            chat_panel(build_chat_context(body, wage_ctx(p, rec), det), "t1", lang)

            if st.button(T(lang, "btn_reset"), key="p_reset"):
                for k in ("p_ready", "t1_hist", "t1_det", "t1_items", "t1_det_body"):
                    st.session_state.pop(k, None)
                st.rerun()

    # ── 탭 2: 수집 공고 ────────────────────────────────────────
    with t2:
        n_chk = chk[lang]["wantedAuthNo"].nunique() if lang in chk else 0
        st.caption(T(lang, "db_note") + "  ·  "
                   + f"{len(det_df) if det_df is not None else 0} / {n_chk}")
        if posts.empty:
            st.error("공고 데이터가 없습니다.")
        else:
            has_det = set(det_df["wantedAuthNo"]) if det_df is not None else set()
            has_chk = set(chk[lang]["wantedAuthNo"]) if lang in chk else set()
            c = st.columns([2, 1, 1])
            kw = c[0].text_input(T(lang, "db_search"), key="b_kw",
                                 placeholder=T(lang, "db_search_ph"))
            gus = [T(lang, "db_all")] + sorted(x for x in posts["sigungu"].dropna().unique()
                                   if str(x).strip())
            gu = c[1].selectbox(T(lang, "db_gu"), gus, key="b_gu")
            SCOPE = {"db_s1": T(lang, "db_s1"), "db_s2": T(lang, "db_s2"),
                     "db_s3": T(lang, "db_s3")}
            only = c[2].selectbox(T(lang, "db_scope"), list(SCOPE),
                                  format_func=lambda k: SCOPE[k], key="b_only")
            v = posts
            if kw:
                v = v[v["company"].str.contains(kw, na=False)
                      | v["title"].str.contains(kw, na=False)]
            if gu != T(lang, "db_all"):
                v = v[v["sigungu"] == gu]
            if only == "db_s1":
                v = v[v["wantedAuthNo"].isin(has_chk)]
            elif only == "db_s2":
                v = v[v["wantedAuthNo"].isin(has_det)]

            st.caption(f"{len(v):,} " + T(lang, "db_count"))
            if v.empty:
                st.info(T(lang, "db_none"))
            else:
                opts = v.head(300)
                idx = st.selectbox(
                    T(lang, "db_sel"), list(opts.index), key="b_sel",
                    format_func=lambda i: (
                        txt(opts.loc[i, "company"], "(기업명 미상)")[:26] + " — "
                        + txt(opts.loc[i, "title"], "")[:44]))
                rec = posts.loc[idx]
                p = predict(posts.loc[[idx]], meta, boosters).iloc[0]
                det = None
                if det_df is not None:
                    sel = det_df[det_df["wantedAuthNo"] == rec["wantedAuthNo"]]
                    if len(sel):
                        det = det_from_row(sel.iloc[0])
                items = []
                if lang in chk:
                    q_ = chk[lang]
                    items = q_[q_["wantedAuthNo"] == rec["wantedAuthNo"]].to_dict("records")

                st.divider()
                show_metrics(p, txt(rec.get("sal_type"), ""),
                             pd.to_numeric(pd.Series([rec.get("sal_min_won")]),
                                           errors="coerce").iloc[0],
                             pd.to_numeric(pd.Series([rec.get("hourly_wage")]),
                                           errors="coerce").iloc[0], lang)
                show_charts(p, pd.to_numeric(pd.Series([rec.get("hourly_wage")]),
                                             errors="coerce").iloc[0],
                            {"ksco_code": txt(rec.get("ksco_code"), ""),
                             "sigungu": txt(rec.get("sigungu"), "")},
                            posts, lang)
                st.markdown(build_report(rec, p, det, items, LANGUAGES[lang], meta),
                            unsafe_allow_html=True)
                if items:
                    with st.expander(T(lang, "db_qonly")):
                        st.markdown(build_questions_only(items, LANGUAGES[lang]))
                b = txt(rec.get("job_content"), "")
                if b:
                    with st.expander(T(lang, "db_orig")):
                        st.text(b)

                st.divider()
                if st.session_state.get("t2_wid") != rec["wantedAuthNo"]:
                    st.session_state["t2_wid"] = rec["wantedAuthNo"]
                    st.session_state.pop("t2_hist", None)
                chat_panel(build_chat_context(b, wage_ctx(p, rec), det,
                                              txt(rec.get("근무시간항목"), "")), "t2", lang)

    # ── 탭 3: 성능 ────────────────────────────────────────────
    with t3:
        st.markdown("#### 성공기준")
        m, f1 = reports.get("metrics"), reports.get("f1")
        c = st.columns(3)
        if m is not None and len(m):
            r = m.iloc[0]
            c[0].metric("① 임금 구간 커버리지", f"{r['coverage_pct']}%", "목표 80% — 달성")
            c[0].caption(f"CQR 보정 전 {r['coverage_before_cqr_pct']}%. "
                         f"보정이 성능의 절반을 만듭니다.")
        if f1 is not None and "대표지표포함" in f1.columns:
            core = f1[f1["대표지표포함"] == "Y"]
            v_ = pd.to_numeric(core["F1"], errors="coerce")
            tp, fp, fn = (core[k].sum() for k in ("TP", "FP", "FN"))
            c[1].metric("② 근로조건 탐지 F1", f"{2 * tp / (2 * tp + fp + fn):.3f}",
                        "목표 0.80 — 달성")
            c[1].caption(f"대표 {len(core)}라벨 micro · macro {v_.mean():.3f} · "
                         f"정답지 47건(LLM 2종 교차 + 불일치 판정)")
        bz = reports.get("backtrans_zh")
        if bz is not None and "원문용어수" in bz.columns:
            o = pd.to_numeric(bz["원문용어수"], errors="coerce").sum()
            k = pd.to_numeric(bz["보존용어수"], errors="coerce").sum()
            c[2].metric("③ 용어 보존율", f"{k / o * 100:.1f}%", "목표 90% — 달성")
            c[2].caption(f"중국어 {int(o)}회 표본. 한국어 괄호 병기 규칙의 효과입니다.")

        st.divider()
        cc = st.columns(2)
        rl = reports.get("reliability")
        if rl is not None:
            cc[0].markdown("**신뢰도 등급별 성능** — 노출 정책의 근거")
            cc[0].dataframe(rl, hide_index=True, use_container_width=True)
        if f1 is not None:
            cc[1].markdown("**라벨별 F1**")
            cols = [x for x in ["라벨", "n", "정답양성률", "TP", "FP", "FN",
                                "F1", "대표지표포함"] if x in f1.columns]
            cc[1].dataframe(f1[cols], hide_index=True, use_container_width=True)

        imp = reports.get("importance")
        if imp is not None and len(imp.columns) >= 2:
            st.markdown("**피처 중요도**")
            imp.columns = ["feature", "importance"][:len(imp.columns)]
            st.bar_chart(imp.set_index("feature"), horizontal=True)

        st.divider()
        st.markdown("#### 한계 — 함께 읽어야 하는 것")
        st.markdown(
            "- **정답지가 47건입니다.** 목표 100건의 절반이고, `사람 검수 100건` 이 아니라 "
            "**LLM 2종(GPT-5.4 · Gemini) 교차 라벨 + 불일치 전량 판정**으로 만들었습니다. "
            "셀 329개의 확정 근거는 `reports/llm/adjudication_log.csv` 에 있습니다.\n"
            "- **양성 사례가 적습니다.** 라벨당 TP+FN 이 1~10건입니다. `실근로시간_미기재` 는 "
            "양성 1건으로 F1 1.000 인데, 이는 1건을 맞춘 것입니다.\n"
            "- **`사회보험_미기재` F1 0.987 은 성능이 아닙니다.** 가이드가 \"언급 없음 → 1\" 로 "
            "정한 라벨이라 정답지가 규칙으로 결정되고, 모델도 같은 규칙을 받았습니다.\n"
            "- **LLM 진단 커버리지 상한은 61.4%** 입니다. 공고 본문 보유율이 그만큼입니다.\n"
            "- **q50 R² 는 0.283** 입니다. 점 추정 정확도는 낮으므로 구간으로 제시하고, "
            "신뢰도 '매우낮음' 은 구간을 아예 숨깁니다.\n"
            "- **월 환산은 209시간 기준**입니다. 실제 근무시간이 다르면 금액도 달라집니다.\n"
            "- **대화 답변은 공고 본문을 근거로 합니다.** 공고에 없는 내용은 "
            "'없다'고 답하도록 했지만, 생성 모델이므로 항상 원문을 함께 확인하세요.\n")


def run_live(body: str, lang: str):
    """본문 하나를 그 자리에서 진단한다. OpenAI 호출."""
    import llm_diagnose as L
    from llm_prompts import (CHECKLIST_SYSTEM, DETECT_SYSTEM, LABEL_TERMS,
                             Checklist, Detection, build_checklist_user,
                             build_detect_user)

    cli = L.client()
    got, err = L.parse(cli, L.MODEL_DETECT, L.EFFORT_DETECT, DETECT_SYSTEM,
                       build_detect_user(body, "", len(body), ""),
                       Detection, "bridge4-streamlit-detect")
    if got is None:
        raise RuntimeError(err or "판정 실패")
    dd = got.model_dump()
    det = {"status": dd["status"],
           "labels": {l: dd[l] for l in LABELS},
           "기타": dd["기타_확인필요"]}

    if not any(dd[l]["flag"] == 1 for l in LABELS):
        return det, []

    req = L.required_terms(L.load_glossary())
    want = set(L.find_terms(" ".join([body] + [dd[l]["evidence"] for l in LABELS]), req))
    for l in LABELS:
        if dd[l]["flag"] == 1:
            want |= set(LABEL_TERMS.get(l, ()))
    rows = [dict(r) for _, r in req.iterrows() if r["용어"] in want]

    flat = {l: dd[l] for l in LABELS} | {"기타_확인필요": dd["기타_확인필요"]}
    ck, err = L.parse(cli, L.MODEL_CHECKLIST, L.EFFORT_CHECKLIST, CHECKLIST_SYSTEM,
                      build_checklist_user(flat, lang, rows, body),
                      Checklist, f"bridge4-streamlit-chk-{lang}")
    return det, ([i.model_dump() for i in ck.items] if ck else [])


if __name__ == "__main__":
    main()
