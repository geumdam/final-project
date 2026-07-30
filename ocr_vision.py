#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""공고 이미지에서 글자를 읽는다 (OpenAI 비전).

왜 필요한가
-----------
알바 공고의 36%는 상세요강을 **통째로 이미지**로 올린다
(알바몬 45% · 알바천국 27%, 실측 1,980건 기준). 그러면 본문 텍스트가 0자다.

사이트 입력칸(급여·근무시간·복리후생)으로 상당 부분을 메울 수 있지만,
**이미지 안에만 있는 내용은 그것으로 대신할 수 없다.** 실측 예:

    구조화 필드    월급 3,200,000원
    이미지 안      기본급 2,456,880원 / 정착지원금 총 380만원 /
                  인센티브 최대 100만원 / 평균급여 260만~290만원 /
                  13개월차부터 2,201,880원

기본급이 245만원인데 구조화 필드는 320만원이다. 정착지원금이 섞인 금액이므로
`임금구성_불명확` 에 해당하는데, 이미지를 읽지 못하면 잡아낼 수 없다.
이 모듈이 그 구멍을 메운다.

설계 결정
---------
1. **이미지를 우리가 받아서 base64 로 넘긴다.** URL 을 그대로 주면 OpenAI 가
   대신 받아 가는데, 고용주 자체 서버(예: meta-m.co.kr)가 낯선 요청을 막으면
   조용히 실패한다. 우리가 받으면 실패를 우리가 알 수 있다.
2. **표를 마크다운 표로 받는다.** 이미지의 알맹이는 대개 급여 표다
   (근속개월별 기본급·인센티브). 줄글로 받으면 어느 숫자가 어느 항목인지
   사라진다.
3. **요약하지 말고 옮겨 적게 한다.** 이 글은 진단의 근거가 되므로,
   모델이 정리해 버리면 '공고에 적힌 것' 이 아니게 된다.
4. **결과를 캐시한다.** 같은 공고를 다시 열 때 다시 청구되면 안 된다.

비용
----
이미지 1장당 비전 입력 토큰이 붙는다. 그래서 자동으로 돌리지 않고
호출부(앱)가 필요할 때만 부른다. MAX_IMAGES 로 장수를 묶는다.

    python ocr_vision.py --url "https://www.albamon.com/jobs/detail/118166594"
"""
from __future__ import annotations

import argparse
import base64
import sys
from urllib.parse import urljoin

MAX_IMAGES = 4          # 이 이상은 읽지 않는다 (비용 상한)
MIN_BYTES = 3_000       # 이보다 작으면 아이콘·여백용 이미지로 본다
MAX_BYTES = 8_000_000   # 이보다 크면 건너뛴다 (요청 실패 방지)
TIMEOUT = 25
RETRY = 2               # 이미지 서버가 느릴 때가 있어 한 번 더 시도한다

# 공고 이미지는 고용주 자체 서버나 대행사 서버에 올라간다(post.ksjob.co.kr 등).
# 그 서버들이 짧은 User-Agent 를 봇으로 보고 막는다 — 실측:
#
#   'Mozilla/5.0'  ->  403  (44 bytes)
#   아래 전체 UA    ->  200  (34,644 bytes)
#
# 그래서 브라우저와 같은 형태의 UA 를 쓴다. 우회가 아니라, 사람이 공고 화면을
# 볼 때 브라우저가 보내는 것과 같은 값이다.
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
ACCEPT_IMG = "image/avif,image/webp,image/apng,image/gif,image/*,*/*;q=0.8"

# gif 는 OpenAI 비전이 받는다. svg 는 받지 않으므로 뺀다.
OK_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp")
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".gif": "image/gif", ".webp": "image/webp"}

OCR_SYSTEM = """\
당신은 한국 채용공고 이미지를 글자로 옮겨 적는 사람이다.

# 하는 일

이미지에 보이는 **모든 글자를 그대로 옮겨 적는다.** 한국어로 적는다.

# 규칙

1. **요약하지 않는다.** 보이는 것을 다 적는다. 이 글이 근로조건 진단의 근거가
   되므로, 정리하거나 줄이면 '공고에 적힌 것' 이 아니게 된다.

2. **표는 마크다운 표로 적는다.** 급여 표(근속개월별 기본급·수당·평균급여)가
   이미지의 알맹이인 경우가 많다. 줄글로 풀면 어느 숫자가 어느 항목인지 사라진다.

3. **숫자는 보이는 그대로 적는다.** 2,456,880원 을 '약 246만원' 으로 바꾸지
   않는다. 단위(원·만원·%)도 그대로 둔다.

4. **읽을 수 없는 글자는 추측하지 않는다.** 흐릿하거나 잘렸으면 `[?]` 로 적는다.
   특히 금액과 시각은 절대 추측하지 않는다. 틀린 숫자는 없는 것보다 나쁘다.

5. **없는 내용을 넣지 않는다.** 이미지에 4대보험 얘기가 없으면 적지 않는다.
   업종을 보고 짐작해 채우지 않는다.

6. 장식용 문구·이벤트 배너·전화번호·담당자 이름은 적지 않는다.
   근로조건과 무관하고, 연락처는 개인정보다.

# 출력

옮겨 적은 글만 출력한다. "이미지에는 다음 내용이 있습니다" 같은 머리말을 붙이지 않는다.
글자가 전혀 없는 이미지(사진·로고뿐)면 정확히 `(글자 없음)` 이라고만 출력한다.
"""


def extract_image_urls(html: str, base_url: str = "") -> list[str]:
    """공고 HTML 에서 <img src> 를 모은다.

    알바몬은 viewData['content'] 에, 알바천국은 본문 iframe 안에 이미지가 있다.
    상대경로는 base_url 로 절대경로로 만든다.
    """
    if not html:
        return []
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        return []
    out: list[str] = []
    for tag in BeautifulSoup(html, "html.parser").select("img"):
        src = (tag.get("src") or tag.get("data-src") or "").strip()
        if not src or src.startswith("data:"):
            continue
        if base_url:
            src = urljoin(base_url, src)
        if not src.startswith(("http://", "https://")):
            continue
        low = src.split("?")[0].lower()
        if not low.endswith(OK_EXT):
            continue
        if src not in out:
            out.append(src)
    return out


def fetch_images(urls, referer: str = "") -> tuple[list[tuple[str, bytes]], list[str]]:
    """이미지를 받아 (mime, bytes) 로 돌려준다. 실패는 메모로 남긴다."""
    import requests

    got: list[tuple[str, bytes]] = []
    notes: list[str] = []
    h = {"User-Agent": UA, "Accept": ACCEPT_IMG,
         "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8"}
    if referer:
        h["Referer"] = referer
    for u in urls[:MAX_IMAGES]:
        last = ""
        for attempt in range(RETRY):
            try:
                r = requests.get(u, timeout=TIMEOUT, headers=h)
                if r.status_code != 200:
                    last = f"HTTP {r.status_code}"
                    continue
                n = len(r.content)
                if n < MIN_BYTES:
                    last = f"{n}B — 아이콘으로 보여 건너뜀"
                    break                      # 크기 문제는 재시도해도 같다
                if n > MAX_BYTES:
                    last = f"{n / 1e6:.1f}MB — 너무 커서 건너뜀"
                    break
                ext = "." + u.split("?")[0].rsplit(".", 1)[-1].lower()
                got.append((MIME.get(ext, "image/png"), r.content))
                last = ""
                break
            except Exception as e:
                last = type(e).__name__     # 느린 서버가 있어 한 번 더 시도한다
        if last:
            notes.append(f"{u[-40:]} {last}")
    if len(urls) > MAX_IMAGES:
        notes.append(f"이미지 {len(urls)}장 중 앞 {MAX_IMAGES}장만 읽었습니다")
    return got, notes


def ocr(client, images, model: str) -> tuple[str, str]:
    """이미지들을 한 번의 호출로 읽는다. (텍스트, 오류) 를 돌려준다.

    한 번에 넣는 이유 — 급여 표가 두 장에 걸쳐 있으면 따로 읽으면 이어지지 않는다.
    """
    if not images:
        return "", "읽을 이미지가 없습니다"
    parts: list[dict] = [{
        "type": "text",
        "text": f"채용공고 이미지 {len(images)}장입니다. 순서대로 글자를 옮겨 적어 주세요.",
    }]
    for mime, blob in images:
        b64 = base64.b64encode(blob).decode("ascii")
        parts.append({"type": "image_url",
                      "image_url": {"url": f"data:{mime};base64,{b64}"}})

    kw = {
        "messages": [{"role": "system", "content": OCR_SYSTEM},
                     {"role": "user", "content": parts}],
        "max_completion_tokens": 4000,
        # 옮겨 적는 일이므로 추론을 길게 돌릴 필요가 없다.
        "reasoning_effort": "low",
    }
    for _ in range(2):
        try:
            r = client.chat.completions.create(model=model, **kw)
            text = (r.choices[0].message.content or "").strip()
            if text == "(글자 없음)":
                return "", ""
            return text, ""
        except Exception as e:
            msg = str(e)
            # 모델이 안 받는 파라미터면 빼고 한 번 더. 새 모델로 갈아탈 때
            # 파라미터 하나로 전부 실패하는 것을 막는다.
            dropped = False
            for k in ("reasoning_effort", "max_completion_tokens"):
                if k in msg and k in kw:
                    kw.pop(k)
                    dropped = True
                    break
            if not dropped:
                return "", f"{type(e).__name__}: {msg[:200]}"
    return "", "재시도 후에도 실패했습니다"


def ocr_posting(client, html: str, base_url: str, model: str) -> dict:
    """공고 HTML -> 이미지 글자. 앱이 부르는 진입점.

    돌려주는 것: {'text', 'n_images', 'n_read', 'notes', 'error'}
    """
    urls = extract_image_urls(html, base_url)
    if not urls:
        return {"text": "", "n_images": 0, "n_read": 0,
                "notes": [], "error": "이미지가 없습니다"}
    images, notes = fetch_images(urls, referer=base_url)
    if not images:
        return {"text": "", "n_images": len(urls), "n_read": 0,
                "notes": notes, "error": "이미지를 받지 못했습니다"}
    text, err = ocr(client, images, model)
    return {"text": text, "n_images": len(urls), "n_read": len(images),
            "notes": notes, "error": err}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="알바몬·알바천국 공고 링크")
    ap.add_argument("--model", default="")
    ap.add_argument("--dry", action="store_true",
                    help="API 를 부르지 않고 이미지 목록만 확인")
    a = ap.parse_args()

    import collect_commercial as C
    import crawler_interface as CI

    m = CI.RE_ALBAMON_PID.search(a.url)
    s = C.make_session()
    if m:
        v = (C.next_data(C.fetch(s, C.ALBAMON_DETAIL.format(pid=m.group(1))))
             ["props"]["pageProps"]["data"]["viewData"])
        html = v.get("content") or ""
    else:
        m2 = CI.RE_ALBA_PID.search(a.url)
        if not m2:
            print("공고 상세 링크가 아닙니다")
            return 1
        html = C.alba_detail(s, m2.group(1)).get("body_html") or ""

    urls = extract_image_urls(html, a.url)
    print(f"이미지 {len(urls)}장")
    for u in urls:
        print("  ", u)
    if a.dry or not urls:
        return 0

    imgs, notes = fetch_images(urls, referer=a.url)
    print(f"받은 이미지 {len(imgs)}장  " + (" / ".join(notes) if notes else ""))
    if not imgs:
        return 1

    import llm_diagnose as L
    model = a.model or L.MODEL_DETECT
    print(f"모델 {model} 로 읽습니다…")
    text, err = ocr(L.client(), imgs, model)
    if err:
        print("실패:", err)
        return 1
    print(f"\n읽은 글자 {len(text)}자\n{'=' * 60}\n{text}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
