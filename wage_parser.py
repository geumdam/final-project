#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
공고 본문에서 임금 읽어내기

왜 필요한가
  붙여넣은 공고에 `월급 2,326,840원` 이 분명히 적혀 있는데도 화면에 '未写明(미표기)'
  이라고 나왔다. 사용자가 임금 형태·금액 폼을 따로 채워야만 인식했기 때문이다.
  본문에 있으면 읽어야 한다. 폼은 보정 수단으로만 남긴다.

주의해서 걸러야 하는 것
  - `2026년 최저시급 10,320원` — 최저임금 안내는 이 공고의 임금이 아니다
  - `인센티브 매월 최대 20만원` — 수당·상여는 기본 임금이 아니다
  - `기본급 233~272만원` — 범위면 하한을 쓴다(sal_min_won 정의와 같게)
  - `월급 2,326,840원` 과 `기본급 233만원` 이 함께 있으면 월급을 택한다
    (기본급은 구성요소이고, 우리가 비교하는 것은 총액이다)

사용법
    from wage_parser import parse_wage
    parse_wage("월급 2,326,840원 기본급 233~272만원")
    -> {'kind': '월급', 'amount': 2326840.0, 'raw': '월급 2,326,840원', 'ambiguous': False}
"""

from __future__ import annotations

import re
import sys

# 임금 형태 우선순위. 총액을 나타내는 것이 앞에 온다.
PRIORITY = ("월급", "연봉", "시급", "일급", "주급", "기본급")

# 형태 표기 -> 표준 이름
KIND_WORDS = {
    "월급": "월급", "월 급여": "월급", "월급여": "월급", "월임금": "월급",
    "월 임금": "월급", "급여": "월급", "월수령": "월급", "월 수령": "월급",
    "연봉": "연봉", "연 봉": "연봉", "년봉": "연봉",
    "시급": "시급", "시간급": "시급", "시간당": "시급",
    "일급": "일급", "일당": "일급", "일 급": "일급",
    "주급": "주급",
    "기본급": "기본급", "기본 급": "기본급", "기본시급": "시급",
}

# 이 표현이 가까이 있으면 공고의 임금이 아니다
EXCLUDE_NEAR = (
    "최저임금", "최저 임금", "최저시급", "최저 시급",
    "인센티브", "상여금", "상여", "성과급", "식대", "교통비", "차량유지비",
    "수당", "퇴직금", "퇴직연금", "보험료", "공제", "세금",
)

_NUM = r"(\d[\d,\.]*)"
# 만원 단위: `220만원`, `233~272만원`, `2,800 만 원`
_MAN = re.compile(_NUM + r"\s*(?:~|-|∼|―)?\s*(?:\d[\d,\.]*)?\s*만\s*원?")
# 원 단위: `2,326,840원`, `10,320 원`
_WON = re.compile(_NUM + r"\s*원")


def _to_float(s: str) -> float | None:
    s = s.replace(",", "").strip().rstrip(".")
    try:
        return float(s)
    except ValueError:
        return None


def _excluded(text: str, start: int, end: int, window: int = 14) -> bool:
    """제외 단어는 금액 **앞**(라벨 위치)에서만 본다.

    뒤까지 보면 `시급 12,000원(제수당 포함)` 처럼 금액 뒤에 붙는 설명 때문에
    정상 임금이 걸러진다. 최저임금 안내만 예외적으로 뒤도 확인한다
    (`시급 10,320원(최저임금)` 형태가 있다).
    """
    before = text[max(0, start - window):start]
    if any(w in before for w in EXCLUDE_NEAR):
        return True
    after = text[end:min(len(text), end + 10)]
    return any(w in after for w in ("최저임금", "최저 임금", "최저시급", "최저 시급"))


def _sanity(kind: str, won: float) -> str:
    """금액 크기로 형태를 교정한다.

    `시급 회사 내규에 따름 (월 220만 원 이상)` 처럼 라벨과 실제 금액이 어긋나는
    공고가 많다. 220만원이 시급일 수는 없으므로 금액을 믿는다.
    """
    if kind in ("시급",) and won >= 100_000:
        return "월급" if won >= 1_000_000 else "일급"
    if kind in ("월급", "연봉") and won < 100_000:
        return "시급"
    if kind == "연봉" and won < 5_000_000:      # 연봉이라기엔 너무 작다
        return "월급"
    return kind


def _find_amounts(text: str) -> list[tuple[int, int, float, str]]:
    """(시작, 끝, 금액원, 표기) 목록. 만원 표기를 먼저 잡아 원 표기와 겹치지 않게 한다."""
    out: list[tuple[int, int, float, str]] = []
    taken: list[tuple[int, int]] = []

    for m in _MAN.finditer(text):
        v = _to_float(m.group(1))
        if v is None:
            continue
        out.append((m.start(), m.end(), v * 10000, m.group(0)))
        taken.append((m.start(), m.end()))

    for m in _WON.finditer(text):
        if any(s <= m.start() < e for s, e in taken):
            continue
        v = _to_float(m.group(1))
        if v is None:
            continue
        out.append((m.start(), m.end(), v, m.group(0)))
    return sorted(out)


def parse_wage(text: str) -> dict | None:
    """본문에서 임금 하나를 뽑는다. 못 찾으면 None.

    반환: {'kind','amount','raw','ambiguous'}
      kind      '월급' | '연봉' | '시급' | '일급' | '주급'
      amount    원 단위 float (범위면 하한)
      ambiguous 형태 표기 없이 금액만 있어 추정한 경우 True
    """
    t = (text or "").replace(" ", " ")
    if not t.strip():
        return None

    found: dict[str, tuple[float, str]] = {}

    for s, e, won, raw in _find_amounts(t):
        if _excluded(t, s, e):
            continue
        # 금액 앞 24자에서 임금 형태 표기를 찾는다
        before = t[max(0, s - 24):s]
        kind = None
        pos = -1
        for w, std in KIND_WORDS.items():
            i = before.rfind(w)
            if i > pos:
                pos, kind = i, std
        if kind is None:
            continue
        if kind not in found:                 # 같은 형태는 첫 번째(하한)만
            found[kind] = (won, raw.strip())

    if not found:
        # 형태 표기가 없으면 금액 크기로 추정한다.
        # 시급은 만원 단위가 아니고, 월급은 100만원 이상인 것이 보통이다.
        cands = [(w, r) for s, e, w, r in _find_amounts(t) if not _excluded(t, s, e)]
        for won, raw in cands:
            if 6000 <= won <= 60000:
                return {"kind": "시급", "amount": won, "raw": raw.strip(),
                        "ambiguous": True}
        for won, raw in cands:
            if 1_000_000 <= won <= 20_000_000:
                return {"kind": "월급", "amount": won, "raw": raw.strip(),
                        "ambiguous": True}
        return None

    for k in PRIORITY:
        if k in found:
            won, raw = found[k]
            if k == "기본급":                  # 총액이 없을 때만 기본급을 쓴다
                k = "월급" if won >= 500_000 else "시급"
            return {"kind": _sanity(k, won), "amount": won, "raw": raw,
                    "ambiguous": False}
    return None


# ─────────────────────────────────────────────────────────────────────────────
# 자체 검사
# ─────────────────────────────────────────────────────────────────────────────

CASES = [
    # (본문, 기대 형태, 기대 금액)
    ("월급 2,326,840원", "월급", 2326840),
    ("급여 월급 2,326,840원 수습기간있음 기본급 233~272만원, "
     "인센티브 매월 최대 20만원, 상여금 별도 지급 2026년 최저시급 10,320원",
     "월급", 2326840),
    ("기본급 233~272만원(근속별 인상)", "월급", 2330000),
    ("시급 회사 내규에 따름 (월 220만 원 이상 가능) 기숙사 제공", "월급", 2200000),
    ("시급 10,320원", "시급", 10320),
    ("연봉 3,620만원", "연봉", 36200000),
    ("일급 98,000원", "일급", 98000),
    ("주간 근무 / 초보 가능 / 기숙사 제공", None, None),
    ("2026년 최저시급 10,320원 참고", None, None),          # 최저임금만 있으면 제외
    ("인센티브 매월 최대 20만원", None, None),               # 수당만 있으면 제외
    ("시급 12,000원(제수당 포함)", "시급", 12000),
    ("월 소정근로시간 209시간, 월급여 2,156,880원", "월급", 2156880),
    ("시간당 11,500원 지급", "시급", 11500),
]

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ok = bad = 0
    for text, want_kind, want_amt in CASES:
        got = parse_wage(text)
        gk = got["kind"] if got else None
        ga = got["amount"] if got else None
        pass_ = (gk == want_kind) and (
            want_amt is None or (ga is not None and abs(ga - want_amt) < 1))
        ok, bad = (ok + 1, bad) if pass_ else (ok, bad + 1)
        mark = "OK  " if pass_ else "실패"
        print(f"{mark} {text[:52]!r:<56} -> {gk} {ga}")
        if not pass_:
            print(f"     기대: {want_kind} {want_amt}")
    print(f"\n{ok}/{ok + bad} 통과")
    sys.exit(1 if bad else 0)
