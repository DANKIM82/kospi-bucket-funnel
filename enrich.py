#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
enrich.py — FinanceDataReader로 시총·섹터(·5년 가격백분위) → enrichment.json
[로컬 실행용] pip install finance-datareader

시총: StockListing('KRX')의 Marcap
섹터: StockListing('KRX-DESC')의 Industry(표준산업분류)를 큰 그룹으로 매핑 (sector_map.py)
사용법:
  python enrich.py 20260609 --light    # 시총+섹터만 (빠름, 권장)
  python enrich.py 20260609            # + 5년 가격백분위
이후:
  python process.py data_5605_20260610.csv enrichment.json
"""
import sys, json, time
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import FinanceDataReader as fdr
from sector_map import industry_to_group

def get_marcap():
    df = fdr.StockListing('KRX')
    df['Code'] = df['Code'].astype(str).str.zfill(6)
    return dict(zip(df['Code'], df['Marcap']))

def get_sectors():
    df = fdr.StockListing('KRX-DESC')
    df['Code'] = df['Code'].astype(str).str.zfill(6)
    if 'Industry' not in df.columns:
        return {}
    df = df.dropna(subset=['Industry'])
    return {c: industry_to_group(ind) for c, ind in zip(df['Code'], df['Industry'])}

def get_px_pct(codes, date):
    end = datetime.strptime(date, '%Y%m%d')
    start = (end - relativedelta(years=5)).strftime('%Y-%m-%d')
    out = {}
    for i, c in enumerate(codes):
        try:
            h = fdr.DataReader(c, start, end.strftime('%Y-%m-%d'))
            if len(h) >= 250:
                cur = h['Close'].iloc[-1]
                out[c] = round(float((h['Close'] < cur).mean()*100), 0)
        except Exception:
            pass
        if i % 50 == 0: print(f"  히스토리 {i}/{len(codes)}…")
        time.sleep(0.05)
    return out

def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    date = args[0] if args else datetime.today().strftime('%Y%m%d')
    light = '--light' in sys.argv
    print(f"기준일 {date} — FinanceDataReader")

    print("[1/3] 시가총액 (StockListing KRX)…")
    mcap = get_marcap(); print(f"  {len(mcap)}종목")

    print("[2/3] 섹터 (KRX-DESC Industry → 그룹)…")
    sector = get_sectors(); print(f"  {len(sector)}종목 매핑")

    codes = [c for c in mcap if c.endswith('0')]
    px = {}
    if light:
        print("[3/3] 히스토리 생략(--light)")
    else:
        print(f"[3/3] 5년 가격 백분위 ({len(codes)}종목)…")
        px = get_px_pct(codes, date)

    out = {}
    for c in mcap:
        out[c] = {'mcap': int(mcap.get(c,0)), 'sector': sector.get(c,'미분류'),
                  'per_hist_pct': None, 'pbr_hist_pct': None, 'px_hist_pct': px.get(c)}
    json.dump(out, open('enrichment.json','w',encoding='utf-8'), ensure_ascii=False)
    print(f"완료 — 시총 {sum(1 for v in out.values() if v['mcap']>0)} / "
          f"섹터 {sum(1 for v in out.values() if v['sector']!='미분류')} / 가격백분위 {len(px)}")
    print("→ enrichment.json 생성. 이제: python process.py <CSV> enrichment.json")

if __name__ == '__main__':
    main()
