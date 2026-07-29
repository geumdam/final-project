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
import re
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

    # ── 사이트가 입력칸으로 밝힌 근로조건 ──────────────────────
    # 알바 공고의 36%는 상세요강을 이미지로 올려 body 가 0자다. 그때도 이
    # 항목들은 채워져 있다. 진단·대화에 body 와 동등한 근거로 넣는다.
    conditions: str = ""                # 사람이 읽는 요약 (프롬프트에 그대로 들어감)
    welfare: str = ""                   # 복리후생 원문 (4대보험 판정의 근거)
    work_time_raw: str = ""             # 근무시간 항목 원문
    work_days_raw: str = ""             # 근무요일 원문
    job_categories: str = ""            # 사이트 표기 업직종

    # ── 수집 메타 ──────────────────────────────────────────────
    ok: bool = True
    error: str = ""
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


# ─────────────────────────────────────────────────────────────────────────────
# 수집 — 팀원 수집기(collect_commercial.py)를 그대로 재사용한다
# ─────────────────────────────────────────────────────────────────────────────

# 알바몬 상세 URL: https://www.albamon.com/jobs/detail/118166594
RE_ALBAMON_PID = re.compile(r"albamon\.com/jobs/detail/(\d+)")
# 알바천국 상세 URL: https://www.alba.co.kr/job/Detail?adid=12345678
RE_ALBA_PID = re.compile(r"alba\.co\.kr/job/\w+\?[^#]*adid=(\d+)", re.I)

# 알바몬 viewData 에서 복리후생. 수집기 allowlist 에는 없어서 여기서 따로 읽는다.
# 이 값이 `사회보험_미기재` 판정을 가른다 — '국민연금·고용보험·산재보험·건강보험'
# 이 적혀 있으면 구직자가 화면에서 볼 수 있으므로 '미기재' 가 아니다.
WELFARE_KEY = "welfareBenefits"


DAYS = "월화수목금토일"


def parse_work_days(raw: str) -> float | None:
    """'월~금' 같은 표기에서 주당 근무일수를 센다.

    수집기의 `resolve_schedule` 은 이 표기를 못 읽어서 `workday_count_min` 이
    비고(수집분 전체에서 44.1% 만 채워짐), 그러면 주당 근로시간도 못 만든다.
    주당 근로시간과 근무일수는 모델이 쓰는 5개 피처 중 2개라 그냥 두면 아깝다.

    못 읽으면 None 을 돌려준다. 억지로 5일이라고 가정하지 않는다.
    """
    t = (raw or "").replace(" ", "")
    if not t:
        return None
    # '주5일' / '주 5회'
    m = re.search(r"주\s*([1-7])\s*[일회]", t)
    if m:
        return float(m.group(1))
    # '월~금' / '월-토' (요일 범위)
    m = re.search(rf"([{DAYS}])\s*[~\-–]\s*([{DAYS}])", t)
    if m:
        a, b = DAYS.index(m.group(1)), DAYS.index(m.group(2))
        return float((b - a) % 7 + 1)
    # '월,수,금' / '월화수' (요일 열거) — 다른 낱말의 한 글자를 세지 않도록
    # 요일 문자만으로 이루어진 토큰에서만 센다.
    tok = re.findall(rf"[{DAYS}](?:\s*[,·/]\s*[{DAYS}])+", t)
    if tok:
        return float(len({c for c in tok[0] if c in DAYS}))
    m = re.fullmatch(rf"[{DAYS}]{{2,7}}", t.split("|")[0])
    if m:
        return float(len(set(m.group(0))))
    if "매일" in t:
        return 7.0
    return None


KSCO_LUT = Path("data") / "ksco_lookup.json"
_lut_cache: dict | None = None


def map_ksco(job_categories: str) -> str:
    """사이트 업직종 표기를 학습 직종 대분류('1.0'~'9.0')로 접는다.

    `data/ksco_lookup.json` (build_private.py 가 만든다) 을 쓴다. 이미 매핑된
    공고 1,876건에서 '업직종 토큰 -> 대분류' 빈도를 세어 둔 표다.

    `data/job_category_mapping.csv` 의 `rule` 정규식은 쓰지 않는다. 값이
    34~39자로 잘려 저장돼 있고 44개는 끝이 '|' 로 끊겨 **빈 문자열까지 매칭**한다.
    그래서 어떤 입력이든 걸리고, 편의점·생산·물류가 전부 3.0(사무직)으로 접혔다.

    공고는 업직종을 여러 개 달 수 있으므로(예: '고객상담·인바운드, 사무보조,
    텔레마케팅·아웃바운드') 토큰별 표를 합산해 가장 표가 많은 대분류를 고른다.
    표에 없는 토큰만 있으면 빈 문자열 — 결측이 틀린 직종보다 낫다.
    """
    global _lut_cache
    t = (job_categories or "").strip()
    if not t:
        return ""
    if _lut_cache is None:
        try:
            _lut_cache = json.loads(KSCO_LUT.read_text(encoding="utf-8"))
        except Exception:
            _lut_cache = {}
    if not _lut_cache:
        return ""
    vote: dict[str, int] = {}
    for part in t.split(","):
        for code, n in (_lut_cache.get(part.strip()) or {}).items():
            vote[code] = vote.get(code, 0) + int(n)
    if not vote:
        return ""
    return max(vote.items(), key=lambda kv: kv[1])[0]


def _fmt_welfare(raw) -> str:
    """[{'value':'10','description':'국민연금'}, ...] -> '국민연금, 고용보험, ...'"""
    if not isinstance(raw, list):
        return ""
    out = []
    for x in raw:
        d = x.get("description") if isinstance(x, dict) else x
        d = str(d or "").strip()
        if d and d not in out:
            out.append(d)
    return ", ".join(out)


def build_conditions(r: "FetchResult") -> str:
    """사이트 입력 항목을 사람이 읽는 한 덩어리로 만든다.

    이 글이 프롬프트에 그대로 들어간다. 값이 없는 줄은 넣지 않는다 —
    '급여: (없음)' 같은 줄을 넣으면 모델이 그걸 '미기재'의 근거로 읽는다.
    """
    L = []
    if r.wage_kind and r.wage_amount:
        L.append(f"- 급여: {r.wage_kind} {r.wage_amount:,.0f}원")
    if r.work_time_raw:
        L.append(f"- 근무시간: {r.work_time_raw}")
    if r.work_days_raw:
        L.append(f"- 근무요일: {r.work_days_raw}")
    if r.employ_type:
        L.append(f"- 고용형태: {r.employ_type}")
    if r.job_categories:
        L.append(f"- 업직종: {r.job_categories}")
    if r.sigungu:
        L.append(f"- 근무지역: 부산 {r.sigungu}")
    if r.welfare:
        L.append(f"- 복리후생: {r.welfare}")
    return "\n".join(L)


def crawl_alba(url: str) -> FetchResult:
    """알바몬 / 알바천국 공고 링크에서 내용을 가져온다.

    팀원이 만든 `collect_commercial.py` 를 그대로 호출한다. 그 수집기는 이미
    2,050건을 실패 0으로 받아낸 코드이고, robots 하드 가드(`guard_url`)와
    개인정보 allowlist 가 들어 있다. 여기서 다시 구현하면 그 방어가 빠진다.

    본문이 0자로 오는 것은 실패가 아니다. 알바 공고의 36%는 상세요강을
    이미지로 올린다(알바몬 45%, 알바천국 27%). 그때는 `conditions` 에
    담긴 사이트 입력 항목이 유일한 근거가 되므로 반드시 함께 채운다.
    """
    try:
        import collect_commercial as C
    except ImportError as e:
        return FetchResult(ok=False, source_url=url,
                           error=f"수집기를 불러올 수 없습니다: {e}")

    m_mon = RE_ALBAMON_PID.search(url)
    m_alba = RE_ALBA_PID.search(url)
    if not (m_mon or m_alba):
        return FetchResult(
            ok=False, source_url=url,
            error="공고 상세 링크가 아닙니다. 예: "
                  "https://www.albamon.com/jobs/detail/118166594")

    try:
        s = C.make_session()
        if m_mon:
            pid = m_mon.group(1)
            html = C.fetch(s, C.ALBAMON_DETAIL.format(pid=pid))
            props = C.next_data(html)["props"]["pageProps"]
            payload = props.get("data") or {}
            view = payload.get("viewData") or {}
            if payload.get("crawlerBlocked") or view.get("crawlingBlock"):
                return FetchResult(ok=False, source_url=url,
                                   error="이 공고는 사이트가 수집을 차단했습니다")
            if not view:
                return FetchResult(ok=False, source_url=url,
                                   error="마감·삭제된 공고로 보입니다")
            welfare = _fmt_welfare(view.get(WELFARE_KEY))
            row = C.build_albamon({"recruitNo": pid},
                                  C.pick(view, C.ALBAMON_VIEW_KEYS))
        else:
            pid = m_alba.group(1)
            row = C.build_alba(pid, C.alba_detail(s, pid))
            welfare = ""      # 알바천국은 정의목록에 복리후생이 따로 오지 않는다
    except Exception as e:                    # 네트워크·구조 변경·차단 전부
        return FetchResult(ok=False, source_url=url,
                           error=f"{type(e).__name__}: {str(e)[:180]}")

    r = FetchResult(
        source_url=url,
        title=str(row.get("title") or ""),
        body=str(row.get("body_text") or ""),
        wage_kind=str(row.get("wage_type") or ""),
        wage_amount=row.get("wage_amount"),
        sigungu=str(row.get("region_district") or ""),
        weekly_hours=row.get("weekly_work_hours_min"),
        work_days=row.get("workday_count_min"),
        ksco_code=map_ksco(str(row.get("job_categories_raw") or "")),
        employ_type=str(row.get("employment_type_raw") or ""),
        welfare=welfare,
        work_time_raw=str(row.get("work_time_raw") or ""),
        work_days_raw=str(row.get("work_days_raw") or ""),
        job_categories=str(row.get("job_categories_raw") or ""),
    )
    # 본문에도 개인정보가 남아 있을 수 있다. 수집기 마스킹이 구분자 폭 때문에
    # 새는 것을 확인했으므로 여기서 한 번 더 지운다 (body_remask.py 참고).
    try:
        from body_remask import remask
        r.body = remask(r.body)
    except ImportError:
        r.warnings.append("body_remask 를 못 불러와 본문 마스킹을 건너뛰었습니다")

    # 근무일수를 못 읽었으면 요일 표기에서 다시 세고, 주당 시간도 되살린다.
    if r.work_days is None:
        r.work_days = parse_work_days(r.work_days_raw)
    daily = row.get("daily_work_hours_min")
    if r.weekly_hours is None and daily and r.work_days:
        r.weekly_hours = round(float(daily) * float(r.work_days), 1)

    r.conditions = build_conditions(r)
    if not r.body.strip():
        r.warnings.append(
            "이 공고는 상세요강이 이미지라 본문 텍스트가 없습니다. "
            "아래 근로조건 항목을 근거로 진단합니다.")
    if not r.conditions and not r.body.strip():
        return FetchResult(ok=False, source_url=url,
                           error="본문도 근로조건 항목도 비어 있습니다")
    return r


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
    # 본문이 비었다고 곧바로 문제인 것은 아니다. 알바 공고의 36%는 상세요강을
    # 이미지로 올리는데, 그때도 사이트 입력 항목(conditions)이 진단 근거가 된다.
    body_n = len((r.body or "").strip())
    cond_n = len((r.conditions or "").strip())
    if body_n == 0 and cond_n == 0:
        p.append("body 와 conditions 가 모두 비었습니다 — 진단·대화가 안 됩니다")
    elif body_n < 30 and cond_n == 0:
        p.append(f"body 가 {body_n}자뿐이고 conditions 도 없습니다 — "
                 f"진단이 '본문없음' 으로 나옵니다")
    elif body_n < 30:
        p.append(f"본문은 {body_n}자(상세요강이 이미지)지만 근로조건 항목이 "
                 f"{cond_n}자 있어 진단은 됩니다")

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
