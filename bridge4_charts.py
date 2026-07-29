#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
진단 결과 시각화

숫자만 보여주면 "이 예측을 믿어도 되나" 가 남는다. 두 가지를 그린다.

  1. 임금 위치 막대 — 예측 80% 구간 안에서 이 공고의 임금이 어디에 있는지,
     최저임금선은 어디인지. 판정(적정/낮음/높음)의 근거를 한눈에 보여준다.
  2. 유사 공고 분포 — 같은 직종·지역의 실제 수집 공고 시급 히스토그램.
     예측이 어떤 표본에서 나왔는지 보여준다. 표본 수가 적으면 그것도 드러난다.

Altair 를 쓴다. Streamlit 의 필수 의존성이라 추가 설치가 없다.
차트 안 문구도 언어별로 바꾼다 — 축 이름이 한국어면 소용이 없다.
"""

from __future__ import annotations

import altair as alt
import pandas as pd

MONTHLY_HOURS = 209

# 차트 문구
TXT: dict[str, dict[str, str]] = {
    "ko": {"pos": "이 공고의 임금 위치", "hourly": "시급(원)", "band": "예측 적정 구간(80%)",
           "posted": "이 공고", "mw": "2026 최저임금", "mid": "예측 중앙",
           "dist": "같은 조건 공고의 시급 분포", "count": "공고 수",
           "n": "표본 {n}건", "few": "표본이 {n}건뿐이라 분포를 참고로만 보세요",
           "nodata": "같은 조건의 수집 공고가 없어 분포를 그릴 수 없습니다"},
    "en": {"pos": "Where this posting's pay sits", "hourly": "Hourly (KRW)",
           "band": "Predicted fair range (80%)", "posted": "This posting",
           "mw": "2026 minimum wage", "mid": "Predicted median",
           "dist": "Hourly pay of similar postings", "count": "Postings",
           "n": "{n} postings", "few": "Only {n} postings — treat the distribution as a hint",
           "nodata": "No similar postings collected, so no distribution to show"},
    "zh": {"pos": "本公告工资所处位置", "hourly": "时薪（韩元）",
           "band": "预测合理区间（80%）", "posted": "本公告",
           "mw": "2026年最低工资", "mid": "预测中位",
           "dist": "同条件公告的时薪分布", "count": "公告数",
           "n": "样本 {n} 条", "few": "样本仅 {n} 条，分布仅供参考",
           "nodata": "没有同条件的已收集公告，无法绘制分布"},
    "vi": {"pos": "Vị trí mức lương của tin này", "hourly": "Lương giờ (won)",
           "band": "Khoảng hợp lý dự đoán (80%)", "posted": "Tin này",
           "mw": "Lương tối thiểu 2026", "mid": "Trung vị dự đoán",
           "dist": "Phân bố lương giờ của các tin tương tự", "count": "Số tin",
           "n": "{n} tin", "few": "Chỉ có {n} tin — hãy xem phân bố như tham khảo",
           "nodata": "Không có tin tương tự nên không vẽ được phân bố"},
    "ja": {"pos": "この求人の賃金の位置", "hourly": "時給（ウォン）",
           "band": "予測適正範囲（80%）", "posted": "この求人",
           "mw": "2026年最低賃金", "mid": "予測中央",
           "dist": "同条件求人の時給分布", "count": "求人数",
           "n": "サンプル {n} 件", "few": "サンプルが {n} 件のみ。分布は参考程度に",
           "nodata": "同条件の求人がなく分布を描けません"},
    "es": {"pos": "Dónde queda el salario de esta oferta", "hourly": "Por hora (wones)",
           "band": "Rango justo previsto (80%)", "posted": "Esta oferta",
           "mw": "Salario mínimo 2026", "mid": "Mediana prevista",
           "dist": "Salario por hora de ofertas similares", "count": "Ofertas",
           "n": "{n} ofertas", "few": "Solo {n} ofertas — toma la distribución como orientación",
           "nodata": "No hay ofertas similares recopiladas para mostrar la distribución"},
}


def t(lang: str, k: str) -> str:
    return TXT.get(lang, TXT["ko"]).get(k, TXT["ko"].get(k, k))


def position_chart(lo: float, mid: float, hi: float, posted: float | None,
                   mw: int, lang: str = "ko") -> alt.LayerChart:
    """예측 구간 위에 이 공고의 임금과 최저임금선을 얹는다."""
    lo_, hi_ = float(lo), float(hi)
    xs = [lo_, hi_, float(mw)] + ([float(posted)] if posted else [])
    pad = max((max(xs) - min(xs)) * 0.12, 500)
    dom = [min(xs) - pad, max(xs) + pad]

    band = alt.Chart(pd.DataFrame([{"lo": lo_, "hi": hi_}])).mark_bar(
        height=34, opacity=0.28, color="#2c3f88", cornerRadius=4
    ).encode(
        x=alt.X("lo:Q", title=t(lang, "hourly"),
                scale=alt.Scale(domain=dom, nice=False),
                axis=alt.Axis(format=",.0f")),
        x2="hi:Q",
        tooltip=[alt.Tooltip("lo:Q", title=t(lang, "band"), format=",.0f"),
                 alt.Tooltip("hi:Q", title=" ", format=",.0f")])

    midline = alt.Chart(pd.DataFrame([{"v": float(mid)}])).mark_rule(
        color="#2c3f88", strokeWidth=2
    ).encode(x="v:Q", tooltip=[alt.Tooltip("v:Q", title=t(lang, "mid"), format=",.0f")])

    mwline = alt.Chart(pd.DataFrame([{"v": float(mw)}])).mark_rule(
        color="#b03030", strokeWidth=2, strokeDash=[5, 3]
    ).encode(x="v:Q", tooltip=[alt.Tooltip("v:Q", title=t(lang, "mw"), format=",.0f")])
    mwtext = alt.Chart(pd.DataFrame([{"v": float(mw), "l": t(lang, "mw")}])).mark_text(
        align="left", dx=4, dy=-22, fontSize=11, color="#b03030"
    ).encode(x="v:Q", text="l:N")

    layers = [band, midline, mwline, mwtext]

    if posted:
        p = float(posted)
        layers.append(alt.Chart(pd.DataFrame([{"v": p}])).mark_point(
            size=190, shape="triangle-down", filled=True, color="#c46a00"
        ).encode(x="v:Q",
                 tooltip=[alt.Tooltip("v:Q", title=t(lang, "posted"), format=",.0f")]))
        layers.append(alt.Chart(
            pd.DataFrame([{"v": p, "l": t(lang, "posted") + f" {p:,.0f}"}])).mark_text(
            align="center", dy=-26, fontSize=12, fontWeight="bold", color="#c46a00"
        ).encode(x="v:Q", text="l:N"))

    return alt.layer(*layers).properties(height=110, title=t(lang, "pos"))


def similar_postings(posts: pd.DataFrame, ksco: str | None,
                     sigungu: str | None) -> pd.DataFrame:
    """같은 직종(+지역)의 임금 표기 공고를 고른다.

    지역까지 맞춘 표본이 30건 미만이면 지역 조건을 풀어 직종만으로 넓힌다.
    표본이 너무 적으면 분포가 의미를 잃기 때문이다.
    """
    if posts is None or posts.empty or "hourly_wage" not in posts.columns:
        return pd.DataFrame()
    d = posts.copy()
    d["_h"] = pd.to_numeric(d["hourly_wage"], errors="coerce")
    d = d[d["_h"].notna() & (d["_h"] > 0)]
    if ksco and ksco != "정보없음" and "ksco_code" in d.columns:
        d = d[d["ksco_code"] == ksco]
    if sigungu and sigungu != "정보없음" and "sigungu" in d.columns:
        narrow = d[d["sigungu"] == sigungu]
        if len(narrow) >= 30:
            d = narrow
    return d


def distribution_chart(sample: pd.DataFrame, posted: float | None,
                       lo: float, hi: float, lang: str = "ko") -> alt.LayerChart | None:
    """유사 공고 시급 히스토그램에 이 공고 위치를 얹는다."""
    if sample is None or sample.empty:
        return None
    d = sample[["_h"]].rename(columns={"_h": "h"})
    # 이상치가 축을 늘려 분포가 뭉개지는 것을 막는다
    q99 = d["h"].quantile(0.99)
    d = d[d["h"] <= max(q99, float(hi))]

    hist = alt.Chart(d).mark_bar(opacity=0.75, color="#7c8cc4").encode(
        x=alt.X("h:Q", bin=alt.Bin(maxbins=34), title=t(lang, "hourly"),
                axis=alt.Axis(format=",.0f")),
        y=alt.Y("count():Q", title=t(lang, "count")),
        tooltip=[alt.Tooltip("count():Q", title=t(lang, "count"))])

    band = alt.Chart(pd.DataFrame([{"lo": float(lo), "hi": float(hi)}])).mark_rect(
        opacity=0.13, color="#2c3f88").encode(x="lo:Q", x2="hi:Q")

    layers = [band, hist]
    if posted:
        p = float(posted)
        layers.append(alt.Chart(pd.DataFrame([{"v": p}])).mark_rule(
            color="#c46a00", strokeWidth=2.5).encode(
            x="v:Q",
            tooltip=[alt.Tooltip("v:Q", title=t(lang, "posted"), format=",.0f")]))
    return alt.layer(*layers).properties(height=200, title=t(lang, "dist"))


def percentile_of(sample: pd.DataFrame, posted: float | None) -> int | None:
    """이 공고 임금이 유사 공고 중 몇 퍼센타일인지."""
    if sample is None or sample.empty or not posted:
        return None
    return int((sample["_h"] < float(posted)).mean() * 100)
