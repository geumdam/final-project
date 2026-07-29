#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
공고 링크 수집기 — 인터페이스 규격

담당: 크롤링 담당자
받는 쪽: streamlit_app.py (링크 입력칸 -> 폼 자동 채움 -> ML 예측 + LLM 진단 + 대화)

────────────────────────────────────────────────────────────────────────────
채워야 하는 것: fetch_posting(url) 하나입니다.
────────────────────────────────────────────────────────────────────────────

아래 FetchResult 형태로 돌려주면 화면·예측·진단·대화는 이미 만들어진 것이 받습니다.
crawl_alba(url) 안의 TODO 부분만 구현하면 됩니다.

확인 방법 (구현하면서 계속 돌려보세요):

    python crawler_interface.py                       # 규격 자체 검사
    python crawler_interface.py --url "https://..."   # 실제 링크로 시험

규격 검사가 통과하면 앱에 그대로 붙습니다. 앱 코드는 건드리지 않아도 됩니다.

────────────────────────────────────────────────────────────────────────────
반드시 채워야 하는 것 vs 있으면 좋은 것
────────────────────────────────────────────────────────────────────────────

필수 (이것만 있어도 근로조건 진단과 대화는 100% 동작합니다)
    body        공고 본문 텍스트. 임금·근무시간은 우리 파서가 여기서 읽어냅니다
                (wage_parser.parse_wage / worktime_parser). 따로 안 넘겨도 됩니다.

있으면 예측이 정확해짐 (없으면 결측 처리되고 구간이 넓어집니다)
    sigungu     부산 구·군. 반드시 아래 SIGUNGU 목록의 값과 글자가 같아야 합니다
    weekly_hours / work_days
    ksco_code   직종 대분류 '1.0'~'9.0'. 알바몬 분류를 이 9개로 접어야 합니다
    employees   기업 근로자수 — 예측에 가장 큰 영향을 주는 값입니다

알바몬·알바천국에는 없는 것 (넣지 않아도 됩니다)
    employees / 기업규모구간 / founded / revenue
    -> 기존 수집분 557건을 확인해 보니 이 정보가 아예 없었습니다.
       비워두면 결측으로 처리되고, 신뢰도 등급이 그 불확실성을 드러냅니다.

────────────────────────────────────────────────────────────────────────────
값이 학습 범주와 다르면 조용히 결측이 됩니다
────────────────────────────────────────────────────────────────────────────

모델은 범주를 정수 코드로 다룹니다. '해운대'(X) / '해운대구'(O) 처럼 한 글자만
달라도 학습에 없는 값이 되어 결측 처리되고, 예측이 눈에 안 띄게 나빠집니다.
그래서 validate() 가 값을 대조해 경고를 냅니다. 구현 중에 꼭 확인하세요.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

MODEL_META = Path("models/meta.json")

# 부산 구·군 (참고용. 실제 검증은 meta.json 의 학습 범주로 합니다)
SIGUNGU = ["강서구", "금정구", "기장군", "남구", "동구", "동래구", "부산진구",
           "북구", "사상구", "사하구", "서구", "수영구", "연제구", "영도구",
           "중구", "해운대구"]

# 직종 대분류 (ksco_code). 알바몬 분류를 이 9개 중 하나로 접어주세요.
KSCO = {
    "1.0": "관리자", "2.0": "전문가·관련직", "3.0": "사무직",
    "4.0": "서비스직 (음식점·카페·매장·요양 등)", "5.0": "판매직",
    "6.0": "농림어업", "7.0": "기능원·관련 기능직",
    "8.0": "장치·기계 조작·조립직 (공장·생산)", "9.0": "단순노무직 (물류·청소·배송)",
}

WAGE_KINDS = ("시급", "일급", "주급", "월급", "연봉")


@dataclass
class FetchResult:
    """fetch_posting 의 반환 형태."""

    # ── 필수 ────────────────────────────────────────────────────
    body: str = ""                      # 공고 본문 (이것만 있어도 진단·대화 동작)

    # ── 표시용 (없으면 화면에 '정보없음') ──────────────────────
    company: str = ""
    title: str = ""
    source_url: str = ""

    # ── 임금 (안 넣으면 body 에서 우리 파서가 읽습니다) ────────
    wage_kind: str = ""                 # WAGE_KINDS 중 하나
    wage_amount: float | None = None     # 원 단위 (220만원 -> 2200000)

    # ── 근무 조건 (있으면 예측이 정확해짐) ─────────────────────
    sigungu: str = ""                   # 반드시 학습 범주와 같은 표기
    weekly_hours: float | None = None
    work_days: float | None = None
    ksco_code: str = ""                 # '1.0' ~ '9.0'
    employ_type: str = ""
    career: str = ""
    education: str = ""

    # ── 알바몬에 없을 것 (비워도 됨) ───────────────────────────
    employees: float | None = None
    company_size: str = ""              # 기업규모구간

    # ── 수집 메타 ──────────────────────────────────────────────
    ok: bool = True
    error: str = ""
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# 여기를 구현하세요
# ─────────────────────────────────────────────────────────────────────────────

def crawl_alba(url: str) -> FetchResult:
    """알바몬 / 알바천국 공고 링크에서 내용을 가져온다.

    TODO 크롤링 담당자
      1. url 로 요청해 HTML(또는 렌더링 결과)을 받는다
      2. 본문 텍스트를 body 에 담는다              <- 이것만 해도 진단·대화 동작
      3. 가능하면 구·군·근무시간·직종을 채운다
      4. 실패하면 FetchResult(ok=False, error="사유") 로 돌려준다

    주의
      - 알바몬은 JS 렌더링·봇 차단이 있어 requests 만으로 안 될 수 있습니다.
        Playwright 가 필요하면 알려주세요 (Streamlit Cloud 배포에 영향이 있습니다).
      - 실패를 예외로 던지지 말고 ok=False 로 돌려주세요. 화면이 사용자에게
        "링크를 읽지 못했습니다. 본문을 직접 붙여넣어 주세요" 라고 안내합니다.
      - 본문에 임금·근무시간 문구가 남아 있으면 파서가 읽으니 지우지 마세요.
    """
    return FetchResult(
        ok=False, source_url=url,
        error="crawl_alba() 가 아직 구현되지 않았습니다")


def fetch_posting(url: str) -> FetchResult:
    """앱이 호출하는 진입점. 사이트별 수집기로 분기한다."""
    u = (url or "").strip()
    if not u.startswith(("http://", "https://")):
        return FetchResult(ok=False, error="링크 형식이 아닙니다")
    if "albamon" in u or "alba.co.kr" in u:
        return crawl_alba(u)
    return FetchResult(ok=False, source_url=u,
                       error="알바몬·알바천국 링크만 지원합니다")


# ─────────────────────────────────────────────────────────────────────────────
# 규격 검사 — 구현하면서 계속 돌려보세요
# ─────────────────────────────────────────────────────────────────────────────

def _categories() -> dict:
    if not MODEL_META.exists():
        return {}
    return json.loads(MODEL_META.read_text(encoding="utf-8")).get("categories", {})


def validate(r: FetchResult) -> list[str]:
    """학습 범주와 대조해 문제를 찾는다. 빈 목록이면 통과."""
    p: list[str] = []
    cats = _categories()

    if not r.ok:
        return [f"수집 실패: {r.error}"]
    if not (r.body or "").strip():
        p.append("body 가 비었습니다 — 이것이 없으면 근로조건 진단과 대화가 안 됩니다")
    elif len(r.body.strip()) < 30:
        p.append(f"body 가 {len(r.body.strip())}자뿐입니다 — 진단이 '본문없음' 으로 나옵니다")

    def chk(field_name: str, value: str, cat_key: str) -> None:
        if not value:
            return
        allowed = cats.get(cat_key)
        if allowed and value not in allowed:
            near = [a for a in allowed if value[:2] in a][:3]
            p.append(f"{field_name}={value!r} 는 학습 범주에 없습니다 → 결측 처리됩니다."
                     + (f" 비슷한 값: {near}" if near else ""))

    chk("sigungu", r.sigungu, "sigungu")
    chk("ksco_code", r.ksco_code, "ksco_code")
    chk("employ_type", r.employ_type, "employ_type")
    chk("career", r.career, "career")
    chk("education", r.education, "education")
    chk("company_size", r.company_size, "기업규모구간")

    if r.wage_kind and r.wage_kind not in WAGE_KINDS:
        p.append(f"wage_kind={r.wage_kind!r} 는 {WAGE_KINDS} 중 하나여야 합니다")
    if r.wage_amount is not None:
        if r.wage_amount <= 0:
            p.append("wage_amount 가 0 이하입니다")
        elif r.wage_kind == "시급" and r.wage_amount > 100_000:
            p.append(f"시급 {r.wage_amount:,.0f}원 — 단위를 확인하세요 (만원을 원으로 바꿨나요?)")
        elif r.wage_kind == "월급" and r.wage_amount < 300_000:
            p.append(f"월급 {r.wage_amount:,.0f}원 — 단위를 확인하세요")
    if r.weekly_hours is not None and not (0 < r.weekly_hours <= 80):
        p.append(f"weekly_hours={r.weekly_hours} 가 범위를 벗어납니다 (0~80)")
    if r.work_days is not None and not (0 < r.work_days <= 7):
        p.append(f"work_days={r.work_days} 가 범위를 벗어납니다 (1~7)")
    return p


def report(r: FetchResult) -> None:
    """수집 결과와 파서가 본문에서 무엇을 읽어냈는지 보여준다."""
    print("=" * 74)
    print(f"ok={r.ok}" + (f"  error={r.error}" if r.error else ""))
    if r.ok:
        print(f"company={r.company!r}  title={r.title!r}")
        print(f"body {len(r.body)}자: {r.body[:110]!r}")
        print(f"sigungu={r.sigungu!r}  ksco_code={r.ksco_code!r}  "
              f"weekly={r.weekly_hours}  days={r.work_days}")
        print(f"wage={r.wage_kind!r} {r.wage_amount}")

        # 본문에서 우리 파서가 읽어내는 것 — 따로 안 채워도 됩니다
        try:
            from wage_parser import parse_wage
            got = parse_wage(r.body)
            print(f"\n  [파서] 본문에서 읽은 임금: {got}")
        except Exception as e:
            print(f"\n  [파서] 임금 읽기 실패: {e}")
        try:
            import worktime_parser as W
            if hasattr(W, "parse_worktime"):
                print(f"  [파서] 본문에서 읽은 근무시간: {W.parse_worktime(r.body)}")
        except Exception:
            pass

    probs = validate(r)
    print("\n검사 결과:", "통과" if not probs else f"{len(probs)}건 확인 필요")
    for x in probs:
        print(f"  - {x}")


def main() -> None:
    ap = argparse.ArgumentParser(description="공고 링크 수집기 규격 검사")
    ap.add_argument("--url", help="실제 링크로 시험")
    args = ap.parse_args()

    if args.url:
        report(fetch_posting(args.url))
        return

    print("규격 자체 검사 (구현 전이라 crawl_alba 는 실패가 정상입니다)\n")

    print("[1] 지원하지 않는 링크")
    report(fetch_posting("https://www.jobkorea.co.kr/somewhere"))

    print("\n[2] 링크 형식 아님")
    report(fetch_posting("albamon.com/12345"))

    print("\n[3] 구현 완료 시 이런 결과가 나오면 통과입니다")
    report(FetchResult(
        body=("주간 근무 / 시급 회사 내규에 따름 (월 220만 원 이상 가능) / "
              "초보 가능 / 기숙사 제공 / 4대보험"),
        company="(주)예시산업", title="생산직 모집",
        source_url="https://www.albamon.com/jobs/detail/12345",
        sigungu="사상구", ksco_code="8.0", weekly_hours=40.0, work_days=5.0))

    print("\n[4] 흔한 실수 — 구·군 표기가 다른 경우")
    report(FetchResult(body="공장 생산직 주 40시간 근무합니다. 4대보험 가입.",
                       sigungu="해운대", ksco_code="제조"))

    print("\n" + "=" * 74)
    print("구현 순서 권장")
    print("  1) body 만 채워서 [3] 처럼 검사 통과시키기  <- 여기까지면 진단·대화 동작")
    print("  2) sigungu·weekly_hours·work_days 추가")
    print("  3) ksco_code 매핑 (알바몬 직종 -> 위 KSCO 9개)")
    print("\n직종 대분류 참고")
    for k, v in KSCO.items():
        print(f"  {k}  {v}")


if __name__ == "__main__":
    main()
