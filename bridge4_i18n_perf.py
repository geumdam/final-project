#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""'모델 성능' 탭과 사이드바 지표의 다국어 문구.

원래 이 탭은 팀·심사용이라 한국어로 남겼는데, 화면 언어를 중국어로 바꿔도
여기만 한국어라 섞여 보였다. 언어를 바꾸면 전체가 그 언어여야 한다.

번역하지 않는 것
  - 지표 숫자와 파일 경로 (`reports/llm/adjudication_log.csv` 등)
  - 모델·라벨의 내부 이름 (표에서는 LABEL_NAME 으로 표시만 바꾼다)
"""

from __future__ import annotations

# 표 컬럼 이름. 원본 CSV 는 한국어 컬럼이라 표시할 때만 바꾼다.
COLS: dict[str, dict[str, str]] = {
    "ko": {"신뢰도": "신뢰도", "건수": "건수", "커버리지": "커버리지",
           "구간폭중위": "구간폭 중위", "중위시급": "중위 시급",
           "q50오차중위": "q50 오차 중위",
           "라벨": "항목", "n": "n", "정답양성률": "정답 양성률",
           "TP": "TP", "FP": "FP", "FN": "FN", "F1": "F1",
           "대표지표포함": "대표지표", "feature": "피처", "importance": "중요도"},
    "en": {"신뢰도": "Reliability", "건수": "Count", "커버리지": "Coverage",
           "구간폭중위": "Median width", "중위시급": "Median hourly",
           "q50오차중위": "Median q50 error",
           "라벨": "Item", "n": "n", "정답양성률": "Positive rate",
           "TP": "TP", "FP": "FP", "FN": "FN", "F1": "F1",
           "대표지표포함": "Headline", "feature": "Feature", "importance": "Importance"},
    "zh": {"신뢰도": "可信度", "건수": "件数", "커버리지": "覆盖率",
           "구간폭중위": "区间宽度中位数", "중위시급": "时薪中位数",
           "q50오차중위": "q50 误差中位数",
           "라벨": "项目", "n": "n", "정답양성률": "正例比例",
           "TP": "TP", "FP": "FP", "FN": "FN", "F1": "F1",
           "대표지표포함": "代表指标", "feature": "特征", "importance": "重要度"},
    "vi": {"신뢰도": "Độ tin cậy", "건수": "Số tin", "커버리지": "Độ phủ",
           "구간폭중위": "Trung vị độ rộng", "중위시급": "Trung vị lương giờ",
           "q50오차중위": "Trung vị sai số q50",
           "라벨": "Hạng mục", "n": "n", "정답양성률": "Tỷ lệ dương",
           "TP": "TP", "FP": "FP", "FN": "FN", "F1": "F1",
           "대표지표포함": "Chỉ số chính", "feature": "Đặc trưng",
           "importance": "Mức quan trọng"},
    "ja": {"신뢰도": "信頼度", "건수": "件数", "커버리지": "カバー率",
           "구간폭중위": "区間幅の中央値", "중위시급": "時給の中央値",
           "q50오차중위": "q50 誤差の中央値",
           "라벨": "項目", "n": "n", "정답양성률": "正例率",
           "TP": "TP", "FP": "FP", "FN": "FN", "F1": "F1",
           "대표지표포함": "代表指標", "feature": "特徴量", "importance": "重要度"},
    "es": {"신뢰도": "Fiabilidad", "건수": "Casos", "커버리지": "Cobertura",
           "구간폭중위": "Anchura mediana", "중위시급": "Mediana por hora",
           "q50오차중위": "Error mediano q50",
           "라벨": "Ítem", "n": "n", "정답양성률": "Tasa de positivos",
           "TP": "TP", "FP": "FP", "FN": "FN", "F1": "F1",
           "대표지표포함": "Indicador clave", "feature": "Variable",
           "importance": "Importancia"},
}

PERF: dict[str, dict[str, str]] = {
    "ko": {
        "criteria": "성공기준",
        "m1": "① 임금 구간 커버리지",
        "m1_goal": "목표 80% — 달성",
        "m1_note": "CQR 보정 전 {before}%. 보정이 성능의 절반을 만듭니다.",
        "m2": "② 근로조건 탐지 F1",
        "m2_goal": "목표 0.80 — 달성",
        "m2_note": "대표 {n}항목 micro · macro {macro} · "
                   "정답지 47건 (LLM 2종 교차 + 불일치 판정)",
        "m3": "③ 용어 보존율",
        "m3_goal": "목표 90% — 달성",
        "m3_note": "중국어 {n}회 표본. 한국어 괄호 병기 규칙의 효과입니다.",
        "sb_m1": "임금 구간 커버리지",
        "sb_m1_goal": "목표 80% · 보정 전 {before}%",
        "sb_m2": "근로조건 탐지 F1",
        "sb_m2_goal": "목표 0.80 · 대표 {n}항목",
        "sb_m3": "용어 보존율",
        "sb_m3_goal": "목표 90% · {n}회",
        "t_rel": "**신뢰도 등급별 성능** — 노출 정책의 근거",
        "t_f1": "**항목별 F1**",
        "t_imp": "**피처 중요도**",
        "lim_hdr": "한계 — 함께 읽어야 하는 것",
        "lim": [
            "**정답지가 47건입니다.** 목표 100건의 절반이고, `사람 검수 100건` 이 아니라 "
            "**LLM 2종(GPT-5.4 · Gemini) 교차 라벨 + 불일치 전량 판정**으로 만들었습니다. "
            "셀 329개의 확정 근거는 `reports/llm/adjudication_log.csv` 에 있습니다.",
            "**양성 사례가 적습니다.** 항목당 TP+FN 이 1~10건입니다. "
            "`실근로시간 미기재` 는 양성 1건으로 F1 1.000 인데, 이는 1건을 맞춘 것입니다.",
            "**`사회보험 미기재` F1 0.987 은 성능이 아닙니다.** 가이드가 "
            "\"언급 없음 → 해당\" 으로 정한 항목이라 정답지가 규칙으로 결정되고, "
            "모델도 같은 규칙을 받았습니다. 대표지표에서 제외했습니다.",
            "**LLM 진단 커버리지 상한은 61.4%** 입니다. 공고 본문 보유율이 그만큼입니다.",
            "**q50 R² 는 0.283** 입니다. 점 추정 정확도는 낮으므로 구간으로 제시하고, "
            "신뢰도 '매우낮음' 은 구간을 아예 숨깁니다.",
            "**임금 모델은 고용24 공고로 학습했습니다.** 알바 공고에 그대로 쓰면 "
            "커버리지가 40.6% 로 떨어지므로, 알바 공고는 같은 직종 실측 분포와 비교합니다.",
            "**월 환산은 209시간 기준**입니다. 실제 근무시간이 다르면 금액도 달라집니다.",
            "**대화 답변은 생성 모델의 출력입니다.** 공고에 없는 내용은 '없다'고 "
            "답하도록 했지만, 중요한 조건은 항상 공고 원문과 함께 확인하세요.",
        ],
    },
    "en": {
        "criteria": "Success criteria",
        "m1": "① Wage interval coverage",
        "m1_goal": "Target 80% — met",
        "m1_note": "{before}% before CQR calibration. Calibration accounts for half of the result.",
        "m2": "② Condition detection F1",
        "m2_goal": "Target 0.80 — met",
        "m2_note": "micro over {n} headline items · macro {macro} · "
                   "47 gold postings (2 LLMs cross-labelled, all disagreements adjudicated)",
        "m3": "③ Term preservation",
        "m3_goal": "Target 90% — met",
        "m3_note": "{n} occurrences, Chinese sample. Effect of keeping Korean terms in brackets.",
        "sb_m1": "Wage interval coverage",
        "sb_m1_goal": "Target 80% · {before}% before calibration",
        "sb_m2": "Condition detection F1",
        "sb_m2_goal": "Target 0.80 · {n} headline items",
        "sb_m3": "Term preservation",
        "sb_m3_goal": "Target 90% · {n} occurrences",
        "t_rel": "**Performance by reliability grade** — basis for what we show",
        "t_f1": "**F1 by item**",
        "t_imp": "**Feature importance**",
        "lim_hdr": "Limits — read these alongside the numbers",
        "lim": [
            "**The gold set is 47 postings**, half the target of 100, and it is not "
            "human review. It was built by cross-labelling with two LLMs (GPT-5.4 · Gemini) "
            "and adjudicating every disagreement. Evidence for all 329 cells is in "
            "`reports/llm/adjudication_log.csv`.",
            "**Positive cases are few** — 1 to 10 TP+FN per item. "
            "`Working hours not stated` has one positive and F1 1.000, which means one hit.",
            "**`Social insurance not stated` F1 0.987 is not performance.** The guide "
            "defines it as \"no mention → flagged\", so the gold labels follow a rule and "
            "the model was given the same rule. It is excluded from the headline figure.",
            "**LLM diagnosis covers at most 61.4%** of postings — that is how many have body text.",
            "**q50 R² is 0.283.** Point accuracy is low, so we present an interval and "
            "hide it entirely when reliability is 'very low'.",
            "**The wage model was trained on Work24 postings.** Applied directly to "
            "part-time listings its coverage drops to 40.6%, so those are compared "
            "against the observed distribution for the same occupation instead.",
            "**Monthly figures assume 209 hours.** Actual hours change the amount.",
            "**Chat answers come from a generative model.** It is told to say when "
            "something is absent from the posting, but always check important terms "
            "against the original.",
        ],
    },
    "zh": {
        "criteria": "达标情况",
        "m1": "① 工资区间覆盖率",
        "m1_goal": "目标 80% — 已达成",
        "m1_note": "CQR 校准前为 {before}%。校准贡献了一半的性能。",
        "m2": "② 劳动条件检测 F1",
        "m2_goal": "目标 0.80 — 已达成",
        "m2_note": "{n} 个代表项目的 micro · macro {macro} · "
                   "标准答案 47 条（2 个 LLM 交叉标注，不一致全部裁定）",
        "m3": "③ 术语保留率",
        "m3_goal": "目标 90% — 已达成",
        "m3_note": "中文样本 {n} 次。这是韩语原词加括号规则的效果。",
        "sb_m1": "工资区间覆盖率",
        "sb_m1_goal": "目标 80% · 校准前 {before}%",
        "sb_m2": "劳动条件检测 F1",
        "sb_m2_goal": "目标 0.80 · {n} 个代表项目",
        "sb_m3": "术语保留率",
        "sb_m3_goal": "目标 90% · {n} 次",
        "t_rel": "**按可信度等级的性能** — 决定显示内容的依据",
        "t_f1": "**各项目 F1**",
        "t_imp": "**特征重要度**",
        "lim_hdr": "局限 — 请与数字一起阅读",
        "lim": [
            "**标准答案只有 47 条**，是目标 100 条的一半，而且不是人工审核。"
            "它是用两个 LLM（GPT-5.4 · Gemini）交叉标注、并对所有不一致逐一裁定得到的。"
            "329 个单元格的判定依据在 `reports/llm/adjudication_log.csv`。",
            "**正例很少** — 每个项目的 TP+FN 只有 1~10 条。"
            "「未写明实际工时」只有 1 个正例，F1 为 1.000，意思是猜对了那 1 条。",
            "**「未写明社会保险」F1 0.987 并不代表性能。** 指南规定"
            "「没有提及即视为未写明」，所以标准答案由规则决定，模型也拿到了同一条规则。"
            "该项目已从代表指标中排除。",
            "**LLM 诊断的覆盖上限是 61.4%** — 这是有正文文字的公告比例。",
            "**q50 的 R² 为 0.283。** 点估计精度低，所以以区间呈现，"
            "可信度为「很低」时完全不显示区间。",
            "**工资模型是用 Work24 公共公告训练的。** 直接用于兼职公告时覆盖率降到 40.6%，"
            "因此兼职公告改与同职业的实测分布比较。",
            "**月薪换算以 209 小时为准。** 实际工时不同，金额也会不同。",
            "**对话回答来自生成式模型。** 已要求它明确说明公告中没有的内容，"
            "但重要条件请务必与公告原文一起确认。",
        ],
    },
    "vi": {
        "criteria": "Tiêu chí đạt được",
        "m1": "① Độ phủ khoảng lương",
        "m1_goal": "Mục tiêu 80% — đã đạt",
        "m1_note": "Trước hiệu chỉnh CQR là {before}%. Hiệu chỉnh tạo ra một nửa hiệu năng.",
        "m2": "② F1 phát hiện điều kiện lao động",
        "m2_goal": "Mục tiêu 0.80 — đã đạt",
        "m2_note": "micro trên {n} hạng mục chính · macro {macro} · "
                   "47 tin đáp án (2 LLM gán nhãn chéo, mọi bất đồng đều được phán định)",
        "m3": "③ Tỷ lệ giữ thuật ngữ",
        "m3_goal": "Mục tiêu 90% — đã đạt",
        "m3_note": "Mẫu tiếng Trung {n} lần. Đây là hiệu quả của quy tắc giữ tiếng Hàn "
                   "trong ngoặc.",
        "sb_m1": "Độ phủ khoảng lương",
        "sb_m1_goal": "Mục tiêu 80% · trước hiệu chỉnh {before}%",
        "sb_m2": "F1 phát hiện điều kiện",
        "sb_m2_goal": "Mục tiêu 0.80 · {n} hạng mục chính",
        "sb_m3": "Tỷ lệ giữ thuật ngữ",
        "sb_m3_goal": "Mục tiêu 90% · {n} lần",
        "t_rel": "**Hiệu năng theo mức độ tin cậy** — căn cứ cho những gì được hiển thị",
        "t_f1": "**F1 theo hạng mục**",
        "t_imp": "**Mức quan trọng của đặc trưng**",
        "lim_hdr": "Hạn chế — hãy đọc cùng với các con số",
        "lim": [
            "**Bộ đáp án chỉ có 47 tin**, một nửa mục tiêu 100 tin, và không phải do người "
            "duyệt. Nó được tạo bằng cách gán nhãn chéo với hai LLM (GPT-5.4 · Gemini) và "
            "phán định toàn bộ các điểm bất đồng. Căn cứ cho 329 ô nằm trong "
            "`reports/llm/adjudication_log.csv`.",
            "**Rất ít trường hợp dương** — mỗi hạng mục chỉ có 1~10 TP+FN. "
            "«Không ghi giờ làm thực tế» chỉ có 1 ca dương và F1 1.000, nghĩa là đúng 1 ca.",
            "**F1 0.987 của «Không ghi bảo hiểm xã hội» không phải là hiệu năng.** "
            "Hướng dẫn quy định «không đề cập → tính là thiếu», nên đáp án do quy tắc quyết "
            "định và mô hình cũng nhận cùng quy tắc đó. Hạng mục này đã bị loại khỏi chỉ số chính.",
            "**Chẩn đoán bằng LLM chỉ phủ tối đa 61.4%** số tin — đó là tỷ lệ tin có văn bản.",
            "**R² của q50 là 0.283.** Độ chính xác điểm thấp nên chúng tôi trình bày theo "
            "khoảng, và ẩn hoàn toàn khi độ tin cậy ở mức «rất thấp».",
            "**Mô hình lương được huấn luyện trên tin công của Work24.** Dùng trực tiếp cho "
            "tin bán thời gian, độ phủ giảm còn 40.6%, nên các tin đó được so với phân bố "
            "thực đo của cùng ngành nghề.",
            "**Quy đổi tháng dựa trên 209 giờ.** Giờ làm thực tế khác thì số tiền cũng khác.",
            "**Câu trả lời trong hội thoại đến từ mô hình sinh.** Mô hình được yêu cầu nói rõ "
            "khi tin không đề cập, nhưng hãy luôn đối chiếu các điều kiện quan trọng với tin gốc.",
        ],
    },
    "ja": {
        "criteria": "達成基準",
        "m1": "① 賃金区間のカバー率",
        "m1_goal": "目標 80% — 達成",
        "m1_note": "CQR 補正前は {before}%。補正が性能の半分をつくっています。",
        "m2": "② 労働条件検出 F1",
        "m2_goal": "目標 0.80 — 達成",
        "m2_note": "代表 {n} 項目の micro · macro {macro} · "
                   "正解データ 47件（LLM 2種で相互ラベル付け、不一致は全件判定）",
        "m3": "③ 用語保持率",
        "m3_goal": "目標 90% — 達成",
        "m3_note": "中国語サンプル {n}回。韓国語の原語を括弧で併記する規則の効果です。",
        "sb_m1": "賃金区間のカバー率",
        "sb_m1_goal": "目標 80% · 補正前 {before}%",
        "sb_m2": "労働条件検出 F1",
        "sb_m2_goal": "目標 0.80 · 代表 {n} 項目",
        "sb_m3": "用語保持率",
        "sb_m3_goal": "目標 90% · {n}回",
        "t_rel": "**信頼度等級ごとの性能** — 何を表示するかの根拠",
        "t_f1": "**項目別 F1**",
        "t_imp": "**特徴量の重要度**",
        "lim_hdr": "限界 — 数値と併せて読んでください",
        "lim": [
            "**正解データは 47件**で、目標 100件の半分です。人による検収ではなく、"
            "LLM 2種（GPT-5.4 · Gemini）の相互ラベル付けと不一致の全件判定でつくりました。"
            "329セルの判定根拠は `reports/llm/adjudication_log.csv` にあります。",
            "**陽性事例が少ないです** — 項目ごとの TP+FN が 1〜10件です。"
            "「実労働時間の未記載」は陽性 1件で F1 1.000 ですが、これは 1件当てたという意味です。",
            "**「社会保険の未記載」の F1 0.987 は性能ではありません。** ガイドが"
            "「言及なし → 該当」と定めた項目なので正解がルールで決まり、モデルも同じルールを"
            "受け取っています。代表指標から除外しました。",
            "**LLM 診断のカバー率上限は 61.4%** です。求人に本文がある割合がそれだけです。",
            "**q50 の R² は 0.283** です。点推定の精度は低いため区間で示し、"
            "信頼度が「非常に低い」ときは区間を隠します。",
            "**賃金モデルは Work24 の求人で学習しています。** アルバイト求人にそのまま使うと"
            "カバー率が 40.6% まで落ちるため、アルバイト求人は同職種の実測分布と比較します。",
            "**月額換算は 209時間が基準**です。実際の労働時間が違えば金額も変わります。",
            "**対話の回答は生成モデルの出力です。** 求人に書かれていないことは「ない」と"
            "答えるようにしていますが、重要な条件は必ず求人原文と併せて確認してください。",
        ],
    },
    "es": {
        "criteria": "Criterios de éxito",
        "m1": "① Cobertura del intervalo salarial",
        "m1_goal": "Objetivo 80% — cumplido",
        "m1_note": "{before}% antes de la calibración CQR. La calibración aporta la mitad "
                   "del rendimiento.",
        "m2": "② F1 de detección de condiciones",
        "m2_goal": "Objetivo 0.80 — cumplido",
        "m2_note": "micro sobre {n} ítems clave · macro {macro} · "
                   "47 ofertas de referencia (2 LLM etiquetaron en paralelo; "
                   "todos los desacuerdos se resolvieron)",
        "m3": "③ Conservación de términos",
        "m3_goal": "Objetivo 90% — cumplido",
        "m3_note": "{n} apariciones, muestra en chino. Es el efecto de mantener el término "
                   "coreano entre paréntesis.",
        "sb_m1": "Cobertura del intervalo",
        "sb_m1_goal": "Objetivo 80% · {before}% sin calibrar",
        "sb_m2": "F1 de detección",
        "sb_m2_goal": "Objetivo 0.80 · {n} ítems clave",
        "sb_m3": "Conservación de términos",
        "sb_m3_goal": "Objetivo 90% · {n} apariciones",
        "t_rel": "**Rendimiento por grado de fiabilidad** — base de lo que se muestra",
        "t_f1": "**F1 por ítem**",
        "t_imp": "**Importancia de las variables**",
        "lim_hdr": "Límites — léelos junto con las cifras",
        "lim": [
            "**El conjunto de referencia son 47 ofertas**, la mitad del objetivo de 100, y no "
            "es revisión humana. Se construyó etiquetando en paralelo con dos LLM "
            "(GPT-5.4 · Gemini) y resolviendo cada desacuerdo. La justificación de las 329 "
            "celdas está en `reports/llm/adjudication_log.csv`.",
            "**Hay pocos casos positivos**: entre 1 y 10 TP+FN por ítem. "
            "«Jornada real no indicada» tiene un positivo y F1 1.000, lo que significa un acierto.",
            "**El F1 0.987 de «Seguridad social no indicada» no es rendimiento.** La guía lo "
            "define como «sin mención → señalado», así que la referencia la fija una regla y "
            "el modelo recibió la misma regla. Se excluye de la cifra principal.",
            "**El diagnóstico con LLM cubre como máximo el 61.4%** de las ofertas: esa es la "
            "proporción que tiene texto.",
            "**El R² de q50 es 0.283.** La precisión puntual es baja, así que presentamos un "
            "intervalo y lo ocultamos por completo cuando la fiabilidad es «muy baja».",
            "**El modelo salarial se entrenó con ofertas de Work24.** Aplicado directamente a "
            "ofertas de tiempo parcial su cobertura baja al 40.6%, así que esas se comparan "
            "con la distribución observada de la misma ocupación.",
            "**Las cifras mensuales asumen 209 horas.** Si las horas reales cambian, "
            "el importe también.",
            "**Las respuestas del chat vienen de un modelo generativo.** Se le indica que "
            "avise cuando algo no aparece en la oferta, pero comprueba siempre las "
            "condiciones importantes con el original.",
        ],
    },
}


def p(lang: str, key: str) -> str:
    """성능 탭 문구. 없으면 한국어로 되돌린다."""
    d = PERF.get(lang) or PERF["ko"]
    v = d.get(key)
    if v is None:
        v = PERF["ko"].get(key, key)
    return v


def limits(lang: str) -> list[str]:
    d = PERF.get(lang) or PERF["ko"]
    return d.get("lim") or PERF["ko"]["lim"]


def cols(lang: str, columns) -> dict:
    """DataFrame 컬럼 이름을 표시용으로 바꾸는 매핑을 만든다."""
    m = COLS.get(lang) or COLS["ko"]
    return {c: m.get(c, c) for c in columns}


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    ko = set(PERF["ko"])
    bad = 0
    for L, d in PERF.items():
        miss, extra = ko - set(d), set(d) - ko
        n = len(limits(L))
        ok = not miss and not extra and n == len(PERF["ko"]["lim"])
        if not ok:
            bad += 1
        print(f'{L}: 키 {len(d)}개 · 한계 {n}개  '
              f'{"OK" if ok else f"누락 {sorted(miss)} 초과 {sorted(extra)}"}')
    for L, d in COLS.items():
        miss = set(COLS["ko"]) - set(d)
        if miss:
            bad += 1
            print(f'COLS {L}: 누락 {sorted(miss)}')
    print("전부 일치" if not bad else f"{bad}개 언어에 문제")
    raise SystemExit(1 if bad else 0)
