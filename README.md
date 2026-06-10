# 코스피 버킷 깔때기 — 실데이터 파이프라인

## 파일
- `funnel_live.html` — 실데이터 깔때기 앱 (808 보통주, 브라우저로 바로 열기)
- `universe.json` — 종목별 분류 결과 (버킷·6축 체크·점수)
- `process.py` — CSV → 분류 → JSON + HTML 생성기
- `enrich.py` — [로컬 실행] pykrx로 시총·섹터·5년 히스토리 수집

## v1 (지금 상태 — CSV만)
구슬 크기 균일 / 섹터 미분류 / 밸류 퍼센타일은 전종목 단면 기준 / L2(경기순환) 비활성

## v2 (pykrx 보강 — 로컬에서 5분)
```bash
pip install pykrx pandas python-dateutil
python enrich.py 20260610                              # → enrichment.json (5년 월별 60회 호출)
python process.py data_5605_20260610.csv enrichment.json   # → funnel_live.html 재생성
```
보강 후: 구슬 크기 = log(시총) 사분위 4단계 / 섹터 색 / L2 활성화 /
밸류 퍼센타일이 "자기 5년 히스토리 기준"으로 업그레이드 (L1 정의에 부합)

## 매일 갱신 (선택)
KRX CSV 수동 다운로드 대신 pykrx `get_market_fundamental_by_ticker(date)`로
5605 데이터 자체를 대체 가능 → 크론/Task Scheduler 1줄로 일일 자동화
