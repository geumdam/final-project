#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
민간 채용 사이트(알바몬·알바천국) 부산 지역 공고 수집

수집 근거
  - 저작권법 제94조 ②항 1호: 교육·학술·연구 목적의 비영리 이용
  - 수집 간격 0.7초를 유지해 시스템 부하를 발생시키지 않음
  - 원본 데이터는 재배포하지 않으며 분석 결과만 제출물에 포함
  - 사이트가 공고별로 내려주는 크롤링 차단 플래그(crawlingBlock)를 존중한다

robots.txt 확인 (2026-07-29)
  알바몬  User-agent: * 에 `/jobs` 차단 없음. 단 아래는 명시적 Disallow 이므로
          BLOCKED 목록에 넣어 요청 자체를 막는다.
            /jobs/detail-content, /jobs/detail/content, /jobs/detail/manager,
            /jobs/detail/print, /jobs/detail/photos, /jobs/apply/,
            /jobs/town/apply/, /alba-contract, /personal
          우리가 쓰는 `/jobs/detail/{번호}` 와 `/jobs/area/home` 은 허용 경로다.
          다만 사이트가 "본문 콘텐츠 경로"를 따로 막아둔 만큼, 본문을 SSR
          페이로드에서 읽는 것은 회색지대로 보고 마스킹을 전제로만 진행한다.
  알바천국 `Disallow: /` 뒤에 `Allow: /job/`, `/recruit/`, `/search/` 등이 온다.
          전면 차단이 아니다. 우리가 쓰는 `/job/object/main`, `/job/Detail`,
          `/job/DetailContent` 는 모두 `/job/` 허용 범위 안이다.

수집 설계 — 왜 본문과 구조화 필드를 함께 받는가
  알바몬 상세 응답(viewData)에는 근무시각·휴게분·주휴여부·사이트 계산
  실근로시간이 구조화돼 있다. 임금·근로시간은 이쪽이 본문 정규식보다 정확하다.
  본문은 직무내용 텍스트다. 공공(고용24) 데이터에는 job_content 가 있는데
  민간에는 없어서 진단·대화 기능이 민간 공고에서 반쪽이었다. 그 구멍을 메운다.

개인정보 처리
  viewData 는 키가 218개이고 그 안에 phoneNumber·managerEmail·userIpAddress·
  nonMembersPassword 가 섞여 있다. 목록 응답에도 managerPhoneNumber 가 그대로
  실려 온다. 그래서 **읽을 키를 명시한 allowlist 방식**으로만 접근한다.
  본문은 body_sanitize.sanitize_body() 로 마스킹한 뒤에만 저장한다.
  원본 HTML·담당자명·연락처·상세주소는 어디에도 저장하지 않는다.

사용법
  python collect_commercial.py smoke                     # 소스별 15건 검증
  python collect_commercial.py collect                   # 소스별 1,000건
  python collect_commercial.py collect --limit 300
  python collect_commercial.py collect --source albamon
  python collect_commercial.py normalize                 # 통합 + 시급 환산
"""

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup, NavigableString, Tag

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from body_sanitize import sanitize_body                            # noqa: E402
from worktime_parser import normalize_korean_time, parse_worktime  # noqa: E402

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

SLEEP_SEC = 0.7            # collect_work24.py 와 동일. 반드시 유지할 것
TIMEOUT = 25
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

# 부산 지역 코드. 팀원 파일럿(collect_commercial_pilot.py)에서 검증된 값이다.
ALBAMON_AREA = "H000"
ALBA_AREA = "051"

ALBAMON_LIST = ("https://www.albamon.com/jobs/area/home"
                f"?areas={ALBAMON_AREA}&page={{page}}&size={{size}}")
ALBAMON_DETAIL = "https://www.albamon.com/jobs/detail/{pid}"
ALBAMON_LIST_SIZE = 100     # 한 요청에 100건. 요청 수를 5분의 1로 줄인다

ALBA_LIST = ("https://www.alba.co.kr/job/object/main?page={page}"
             f"&strAreaMulti={ALBA_AREA}%7C%7C%EC%A0%84%EC%B2%B4%7C%7C"
             "&hidSort=FREEORDER&hidSortOrder=1&hidSortCnt=20&hidSortFilter=Y")
ALBA_DETAIL = "https://www.alba.co.kr/job/Detail?adid={pid}"
ALBA_LIST_SIZE = 20         # 서버 고정

DEFAULT_LIMIT = 1000        # 소스별 목표 건수
SMOKE_LIMIT = 15

RAW_DIR = BASE_DIR / "data" / "raw_commercial"
OUT_DIR = BASE_DIR / "data"
LOG_PATH = OUT_DIR / "commercial_run.log"

KST = timezone(timedelta(hours=9))
MIN_WAGE_2026 = 10320       # 고용노동부 고시 제2025-47호
PARSER_VERSION = "commercial-v1"
DUP_VERSION = "offer-v3-kim"
SAME_DAY_VERSION = "same-day-exact-v1"

# ---------------------------------------------------------------------------
# robots.txt 가드
#
# URL 조립 실수로 차단 경로를 치는 일을 코드 수준에서 막는다.
# 예외를 던져 조용히 넘어가지 않게 한다.
# ---------------------------------------------------------------------------

ALBAMON_BLOCKED = (
    "/jobs/detail-content", "/jobs/detail/content", "/jobs/detail/manager",
    "/jobs/detail/print", "/jobs/detail/photos", "/jobs/apply/",
    "/jobs/town/apply/", "/alba-contract", "/personal",
)
# 알바천국은 Disallow: / 가 기본이라 허용 접두어를 화이트리스트로 둔다
ALBA_ALLOWED = ("/job/", "/recruit/", "/search/", "/story/", "/customer/",
                "/sitemap/", "/serviceguide/", "/contract/")


class RobotsViolation(RuntimeError):
    """robots.txt 가 막은 경로를 요청하려 했다."""


class DetailUnavailable(RuntimeError):
    """사이트가 상세를 주지 않는다 (마감·삭제 등). 목록 정보까지만 남긴다."""


def guard_url(url: str) -> str:
    """robots.txt 기준으로 요청 가능한 URL인지 확인한다."""
    u = urlparse(url)
    path = u.path

    if u.netloc.endswith("albamon.com"):
        for bad in ALBAMON_BLOCKED:
            if path.startswith(bad):
                raise RobotsViolation(f"알바몬 robots Disallow: {path}")
        # `/jobs/detail/*?*keyword` 도 Disallow 다
        if path.startswith("/jobs/detail/") and "keyword" in (u.query or ""):
            raise RobotsViolation(f"알바몬 robots Disallow(keyword): {url}")
        return url

    if u.netloc.endswith("alba.co.kr"):
        if path in ("/", "") or any(path.startswith(p) for p in ALBA_ALLOWED):
            return url
        raise RobotsViolation(f"알바천국 robots Disallow: {path}")

    raise RobotsViolation(f"허용되지 않은 호스트: {u.netloc}")


# ---------------------------------------------------------------------------
# 공통 유틸
# ---------------------------------------------------------------------------

_log_lines: list[str] = []


def log(msg: str) -> None:
    print(msg, flush=True)
    _log_lines.append(f"{datetime.now(KST):%Y-%m-%d %H:%M:%S}  {msg}")


def flush_log() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write("\n".join(_log_lines) + "\n")


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    return s


def fetch(s: requests.Session, url: str, referer: str | None = None) -> str:
    """수집 간격을 지키며 한 페이지를 받는다."""
    guard_url(url)
    headers = {"Referer": referer} if referer else {}
    r = s.get(url, timeout=TIMEOUT, headers=headers)
    r.raise_for_status()
    time.sleep(SLEEP_SEC)
    return r.text


def short_hash(*parts) -> str:
    raw = "|".join(str(p or "") for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def record_hash(*parts) -> str:
    raw = "|".join(str(p or "") for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def clean(text) -> str:
    """공백을 정리한 문자열. BeautifulSoup 노드를 그대로 넘겨도 된다.

    Tag 를 str() 하면 태그 마크업이 나온다. 라벨 비교가 전부 빗나가므로
    노드는 반드시 get_text() 를 거쳐야 한다.
    """
    if text is None:
        return ""
    if isinstance(text, (Tag, NavigableString)):
        text = text.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", str(text)).strip()


def parse_won(text) -> float | None:
    """'12,000원' -> 12000.0, '시급 10,320 원' -> 10320.0"""
    if text is None:
        return None
    m = re.search(r"([\d,]{3,})", str(text))
    if not m:
        return None
    try:
        v = float(m.group(1).replace(",", ""))
    except ValueError:
        return None
    return v if v > 0 else None


def to_float(value, zero_is_missing: bool = True) -> float | None:
    """숫자로 바꾼다. 못 바꾸면 None.

    알바몬은 숫자를 문자열로 내려보내는 필드가 섞여 있다
    (salaryCalculatorRealWorkTime="0.0", workHour={"value":"60"}).
    `or None` 만 걸어두면 "0.0" 이 참이라 결측 처리가 통째로 무력화된다.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, dict):
        value = value.get("value")
    try:
        v = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if zero_is_missing and v == 0:
        return None
    return v


def desc(value) -> str:
    """알바몬은 코드값을 {key,value,description} 으로 감싸 보낸다."""
    if isinstance(value, dict):
        for k in ("description", "value", "name", "key"):
            if value.get(k):
                return clean(value[k])
        return ""
    if isinstance(value, list):
        return ", ".join(filter(None, (desc(v) for v in value)))
    return clean(value)


def join_unique(parts, sep: str = " ") -> str:
    """빈 값·중복·이미 포함된 조각을 걷어내고 잇는다.

    알바몬은 같은 문구를 workTimeOpt / workTimeOption / workWeekEtc 에 중복해서
    담아 보낸다. 그대로 이으면 '휴게시간 60분 / 휴게시간 60분' 이 된다.
    """
    out: list[str] = []
    for raw in parts:
        p = clean(raw)
        if not p or any(p in q for q in out):
            continue
        out = [q for q in out if q not in p]     # 더 긴 조각이 이기게 한다
        out.append(p)
    return sep.join(out)


def split_area(text: str) -> tuple[str, str, str, str]:
    """'부산 동구 초량1동' -> ('부산', '동구', '초량1동', 'district')

    구·군을 못 얻으면 scope 를 citywide 로 둔다. 지역 비교에서 제외해야 한다.
    """
    t = clean(text)
    if not t:
        return "", "", "", "citywide"
    parts = t.split()
    si = parts[0] if parts else ""
    gu = next((p for p in parts[1:] if p.endswith(("구", "군", "시"))), "")
    dong = next((p for p in parts[1:] if p.endswith(("동", "읍", "면", "리"))), "")
    return si, gu, dong, ("district" if gu else "citywide")


# ---------------------------------------------------------------------------
# 근무시간 해석 — worktime_parser.py 를 그대로 재사용한다
# ---------------------------------------------------------------------------

RE_RANGE = re.compile(r"\d{1,2}:\d{2}\s*[~\-]\s*\d{1,2}:\d{2}")
RE_NEGO = re.compile(r"협의|추후\s*결정|면접\s*후|스케줄|채용공고란")
RE_DURATION = re.compile(r"(?:^|[\s(,·:/])(?:1\s*)?일\s*[\d.]+\s*시간|주\s*[\d.]+\s*시간")
# '영업시간 6시~22시사이 시간제 근무' 의 16시간은 가게 영업시간이지
# 그 사람의 근무시간이 아니다. 시급 환산에 그대로 쓰면 임금이 반토막 난다.
RE_BUSINESS_HOURS = re.compile(r"영업\s*시간|오픈\s*~|매장\s*운영|운영\s*시간")
BUSINESS_HOURS_MIN = 12.0


def resolve_schedule(work_time: str, work_days: str, break_min,
                     opt_text: str = "") -> dict:
    """근무시간 텍스트에서 근로시간을 뽑고 파싱 상태를 분류한다.

    opt_text 는 알바몬 `workTimeOpt` 처럼 "시간협의" 뒤에 숨어 있는 실제 시각
    표기다. 이걸 넘기지 않으면 협의 공고가 통째로 negotiable 로 빠진다.
    """
    rest = f"휴게시간 {int(break_min)}분" if break_min else ""
    r = parse_worktime(work_time=work_time, work_form=work_days,
                       rest_time=rest, extra=opt_text)

    # 근무 시각대 개수는 **한글 시각을 변환한 뒤** 세야 한다.
    # '8시~17시,12시~21시' 를 원문 그대로 세면 0개가 나와, 실제로 시간을
    # 뽑아냈는데도 negotiable 로 잘못 분류된다.
    joined = " ".join(filter(None, (work_time, work_days, opt_text)))
    shifts = len(RE_RANGE.findall(normalize_korean_time(joined)))

    # 영업시간을 개인 근무시간으로 읽은 경우는 버린다. 모른다고 말하는 편이
    # 하루 16시간이라는 없는 숫자를 남기는 것보다 낫다.
    # time_is_personal_shift 가 False 면 '일 N시간' 명시값이 이미 시각 범위를
    # 눌렀다는 뜻이라 그 값은 믿을 수 있다. 그때는 손대지 않는다.
    if (RE_BUSINESS_HOURS.search(joined) and r["time_is_personal_shift"]
            and r["daily_hours"] and r["daily_hours"] > BUSINESS_HOURS_MIN):
        r = dict(r, daily_hours=None, weekly_hours=None, source="")

    # 파싱 상태
    if r["daily_hours"] is None and r["weekly_hours"] is None:
        status = "negotiable" if RE_NEGO.search(joined) else "insufficient"
    elif shifts >= 2:
        status = "multi_shift"
    elif r["end_interpretation"] == "익일(야간근무)":
        status = "overnight"
    elif shifts == 1:
        status = "exact"
    elif RE_DURATION.search(joined):
        status = "duration_only"
    else:
        status = "negotiable" if RE_NEGO.search(joined) else "insufficient"

    # 주당 근로시간 신뢰도
    src = r["source"]
    if src == "소정표기":
        wk_status, rel = "stated_weekly_hours", "high"
    elif src == "주N시간":
        wk_status, rel = "stated_weekly_hours", "high"
    elif src == "일수x일일":
        if r["negotiable_mentioned"]:
            wk_status, rel = "stated_with_negotiation", "low"
        elif shifts >= 2:
            wk_status, rel = "multi_shift_equal_duration", "low"
        else:
            wk_status, rel = "fixed_derived", "medium"
    elif r["daily_hours"] is not None:
        wk_status, rel = "insufficient", "low"
    else:
        wk_status, rel = "insufficient", "none"

    return {
        "schedule_parse_status": status,
        "work_start_time": r["start"],
        "work_end_time": r["end"],
        "work_shift_count": shifts or (1 if r["daily_hours"] else 0),
        "workday_count_min": r["work_days"],
        "workday_count_max": r["work_days"],
        "daily_work_hours_min": r["daily_hours"],
        "daily_work_hours_max": r["daily_hours"],
        "weekly_work_hours_min": r["weekly_hours"],
        "weekly_work_hours_max": r["weekly_hours"],
        "weekly_hours_status": wk_status,
        "weekly_hours_reliability": rel,
    }


# ---------------------------------------------------------------------------
# 알바몬
# ---------------------------------------------------------------------------

# 목록 응답에서 읽을 키. managerPhoneNumber·workplaceAddress·latitude 등은
# 목록에도 실려 오지만 여기에 없으므로 접근하지 않는다.
ALBAMON_LIST_KEYS = (
    "recruitNo", "recruitTitle", "postedDate", "companyName", "payType",
    "pay", "negoPay", "workingTime", "workingPeriod", "workingWeek",
    "workingDate", "parts", "closingDate", "workplaceArea", "recruitType",
    "paidService",
)

# 상세 viewData 에서 읽을 키. 이 목록에 없는 키는 절대 읽지 않는다.
#   차단 대상 예시 — phoneNumber, managerEmail, managerFax, userIpAddress,
#   nonMembersPassword, recruiter, recruiterKey, companyAddress,
#   workingAddress, representativeName, applySmsDescription
ALBAMON_VIEW_KEYS = (
    "recruitNo", "recruitTitle", "registDateTime", "firstPostDateTime",
    "deadlineDate", "closingDateTime",
    "salaryType", "salary", "salaryDescription", "minimumWage",
    "holidaySalaryStatus", "salaryCalculatorRealWorkTime",
    "salaryCalculatorWorkTime", "salaryCalculatorWorkDay",
    "payEtcInfo",
    "workTimeDetail", "workTimeOption", "workTimeOpt", "workTimeConsult",
    "workStartTime", "workEndTime", "recessMinute",
    "workDays", "workWeek", "workWeekEtc", "workPeriod", "workTermDescription",
    "employmentType", "part", "jobField", "area", "publishAreaDongCode",
    "foreignerApplyStatus", "laborContractWriteStatus", "companyName",
    "crawlingBlock", "content",
)


def next_data(html: str) -> dict:
    """__NEXT_DATA__ SSR 페이로드를 꺼낸다."""
    node = BeautifulSoup(html, "html.parser").select_one("script#__NEXT_DATA__")
    if not node or not node.string:
        raise RuntimeError("__NEXT_DATA__ 없음")
    return json.loads(node.string)


def pick(src: dict, keys) -> dict:
    """allowlist 에 있는 키만 옮긴다."""
    return {k: src.get(k) for k in keys if k in src}


def albamon_list(s: requests.Session, limit: int) -> list[dict]:
    """목록 페이지에서 공고 요약을 모은다. 유료 공고는 매 페이지 반복 노출되므로
    recruitNo 로 중복을 제거한다."""
    seen: dict[str, dict] = {}
    page = 1
    while len(seen) < limit:
        url = ALBAMON_LIST.format(page=page, size=ALBAMON_LIST_SIZE)
        try:
            data = (next_data(fetch(s, url))["props"]["pageProps"]
                    ["dehydratedState"]["queries"][0]["state"]["data"])
        except Exception as exc:
            log(f"[albamon list] {page}페이지 실패: {exc}")
            break

        items: list[dict] = list(data.get("base", {}).get("normal", {})
                                 .get("collection") or [])
        paid_ids = set()
        for group in (data.get("paid") or {}).values():
            for it in (group.get("collection") or []):
                paid_ids.add(it.get("recruitNo"))
                items.append(it)

        fresh = 0
        for it in items:
            row = pick(it, ALBAMON_LIST_KEYS)
            pid = str(row.get("recruitNo") or "")
            if not pid or pid in seen:
                continue
            row["_paid"] = row.get("recruitNo") in paid_ids
            seen[pid] = row
            fresh += 1
            if len(seen) >= limit:
                break

        log(f"[albamon list] {page}페이지 신규 {fresh}건 (누적 {len(seen)})")
        if fresh == 0:
            break
        page += 1

    return list(seen.values())[:limit]


def albamon_detail(s: requests.Session, pid: str) -> dict | None:
    """상세 페이지에서 allowlist 필드만 가져온다.

    사이트가 크롤링 차단으로 표시한 공고는 None 을 돌려준다.
    마감·삭제된 공고는 DetailUnavailable 을 던진다.

    마감 공고를 조용히 넘기면 안 된다. 알바몬은 마감되면 viewData 를 통째로
    비우고 `pageProps.fetchError` 에 이유를 담아 보낸다("마감된 공고입니다").
    이걸 확인하지 않으면 근무시간·임금이 전부 빈 행을 detail_status=complete
    로 기록하게 되고, 결측인지 실제로 없는 값인지 구분할 수 없게 된다.
    """
    url = ALBAMON_DETAIL.format(pid=pid)
    props = next_data(fetch(s, url))["props"]["pageProps"]
    payload = props.get("data") or {}
    view = payload.get("viewData") or {}

    if payload.get("crawlerBlocked") or view.get("crawlingBlock"):
        return None

    if props.get("fetchError"):
        reason = props["fetchError"]
        try:
            reason = json.loads(reason).get("message") or reason
        except (json.JSONDecodeError, TypeError):
            pass
        raise DetailUnavailable(clean(reason))
    if not view:
        raise DetailUnavailable("viewData 없음")

    return pick(view, ALBAMON_VIEW_KEYS)


def build_albamon(row: dict, view: dict | None) -> dict:
    """목록 요약 + 상세 allowlist -> 한 행."""
    pid = str(row.get("recruitNo") or "")
    view = view or {}

    # 지역은 목록의 workplaceArea('부산 동구 초량1동')가 형태가 일정해 먼저 쓴다.
    # 상세의 workingAddress 는 상세주소라 읽지 않는다.
    si, gu, dong, scope = split_area(
        clean(row.get("workplaceArea")) or desc(view.get("area")))

    # 근무시간 원문 — 상세의 workTimeDetail 이 있으면 그게 가장 구체적이다
    work_time = clean(view.get("workTimeDetail")) or clean(row.get("workingTime"))
    start, end = clean(view.get("workStartTime")), clean(view.get("workEndTime"))
    if not RE_RANGE.search(work_time) and start and end:
        work_time = f"{start}~{end}"

    # `work_time_raw` 는 휴게시간·교대안내를 괄호로 달아 자기완결 문자열로 만든다.
    # build_compare.parse_daily_hours() 가 이 컬럼 안에서 '휴게시간 N분' 을 찾아
    # 근무시간에서 빼기 때문에, 떼어내면 하루 근무시간이 휴게만큼 부풀려진다.
    # 팀원 파일럿의 표기('06:00~16:00 ( 휴게시간 60분 )')와 같은 형태다.

    work_days = join_unique((
        desc(view.get("workDays")), desc(view.get("workWeek")),
        view.get("workWeekEtc"), row.get("workingWeek"),
        row.get("workingDate")), sep=" | ")

    # negotiable 해소의 핵심. "시간협의" 뒤에 실제 시각이 여기 숨어 있다.
    # workWeekEtc 는 이미 work_days 에 들어갔으므로 여기서는 뺀다.
    opt = join_unique((view.get("workTimeOpt"), view.get("workTimeOption")))

    break_min = to_float(view.get("recessMinute")) or 0

    # 파싱에는 시각만(work_time) 넘기고, 저장용 원문에만 괄호를 붙인다.
    # 괄호 안 내용을 파싱 입력에도 섞으면 시각대가 두 번 세어져 multi_shift 로
    # 잘못 분류된다.
    sched = resolve_schedule(work_time, work_days, break_min, opt)

    notes = join_unique((f"휴게시간 {int(break_min)}분" if break_min else "", opt),
                        sep=" / ")
    work_time_raw = f"{work_time} ( {notes} )" if notes else work_time

    wage_type = desc(view.get("salaryType")) or desc(row.get("payType"))
    wage_amount = to_float(view.get("salary")) or parse_won(row.get("pay"))

    body = sanitize_body(view.get("content") or "")
    company = clean(view.get("companyName")) or clean(row.get("companyName"))

    reg = clean(view.get("registDateTime")) or clean(row.get("postedDate"))
    # "0.0" 은 "임금계산기를 안 썼다"는 뜻이다. 숫자로 남기면 대조가 전부 어긋난다.
    site_daily = to_float(view.get("salaryCalculatorRealWorkTime"))

    return {
        "source": "albamon",
        "posting_id": pid,
        "source_url": ALBAMON_DETAIL.format(pid=pid),
        "title": clean(view.get("recruitTitle")) or clean(row.get("recruitTitle")),
        "region_si": si, "region_district": gu, "region_neighborhood": dong,
        "region_scope": scope,
        "wage_type": wage_type, "wage_amount": wage_amount,
        # 임금 원문을 남긴다. 파서를 고쳤을 때 재수집 없이 다시 읽을 수 있다.
        "wage_raw": join_unique((wage_type, clean(view.get("salaryDescription")),
                                 clean(row.get("pay")),
                                 clean(view.get("payEtcInfo")))),
        "work_time_raw": work_time_raw,
        "registered_raw": reg,
        "job_categories_raw": desc(view.get("part")) or desc(row.get("parts")),
        "work_period_raw": desc(view.get("workPeriod")) or clean(row.get("workingPeriod")),
        "work_days_raw": work_days,
        "employment_type_raw": desc(view.get("employmentType")),
        "deadline_raw": clean(view.get("deadlineDate")) or clean(row.get("closingDate")),
        "company_hash": short_hash(company),
        "listing_paid_flag": bool(row.get("_paid")),
        "has_contract_badge": bool(view.get("laborContractWriteStatus")),
        "foreigner_application_status": (
            "allowed" if view.get("foreignerApplyStatus") is True
            else "not_explicitly_marked" if view.get("foreignerApplyStatus") is False
            else ""),
        "source_work_week_raw": work_days,
        "source_work_time_detail_raw": clean(view.get("workTimeDetail")),
        "source_work_time_option_raw": clean(view.get("workTimeOption")),
        "source_work_time_opt_raw": clean(view.get("workTimeOpt")),
        "source_work_start_time": start,
        "source_work_end_time": end,
        "source_workday_count": to_float(view.get("salaryCalculatorWorkDay")),
        "source_daily_hours": site_daily,
        "break_minutes": break_min or None,
        "holiday_pay_flag": bool(to_float(view.get("holidaySalaryStatus"))),
        "site_min_wage": to_float(view.get("minimumWage")),
        "body_text": body["text"],
        "body_chars": body["chars"],
        "body_image_count": body["image_count"],
        "pii_redacted": body["redacted"],
        "pii_redact_types": ",".join(body["redact_types"]),
        **sched,
    }


# ---------------------------------------------------------------------------
# 알바천국
# ---------------------------------------------------------------------------

# 상세 정의목록에서 읽을 라벨. 회사주소·담당자명·연락처·홈페이지는 뺀다.
ALBA_DEF_LABELS = {
    "근무시간", "근무요일", "근무기간", "급여", "고용형태", "모집직종",
    "모집마감", "모집인원", "동정보", "학력", "기타조건", "복리후생",
}

# 급여 칸 뒤에 붙는 안내 문구. 임금형태·금액 파싱 전에 떼어내야 한다.
# '건별 5,000,000 원 ... 2026년 최저시급 10,320원 급여계산기' 에서 안내를 남기면
# 뒤쪽 '최저시급' 의 '시급' 이 임금형태로 잡혀 건당 500만원이 시급이 된다.
RE_PAY_NOTICE = re.compile(r"\d{4}\s*년\s*최저시급[^원]*원|급여\s*계산기|최저임금\s*이상")
# 급여 원문 맨 앞에 임금형태가 온다. 반드시 앞에서만 읽는다.
RE_PAY_HEAD = re.compile(r"^\s*(시급|일급|주급|월급|연봉|건별)\s*([\d,]+)")
# '회사명 채용정보 : 제목 - 알바천국'
RE_ALBA_TITLE = re.compile(r"^(.*?)\s*채용정보\s*:\s*(.*?)\s*-\s*알바천국\s*$")


def alba_list(s: requests.Session, limit: int) -> list[str]:
    """목록 페이지에서 adid 만 모은다. 상세에서 전부 다시 읽으므로 요약은 불필요."""
    seen: list[str] = []
    known: set[str] = set()
    page = 1
    while len(seen) < limit:
        html = fetch(s, ALBA_LIST.format(page=page))
        # 배너·추천 영역에도 adid 링크가 있어 전체 정규식은 부산 밖 공고를 섞는다.
        # 검색결과 표의 행에서만 뽑는다.
        soup = BeautifulSoup(html, "html.parser")
        ids = []
        for tr in soup.select("tr"):
            a = tr.select_one('a[href*="adid="]')
            if not a:
                continue
            m = re.search(r"adid=(\d+)", a["href"])
            if m:
                ids.append(m.group(1))
        fresh = [i for i in dict.fromkeys(ids) if i not in known]
        for i in fresh:
            known.add(i)
            seen.append(i)
            if len(seen) >= limit:
                break
        log(f"[alba list] {page}페이지 신규 {len(fresh)}건 (누적 {len(seen)})")
        if not fresh:
            break
        page += 1
    return seen[:limit]


def alba_detail(s: requests.Session, pid: str) -> dict:
    """상세 정의목록 + JSON-LD + 본문 iframe."""
    url = ALBA_DETAIL.format(pid=pid)
    html = fetch(s, url)
    soup = BeautifulSoup(html, "html.parser")

    defs: dict[str, str] = {}
    for item in soup.select(".detail-def__item"):
        term = clean(item.select_one(".detail-def__term"))
        if term not in ALBA_DEF_LABELS:
            continue
        defs[term] = clean(item.select_one(".detail-def__data"))

    ld: dict = {}
    for tag in soup.select('script[type="application/ld+json"]'):
        try:
            obj = json.loads(tag.string or "{}")
        except json.JSONDecodeError:
            continue
        if obj.get("@type") == "JobPosting":
            ld = obj
            break

    # JSON-LD 가 아예 없는 공고가 있다(실측 1,000건 중 65건). 그때는 <title> 에서
    # 회사명과 제목을 되살린다. 안 하면 company_hash 가 전부 빈 문자열 해시로
    # 뭉쳐 같은 회사로 오인되고 중복 판정이 무너진다.
    head_title = clean(soup.select_one("title"))
    m = RE_ALBA_TITLE.match(head_title)
    fallback = {"company": clean(m.group(1)), "title": clean(m.group(2))} if m \
        else {"company": "", "title": ""}

    # 본문은 iframe 안에 있다. ccp 토큰이 부모 페이지에만 있어 순서를 지켜야 한다.
    body_html = ""
    frame = soup.select_one("#DetailContentIframe")
    if frame and frame.get("src"):
        src = frame["src"]
        if src.startswith("/"):
            src = "https://www.alba.co.kr" + src
        try:
            inner = fetch(s, src, referer=url)
            node = BeautifulSoup(inner, "html.parser").select_one("#DetailContent")
            body_html = str(node) if node else ""
        except (requests.RequestException, RobotsViolation) as exc:
            log(f"[alba body] {pid} 실패: {exc}")

    return {"defs": defs, "ld": ld, "body_html": body_html,
            "fallback": fallback}


def build_alba(pid: str, got: dict) -> dict:
    defs, ld = got["defs"], got["ld"]
    fb = got.get("fallback") or {}

    si, gu, dong, scope = split_area(defs.get("동정보", ""))
    if not gu:
        loc = ((ld.get("jobLocation") or {}).get("address") or {})
        si, gu = clean(loc.get("addressRegion")), clean(loc.get("addressLocality"))
        scope = "district" if gu else "citywide"

    work_time = defs.get("근무시간", "")
    work_days = defs.get("근무요일", "")

    # '휴게시간 120분' 이 근무시간 칸에 붙어 온다
    m = re.search(r"휴게\s*시간?\s*(\d+)\s*분", f"{work_time} {work_days}")
    break_min = int(m.group(1)) if m else 0

    sched = resolve_schedule(work_time, work_days, break_min)

    # 임금형태는 급여 칸 맨 앞의 표기를 따른다. 사장님이 직접 고른 값이고
    # 화면에 그대로 보이는 값이다. JSON-LD unitText 는 '건별' 을 표현하지 못해
    # HOUR 로 내려보내는 일이 있어 보조로만 쓴다.
    pay_raw = clean(RE_PAY_NOTICE.sub(" ", defs.get("급여", "")))
    unit = {"HOUR": "시급", "DAY": "일급", "WEEK": "주급",
            "MONTH": "월급", "YEAR": "연봉"}
    sal = ((ld.get("baseSalary") or {}).get("value") or {})

    wage_type, wage_amount = "", None
    m = RE_PAY_HEAD.match(pay_raw)
    if m:
        wage_type, wage_amount = m.group(1), parse_won(m.group(2))
    if not wage_type:
        wage_type = unit.get(clean(sal.get("unitText")), "")
    if wage_amount is None:
        wage_amount = to_float(sal.get("value")) or parse_won(pay_raw)

    body = sanitize_body(got["body_html"])
    company = (clean((ld.get("hiringOrganization") or {}).get("name"))
               or fb.get("company", ""))
    posted = clean(ld.get("datePosted"))

    return {
        "source": "alba",
        "posting_id": pid,
        "source_url": ALBA_DETAIL.format(pid=pid),
        "title": clean(ld.get("title")) or fb.get("title", ""),
        "wage_raw": pay_raw,
        "region_si": si, "region_district": gu, "region_neighborhood": dong,
        "region_scope": scope,
        "wage_type": wage_type, "wage_amount": wage_amount,
        "work_time_raw": work_time,
        "registered_raw": posted,
        "job_categories_raw": defs.get("모집직종", ""),
        "work_period_raw": defs.get("근무기간", ""),
        "work_days_raw": work_days,
        "employment_type_raw": defs.get("고용형태", ""),
        "deadline_raw": defs.get("모집마감", "") or clean(ld.get("validThrough")),
        "company_hash": short_hash(company),
        "listing_paid_flag": "",
        "has_contract_badge": "",
        "foreigner_application_status": "",
        "source_work_week_raw": work_days,
        "source_work_time_detail_raw": work_time,
        "source_work_time_option_raw": "",
        "source_work_time_opt_raw": "",
        "source_work_start_time": sched["work_start_time"],
        "source_work_end_time": sched["work_end_time"],
        "source_workday_count": None,
        "source_daily_hours": None,
        "break_minutes": break_min or None,
        "holiday_pay_flag": "주휴수당" in defs.get("복리후생", ""),
        "site_min_wage": None,
        "body_text": body["text"],
        "body_chars": body["chars"],
        "body_image_count": body["image_count"],
        "pii_redacted": body["redacted"],
        "pii_redact_types": ",".join(body["redact_types"]),
        **sched,
    }


# ---------------------------------------------------------------------------
# 공통 후처리 — 스키마 컬럼과 중복 판정
# ---------------------------------------------------------------------------

# 팀원 파일럿 62열을 그대로 유지한다. build_compare.py 의 RENAME 맵이
# 이 이름들을 그대로 참조하므로 순서·이름을 바꾸면 안 된다.
COLUMNS = [
    "source", "posting_id", "source_url", "collected_at", "sample_method",
    "title", "region_si", "region_district", "region_neighborhood",
    "region_scope", "wage_type", "wage_amount", "work_time_raw",
    "registered_raw", "job_categories_raw", "work_period_raw", "work_days_raw",
    "employment_type_raw", "deadline_raw", "company_hash", "listing_paid_flag",
    "has_contract_badge", "detail_enriched", "pii_redacted", "record_hash",
    "detail_status", "detail_error", "foreigner_application_status",
    "source_work_week_raw", "source_work_time_detail_raw",
    "source_work_time_option_raw", "source_work_time_opt_raw",
    "source_work_start_time", "source_work_end_time", "source_workday_count",
    "source_daily_hours", "schedule_parse_status", "work_start_time",
    "work_end_time", "work_shift_count", "break_minutes",
    "workday_count_min", "workday_count_max", "daily_work_hours_min",
    "daily_work_hours_max", "weekly_work_hours_min", "weekly_work_hours_max",
    "weekly_hours_status", "weekly_hours_reliability", "title_wage_conflict",
    "duplicate_group_hash", "duplicate_group_size", "duplicate_group_rank",
    "is_offer_duplicate", "duplicate_group_version", "posting_date",
    "same_day_duplicate_hash", "same_day_duplicate_size",
    "same_day_duplicate_rank", "is_same_day_duplicate",
    "same_day_duplicate_version", "parser_version",
    # 이번 수집에서 추가한 컬럼
    "body_text", "body_chars", "body_image_count", "pii_redact_types",
    "holiday_pay_flag", "site_min_wage", "daily_hours_agreement",
    "crawl_block_flag", "wage_raw", "wage_type_suspect",
]

# 2026년 최저임금 10,320원의 10배. 이보다 큰 '시급' 은 표기가 잘못된 것이다
# (건당 500만원을 시급으로 적어 놓은 공고가 실제로 있다).
MAX_PLAUSIBLE_HOURLY = 100_000

RE_TITLE_WAGE = re.compile(r"(시급|일급|월급|주급|연봉)\s*([\d,]{3,})")


def title_wage_conflict(title: str, wage_type, wage_amount) -> bool:
    """제목에 적힌 금액이 필드값과 다른 경우. 과장 광고 탐지에 쓴다."""
    m = RE_TITLE_WAGE.search(title or "")
    if not m or wage_amount is None:
        return False
    t_amount = parse_won(m.group(2))
    if t_amount is None:
        return False
    if m.group(1) != (wage_type or ""):
        return True
    return abs(t_amount - float(wage_amount)) / max(float(wage_amount), 1) > 0.05


def to_posting_date(raw: str, collected: str) -> str:
    """'8분전' 같은 상대 표기는 수집일로 본다. 절대 표기는 그대로 쓴다."""
    t = clean(raw)
    m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", t)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return collected[:10]


def finalize(rows: list[dict], sample_method: str) -> pd.DataFrame:
    """행마다 해시·중복 판정·버전을 채우고 스키마 순서로 정렬한다."""
    now = datetime.now(KST).isoformat(timespec="seconds")

    for r in rows:
        r.setdefault("collected_at", now)
        r["sample_method"] = sample_method
        r["parser_version"] = PARSER_VERSION
        # 마감 공고는 수집 단계에서 False 로 적어 둔다. 여기서 덮으면 안 된다.
        r.setdefault("detail_enriched", True)
        r.setdefault("detail_status", "complete")
        r.setdefault("detail_error", "")
        r.setdefault("crawl_block_flag", False)
        r["posting_date"] = to_posting_date(r.get("registered_raw", ""),
                                            r["collected_at"])
        r["title_wage_conflict"] = title_wage_conflict(
            r.get("title"), r.get("wage_type"), r.get("wage_amount"))

        # 말이 안 되는 시급은 임금형태 표기 오류다. 그대로 두면 시급 500만원이
        # 평균을 통째로 끌어올린다. 금액은 남기고 형태만 비워 환산에서 뺀다.
        amt = to_float(r.get("wage_amount"))
        r["wage_type_suspect"] = bool(
            r.get("wage_type") == "시급" and amt and amt > MAX_PLAUSIBLE_HOURLY)
        if r["wage_type_suspect"]:
            r["wage_type"] = ""
        r["record_hash"] = record_hash(
            r.get("source"), r.get("posting_id"), r.get("title"),
            r.get("wage_type"), r.get("wage_amount"), r.get("work_time_raw"))

        # 사이트가 계산한 일 근무시간과 우리 파서를 맞춰 본다.
        # 알바몬의 salaryCalculatorRealWorkTime 은 휴게시간을 빼지 않은 총 체류
        # 시간이다(06:00~16:00 휴게 60분 -> 사이트 10.0, 우리 9.0). 그래서
        # 우리 값에 휴게를 되돌린 '총 시간'과 비교해야 뜻이 있는 대조가 된다.
        # 0.0 은 값이 없다는 뜻이므로 결측으로 본다.
        site = r.get("source_daily_hours") or None
        ours = r.get("daily_work_hours_min")
        if site is None or ours is None:
            r["daily_hours_agreement"] = ""
        else:
            gross = float(ours) + (float(r.get("break_minutes") or 0) / 60)
            r["daily_hours_agreement"] = (
                "agree" if abs(float(site) - gross) <= 0.5 else "differ")

        # 같은 일자리를 여러 번 올린 건을 묶는다 (제목·회사·임금·시간 동일)
        r["duplicate_group_hash"] = short_hash(
            r.get("source"), r.get("company_hash"),
            re.sub(r"[\s\W]+", "", r.get("title") or ""),
            r.get("wage_type"), r.get("wage_amount"), r.get("work_time_raw"),
            r.get("region_district"))
        r["duplicate_group_version"] = DUP_VERSION
        r["same_day_duplicate_hash"] = short_hash(
            r["duplicate_group_hash"], r["posting_date"])
        r["same_day_duplicate_version"] = SAME_DAY_VERSION

    df = pd.DataFrame(rows)

    for key, size, rank, flag in (
            ("duplicate_group_hash", "duplicate_group_size",
             "duplicate_group_rank", "is_offer_duplicate"),
            ("same_day_duplicate_hash", "same_day_duplicate_size",
             "same_day_duplicate_rank", "is_same_day_duplicate")):
        g = df.groupby(key)
        df[size] = g[key].transform("size")
        df[rank] = g.cumcount() + 1
        df[flag] = df[rank] > 1

    for c in COLUMNS:
        if c not in df.columns:
            df[c] = ""
    return df[COLUMNS]


# ---------------------------------------------------------------------------
# 수집 실행
# ---------------------------------------------------------------------------

def checkpoint_path(source: str, pid: str) -> Path:
    return RAW_DIR / source / f"{pid}.json"


def save_checkpoint(source: str, pid: str, payload: dict) -> None:
    """allowlist 통과 + 마스킹 완료된 값만 남긴다. 원본 HTML은 저장하지 않는다."""
    p = checkpoint_path(source, pid)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def load_checkpoint(source: str, pid: str) -> dict | None:
    p = checkpoint_path(source, pid)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def collect_albamon(s: requests.Session, limit: int) -> list[dict]:
    summaries = albamon_list(s, limit)
    log(f"[albamon] 목록 {len(summaries)}건 확보. 상세 수집 시작")

    rows, blocked, closed, failed = [], 0, 0, 0
    for i, row in enumerate(summaries, 1):
        pid = str(row.get("recruitNo"))
        cached = load_checkpoint("albamon", pid)
        if cached is not None:
            rows.append(cached)
            continue
        try:
            view = albamon_detail(s, pid)
        except DetailUnavailable as exc:
            # 마감 공고. 목록에서 얻은 임금·지역은 유효한 관측이므로 남기되,
            # 상세를 못 받았다는 사실을 detail_status 에 분명히 적는다.
            closed += 1
            rec = build_albamon(row, None)
            rec.update(detail_status="unavailable", detail_error=str(exc),
                       detail_enriched=False)
            save_checkpoint("albamon", pid, rec)
            rows.append(rec)
            continue
        except (requests.RequestException, RuntimeError, RobotsViolation) as exc:
            failed += 1
            rec = build_albamon(row, None)
            rec.update(detail_status="failed", detail_error=type(exc).__name__,
                       detail_enriched=False)
            rows.append(rec)
            log(f"[albamon detail {i}/{len(summaries)}] {pid} 실패: {exc}")
            continue

        if view is None:
            blocked += 1
            log(f"[albamon detail {i}/{len(summaries)}] {pid} 크롤링 차단 표기 — 건너뜀")
            continue

        rec = build_albamon(row, view)
        save_checkpoint("albamon", pid, rec)
        rows.append(rec)
        if i % 50 == 0:
            log(f"[albamon detail] {i}/{len(summaries)} 진행")

    log(f"[albamon] 수집 {len(rows)}건 / 차단 {blocked}건 / "
        f"마감(상세없음) {closed}건 / 실패 {failed}건")
    return rows


def collect_alba(s: requests.Session, limit: int) -> list[dict]:
    ids = alba_list(s, limit)
    log(f"[alba] 목록 {len(ids)}건 확보. 상세 수집 시작")

    rows, failed = [], 0
    for i, pid in enumerate(ids, 1):
        cached = load_checkpoint("alba", pid)
        if cached is not None:
            rows.append(cached)
            continue
        try:
            rec = build_alba(pid, alba_detail(s, pid))
        except (requests.RequestException, RuntimeError, RobotsViolation) as exc:
            failed += 1
            log(f"[alba detail {i}/{len(ids)}] {pid} 실패: {exc}")
            continue
        save_checkpoint("alba", pid, rec)
        rows.append(rec)
        if i % 50 == 0:
            log(f"[alba detail] {i}/{len(ids)} 진행")

    log(f"[alba] 수집 {len(rows)}건 / 실패 {failed}건")
    return rows


def run_collect(sources: list[str], limit: int, tag: str) -> None:
    s = make_session()
    stamp = datetime.now(KST).strftime("%Y%m%d")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for source in sources:
        rows = (collect_albamon(s, limit) if source == "albamon"
                else collect_alba(s, limit))
        if not rows:
            log(f"[{source}] 수집 0건 — 파일을 쓰지 않는다")
            continue
        df = finalize(rows, tag)
        path = OUT_DIR / f"{source}_busan_{stamp}.csv"
        df.to_csv(path, index=False, encoding="utf-8-sig")
        log(f"[{source}] -> {path.name}  {len(df)}행 x {df.shape[1]}열")
        report(df, source)


def report(df: pd.DataFrame, label: str) -> None:
    log(f"\n[{label}] 상세 수집 상태")
    for k, v in df["detail_status"].value_counts().items():
        log(f"   {k:16} {v:5}건  ({v / len(df):5.1%})")

    log(f"[{label}] 근무시간 파싱 상태")
    for k, v in df["schedule_parse_status"].value_counts().items():
        log(f"   {k:16} {v:5}건  ({v / len(df):5.1%})")

    # normalize 에서는 CSV를 다시 읽어 들어오므로 결측이 섞일 수 있다
    ok = pd.to_numeric(df["body_chars"], errors="coerce").fillna(0)
    img = pd.to_numeric(df["body_image_count"], errors="coerce").fillna(0)
    usable = ((ok >= 50).sum())
    log(f"[{label}] 본문 확보 {(ok > 0).sum()}건 / 진단에 쓸 만한 50자 이상 {usable}건")
    img_only = ((ok < 50) & (img > 0)).sum()
    log(f"[{label}] 이미지 전용 공고 {img_only}건 — 텍스트 진단 불가")
    log(f"[{label}] 마스킹 발생 {df['pii_redacted'].astype(str).eq('True').sum()}건")

    agree = df["daily_hours_agreement"].value_counts().to_dict()
    if agree:
        log(f"[{label}] 사이트 계산 실근로시간 대조 {agree}")

    # 같은 사업주가 동일 공고를 여러 번 올린다. 접지 않으면 그 사업주의 조건이
    # 배수로 반영돼 분포가 통째로 기울어진다.
    dup = df["is_offer_duplicate"].astype(str).eq("True")
    same = df["is_same_day_duplicate"].astype(str).eq("True")
    size = pd.to_numeric(df["duplicate_group_size"], errors="coerce").fillna(1)
    log(f"[{label}] 재게시 중복 {dup.sum()}건 ({dup.mean():.1%}) — "
        f"제거하면 {(~dup).sum()}건")
    log(f"[{label}] 같은 날 중복 {same.sum()}건 ({same.mean():.1%})")
    log(f"[{label}] 회사 수 {df['company_hash'].nunique()}개 / "
        f"공고 {len(df)}건 — 최대 중복 묶음 {int(size.max())}건")
    top = (df[size > 1].groupby("company_hash").size()
           .sort_values(ascending=False).head(3))
    for h, n in top.items():
        log(f"     회사 {h} 가 {n}건")


# ---------------------------------------------------------------------------
# normalize — 두 소스 통합 + 시급 환산
# ---------------------------------------------------------------------------

def run_normalize() -> None:
    """수집 CSV를 합쳐 분석용 테이블을 만든다.

    직종 대분류는 job_mapping.py, 시급 환산은 build_compare.py 의 규칙을
    그대로 쓴다. 같은 축으로 비교해야 공공 데이터와 붙일 수 있다.
    """
    import importlib.util

    files = sorted(OUT_DIR.glob("albamon_busan_*.csv")) + \
        sorted(OUT_DIR.glob("alba_busan_*.csv"))
    if not files:
        sys.exit("수집 CSV가 없습니다. collect 를 먼저 실행하세요.")

    frames = []
    for p in files:
        d = pd.read_csv(p, low_memory=False)
        log(f"[load] {p.name}  {len(d)}행")
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)

    before = len(df)
    df = df.drop_duplicates(subset=["source", "posting_id"], keep="first")
    log(f"[normalize] 같은 공고 재수집분 제거 {before} -> {len(df)}건")

    def load(name):
        spec = importlib.util.spec_from_file_location(name, BASE_DIR / f"{name}.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    jm = load("job_mapping")
    codes = [jm.map_one(v)[0] for v in df["job_categories_raw"].fillna("")]
    df["ksco_code"] = codes
    df["ksco_name"] = [jm.KSCO.get(c) if c else None for c in codes]
    log(f"[normalize] 직종 대분류 부여율 {pd.Series(codes).notna().mean():.1%}")

    bc = load("build_compare")
    df["work_days_raw"] = df["work_days_raw"].fillna("")
    df["sal_type"] = df["wage_type"]
    df["sal_amount"] = df["wage_amount"]
    df = bc.compute_hourly(df)

    df["below_min_wage"] = df["hourly_wage"] < MIN_WAGE_2026
    path = OUT_DIR / "commercial_analysis.csv"
    df.to_csv(path, index=False, encoding="utf-8-sig")
    log(f"\n[normalize] -> {path.name}  {len(df)}행 x {df.shape[1]}열")

    h = df[df["hourly_wage"].notna()]
    log(f"[normalize] 시급 환산 {len(h)}건 ({len(h) / len(df):.1%})")
    log(h.groupby("source")["hourly_wage"].agg(
        건수="count", 중앙="median", 평균="mean").round(0).to_string())
    log(f"[normalize] 최저임금 미만 {h['below_min_wage'].mean():.1%}")
    report(df, "통합")


# ---------------------------------------------------------------------------

def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("smoke", "collect"):
        p = sub.add_parser(name)
        p.add_argument("--source", choices=("albamon", "alba", "both"),
                       default="both")
        p.add_argument("--limit", type=int,
                       default=SMOKE_LIMIT if name == "smoke" else DEFAULT_LIMIT)
    sub.add_parser("normalize")

    args = ap.parse_args()
    try:
        if args.cmd == "normalize":
            run_normalize()
        else:
            sources = (["albamon", "alba"] if args.source == "both"
                       else [args.source])
            tag = ("smoke_pilot" if args.cmd == "smoke"
                   else "latest_listing_pages_v1")
            run_collect(sources, args.limit, tag)
    finally:
        flush_log()


if __name__ == "__main__":
    main()
