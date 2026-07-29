#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
근무시간 파싱 규칙 (재사용 모듈)

고용24 수집에서 시행착오로 확보한 규칙을 떼어낸 것이다.
알바몬·알바천국 등 민간 공고 수집에서 `schedule_parse_status = negotiable`
로 빠지는 건을 줄이는 데 그대로 쓸 수 있다.

핵심은 다섯 가지다. 하나라도 빠지면 시간당 임금 환산이 틀어진다.

  1) 종료 시각이 12시간제로 적힌다
     "09:00~06:00" 은 익일 6시가 아니라 오후 6시다. 9시간이지 21시간이 아니다.
     오전에 시작해 오전에 끝나는 근무는 없다는 사실로 구분한다.

  2) 한글 시각 표기
     "(오전) 7시 30분~(오후) 6시 00분" 을 못 읽으면 그 뒤의
     "점심시간 12:00~13:00" 을 근무시간으로 잡아 1시간이 된다.

  3) 휴게시간은 두 곳에서 오고 여러 구간으로 쪼개진다
     별도 필드에는 값만 있고("12시00분~13시00분"), 본문에는 접두어가 붙는다.
     "휴게시간 오전 10:30~10:45 오후 15:00~15:15" 는 합쳐서 30분이다.

  4) "주 52시간" 은 소정근로시간이 아니라 법정 상한 안내다
     "주52시간 준수" 를 소정근로시간으로 읽으면 안 된다.
     총 근로시간은 (근무일수 x 일일시간) 을 넘을 수 없다는 불변식으로 걸러낸다.

  5) 요일 뒤 숫자를 일일 근로시간으로 오인한다
     "매주 목요일 1시간 30분 야간근무" 에서 "일 1시간" 이 잡힌다.
     '일' 앞에 한글이 붙으면 요일이다.

사용법:
    from worktime_parser import parse_worktime
    r = parse_worktime(work_time_text, work_form_text, rest_time_text)
    r["weekly_hours"], r["daily_hours"], r["work_days"], r["source"]

    python worktime_parser.py            # 내장 테스트 11건 실행
"""

from __future__ import annotations

import re
import sys

MAX_DAILY = 16.0
MIN_DAILY = 1.0
MAX_WEEKLY = 80.0
MIN_WEEKLY = 1.0

# '주 N시간' 뒤에 이런 말이 붙으면 법정 상한 안내다
CAP_WORDS = r"^\s*(준수|초과|이내|적용|근무제|한도|미만|기준)"
# 휴게 구간 나열이 끝났음을 알리는 말
BREAK_STOP = r"매주|야간|당직|특근|연장|잔업|토요|일요|주말|격주|교대"


def normalize_korean_time(text: str) -> str:
    """'(오전) 7시 30분' -> '07:30', '(오후) 6시' -> '18:00'.
    '52시간'처럼 뒤에 '간'이 붙으면 시각이 아니므로 건드리지 않는다.
    '9:00시'처럼 HH:MM 뒤에 붙은 '시'는 떼어낸다."""
    if not text:
        return ""
    text = re.sub(r"(\d{1,2}:\d{2})\s*시(?!간)", r"\1", text)

    def rep(m: re.Match) -> str:
        ampm, h, mi = m.group(1), int(m.group(2)), int(m.group(3) or 0)
        if ampm == "오후" and h < 12:
            h += 12
        elif ampm == "오전" and h == 12:
            h = 0
        return f"{h % 24:02d}:{mi:02d}"

    return re.sub(r"\(?\s*(오전|오후)?\s*\)?\s*(\d{1,2})\s*시(?!간)\s*(\d{1,2})?\s*분?",
                  rep, text)


def strip_break_ranges(text: str) -> str:
    """'점심시간 12:00~13:00' 같은 휴게 구간을 근무시간 후보에서 뺀다."""
    return re.sub(r"(점심|휴게|휴식|식사|중식|석식)\s*시간?\s*:?\s*"
                  r"\d{1,2}:\d{2}\s*[~\-]\s*\d{1,2}:\d{2}", " ", text)


def _sum_break_minutes(seg: str) -> int:
    total = 0
    for m in re.finditer(r"(\d{1,2}):(\d{2})\s*[~\-]\s*(\d{1,2}):(\d{2})", seg):
        a = int(m.group(1)) * 60 + int(m.group(2))
        b = int(m.group(3)) * 60 + int(m.group(4))
        if 0 < b - a <= 120:          # 2시간 넘는 구간은 휴게가 아니다
            total += b - a
    return total


def _break_minutes_direct(text: str) -> int:
    """민간 사이트는 휴게를 분·시간 단위로 바로 적는다.
    '( 휴게시간 60분 )' / '휴게 1시간 30분' / '휴게 1.5시간'"""
    if not text:
        return 0
    m = re.search(r"(?:휴게|휴식|점심|중식)\s*시간?\s*"
                  r"(?:(\d+)\s*시간)?\s*(?:([\d.]+)\s*분)?", text)
    if not m or not (m.group(1) or m.group(2)):
        return 0
    mins = int(m.group(1) or 0) * 60 + int(float(m.group(2) or 0))
    return mins if 0 < mins <= 4 * 60 else 0


def parse_worktime(work_time: str = "", work_form: str = "",
                   rest_time: str = "", extra: str = "") -> dict:
    """근무시간 텍스트에서 주당·일일 근로시간을 뽑는다.

    work_time : '근무 시간' / '상세 근무시간' 필드
    work_form : '근무 형태' 필드 ('주 5일 근무' 등)
    rest_time : '휴게 시간' 필드
    extra     : 목록 페이지의 근무 요약 등 보조 텍스트
    """
    raw = " ".join(str(x or "") for x in (work_form, work_time, extra))
    raw = re.sub(r"도움말.*?닫기", " ", raw, flags=re.S)   # 툴팁 안내문 제거
    txt = normalize_korean_time(raw)

    # ── 근무일수
    days = None
    m = re.search(r"주\s*(\d)\s*일", txt)
    if m:
        days = int(m.group(1))

    # ── 주 소정근로시간 (명시값 우선, 법정 상한 안내는 배제)
    weekly, weekly_src = None, ""
    m = re.search(r"소정\s*근로\s*시간\s*:?\s*([\d.]+)\s*시간", txt)
    if m:
        weekly, weekly_src = float(m.group(1)), "소정표기"
    else:
        for m in re.finditer(r"주\s*([\d.]+)\s*시간", txt):
            if re.search(CAP_WORDS, txt[m.end():m.end() + 10]):
                continue
            weekly, weekly_src = float(m.group(1)), "주N시간"
            break

    # ── 근무 시각 -> 일일 근로시간
    start = end = interp = ""
    daily = None
    m = re.search(r"(\d{1,2}):(\d{2})\s*[~\-]\s*(\d{1,2}):(\d{2})",
                  strip_break_ranges(txt))
    if m:
        sh, sm, eh, em = (int(x) for x in m.groups())
        start = f"{sh:02d}:{sm:02d}"
        s_min, e_min = sh * 60 + sm, eh * 60 + em
        interp = "그대로"
        if e_min <= s_min:
            if sh < 12 and eh <= 11:
                e_min += 12 * 60
                interp = "12시간제(오후로 해석)"
            else:
                e_min += 24 * 60
                interp = "익일(야간근무)"
        end = f"{(e_min // 60) % 24:02d}:{e_min % 60:02d}"
        span = e_min - s_min

        rest = _sum_break_minutes(normalize_korean_time(rest_time or ""))
        if not rest:
            rest = _break_minutes_direct(rest_time) or _break_minutes_direct(txt)
        if not rest:
            bm = re.search(r"(?:점심|휴게|휴식|중식|석식)\s*시간?", txt)
            if bm:
                tail = re.split(BREAK_STOP, txt[bm.end(): bm.end() + 70])[0]
                rest = _sum_break_minutes(tail)
        if rest > 4 * 60:
            rest = 0
        daily = round((span - rest) / 60, 2)

    # ── 일일 근로시간이 명시돼 있으면 시각 범위보다 우선
    #    시각 범위는 개인 근무시간이 아니라 영업시간일 때가 있다
    time_is_shift = daily is not None
    dm = re.search(r"(?:^|[\s(,·:/])(?:1\s*)?일\s*([\d.]+)\s*시간", txt)
    if dm:
        v = float(dm.group(1))
        if MIN_DAILY <= v <= MAX_DAILY:
            if daily is not None and abs(daily - v) > 1.0:
                time_is_shift = False
            daily = v

    # ── 이상치 차단
    if daily is not None and not (MIN_DAILY <= daily <= MAX_DAILY):
        daily = None
    if weekly is not None and not (MIN_WEEKLY <= weekly <= MAX_WEEKLY):
        weekly, weekly_src = None, ""
    if days is not None and not (1 <= days <= 7):
        days = None

    # ── 불변식: 총 근로시간 <= 근무일수 x 일일시간
    #    '주 52시간 준수' 같은 안내가 새어 들어오면 여기서 걸린다
    if weekly_src == "주N시간" and days and daily and weekly and \
            weekly > days * daily + 0.5:
        weekly, weekly_src = None, ""

    if weekly is None and days and daily:
        weekly = round(days * daily, 2)
        weekly_src = "일수x일일"
        if not (MIN_WEEKLY <= weekly <= MAX_WEEKLY):
            weekly, weekly_src = None, ""
    if daily is None and days and weekly:
        daily = round(weekly / days, 2)

    negotiable = bool(re.search(r"협의|추후\s*결정|면접\s*후|스케줄|시간\s*조정", txt))
    return {
        "weekly_hours": weekly, "daily_hours": daily, "work_days": days,
        "start": start, "end": end,
        "source": weekly_src or ("협의" if negotiable else ""),
        "end_interpretation": interp,
        "time_is_personal_shift": time_is_shift,
        "negotiable_mentioned": negotiable,
    }


def hourly_from_monthly(amount: float, weekly_hours: float,
                        weekly_rest_multiplier: float = 1.2) -> float | None:
    """월급 -> 통상시급. 주휴 포함이 법정 기준이다.
    주 40시간이면 40 x 4.345 x 1.2 = 208.6시간 (관행상 209시간)."""
    if not amount or not weekly_hours:
        return None
    return round(amount / (weekly_hours * 4.345 * weekly_rest_multiplier))


TESTS = [
    # (근무시간, 근무형태, 휴게, 기대 일일, 기대 주당)
    ("09:00~06:00", "주 5일 근무", "", 9.0, 45.0),
    ("08:30~08:00", "주 5일 근무", "", 11.5, 57.5),
    ("(오전) 7시 00분~(오후) 5시 00분 점심시간: 12:00~13:00", "주 6일 근무", "", 9.0, 54.0),
    ("(평일) 9:00시~18:00시", "주 5일 근무", "", 9.0, 45.0),
    ("15:00~05:00", "", "", 14.0, None),
    ("12:00~01:00", "", "", 13.0, None),
    ("20:00~08:00", "주 5일 근무", "", 12.0, 60.0),
    ("월~금 08:30~17:30 주 52시간 초과 하지 않음", "주 5일 근무", "12:00~13:00", 8.0, 40.0),
    ("주 5일, 일 8시간 근무 (스케줄 근무, 07:00~24:00)", "", "", 8.0, 40.0),
    ("(오전) 8시 30분~(오후) 6시 00분 휴게시간 오전 10:30~10:45 오후 15:00~15:15 "
     "매주 목요일 1시간 30분 야간근무 (18:00~20:00)", "주 5일 근무", "", 9.0, 45.0),
    ("근무시간 08:00~18:00 (연장 1시간 포함) 휴게시간 12:30~13:30", "주 5일 근무",
     "12시30분~13시30분", 9.0, 45.0),
    # 민간 사이트(알바몬·알바천국) 표기
    ("08:00~16:00 ( 휴게시간 60분 )", "월~금", "", 7.0, None),
    ("18:00~21:00", "주3일 ( 수, 목, 일 )", "", 3.0, 9.0),
    ("22:00~08:00(익일)", "월~금", "", 10.0, None),
    ("시간협의 ( 오전 08:00 ~ 16:00 오후 13:00 ~ 21:00 )", "요일협의 ( 주5일 근무요일 협의 )",
     "", 8.0, 40.0),
    ("11:00~18:00 ( 휴게시간 60분 )", "주3일 ( 목, 금, 토 )", "", 6.0, 18.0),
]


def _selftest() -> int:
    bad = 0
    print(f"{'일일':>6}{'기대':>7}{'주당':>8}{'기대':>8}  원문")
    for wt, wf, rt, eh, ew in TESTS:
        r = parse_worktime(wt, wf, rt)
        ok = r["daily_hours"] == eh and r["weekly_hours"] == ew
        bad += 0 if ok else 1
        print(f"{str(r['daily_hours']):>6}{str(eh):>7}"
              f"{str(r['weekly_hours']):>8}{str(ew):>8}  {wt[:52]}"
              + ("" if ok else "   <-- 불일치"))
    print(f"\n불일치 {bad}건 / {len(TESTS)}건")
    return bad


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(1 if _selftest() else 0)
