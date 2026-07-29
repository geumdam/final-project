# 브릿지포 — Streamlit 배포본

부산 지역 외국인 구직자용 **적정 임금 예측 + 다국어 근로조건 진단** 서비스.

## 실행

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Streamlit Community Cloud 배포

1. 이 폴더를 GitHub 저장소로 올린다 (public 또는 private).
2. https://share.streamlit.io 에서 **New app** → 저장소·브랜치 선택
   → Main file path 를 `streamlit_app.py` 로 지정.
3. **Settings → Secrets** 에 아래를 넣는다. 없어도 앱은 동작하고,
   '직접 입력' 탭의 실시간 LLM 진단만 비활성화된다.

```toml
OPENAI_API_KEY = "sk-..."
```

> `.env` 파일은 저장소에 올리지 마세요. 키가 공개됩니다.
> `.gitignore` 에 이미 등록해 두었습니다.

## 비용

- **임금 예측**: 로컬 추론. API 호출이 없어 비용 0원.
- **근로조건 진단 · 체크리스트**: 사전 계산본(`reports/llm/`)을 읽으므로 비용 0원.
- **'직접 입력' 탭의 실시간 진단**: 켤 때만 OpenAI 를 호출한다. 호출당 수 센트 수준.

## 담고 있는 것

```
models/lgbm_q10|q50|q90.txt   LightGBM 분위수 회귀 (각 900 트리 · 19 피처)
models/meta.json              피처 순서 · 학습 범주 · CQR 보정폭
data/postings.parquet          공고 5,168건 (앱이 쓰는 30열만)
reports/                       성능 지표 · 신뢰도 등급 · F1 · 보존율
reports/llm/                   사전 계산된 근로조건 판정 · 모국어 체크리스트
```

## 주의 — 예측을 그대로 신뢰하면 안 되는 지점

- **CQR 보정폭을 반드시 적용해야 한다.** `meta.json` 의 `cqr_widen_log` 를
  log 공간에서 q10 에 빼고 q90 에 더한 뒤 `expm1` 한다. 빼먹으면 커버리지가
  81% → 57% 로 무너진다.
- **범주형은 학습 범주 순서를 그대로 써야 한다.** LightGBM 은 범주를 정수 코드로
  다루므로, `meta.json` 의 `categories` 로 `pd.Categorical` 을 강제해야 한다.
- **신뢰도 '매우낮음' 은 구간을 노출하지 않는다.** 등급별 커버리지가 74~85% 로
  갈리기 때문이다 (`reports/reliability_breakdown.csv`).
