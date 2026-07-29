#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
브릿지포 진단 리포트 생성기

공고 1건 + ML 임금 예측 + LLM 근로조건 판정을 받아, 구직자가 읽는 3단 리포트를 만든다.

    1. [ML 기반]  적정 임금 진단      — 예측 범위 · 제시 임금 평가
    2. [LLM 기반] 근로조건 주의 항목   — 항목별 모국어 설명 + 사장님께 물어볼 질문
    3. 한눈에 보는 요약

이 모듈은 API 를 호출하지 않는다. 문자열(마크다운)만 만든다.
CLI(bridge4_service.py)와 웹앱(streamlit_app.py)이 같은 함수를 쓴다.

톤 원칙
  - 구직자를 보호하는 근로 가이드. 겁주지 않고, 확인할 것을 알려준다.
  - 한국어 질문은 사장님이 읽어도 무례하지 않은 정중한 존댓말.
  - 공고에 명확히 적힌 것은 트집 잡지 않는다. 누락·모호한 것만 다룬다.
"""

from __future__ import annotations

import pandas as pd

LABELS = (
    "임금구성_불명확", "실근로시간_미기재", "수습조건_미기재", "숙식공제_불명확",
    "연장야간_조건미기재", "사회보험_미기재", "임금_미확정",
)

# 항목별 한국어 설명. 모국어 설명은 체크리스트의 '확인이유' 를 쓴다.
WHY = {
    "임금구성_불명확": "표시된 임금에 어떤 수당이 얼마씩 들어 있는지 몰라 기본급을 알 수 없습니다. "
                  "기본급은 퇴직금·상여 산정의 기준이라 실수령액에 직접 영향을 줍니다.",
    "실근로시간_미기재": "주당 근로시간이나 근무시각이 공고에 없습니다. "
                   "시급제라면 근로시간을 모르면 한 달에 얼마를 받는지 계산할 수 없습니다.",
    "수습조건_미기재": "수습을 언급했지만 기간이나 감액 비율이 없습니다. "
                  "수습 중에는 최저임금의 90%까지 감액이 가능하므로 확인이 필요합니다.",
    "숙식공제_불명확": "기숙사·식사를 제공한다고만 적혀 있고, 임금에서 공제하는지가 없습니다. "
                  "공제라면 실제 받는 돈이 줄어듭니다.",
    "연장야간_조건미기재": "연장·야간·휴일 근로를 언급했지만 가산수당 지급 기준이 없습니다. "
                    "법정 가산율(연장·야간 1.5배)이 적용되는지 확인해야 합니다.",
    "사회보험_미기재": "4대보험 가입 여부가 없습니다. "
                  "가입해야 산재 처리와 실업급여를 받을 수 있습니다.",
    "임금_미확정": "임금이 숫자로 정해지지 않았습니다. "
               "'면접 후 결정'이나 '내규에 따름'은 지원 전에 금액을 알 수 없다는 뜻입니다.",
}

# 월 소정근로시간. 주 40시간 × 4.345주 × 1.2(주휴) = 208.6h -> 관행상 209h
MONTHLY_HOURS = 209

# 구직자는 월급으로 생각한다("220만원이면 괜찮은가?"). 그래서 월급을 앞세우고
# 시급은 괄호로 보조 표기한다.
VERDICT_TEXT = {
    "위법소지": ("🔴 최저임금 미달 가능",
              "공고 임금을 시급으로 환산하면 **{real:,}원** 으로, "
              "2026년 최저임금 **{mw:,}원** 에 못 미칩니다. "
              "최저임금 미달은 위법입니다. 반드시 확인하세요."),
    "낮음": ("🟡 적정 범위보다 낮음",
           "공고 임금(월 약 {real_m}만원 · 시급 {real:,}원)이 비슷한 조건의 적정 범위 "
           "**월 {lo_m}만 ~ {hi_m}만원** 보다 낮습니다. "
           "같은 조건의 다른 공고를 함께 비교해 보세요."),
    "적정": ("🟢 적정 수준",
           "제시된 월 약 {real_m}만원(시급 {real:,}원)은 부산 지역 동종 조건의 "
           "적정 범위 **월 {lo_m}만 ~ {hi_m}만원** 에 부합합니다."),
    "높음": ("🔵 적정 범위보다 높음",
           "공고 임금(월 약 {real_m}만원 · 시급 {real:,}원)이 적정 범위 "
           "**월 {lo_m}만 ~ {hi_m}만원** 보다 높습니다. "
           "임금이 높은 공고는 근무 강도나 교대 조건이 함께 붙는 경우가 많으니, "
           "아래 근로조건을 특히 꼼꼼히 확인하세요."),
    "미확정": ("⚪ 임금 미확정",
            "공고에 임금 금액이 정해져 있지 않습니다. "
            "비슷한 조건이라면 **월 {lo_m}만 ~ {hi_m}만원** (시급 {lo:,}~{hi:,}원) "
            "수준이니, 이 범위를 기준으로 면접에서 확인하세요."),
}


def to_man(hourly: float | int) -> int:
    """시급 -> 월 환산 만원 단위. 월 소정근로시간 209h 기준."""
    return round(hourly * MONTHLY_HOURS / 10000)


def _num(v) -> float | None:
    x = pd.to_numeric(pd.Series([v]), errors="coerce").iloc[0]
    return None if pd.isna(x) else float(x)


def _txt(v, default: str = "") -> str:
    s = "" if v is None else str(v).strip()
    return default if s in ("", "nan", "None") else s


def wage_verdict(real_hourly: float | None, lo: int, hi: int, mw26: int,
                 undecided: bool) -> str:
    """제시 임금 평가. 표기 임금이 없거나 미확정이면 '미확정'."""
    if undecided or real_hourly is None:
        return "미확정"
    if real_hourly < mw26:
        return "위법소지"
    if real_hourly < lo:
        return "낮음"
    if real_hourly > hi:
        return "높음"
    return "적정"


def build_report(rec: pd.Series, pred: pd.Series, detection: dict | None,
                 checklist: list[dict], lang_name: str, meta: dict,
                 show_monthly: bool = True) -> str:
    """진단 리포트(마크다운)를 만든다.

    rec        공고 1행 (company/title/sigungu/sal_type/sal_min_won/hourly_wage 등)
    pred       예측 1행 (lo/mid/hi/width/rel)
    detection  {'status','labels':{라벨:{'flag','evidence'}},'기타':[...]}  없으면 None
    checklist  [{'항목','한국어질문','모국어질문','확인이유','위험도'}, ...]
    lang_name  모국어 표기 (예: '简体中文')
    """
    lo, mid, hi = int(pred["lo"]), int(pred["mid"]), int(pred["hi"])
    rel = str(pred["rel"])
    mw26 = int(meta["minimum_wage_2026"])
    mw27 = int(meta["minimum_wage_2027"])

    real = _num(rec.get("hourly_wage"))
    amt = _num(rec.get("sal_min_won"))
    kind = _txt(rec.get("sal_type"))

    flags = []
    if detection and detection.get("status") != "본문없음":
        flags = [l for l in LABELS
                 if (detection.get("labels", {}).get(l) or {}).get("flag") == 1]
    undecided = ("임금_미확정" in flags) or amt is None
    v = wage_verdict(real, lo, hi, mw26, undecided)

    L: list[str] = []

    # ── 헤더 ─────────────────────────────────────────────────────────
    L.append(f"## {_txt(rec.get('company'), '(기업명 미상)')}")
    sub = " · ".join(x for x in [_txt(rec.get("title")), _txt(rec.get("sigungu")),
                                 _txt(rec.get("ksco_name"))] if x)
    if sub:
        L.append(f"*{sub}*")
    L.append("")
    L.append("---")

    # ── 1. ML ────────────────────────────────────────────────────────
    L.append("### 📊 1. [ML 기반] 적정 임금 진단")
    L.append("")
    if rel == "매우낮음":
        L.append("- **ML 예측 적정 범위**: 제시 보류 — 비슷한 조건의 공고가 부족해 "
                 "신뢰할 만한 범위를 내기 어렵습니다.")
        L.append(f"- **참고 중앙 추정**: 월 약 {to_man(mid)}만원 (시급 {mid:,}원) "
                 f"*(신뢰도 매우낮음)*")
    elif rel == "낮음":
        L.append(f"- **ML 예측 적정 범위**: 월 약 **{to_man(mid)}만원** (시급 {mid:,}원) "
                 f"*(비슷한 조건이 적어 구간 대신 중앙값만 제시)*")
    else:
        L.append(f"- **ML 예측 적정 범위**: "
                 f"**월 {to_man(lo)}만원 ~ {to_man(hi)}만원** (80% 신뢰구간)")
        L.append(f"  · 시급 환산 {lo:,} ~ {hi:,}원 · 신뢰도 **{rel}**")

    if amt is not None:
        s = f"- **공고 제시 임금**: {kind} {amt:,.0f}원"
        if real is not None:
            s += (f" → 주휴 포함 환산 **월 약 {to_man(real)}만원** "
                  f"(시급 {real:,.0f}원)")
        L.append(s)
    else:
        L.append("- **공고 제시 임금**: 미표기")

    title, body = VERDICT_TEXT[v]
    L.append("")
    L.append(f"- **제시 임금 평가**: **{title}**")
    L.append("  " + body.format(
        real=int(real) if real else 0,
        real_m=to_man(real) if real else 0,
        lo=lo, hi=hi, lo_m=to_man(lo), hi_m=to_man(hi), mw=mw26))
    if v not in ("위법소지", "미확정") and real is not None and real < mw27:
        L.append(f"  > 참고: 2027년 최저임금은 시급 **{mw27:,}원** 입니다. "
                 f"내년에는 인상되어야 하는 수준입니다.")
    L.append("")
    L.append("  <sub>월 환산은 주휴 포함 월 소정근로시간 209시간 기준입니다. "
             "실제 근무시간이 다르면 금액도 달라집니다.</sub>")
    L.append("")
    L.append("---")

    # ── 2. LLM ───────────────────────────────────────────────────────
    L.append("### 🔍 2. [LLM 기반] 근로조건 주의 항목 진단")
    L.append("")

    if detection is None:
        L.append("아직 이 공고의 근로조건 진단 결과가 없습니다.")
    elif detection.get("status") == "본문없음":
        L.append("이 공고는 본문이 제공되지 않아 근로조건을 진단할 수 없습니다. "
                 "수집한 공고의 약 39%가 본문을 제공하지 않습니다. "
                 "**공고 원문을 직접 확인하고, 아래 임금 범위를 기준으로 면접에서 물어보세요.**")
    elif not flags:
        L.append("✅ 7가지 항목에서 **주의할 점이 발견되지 않았습니다.** "
                 "근로조건이 비교적 명확하게 적혀 있는 공고입니다.")
    else:
        by = {c.get("항목"): c for c in checklist}
        L.append(f"7가지 항목 중 **{len(flags)}개**에서 확인이 필요합니다.")
        L.append("")
        for i, l in enumerate(flags, 1):
            ev = _txt((detection["labels"].get(l) or {}).get("evidence"))
            c = by.get(l)
            L.append(f"#### 💡 주의 항목 {i}: {l}")
            L.append("")
            if ev:
                L.append(f"> 공고 원문: 「{ev}」")
            else:
                L.append("> 공고에 이 항목에 대한 언급이 아예 없습니다.")
            L.append("")
            L.append(f"- **왜 확인해야 하나요**: {WHY[l]}")
            if c and _txt(c.get("확인이유")):
                L.append(f"- **AI의 설명 ({lang_name})**: {c['확인이유']}")
            L.append("- **사장님께 물어볼 질문**:")
            if c and _txt(c.get("한국어질문")):
                L.append(f"  - 🇰🇷 **한국어**: \"{c['한국어질문']}\"")
                if _txt(c.get("모국어질문")):
                    L.append(f"  - 🌐 **{lang_name}**: \"{c['모국어질문']}\"")
            else:
                L.append(f"  - *({lang_name} 질문이 아직 생성되지 않았습니다. "
                         f"사이드바에서 다른 언어를 선택해 보세요.)*")
            if c and _txt(c.get("위험도")):
                L.append(f"  - 중요도: **{c['위험도']}**")
            L.append("")

    etc = (detection or {}).get("기타") or []
    if etc:
        L.append("#### 📎 그 밖에 확인할 점")
        for e in etc:
            L.append(f"- {e}")
        L.append("")

    L.append("---")

    # ── 3. 요약 ──────────────────────────────────────────────────────
    L.append("### 🎯 3. 한눈에 보는 요약")
    L.append("")
    one = {
        "위법소지": f"환산 시급 {int(real or 0):,}원으로 **최저임금 미달 가능** — 반드시 확인",
        "낮음": f"적정 범위(월 {to_man(lo)}~{to_man(hi)}만원)보다 **낮은 편**",
        "적정": f"부산 동종 조건 평균(월 {to_man(lo)}~{to_man(hi)}만원) **수준에 부합**",
        "높음": f"적정 범위(월 {to_man(lo)}~{to_man(hi)}만원)보다 **높음** — 근무 조건을 함께 확인",
        "미확정": f"임금이 **정해지지 않음** — 월 {to_man(lo)}~{to_man(hi)}만원을 기준으로 면접에서 확인",
    }[v]
    L.append(f"- **임금 적정성**: {one}")

    if flags:
        risky = [c.get("항목") for c in checklist if c.get("위험도") == "높음"]
        top = [l for l in flags if l in risky] or flags
        L.append(f"- **핵심 주의점**: {' · '.join(top[:2])}"
                 + (f" (그 외 {len(flags) - len(top[:2])}건)" if len(flags) > 2 else ""))
    elif detection and detection.get("status") == "본문없음":
        L.append("- **핵심 주의점**: 본문이 없어 진단 불가 — 공고 원문을 직접 확인")
    else:
        L.append("- **핵심 주의점**: 없음")

    n_q = len([c for c in checklist if _txt(c.get("한국어질문"))])
    if n_q:
        L.append(f"- **다음 할 일**: 위 한국어 질문 **{n_q}개**를 지원 전에 채용 담당자에게 확인하세요. "
                 f"괄호 안 한국어 단어를 손으로 가리키며 물어보면 됩니다.")
    return "\n".join(L)


def build_questions_only(checklist: list[dict], lang_name: str) -> str:
    """면접장에서 그대로 보여줄 질문 목록만."""
    if not checklist:
        return ""
    L = [f"### 📋 채용 담당자에게 보여줄 질문 ({lang_name})", ""]
    for i, c in enumerate([c for c in checklist if _txt(c.get("한국어질문"))], 1):
        L.append(f"**{i}. {c['한국어질문']}**")
        if _txt(c.get("모국어질문")):
            L.append(f"　　{c['모국어질문']}")
        L.append("")
    return "\n".join(L)
