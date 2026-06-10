#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
enrich.py — pykrx로 시총·섹터·5년 밸류 히스토리 퍼센타일 수집 → enrichment.json
[로컬 실행용] pip install pykrx pandas
사용법:
  python enrich.py 20260610          # 기준일 (CSV 기준일과 맞추기)
이후:
  python process.py data_5605_20260610.csv enrichment.json
"""
import sys, json, time
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from pykrx import stock

def main():
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.today().strftime('%Y%m%d')
    print(f"기준일 {date} — KOSPI")

    # 1) 시가총액 (구슬 크기 사분위용)
    print("[1/3] 시가총액…")
    cap = stock.get_market_cap_by_ticker(date, market="KOSPI")  # index=티커
    mcap = cap['시가총액'].to_dict()

    # 2) 섹터 — KRX 업종지수(1005~) 구성종목으로 매핑
    print("[2/3] 섹터(업종지수 구성종목)…")
    sector = {}
    for idx_code in stock.get_index_ticker_list(market="KOSPI"):
        name = stock.get_index_ticker_name(idx_code)
        # 업종지수만 (코스피 200 등 전략지수 제외): '코스피 ' 접두 업종명 패턴
        if not name.startswith('코스피 '):
            continue
        sec_name = name.replace('코스피 ', '')
        if sec_name in ('200', '100', '50', '대형주', '중형주', '소형주', '배당성장 50'):
            continue
        try:
            for t in stock.get_index_portfolio_deposit_file(idx_code, date):
                sector.setdefault(t, sec_name)
            time.sleep(0.3)
        except Exception as e:
            print(f"  skip {name}: {e}")

    # 3) 5년 밸류 히스토리 → 현재 PER/PBR의 자기-히스토리 퍼센타일
    #    (종목별 800회 호출 대신, 월말 스냅샷 60회로 전종목 일괄 수집)
    print("[3/3] 5년 월별 밸류 스냅샷 (약 60회 호출, 수 분 소요)…")
    end = datetime.strptime(date, '%Y%m%d')
    frames = []
    for m in range(60, -1, -1):
        d = (end - relativedelta(months=m)).strftime('%Y%m%d')
        try:
            f = stock.get_market_fundamental_by_ticker(d, market="KOSPI")[['PER', 'PBR']]
            f['date'] = d
            frames.append(f.reset_index())
            time.sleep(0.4)
        except Exception:
            pass
    hist = pd.concat(frames)
    hist = hist[(hist['PER'] > 0) & (hist['PBR'] > 0)]

    cur = stock.get_market_fundamental_by_ticker(date, market="KOSPI")[['PER', 'PBR']]
    per_pct, pbr_pct = {}, {}
    for t, g in hist.groupby('티커'):
        if t not in cur.index or len(g) < 24:   # 최소 2년 히스토리
            continue
        cp, cb = cur.loc[t, 'PER'], cur.loc[t, 'PBR']
        if cp > 0:
            per_pct[t] = round(float((g['PER'] < cp).mean() * 100), 0)
        if cb > 0:
            pbr_pct[t] = round(float((g['PBR'] < cb).mean() * 100), 0)

    out = {}
    for t in cap.index:
        out[t] = {'mcap': int(mcap.get(t, 0)),
                  'sector': sector.get(t, '미분류'),
                  'per_hist_pct': per_pct.get(t),
                  'pbr_hist_pct': pbr_pct.get(t)}
    with open('enrichment.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)
    n_sec = sum(1 for v in out.values() if v['sector'] != '미분류')
    n_hist = sum(1 for v in out.values() if v['per_hist_pct'] is not None)
    print(f"완료 — {len(out)}종목 / 섹터 {n_sec} / 히스토리 퍼센타일 {n_hist}")
    print("→ enrichment.json 생성. 이제: python process.py <CSV> enrichment.json")

if __name__ == '__main__':
    main()
