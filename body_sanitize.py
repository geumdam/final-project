#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
공고 본문 정제 + 개인정보 마스킹 (재사용 모듈)

민간 사이트(알바몬·알바천국) 본문은 사장님이 위지윅 편집기로 쓴 HTML 덩어리다.
알바몬 1건이 21KB인데 대부분 인라인 스타일·템플릿 마크업이고, 실제 내용은
이미지로 박혀 있는 경우가 흔하다. 그래서 두 가지를 한꺼번에 한다.

  1) 평문화 — 태그·스타일·스크립트를 걷어내고 읽을 수 있는 텍스트만 남긴다
  2) 마스킹 — 담당자 연락처가 본문에 그대로 적혀 있다. 저장 전에 지운다

왜 마스킹이 필수인가
  본문에는 "문의 010-1234-5678 김대리" 같은 줄이 흔하다. 공고 텍스트를
  LLM 진단·대화 컨텍스트로 넘기는 순간 개인정보가 같이 흘러간다.
  팀원 수집 스크립트가 자유서술 본문을 아예 저장하지 않기로 한 이유가 이것이고,
  본문을 저장하기로 방향을 바꾼 만큼 마스킹은 타협 대상이 아니다.

이미지는 개수만 센다
  URL을 저장하지 않는다. `image_count > 0` 인데 `chars` 가 거의 없으면
  "내용이 이미지뿐인 공고"다. 진단에 쓸 수 없으므로 품질 플래그로 걸러낸다.

주의 — 마스킹이 먹어서는 안 되는 것
  근무시간 "18:00~21:00", 금액 "3,000,000원", 등록일 "2026-07-29" 는
  전화번호와 자리수 모양이 겹칠 수 있다. 내장 테스트로 고정해 둔다.

사용법
    from body_sanitize import sanitize_body
    r = sanitize_body(html)
    r["text"], r["chars"], r["image_count"], r["redacted"], r["redact_types"]

    python body_sanitize.py            # 내장 테스트 실행
"""

from __future__ import annotations

import html as html_mod
import re
import sys

from bs4 import BeautifulSoup, Comment

# 본문에서 통째로 걷어낼 요소. iframe/noscript 안의 텍스트는 본문이 아니다.
DROP_TAGS = ("script", "style", "noscript", "iframe", "svg", "template")

# 알바천국 본문에 흰 글씨로 숨겨 넣는 사이트 표기. 내용이 아니다.
NOISE_LINES = (
    "이공고는 알/바/천/국 사이트에서 등록한 구인공고입니다",
    "알바천국에서 제공하는 채용 상세모집내용 입니다",
)

MASK_PHONE = "[전화번호]"
MASK_EMAIL = "[이메일]"
MASK_MSGR = "[메신저ID]"
MASK_ADDR = "[주소]"
MASK_BIZNO = "[사업자번호]"


# ---------------------------------------------------------------------------
# 마스킹 규칙
#
# 순서가 중요하다. 이메일을 먼저 지워야 남은 '@xxx' 를 SNS 핸들로 볼 수 있고,
# 사업자번호(3-2-5)를 먼저 지워야 전화번호(3-4-4) 규칙이 잘못 물지 않는다.
# ---------------------------------------------------------------------------

# 구분자는 하이픈·점·공백을 모두 허용한다. '010.1234.5678' 로 우회하는 공고가 있다.
_SEP = r"[-.\s]?"

RULES: list[tuple[str, re.Pattern, str]] = [
    ("email", re.compile(
        r"[A-Za-z0-9._%+-]+\s*(?:@|＠|\[at\]|\(at\))\s*"
        r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), MASK_EMAIL),

    # 오픈채팅·SNS URL. 실제 공고에 "인스타 >> https://instagram.com/..." 로
    # 적혀 있어 키워드 규칙이 못 잡는다. 이것도 연락 채널이므로 지운다.
    # 회사 홈페이지·블로그는 남긴다(사업체 공개정보).
    ("messenger", re.compile(
        r"(?:https?://)?(?:www\.)?"
        r"(?:open\.kakao\.com|pf\.kakao\.com|kakao\.com/o|t\.me|wa\.me|"
        r"line\.me|instagram\.com|facebook\.com|band\.us)"
        r"/[A-Za-z0-9._~/?#\[\]@!$&'()*+,;=%-]*"), MASK_MSGR),

    ("bizno", re.compile(
        r"(?<!\d)\d{3}-\d{2}-\d{5}(?!\d)"), MASK_BIZNO),

    # 휴대폰 — 하이픈 있는 형태와 11자리 연속 형태를 함께 잡는다
    ("phone", re.compile(
        rf"(?<!\d)01[016-9]{_SEP}\d{{3,4}}{_SEP}\d{{4}}(?!\d)"), MASK_PHONE),

    # 안심번호(050x)·대표번호(15xx/16xx/18xx)
    ("phone", re.compile(
        rf"(?<!\d)050\d{_SEP}\d{{3,4}}{_SEP}\d{{4}}(?!\d)"), MASK_PHONE),
    ("phone", re.compile(
        rf"(?<!\d)1[568]\d{{2}}{_SEP}\d{{4}}(?!\d)"), MASK_PHONE),

    # '051)123-4567' — 국번을 괄호로 닫는 표기가 흔하다
    ("phone", re.compile(
        r"(?<!\d)0\d{1,2}\)\s*\d{3,4}[-.\s]?\d{4}(?!\d)"), MASK_PHONE),

    # 유선 — 02는 국번 3~4자리, 그 밖의 지역번호는 3자리
    ("phone", re.compile(
        rf"(?<!\d)02{_SEP}\d{{3,4}}{_SEP}\d{{4}}(?!\d)"), MASK_PHONE),
    ("phone", re.compile(
        r"(?<!\d)0(?:3[1-3]|4[1-4]|5[1-5]|6[1-4])[-.]\d{3,4}[-.]\d{4}(?!\d)"),
     MASK_PHONE),

    # 한글로 우회한 휴대폰. '공일공-1234-5678'
    ("phone", re.compile(
        r"(?:공일공|영일영)\s*[-.\s]?\s*[\d공일이삼사오육칠팔구영]{3,4}"
        r"\s*[-.\s]?\s*[\d공일이삼사오육칠팔구영]{4}"), MASK_PHONE),

    # 메신저 아이디 — 키워드 뒤에 오는 영문/숫자 아이디만 지운다.
    # '카톡 문의주세요' 처럼 한글이 오면 아이디가 아니므로 걸리지 않는다.
    ("messenger", re.compile(
        r"(카카오톡|카톡|카카오|오픈채팅|오픈카톡|라인|텔레그램|인스타그램|인스타|"
        r"위챗|왓츠앱)\s*(?:아이디|ID|id|Id)?\s*[:：]?\s*"
        r"(?=[A-Za-z0-9])[A-Za-z0-9._-]{3,30}"), r"\1 " + MASK_MSGR),

    # 이메일을 지운 뒤 남은 '@핸들' 은 SNS 아이디로 본다
    ("messenger", re.compile(
        r"(?<![A-Za-z0-9._%+-])@[A-Za-z0-9._]{3,30}"), MASK_MSGR),
]

# 상세주소. 동·구 이름은 남기고 번지·건물번호만 지운다.
# 근무 지역은 분석에 필요하고, 집어낼 대상은 '어느 건물인지'다.
_UNIT = r"(?!\s*(?:km|KM|m|분|시간|명|원|개|년|주|일|층|회|kg|cm))"
ADDR_RULES: list[tuple[re.Pattern, str]] = [
    # '테헤란로 152', '중앙대로 1234-5' -> '테헤란로 [주소]'
    (re.compile(rf"([가-힣A-Za-z0-9]{{2,10}}(?:대로|로|길))\s+\d+(?:-\d+)?{_UNIT}"),
     r"\1 " + MASK_ADDR),
    # '우동 1234-5번지' -> '우동 [주소]'
    # 하이픈으로 이어진 지번이나 '번지' 표기만 잡는다. '이동 3', '활동 2' 처럼
    # 동으로 끝나는 흔한 낱말 뒤의 맨숫자까지 물면 근무조건을 먹는다.
    (re.compile(r"([가-힣]{1,6}동)\s+(?:\d+-\d+\s*번?지?|\d+\s*번지)"),
     r"\1 " + MASK_ADDR),
    # '101동 502호'
    (re.compile(r"\d+\s*동\s*\d+\s*호"), MASK_ADDR),
]


def _to_text(html: str) -> tuple[str, int]:
    """HTML -> 평문. 이미지 개수를 함께 돌려준다."""
    soup = BeautifulSoup(html or "", "html.parser")

    image_count = len(soup.find_all("img"))
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    for tag in soup.find_all(DROP_TAGS):
        tag.decompose()

    text = soup.get_text("\n")
    text = html_mod.unescape(text)
    # &nbsp; 는 공백으로. 폭 0 문자·이형 공백도 정리한다.
    text = text.replace("\xa0", " ").replace("​", "")
    return text, image_count


def _tidy(text: str) -> str:
    """줄 단위로 공백을 정리하고 빈 줄과 노이즈를 접는다."""
    lines = []
    for raw in text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw).strip()
        if not line:
            continue
        if any(n in line for n in NOISE_LINES):
            continue
        # 같은 줄이 연달아 반복되면 템플릿 잔여물이다
        if lines and lines[-1] == line:
            continue
        lines.append(line)
    return "\n".join(lines)


def redact(text: str) -> tuple[str, list[str]]:
    """개인정보를 마스킹하고 어떤 종류가 걸렸는지 돌려준다."""
    hit: list[str] = []

    for kind, pattern, repl in RULES:
        text, n = pattern.subn(repl, text)
        if n and kind not in hit:
            hit.append(kind)

    for pattern, repl in ADDR_RULES:
        text, n = pattern.subn(repl, text)
        if n and "address" not in hit:
            hit.append("address")

    return text, hit


def sanitize_body(html: str) -> dict:
    """공고 본문 HTML -> 저장 가능한 평문.

    반환
      text         마스킹까지 끝난 평문
      chars        text 길이
      image_count  본문에 들어 있던 이미지 개수 (URL은 저장하지 않는다)
      redacted     마스킹이 한 건이라도 일어났는가
      redact_types 걸린 종류 목록 (email/phone/messenger/address/bizno)
    """
    text, image_count = _to_text(html)
    text = _tidy(text)
    text, hit = redact(text)
    text = _tidy(text)          # 마스킹으로 빈 줄이 생길 수 있다

    return {
        "text": text,
        "chars": len(text),
        "image_count": image_count,
        "redacted": bool(hit),
        "redact_types": hit,
    }


# ---------------------------------------------------------------------------
# 내장 테스트
#
# (입력 HTML, 남아 있어야 하는 문자열들, 사라져야 하는 문자열들)
# ---------------------------------------------------------------------------

TESTS: list[tuple[str, list[str], list[str]]] = [
    # 지워야 하는 것
    ("<p>문의 010-1234-5678 로 연락주세요</p>",
     [MASK_PHONE], ["010-1234-5678"]),
    ("<p>연락처 010.9876.5432</p>",
     [MASK_PHONE], ["010.9876.5432", "9876"]),
    ("<p>지원 01012345678</p>",
     [MASK_PHONE], ["01012345678"]),
    ("<p>대표 051-123-4567 문의</p>",
     [MASK_PHONE], ["051-123-4567"]),
    ("<p>안심번호 0504-1234-5678</p>",
     [MASK_PHONE], ["0504-1234-5678"]),
    ("<p>고객센터 1588-1234</p>",
     [MASK_PHONE], ["1588-1234"]),
    ("<p>공일공-1234-5678 로 문의</p>",
     [MASK_PHONE], ["공일공-1234-5678"]),
    ("<p>이력서는 hong@example.co.kr 로</p>",
     [MASK_EMAIL], ["hong@example.co.kr", "example"]),
    ("<p>카톡 abc_123 으로 주세요</p>",
     [MASK_MSGR], ["abc_123"]),
    ("<p>인스타 @cafe.busan 보세요</p>",
     [MASK_MSGR], ["cafe.busan"]),
    # 실제 공고에서 나온 형태 — 키워드와 URL 사이에 기호가 끼어 있다
    ("<p>분위기가 궁금하시면 인스타 &gt;&gt; "
     "https://www.instagram.com/culcom_haeundae/</p>",
     [MASK_MSGR], ["culcom_haeundae", "instagram.com"]),
    ("<p>오픈채팅 https://open.kakao.com/o/gAbCdEf 로 오세요</p>",
     [MASK_MSGR], ["gAbCdEf", "open.kakao.com"]),
    ("<p>문의 051)123-4567</p>",
     [MASK_PHONE], ["051)123-4567"]),
    # 회사 홈페이지는 사업체 공개정보라 남긴다
    ("<p>회사 소개 https://culcom.co.kr 참고</p>",
     ["culcom.co.kr"], [MASK_MSGR]),
    ("<p>사업자등록번호 123-45-67890</p>",
     [MASK_BIZNO], ["123-45-67890"]),
    ("<p>부산 해운대구 센텀중앙로 79 3층</p>",
     [MASK_ADDR, "해운대구", "센텀중앙로"], ["센텀중앙로 79"]),
    ("<p>우동 1234-5번지</p>",
     [MASK_ADDR, "우동"], ["1234-5"]),

    # 남겨야 하는 것 — 마스킹이 근무조건을 먹으면 안 된다
    ("<p>근무시간 18:00~21:00 (휴게시간 60분)</p>",
     ["18:00~21:00", "60분"], [MASK_PHONE, MASK_ADDR]),
    ("<p>급여 월급 3,000,000원 / 시급 10,320원</p>",
     ["3,000,000원", "10,320원"], [MASK_PHONE]),
    ("<p>등록일 2026-07-29 마감 2026-08-15</p>",
     ["2026-07-29", "2026-08-15"], [MASK_PHONE, MASK_BIZNO]),
    ("<p>주 5일 근무 / 1일 8시간</p>",
     ["주 5일", "1일 8시간"], [MASK_ADDR]),
    ("<p>지하철 2호선 서면역 도보 5분</p>",
     ["서면역", "도보 5분"], [MASK_ADDR]),
    ("<p>카톡으로 문의주세요</p>",
     ["카톡"], [MASK_MSGR]),
    ("<p>배달로 3km 이내</p>",
     ["3km"], [MASK_ADDR]),

    # 평문화
    ("<div><style>.a{color:red}</style><script>var x=1</script>"
     "<p>주방보조 모집</p><!-- 주석 --></div>",
     ["주방보조 모집"], ["color:red", "var x=1", "주석"]),
    ("<p>홀서빙&nbsp;모집&nbsp;&amp;&nbsp;급구</p>",
     ["홀서빙 모집 & 급구"], ["&nbsp;", "&amp;"]),
]


def _selftest() -> int:
    bad = 0
    for i, (src, want, unwant) in enumerate(TESTS, 1):
        r = sanitize_body(src)
        text = r["text"]
        miss = [w for w in want if w not in text]
        leak = [u for u in unwant if u in text]
        if miss or leak:
            bad += 1
            print(f"[{i:2}] 불일치")
            print(f"     결과   {text!r}")
            if miss:
                print(f"     없음   {miss}")
            if leak:
                print(f"     잔여   {leak}")
        else:
            print(f"[{i:2}] ok   {text[:58]}")

    # 이미지 개수
    r = sanitize_body('<div><img src="a.jpg"><img src="b.jpg">내용</div>')
    if r["image_count"] != 2:
        bad += 1
        print(f"[img] 이미지 개수 {r['image_count']} != 2")
    else:
        print("[img] ok   이미지 2개 인식")

    # 이미지뿐인 공고 — 진단에 쓸 수 없음을 식별할 수 있어야 한다
    r = sanitize_body('<div>&nbsp;<img src="a.jpg">&nbsp;<img src="b.jpg"></div>')
    if not (r["image_count"] == 2 and r["chars"] < 10):
        bad += 1
        print(f"[img] 이미지 전용 공고 식별 실패 chars={r['chars']}")
    else:
        print("[img] ok   이미지 전용 공고 식별")

    print(f"\n불일치 {bad}건 / {len(TESTS) + 2}건")
    return bad


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(1 if _selftest() else 0)
