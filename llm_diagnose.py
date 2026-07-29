#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
브릿지포 LLM 파트 실행기 — OpenAI API

프롬프트 문안과 출력 스키마는 llm_prompts.py 에 있다. 이 파일은 호출·집계·평가만 한다.

서브커맨드
  detect      공고 본문 -> 근로조건 7종 판정 (라벨 + 근거인용)
  eval        detect 결과 vs 사람 검수 라벨 -> 라벨별/전체 F1   [성공기준 3]
  checklist   판정 결과 -> 모국어 확인 질문
  backtrans   모국어 질문 -> 한국어 역번역 -> 필수용어 보존율   [성공기준 4]
  pipeline    detect -> checklist -> backtrans 를 한 번에 (데모용)

성공기준
  3) LLM 근로조건 탐지 F1 >= 0.80  (사람 검수 100건 기준)
  4) 역번역 시 근로조건 핵심 용어 보존율 >= 90%

사용 예
  python llm_diagnose.py detect --limit 10
  python llm_diagnose.py detect                      # 검수표본 100건 전량
  python llm_diagnose.py eval
  python llm_diagnose.py checklist --lang en --limit 5
  python llm_diagnose.py backtrans --lang en
  python llm_diagnose.py pipeline --lang vi --limit 3

주의
  - job_content 보유율은 61.4% 다. 본문이 없는 공고는 status='본문없음' 으로 남기고
    라벨을 추측하지 않는다. LLM 진단의 커버리지 상한이 61.4% 라는 뜻이다.
  - .env 의 OPENAI_API_KEY 를 읽는다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from llm_prompts import (
    BACKTRANS_SYSTEM,
    CHECKLIST_SYSTEM,
    DETECT_SYSTEM,
    LABEL_TERMS,
    LABELS,
    LANGUAGES,
    BackTranslation,
    Checklist,
    Detection,
    build_backtrans_user,
    build_checklist_user,
    build_detect_user,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# ─────────────────────────────────────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────────────────────────────────────

DATA = Path("data")
OUT = Path("reports/llm")

SAMPLE = DATA / "llm_validation_sample_100.csv"
GLOSSARY = DATA / "glossary_labor_terms.csv"
TEAM = DATA / "team_merged.csv"

# 기본값은 '싸게 먼저'. 예산이 한정돼 있으므로 mini + 낮은 추론 강도로 시작하고,
# 성공기준(F1 0.80 / 보존율 90%)에 미달할 때만 --model gpt-5.4 --effort high 로 올린다.
#
# 참고: reports/llm/detect_predictions.csv 의 87건 판정은 gpt-5.4 / effort=high 로
# 만든 것이다. 아래 기본값으로 다시 돌리면 결과가 달라질 수 있으므로,
# 출력 CSV 에 model / effort 를 함께 기록해 어느 설정의 결과인지 남긴다.
MODEL_DETECT = "gpt-5.4-mini"
MODEL_CHECKLIST = "gpt-5.4-mini"
MODEL_BACKTRANS = "gpt-5.4-mini"

EFFORT_DETECT = "medium"
EFFORT_CHECKLIST = "low"
EFFORT_BACKTRANS = "low"

# 실제 청구액은 요금표에 따르므로 여기서는 토큰만 집계해 보고한다.
# 대시보드(platform.openai.com/usage)의 단가를 곱해서 쓰면 된다.
USAGE: dict[str, int] = {"입력": 0, "캐시읽힘": 0, "출력": 0, "호출": 0}


def report_usage(tag: str) -> None:
    u = USAGE
    if not u["호출"]:
        return
    fresh = u["입력"] - u["캐시읽힘"]
    print(f"\n[{tag} 사용량] 호출 {u['호출']}회")
    print(f"  입력 {u['입력']:,} 토큰 (캐시로 읽은 것 {u['캐시읽힘']:,} / 새로 과금 {fresh:,})")
    print(f"  출력 {u['출력']:,} 토큰 (추론 토큰 포함)")
    if u["입력"]:
        print(f"  캐시 적중률 {u['캐시읽힘'] / u['입력'] * 100:.0f}%"
              f"  — 낮으면 system 프롬프트가 매 호출 새로 과금됩니다")

WORKERS = 6
MAX_RETRY = 3

# 대표 F1(성공기준 3번)에서 제외할 라벨.
# 사회보험_미기재 는 공고 94.7% 가 미기재라 라벨이 거의 상수다. 전부 1 로 찍어도
# F1 0.97 이 나오므로 성능을 구분하지 못한다. 탐지 기능은 유지하고 별도로 보고한다.
EXCLUDE_FROM_F1 = ("사회보험_미기재",)

# 역번역 실패 사유를 스레드 밖으로 전달하는 용도
BACKTRANS_ERR: dict[str, str] = {}


def client():
    # python-dotenv 는 로컬 개발 편의용 선택 의존성이다.
    # 배포본에는 .env 가 없고 Streamlit Secrets 를 쓰므로 없어도 동작해야 한다.
    # (필수 import 로 두었다가 배포본이 ModuleNotFoundError 로 죽었다)
    if not os.getenv("OPENAI_API_KEY"):
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ModuleNotFoundError:
            pass
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        sys.exit("OPENAI_API_KEY 가 없습니다. .env 에 추가하세요.")
    from openai import OpenAI

    return OpenAI(api_key=key, timeout=180.0, max_retries=2)


def abort_if_all_failed(ok_count: int, total: int, err: str, path: Path) -> None:
    """호출이 전부 실패했으면 기존 결과 파일을 덮어쓰지 않고 멈춘다.

    한도 초과(insufficient_quota)나 키 문제로 전건 실패했을 때, 빈 결과가
    직전에 성공한 결과를 지워버리는 사고를 막는다. 실제로 한 번 겪었다.
    """
    if total and ok_count == 0:
        print(f"\n호출 {total}건이 전부 실패했습니다. {path.name} 을 덮어쓰지 않고 중단합니다.")
        print(f"  사유: {err[:300]}")
        if "insufficient_quota" in err or "exceeded your current quota" in err:
            print("\n  OpenAI 사용 한도를 초과했습니다. 크레딧을 충전한 뒤 다시 실행하세요.")
            print("  https://platform.openai.com/settings/organization/billing")
        sys.exit(1)


def safe_to_csv(df: pd.DataFrame, path: Path) -> None:
    """OneDrive 잠금 대응 — tmp 로 쓰고 교체, 실패 시 재시도."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=False, encoding="utf-8-sig")
    for i in range(4):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if i == 3:
                print(f"  ! {path.name} 잠김 — {tmp.name} 로 남겨둡니다")
                return
            time.sleep(1.5)


def parse(cli, model: str, effort: str, system: str, user: str, schema, cache_key: str):
    """Structured Outputs 로 호출하고 파싱된 객체를 돌려준다."""
    last = None
    for attempt in range(MAX_RETRY):
        try:
            r = cli.chat.completions.parse(
                model=model,
                reasoning_effort=effort,
                # 정적인 system 을 앞에, 공고별 내용을 뒤에 두어 프롬프트 캐시가 붙게 한다
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                response_format=schema,
                max_completion_tokens=8000,
                prompt_cache_key=cache_key,
            )
            if r.usage:                     # 토큰 집계 — 예산 관리에 쓴다
                USAGE["호출"] += 1
                USAGE["입력"] += r.usage.prompt_tokens or 0
                USAGE["출력"] += r.usage.completion_tokens or 0
                det = getattr(r.usage, "prompt_tokens_details", None)
                USAGE["캐시읽힘"] += getattr(det, "cached_tokens", 0) or 0
            msg = r.choices[0].message
            if msg.refusal:
                return None, f"refusal: {msg.refusal}"
            if msg.parsed is None:
                last = f"finish_reason={r.choices[0].finish_reason}"
                continue
            return msg.parsed, None
        except Exception as e:  # 네트워크/파싱 오류만 재시도
            last = f"{type(e).__name__}: {e}"
            time.sleep(2 * (attempt + 1))
    return None, last


# ─────────────────────────────────────────────────────────────────────────────
# prep — 검수표본에 '근무시간항목' 열을 붙인다
# ─────────────────────────────────────────────────────────────────────────────

# 고용주가 채용 사이트에 직접 입력한 근무시간 텍스트만 쓴다.
# weekly_hours / weekly_hours_final / paid_weekly_hours 는 우리 파서의 산출값이라
# '공고에 기재됨' 의 근거가 될 수 없다 (hours_source=벤치마크_직종평균 인 건이 섞여 있다).
RAW_HOURS_COLS = ("work_hours_detail", "work_time", "rest_time")


def build_hours_field(rec: dict) -> str:
    """고용주 입력 근무시간 텍스트를 하나의 블록으로 합친다."""
    parts = []
    for c in RAW_HOURS_COLS:
        v = str(rec.get(c) or "").strip()
        if v and v not in ("nan", "None", "정보없음"):
            label = {"work_time": "근무시각", "rest_time": "휴게시간"}.get(c, "")
            parts.append(f"{label}: {v}" if label else v)
    return "  /  ".join(parts)


def cmd_prep(args) -> None:
    """검수표본에 근무시간항목 열을 채운다. 모델과 사람이 같은 정보를 보게 하는 단계."""
    sample = pd.read_csv(SAMPLE, encoding="utf-8-sig", dtype=str, low_memory=False)
    srcs = [p for p in (DATA / "work24_analysis.csv", TEAM) if p.exists()]
    if not srcs:
        sys.exit("work24_analysis.csv / team_merged.csv 를 찾을 수 없습니다.")

    lookup: dict[str, dict] = {}
    for p in srcs:
        d = pd.read_csv(p, encoding="utf-8-sig", dtype=str, low_memory=False)
        if "wantedAuthNo" not in d.columns:
            continue
        keep = ["wantedAuthNo"] + [c for c in RAW_HOURS_COLS if c in d.columns]
        for rec in d[keep].to_dict("records"):
            k = rec["wantedAuthNo"]
            if k not in lookup:                 # 먼저 읽은 파일(work24)을 우선
                lookup[k] = rec

    sample["근무시간항목"] = [build_hours_field(lookup.get(k, {}))
                          for k in sample["wantedAuthNo"]]

    # 라벨 열 앞에 오도록 순서 조정 — 검수자가 본문 바로 옆에서 보게 한다
    cols = [c for c in sample.columns if c != "근무시간항목"]
    i = cols.index("job_content") + 1 if "job_content" in cols else len(cols)
    sample = sample[cols[:i] + ["근무시간항목"] + cols[i:]]

    safe_to_csv(sample, SAMPLE)
    have = (sample["근무시간항목"].str.strip() != "").sum()
    print(f"prep  {SAMPLE.name} 에 근무시간항목 열 추가")
    print(f"  보유 {have}/{len(sample)}건 / 없음 {len(sample) - have}건")
    print(f"\n예시 2건")
    for v in sample.loc[sample["근무시간항목"].str.strip() != "", "근무시간항목"].head(2):
        print(f"  - {v[:150]}")
    print(f"\n검수자는 job_content 와 근무시간항목을 함께 보고 실근로시간_미기재 를 판정하세요.")


def load_glossary() -> pd.DataFrame:
    g = pd.read_csv(GLOSSARY, encoding="utf-8-sig", dtype=str).fillna("")
    g["필수보존"] = g["필수보존"].str.strip()
    return g


def required_terms(g: pd.DataFrame) -> pd.DataFrame:
    return g[g["필수보존"] == "Y"].reset_index(drop=True)


def find_terms(text: str, terms: pd.DataFrame) -> set[str]:
    """정규식으로 텍스트에 등장한 용어명 집합을 돌려준다."""
    t = text or ""
    hit = set()
    for _, r in terms.iterrows():
        pat = r["정규식"].strip()
        if not pat:
            continue
        try:
            if re.search(pat, t):
                hit.add(r["용어"])
        except re.error:
            if r["용어"] in t:
                hit.add(r["용어"])
    return hit


# ─────────────────────────────────────────────────────────────────────────────
# detect
# ─────────────────────────────────────────────────────────────────────────────

def cmd_detect(args) -> None:
    cli = client()
    model = getattr(args, "model", None) or MODEL_DETECT
    effort = getattr(args, "effort", None) or EFFORT_DETECT
    src = Path(args.src) if args.src else SAMPLE
    d = pd.read_csv(src, encoding="utf-8-sig", dtype=str, low_memory=False)
    if args.limit:
        d = d.head(args.limit)

    key_col = "wantedAuthNo" if "wantedAuthNo" in d.columns else d.columns[0]
    body_col = "job_content"
    if body_col not in d.columns:
        sys.exit(f"{src.name} 에 job_content 컬럼이 없습니다.")

    print(f"detect  {src.name}  {len(d)}건  model={model} effort={effort}")

    rows = d.to_dict("records")

    def work(rec):
        body = str(rec.get(body_col) or "").strip()
        if body in ("", "nan", "정보없음"):
            return {
                "wantedAuthNo": rec.get(key_col),
                "status": "본문없음",
                **{f"pred_{l}": 0 for l in LABELS},
                **{f"ev_{l}": "" for l in LABELS},
                "기타_확인필요": "",
                "error": "",
            }
        n = rec.get("본문길이")
        n = int(float(n)) if str(n).replace(".", "").isdigit() else len(body)
        hours = str(rec.get("근무시간항목") or "").strip()
        if hours in ("nan", "None"):
            hours = ""
        if not hours:                       # prep 을 안 돌린 입력이면 원천에서 직접 조립
            hours = build_hours_field(rec)
        got, err = parse(
            cli,
            model,
            effort,
            DETECT_SYSTEM,
            build_detect_user(body, str(rec.get("직종") or ""), n, hours),
            Detection,
            f"bridge4-detect-{model}-{effort}",
        )
        if got is None:
            return {
                "wantedAuthNo": rec.get(key_col),
                "status": "실패",
                **{f"pred_{l}": "" for l in LABELS},
                **{f"ev_{l}": "" for l in LABELS},
                "기타_확인필요": "",
                "error": err or "unknown",
            }
        dd = got.model_dump()
        out = {"wantedAuthNo": rec.get(key_col), "status": dd["status"], "error": ""}
        for l in LABELS:
            out[f"pred_{l}"] = dd[l]["flag"]
            out[f"ev_{l}"] = dd[l]["evidence"]
        out["기타_확인필요"] = " | ".join(dd["기타_확인필요"])
        out["model"] = model
        out["effort"] = effort
        return out

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        res = list(ex.map(work, rows))
    r = pd.DataFrame(res)

    dst = OUT / "detect_predictions.csv"
    need = r["status"] != "본문없음"          # 본문없음은 호출 자체를 안 한다
    abort_if_all_failed(int((r["status"] == "진단완료").sum()), int(need.sum()),
                        next((e for e in r["error"] if e), ""), dst)
    safe_to_csv(r, dst)

    ok = (r["status"] == "진단완료").sum()
    print(f"\n완료 {ok}건 / 본문없음 {(r['status'] == '본문없음').sum()}건 "
          f"/ 실패 {(r['status'] == '실패').sum()}건  ({time.time() - t0:.0f}초)")
    if (r["status"] == "실패").any():
        print("  실패 사유 예:", r.loc[r["status"] == "실패", "error"].iloc[0][:160])

    print("\n라벨별 1 판정 비율 (진단완료 기준)")
    m = r["status"] == "진단완료"
    for l in LABELS:
        s = pd.to_numeric(r.loc[m, f"pred_{l}"], errors="coerce")
        ev = (r.loc[m, f"ev_{l}"].fillna("").str.strip() != "").sum()
        print(f"  {l:<22} 1판정 {int(s.sum()):>3}/{int(m.sum())} ({s.mean() * 100:>5.1f}%)"
              f"  근거인용 {ev}건")
    print(f"\n저장: {dst}")
    report_usage("detect")


# ─────────────────────────────────────────────────────────────────────────────
# eval  [성공기준 3]
# ─────────────────────────────────────────────────────────────────────────────

def cmd_eval(args) -> None:
    pred = pd.read_csv(OUT / "detect_predictions.csv", encoding="utf-8-sig", dtype=str)
    gold = pd.read_csv(Path(args.gold) if args.gold else SAMPLE,
                       encoding="utf-8-sig", dtype=str)

    m = gold.merge(pred, on="wantedAuthNo", how="inner", suffixes=("", "_p"))
    print(f"eval  대조 가능 {len(m)}건")

    filled = sum(m[l].notna().sum() for l in LABELS if l in m.columns)
    if filled == 0:
        print("\n사람 검수 라벨이 아직 비어 있습니다.")
        print("  data/llm_validation_sample_100.csv 의 7개 라벨 열을 채운 뒤 다시 실행하세요.")
        print("  라벨 기준: data/LABELING_GUIDE.md")
        print("\n지금 확인할 수 있는 것 — 모델 판정 분포만:")
        for l in LABELS:
            s = pd.to_numeric(m.get(f"pred_{l}"), errors="coerce")
            if s is not None and s.notna().any():
                print(f"  {l:<22} 1판정 {int(s.sum()):>3}건")
        return

    def prf(y, p):
        tp = int(((y == 1) & (p == 1)).sum())
        fp = int(((y == 0) & (p == 1)).sum())
        fn = int(((y == 1) & (p == 0)).sum())
        tn = int(((y == 0) & (p == 0)).sum())
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * pr * rc / (pr + rc) if pr + rc else 0.0
        return tp, fp, fn, tn, pr, rc, f1

    print(f"\n{'라벨':<22} {'n':>4} {'양성률':>7} {'TP':>4} {'FP':>4} {'FN':>4} "
          f"{'정밀도':>7} {'재현율':>7} {'F1':>7}")
    print("-" * 84)

    rows = []
    for l in LABELS:
        if l not in m.columns:
            continue
        y = pd.to_numeric(m[l], errors="coerce")
        p = pd.to_numeric(m[f"pred_{l}"], errors="coerce")
        ok = y.notna() & p.notna()          # 사람이 '?' 로 남긴 칸은 제외
        y, p = y[ok].astype(int), p[ok].astype(int)
        if not len(y):
            continue
        tp, fp, fn, tn, pr, rc, f1 = prf(y, p)
        base = y.mean()                     # 정답의 양성률 — 다수결 기준선

        # 정답에 양성이 하나도 없고 예측도 양성이 없으면 F1 이 정의되지 않는다(0/0).
        # 이걸 0.000 으로 세면 macro 평균이 부당하게 내려간다. 완전 일치인데도
        # '성능 0' 으로 보이기 때문이다. 별도로 빼서 보고한다.
        undefined = (tp + fp + fn) == 0
        포함 = "N" if (l in EXCLUDE_FROM_F1 or undefined) else "Y"
        rows.append({"라벨": l, "n": len(y), "정답양성률": round(base, 4),
                     "TP": tp, "FP": fp, "FN": fn, "TN": tn,
                     "정밀도": round(pr, 4), "재현율": round(rc, 4),
                     "F1": "" if undefined else round(f1, 4),
                     "대표지표포함": 포함,
                     "제외사유": ("라벨 편향" if l in EXCLUDE_FROM_F1 else
                              "정답에 양성 없음 — F1 정의 불가" if undefined else "")})
        tag = ("  <- 대표지표 제외(편향)" if l in EXCLUDE_FROM_F1 else
               "  <- 정답 양성 0건, F1 정의 불가" if undefined else "")
        f1s = "     —" if undefined else f"{f1:>7.3f}"
        print(f"{l:<22} {len(y):>4} {base * 100:>6.1f}% {tp:>4} {fp:>4} {fn:>4} "
              f"{pr:>7.3f} {rc:>7.3f} {f1s}{tag}")

    if not rows:
        print("대조할 라벨이 없습니다.")
        return

    def agg(sel: list[dict]) -> tuple[float, float, float, float]:
        tp = sum(r["TP"] for r in sel); fp = sum(r["FP"] for r in sel)
        fn = sum(r["FN"] for r in sel)
        p_ = tp / (tp + fp) if tp + fp else 0.0
        r_ = tp / (tp + fn) if tp + fn else 0.0
        mi = 2 * p_ * r_ / (p_ + r_) if p_ + r_ else 0.0
        f1s = [r["F1"] for r in sel if r["F1"] != ""]
        ma = sum(f1s) / len(f1s) if f1s else 0.0
        return p_, r_, mi, ma

    core = [r for r in rows if r["대표지표포함"] == "Y"]
    excl = [r for r in rows if r["대표지표포함"] == "N"]
    if not core:
        print("\n대표지표에 남은 라벨이 없습니다.")
        return

    cp, cr, cmi, cma = agg(core)
    print("-" * 84)
    print(f"{'micro (대표 %d라벨)' % len(core):<22} {'':>12} "
          f"{sum(r['TP'] for r in core):>4} {sum(r['FP'] for r in core):>4} "
          f"{sum(r['FN'] for r in core):>4} {cp:>7.3f} {cr:>7.3f} {cmi:>7.3f}")
    print(f"{'macro (대표 %d라벨)' % len(core):<22} {'':>44} {cma:>7.3f}")

    tgt = 0.80
    print(f"\n성공기준 3)  F1 >= {tgt}   — 대표지표는 {len(core)}개 라벨 기준")
    print(f"  micro F1 {cmi:.3f}  {'달성' if cmi >= tgt else '미달'}")
    print(f"  macro F1 {cma:.3f}  {'달성' if cma >= tgt else '미달'}")

    if excl:
        _, _, emi, _ = agg(excl)
        print(f"\n[참고 — 대표지표 제외 라벨] 별도 보고")
        for r in excl:
            if r["F1"] == "":
                print(f"  {r['라벨']:<22} F1 정의 불가 — 정답 양성 0건, "
                      f"오탐 {r['FP']}건 (완전 일치)")
            else:
                naive = 2 * r["정답양성률"] / (1 + r["정답양성률"]) if r["정답양성률"] else 0.0
                print(f"  {r['라벨']:<22} F1 {r['F1']:.3f}  "
                      f"(정답 양성률 {r['정답양성률'] * 100:.1f}% — "
                      f"전부 1로 찍어도 F1 {naive:.3f})")
        print("  위 라벨들은 성능을 구분하지 못해 대표지표에서 뺐습니다.")
        print("  탐지 기능 자체는 유지하며, 체크리스트 생성에는 그대로 쓰입니다.")

    if cmi < tgt:
        worst = min([r for r in core if r["F1"] != ""], key=lambda r: r["F1"])
        bias = "허위양성(FP)" if worst["FP"] > worst["FN"] else "누락(FN)"
        print(f"\n  가장 낮은 라벨: {worst['라벨']} F1={worst['F1']:.3f} — 주 오류는 {bias}")
        print("  -> llm_prompts.py 의 해당 라벨 대조 사례에 그 오류 유형을 추가하세요.")

    safe_to_csv(pd.DataFrame(rows), OUT / "eval_f1.csv")
    print(f"\n저장: {OUT / 'eval_f1.csv'}")


# ─────────────────────────────────────────────────────────────────────────────
# checklist
# ─────────────────────────────────────────────────────────────────────────────

def cmd_checklist(args) -> None:
    cli = client()
    pred = pd.read_csv(OUT / "detect_predictions.csv", encoding="utf-8-sig", dtype=str)
    src = pd.read_csv(SAMPLE, encoding="utf-8-sig", dtype=str)
    g = load_glossary()
    req = required_terms(g)
    lang = args.lang
    model = getattr(args, "model", None) or MODEL_CHECKLIST
    effort = getattr(args, "effort", None) or EFFORT_CHECKLIST

    done = pred[pred["status"] == "진단완료"].copy()
    for l in LABELS:
        done[f"pred_{l}"] = pd.to_numeric(done[f"pred_{l}"], errors="coerce").fillna(0)
    flagged = done[done[[f"pred_{l}" for l in LABELS]].sum(axis=1) > 0]
    if args.limit:
        flagged = flagged.head(args.limit)

    print(f"checklist  {len(flagged)}건  lang={lang} ({LANGUAGES.get(lang, lang)})  "
          f"model={model} effort={effort}")

    body = src.set_index("wantedAuthNo")["job_content"].to_dict()

    def txt_of(v) -> str:
        """빈 칸은 NaN(float) 으로 읽히므로 문자열로 정규화한다."""
        s = "" if v is None else str(v)
        return "" if s in ("nan", "None") else s.strip()

    def work(rec):
        det = {l: {"flag": int(rec[f"pred_{l}"]), "evidence": txt_of(rec.get(f"ev_{l}"))}
               for l in LABELS}
        det["기타_확인필요"] = [x for x in txt_of(rec.get("기타_확인필요")).split(" | ") if x]

        # 주입할 용어 = (공고 본문·근거에서 정규식에 걸린 것)
        #             U (판정된 라벨에 딸린 용어)
        #
        # 뒤쪽 합집합이 없으면, 모델이 본문에 없던 용어를 질문에 써놓고 병기 지시를
        # 못 받는다. 100건 실행에서 용어 유실 6건 중 5건이 그 경우였다.
        txt = " ".join([str(body.get(rec["wantedAuthNo"]) or "")]
                       + [det[l]["evidence"] for l in LABELS])
        want = set(find_terms(txt, req))
        for l in LABELS:
            if det[l]["flag"] == 1:
                want |= set(LABEL_TERMS.get(l, ()))
        rows_g = [r for _, r in req.iterrows() if r["용어"] in want]
        if not rows_g:                       # 최소한 임금·시간 핵심 용어는 넣어준다
            rows_g = [r for _, r in req.iterrows()
                      if r["용어"] in ("기본급", "소정근로시간", "4대보험")]

        got, err = parse(
            cli, model, effort, CHECKLIST_SYSTEM,
            build_checklist_user(det, lang, [dict(r) for r in rows_g],
                                 str(body.get(rec["wantedAuthNo"]) or "")),
            Checklist, f"bridge4-checklist-{lang}-{model}",
        )
        if got is None:
            return [{"wantedAuthNo": rec["wantedAuthNo"], "lang": lang, "항목": "",
                     "한국어질문": "", "모국어질문": "", "확인이유": "", "위험도": "",
                     "error": err}]
        return [{"wantedAuthNo": rec["wantedAuthNo"], "lang": lang, **i.model_dump(),
                 "error": ""} for i in got.items]

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        res = list(ex.map(work, flagged.to_dict("records")))
    q = pd.DataFrame([x for sub in res for x in sub])

    dst = OUT / f"checklist_{lang}.csv"
    good = q[q["한국어질문"].fillna("") != ""]
    abort_if_all_failed(len(good), len(flagged),
                        next((e for e in q["error"].fillna("") if e), ""), dst)
    safe_to_csv(q, dst)
    print(f"\n질문 {len(good)}개 생성 (공고 {good['wantedAuthNo'].nunique()}건)")
    if len(good):
        print("\n항목별 분포")
        for k, v in good["항목"].value_counts().items():
            print(f"  {k:<22} {v}개")
        print("\n예시 3개")
        for _, r in good.head(3).iterrows():
            print(f"  [{r['항목']} / 위험도 {r['위험도']}]")
            print(f"    KO : {r['한국어질문']}")
            print(f"    {lang.upper():<3}: {r['모국어질문']}")
    print(f"\n저장: {dst}")
    report_usage("checklist")


# ─────────────────────────────────────────────────────────────────────────────
# backtrans  [성공기준 4]
# ─────────────────────────────────────────────────────────────────────────────

def cmd_backtrans(args) -> None:
    cli = client()
    lang = args.lang
    src = OUT / f"checklist_{lang}.csv"
    if not src.exists():
        sys.exit(f"{src} 가 없습니다. 먼저 checklist --lang {lang} 를 실행하세요.")

    q = pd.read_csv(src, encoding="utf-8-sig", dtype=str).fillna("")
    q = q[(q["한국어질문"] != "") & (q["모국어질문"] != "")].reset_index(drop=True)
    if args.limit:
        q = q.head(args.limit)
    if q.empty:
        sys.exit(f"{src.name} 에 유효한 질문이 없습니다. checklist --lang {lang} 를 먼저 성공시키세요.")
    req = required_terms(load_glossary())
    model = getattr(args, "model", None) or MODEL_BACKTRANS
    effort = getattr(args, "effort", None) or EFFORT_BACKTRANS

    print(f"backtrans  {len(q)}문장  lang={lang}  model={model} effort={effort}")

    # 20문장씩 묶어 호출 — 문장 단위 호출보다 저렴하고, 순서 검증도 가능하다
    CH = 20
    chunks = [q.iloc[i:i + CH] for i in range(0, len(q), CH)]

    def work(ch):
        got, err = parse(
            cli, model, effort, BACKTRANS_SYSTEM,
            build_backtrans_user(ch["모국어질문"].tolist(), lang),
            BackTranslation, f"bridge4-backtrans-{lang}-v1",
        )
        if got is None:
            BACKTRANS_ERR["last"] = err or "unknown"
            return [""] * len(ch)
        out = got.한국어역번역
        if len(out) != len(ch):              # 개수가 어긋나면 그 묶음은 버린다
            print(f"  ! 문장 개수 불일치 {len(out)} != {len(ch)} — 해당 묶음 제외")
            return [""] * len(ch)
        return out

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        res = list(ex.map(work, chunks))
    q["역번역"] = [x for sub in res for x in sub]

    got = int((q["역번역"].str.strip() != "").sum())
    abort_if_all_failed(got, len(q), BACKTRANS_ERR.get("last", ""),
                        OUT / f"backtrans_{lang}.csv")

    # ── 보존율: 원문 한국어질문에 있던 필수용어가 역번역문에도 있는가
    tot_orig = tot_keep = 0
    per_term: dict[str, list[int]] = {}
    rows = []
    for _, r in q.iterrows():
        o = find_terms(r["한국어질문"], req)
        b = find_terms(r["역번역"], req)
        keep = o & b
        lost = o - b
        tot_orig += len(o)
        tot_keep += len(keep)
        for t in o:
            per_term.setdefault(t, [0, 0])
            per_term[t][0] += 1
            per_term[t][1] += 1 if t in b else 0
        rows.append({**r.to_dict(),
                     "원문용어수": len(o), "보존용어수": len(keep),
                     "유실용어": "|".join(sorted(lost)),
                     "보존율": round(len(keep) / len(o), 3) if o else ""})

    out = pd.DataFrame(rows)
    safe_to_csv(out, OUT / f"backtrans_{lang}.csv")

    rate = tot_keep / tot_orig if tot_orig else 0.0
    print(f"\n필수용어 등장 {tot_orig}회 중 보존 {tot_keep}회")
    print(f"보존율 {rate * 100:.1f}%")
    print(f"\n성공기준 4)  보존율 >= 90%   ->  {'달성' if rate >= 0.90 else '미달'}")

    if per_term:
        print("\n용어별")
        for t, (n, k) in sorted(per_term.items(), key=lambda x: (x[1][1] / x[1][0], -x[1][0])):
            mark = "" if k == n else "   <- 유실"
            print(f"  {t:<14} {k:>3}/{n:<3} {k / n * 100:>5.1f}%{mark}")

    bad = out[(out["유실용어"] != "") & (out["역번역"] != "")]
    if len(bad):
        print(f"\n유실 사례 (상위 3건)")
        for _, r in bad.head(3).iterrows():
            print(f"  유실: {r['유실용어']}")
            print(f"    원문   : {r['한국어질문']}")
            print(f"    {lang.upper():<3}   : {r['모국어질문']}")
            print(f"    역번역 : {r['역번역']}")
        print("\n  -> 병기 규칙이 지켜지지 않은 경우가 대부분입니다.")
        print("     llm_prompts.py CHECKLIST_SYSTEM '번역 규칙' 의 병기 예시에 해당 용어를 추가하세요.")
    print(f"\n저장: {OUT / f'backtrans_{lang}.csv'}")
    report_usage("backtrans")


# ─────────────────────────────────────────────────────────────────────────────
# pipeline (데모)
# ─────────────────────────────────────────────────────────────────────────────

def cmd_pipeline(args) -> None:
    print("=" * 78)
    cmd_detect(args)
    print("\n" + "=" * 78)
    cmd_checklist(args)
    print("\n" + "=" * 78)
    cmd_backtrans(argparse.Namespace(lang=args.lang, limit=None))


def main() -> None:
    ap = argparse.ArgumentParser(description="브릿지포 LLM 진단 (OpenAI)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prep", help="검수표본에 근무시간항목 열 추가 (detect 전에 1회)")
    p.set_defaults(fn=cmd_prep)

    p = sub.add_parser("detect", help="근로조건 7종 판정")
    p.add_argument("--src", help="입력 CSV (기본: data/llm_validation_sample_100.csv)")
    p.add_argument("--limit", type=int)
    p.add_argument("--model", help="모델 override (예: gpt-5.4, gpt-5.4-mini)")
    p.add_argument("--effort", choices=['minimal','low','medium','high','xhigh'],
                   help="추론 강도 override. 낮추면 저렴해집니다")
    p.set_defaults(fn=cmd_detect)

    p = sub.add_parser("eval", help="사람 검수 라벨과 대조해 F1 산출")
    p.add_argument("--gold", help="정답 CSV (기본: 검수표본)")
    p.set_defaults(fn=cmd_eval)

    p = sub.add_parser("checklist", help="모국어 확인 질문 생성")
    p.add_argument("--lang", default="en", choices=list(LANGUAGES))
    p.add_argument("--limit", type=int)
    p.add_argument("--model", help="모델 override (예: gpt-5.4, gpt-5.4-mini)")
    p.add_argument("--effort", choices=['minimal','low','medium','high','xhigh'],
                   help="추론 강도 override. 낮추면 저렴해집니다")
    p.set_defaults(fn=cmd_checklist)

    p = sub.add_parser("backtrans", help="역번역 후 용어 보존율 측정")
    p.add_argument("--lang", default="en", choices=list(LANGUAGES))
    p.add_argument("--limit", type=int)
    p.add_argument("--model", help="모델 override (예: gpt-5.4, gpt-5.4-mini)")
    p.add_argument("--effort", choices=['minimal','low','medium','high','xhigh'],
                   help="추론 강도 override. 낮추면 저렴해집니다")
    p.set_defaults(fn=cmd_backtrans)

    p = sub.add_parser("pipeline", help="detect -> checklist -> backtrans")
    p.add_argument("--lang", default="en", choices=list(LANGUAGES))
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--src", default=None)
    p.set_defaults(fn=cmd_pipeline)

    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    args.fn(args)


if __name__ == "__main__":
    main()
