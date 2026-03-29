# Snack Market Dashboard v3

Streamlit 기반 월간 FMCG 패널 데이터 대시보드입니다.

## 기능
- 엑셀 업로드
- 제조사 / 브랜드 / 타입 / 경로 필터
- KPI / 그래프 / 랭킹 / SKU 상세
- 카테고리 자동 인식
- Gemini 자연어 질문창
  - API 키가 있으면 Gemini로 질문 해석 및 요약
  - API 키가 없으면 로컬 규칙 기반 해석으로 동작

## 로컬 실행
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Gemini 연결
Streamlit Community Cloud 또는 로컬 환경에서 `GEMINI_API_KEY`를 설정하면 됩니다.

### Streamlit Secrets 예시
```toml
GEMINI_API_KEY = "YOUR_API_KEY"
```


## v4 변경 사항
- 금액 기본 표시 단위를 억원으로 변경
- 10억원 이상은 소수점 생략, 10억원 미만만 소수점 1자리 허용
- 백만원 단위 사용 시 소수점 미표시
- 그래프에 값 라벨 직접 표시
- 자연어 분석 블록을 하단으로 이동
- 빨간색 푸터 추가
