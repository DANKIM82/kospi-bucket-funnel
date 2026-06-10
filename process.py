#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
process.py — KRX 밸류 CSV(5605) → 버킷 분류 → universe.json + funnel_live.html
사용법:
  python process.py data_5605_20260610.csv            # enrichment 없이 (v1)
  python process.py data_5605_20260610.csv enrichment.json  # pykrx 보강 후 (v2)
"""
import sys, json, math
import pandas as pd
import numpy as np

CYCLICAL_SECTORS = {'철강금속','철강','화학','운수장비','조선','운수창고','기계','전기가스업','건설업','종이목재','비금속광물'}

def load(csv_path, enrich_path=None):
    df = pd.read_csv(csv_path, encoding='cp949')
    df['종목코드'] = df['종목코드'].astype(str).str.zfill(6)
    df = df[df['종목코드'].str.endswith('0')].copy()          # 보통주만
    df['ROE'] = df['EPS'] / df['BPS'] * 100
    df['G'] = (df['선행 EPS'] / df['EPS'] - 1) * 100           # 이익성장 근사
    df.loc[df['EPS'] <= 0, 'G'] = np.nan
    enrich = {}
    if enrich_path:
        with open(enrich_path, encoding='utf-8') as f:
            enrich = json.load(f)
    df['mcap'] = df['종목코드'].map(lambda c: enrich.get(c, {}).get('mcap'))
    df['sector'] = df['종목코드'].map(lambda c: enrich.get(c, {}).get('sector', '미분류'))
    df['per_hist'] = df['종목코드'].map(lambda c: enrich.get(c, {}).get('per_hist_pct'))
    df['pbr_hist'] = df['종목코드'].map(lambda c: enrich.get(c, {}).get('pbr_hist_pct'))
    # 밸류 퍼센타일: 히스토리(자기 5년) 우선, 없으면 단면(전종목 비교)
    cross = df['PER'].rank(pct=True) * 100
    df['PER_pct'] = df['per_hist'].fillna(cross)
    df['val_basis'] = np.where(df['per_hist'].notna(), 'hist', 'cross')
    # 구슬 크기: log(시총) 사분위 4단계 (시총 없으면 tier 1 균일)
    if df['mcap'].notna().sum() > 10:
        logm = np.log10(df['mcap'].astype(float))
        df['tier'] = pd.qcut(logm, 4, labels=False)
        df['tier'] = df['tier'].fillna(0).astype(int)
    else:
        df['tier'] = 1
    df['cyc'] = df['sector'].isin(CYCLICAL_SECTORS)
    return df

def bucket(r):
    full = pd.notna(r['PER']) and pd.notna(r['ROE'])
    g = r['G']
    if full and pd.notna(g) and g >= 18 and r['ROE'] >= 10: return 'L4'
    if full and r['PER_pct'] < 45 and r['ROE'] >= 10: return 'L1'
    if pd.notna(r['PBR']) and r['PBR'] < 0.4 and r['배당수익률'] >= 3: return 'V3'
    if r['cyc'] and pd.notna(g) and g > 0 and pd.notna(r['ROE']) and r['ROE'] >= 5: return 'L2'
    if full and r['배당수익률'] >= 4 and r['ROE'] >= 7: return 'L5'
    return 'W'

CHECKS = [
    ('성격 적합 · Lynch',    lambda r: (not r['cyc']) or (pd.notna(r['G']) and r['G'] > 0)),
    ('이벤트 촉매 · Greenblatt', lambda r: r['배당수익률'] >= 4),
    ('숏 신호 없음 · Chanos', lambda r: not (r['PER_pct'] > 66 and pd.notna(r['G']) and r['G'] < 0) and (pd.isna(r['ROE']) or r['ROE'] >= 3)),
    ('모트 작동 · Dorsey',    lambda r: pd.notna(r['ROE']) and r['ROE'] >= 8),
    ('밸류·성장 균형 · 팩터',  lambda r: r['PER_pct'] < 67 or (pd.notna(r['G']) and r['G'] >= 15)),
    ('기대 갭 · Mauboussin',  lambda r: r['PER_pct'] < 50 or (pd.notna(r['G']) and r['G'] >= 20)),
]

def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else 'data_5605_20260610.csv'
    enrich_path = sys.argv[2] if len(sys.argv) > 2 else None
    df = load(csv_path, enrich_path)
    df['bucket'] = df.apply(bucket, axis=1)
    out = []
    for _, r in df.iterrows():
        chk = [bool(fn(r)) for _, fn in CHECKS]
        out.append({
            'c': r['종목코드'], 'n': r['종목명'],
            'sec': r['sector'], 'cyc': bool(r['cyc']), 'tier': int(r['tier']),
            'per': None if pd.isna(r['PER']) else round(float(r['PER']), 1),
            'pbr': None if pd.isna(r['PBR']) else round(float(r['PBR']), 2),
            'roe': None if pd.isna(r['ROE']) else round(float(r['ROE']), 1),
            'g': None if pd.isna(r['G']) else round(float(r['G']), 1),
            'dy': round(float(r['배당수익률']), 2),
            'vp': round(float(r['PER_pct']), 0) if pd.notna(r['PER_pct']) else None,
            'vb': r['val_basis'],
            'bk': r['bucket'], 'chk': chk, 'sc': sum(chk),
        })
    with open('universe.json', 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False)
    html = TEMPLATE.replace('__DATA__', json.dumps(out, ensure_ascii=False)) \
                   .replace('__META__', json.dumps({
                        'date': csv_path.split('_')[-1].split('.')[0],
                        'n': len(out), 'enriched': enrich_path is not None}, ensure_ascii=False))
    with open('funnel_live.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"OK — {len(out)}종목 / enriched={enrich_path is not None}")
    print(df['bucket'].value_counts().to_string())
    print("→ universe.json, funnel_live.html 생성")

TEMPLATE = r'''<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>코스피 버킷 깔때기 — 실데이터</title>
<style>
:root{--bg:#FAFAF7;--sf:#F1EFEA;--bd:#DDD9D0;--tx:#2C2C2A;--mut:#6B6963;--ter:#9B988F}
*{box-sizing:border-box;margin:0}
body{font-family:'Pretendard','Apple SD Gothic Neo','Malgun Gothic',sans-serif;background:var(--bg);color:var(--tx);padding:20px;max-width:760px;margin:0 auto}
h1{font-size:19px;font-weight:600;margin-bottom:2px}
.sub{font-size:12px;color:var(--ter);margin-bottom:12px}
.bar{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:8px}
button{font:inherit;font-size:12.5px;padding:6px 13px;border:1px solid var(--bd);border-radius:8px;background:#fff;color:var(--mut);cursor:pointer}
button:hover{background:var(--sf)}
input{font:inherit;font-size:12.5px;padding:6px 10px;border:1px solid var(--bd);border-radius:8px;background:#fff;width:150px}
.read{display:flex;align-items:center;gap:8px;min-height:34px;font-size:12.5px;padding:7px 12px;border-radius:8px;background:var(--sf);color:var(--mut);flex-wrap:wrap;margin-bottom:8px}
.pill{font-size:11px;padding:2px 8px;border-radius:999px;display:inline-block}
.panel{background:#fff;border:1px solid var(--bd);border-radius:12px;padding:14px 16px;margin-top:10px;font-size:13px;line-height:1.6}
svg{display:block;width:100%;background:var(--sf);border-radius:12px}
.foot{font-size:11px;color:var(--ter);margin-top:10px;line-height:1.6}
b{font-weight:600}
</style></head><body>
<h1>코스피 버킷 깔때기 <span style="font-weight:400;font-size:13px;color:var(--ter)">실데이터</span></h1>
<div class="sub" id="meta"></div>
<div class="bar">
 <button id="go">▶ 1차 분류</button>
 <button id="sp">속도 2x</button>
 <button id="rs">↺ 리셋</button>
 <input id="q" placeholder="종목 검색 후 Enter">
</div>
<div class="read" id="read">1차: 버킷 분류 → 2차: 관찰 제외 종목만 6축 검사 → 최종 조사 후보</div>
<svg id="sv" viewBox="0 0 680 905">
 <path d="M52 30 L324 222" stroke="#B9B5AA" stroke-width="8" stroke-linecap="round"/>
 <path d="M628 30 L356 222" stroke="#B9B5AA" stroke-width="8" stroke-linecap="round"/>
 <path d="M324 222 L324 248" stroke="#B9B5AA" stroke-width="8" stroke-linecap="round"/>
 <path d="M356 222 L356 248" stroke="#B9B5AA" stroke-width="8" stroke-linecap="round"/>
 <text x="340" y="272" text-anchor="middle" style="font-size:10.5px;fill:#9B988F">1차 · 버킷 규칙</text>
 <path d="M150 470 L326 592" stroke="#B9B5AA" stroke-width="8" stroke-linecap="round"/>
 <path d="M530 470 L354 592" stroke="#B9B5AA" stroke-width="8" stroke-linecap="round"/>
 <path d="M326 592 L326 616" stroke="#B9B5AA" stroke-width="8" stroke-linecap="round"/>
 <path d="M354 592 L354 616" stroke="#B9B5AA" stroke-width="8" stroke-linecap="round"/>
 <text x="340" y="640" text-anchor="middle" style="font-size:10.5px;fill:#9B988F">2차 · 6축 검사 (4개 이상 통과)</text>
 <g id="bins"></g><g id="balls"></g>
</svg>
<div id="card" class="panel" style="display:none"></div>
<div class="foot">자동 분류는 매수/매도 판정이 아니라 <b>조사 우선순위</b> 표시입니다. 성장은 컨센서스 선행EPS 기준 근사치이며 컨센이 없는 종목은 일부 검사가 보수적으로 처리됩니다. 밸류 퍼센타일: 히스토리 보강 전엔 전종목 단면 기준. 출처: KRX 정보데이터시스템.</div>
<script>
const DATA=__DATA__;
const META=__META__;
document.getElementById('meta').textContent=`${META.n}개 보통주 · 기준일 ${META.date} · ${META.enriched?'pykrx 보강 적용(시총·섹터·히스토리)':'보강 전 v1 — enrich.py 실행 후 재생성하면 시총·섹터 반영'}`;
const SECC={'IT·전기전자':'#378ADD','화학':'#D4537E','운수장비':'#7F77DD','철강금속':'#D85A30','금융업':'#8A8980','의약품':'#639922','음식료품':'#E24B4A','유통업':'#E24B4A','건설업':'#BA7517','기계':'#BA7517','운수창고':'#BA7517','전기가스업':'#1D9E75','서비스업':'#378ADD','통신업':'#1D9E75','미분류':'#9B988F'};
const secCol=s=>SECC[s]||'#6E7B8E';
const BK=[{id:'L1',nm:'싸진 우량주',c:'#1F7A4D',rule:'싸다 + ROE 강함'},
 {id:'L2',nm:'바닥 탈출',c:'#BA7517',rule:'경기순환 + 이익 회복'},
 {id:'L4',nm:'성장주',c:'#0F6E56',rule:'이익성장 빠름 + ROE 강함'},
 {id:'L5',nm:'배당 이벤트',c:'#534AB7',rule:'고배당 + 수익성'},
 {id:'V3',nm:'자산주',c:'#2E5A8C',rule:'PBR 극저 + 배당'},
 {id:'W',nm:'관찰',c:'#8A8780',rule:'신호 없음 — 머뭄'}];
const FIN=[{id:'GO',nm:'조사 후보',c:'#1F7A4D',ds:'6축 중 4개 이상 통과. 여기서부터 사람이 깊게 팝니다.'},
 {id:'HOLD',nm:'보류',c:'#8A6508',ds:'버킷 신호는 있으나 6축에서 걸림. 걸린 축 해소 시 재검토.'}];
const CHKN=['성격 적합 · Lynch','이벤트 촉매 · Greenblatt','숏 신호 없음 · Chanos','모트 작동 · Dorsey','밸류·성장 균형 · 팩터','기대 갭 · Mauboussin'];
const bkIdx=b=>BK.findIndex(x=>x.id===b);
const R=[4.5,5.5,7,9];
const B1={x0:22,w:101,g:6,top:300,fl:438},B2=[{x:60,w:330},{x:430,w:190}],B2TOP=660,B2FL=872;
const b1cx=i=>B1.x0+i*(B1.w+B1.g)+B1.w/2;
const NS='http://www.w3.org/2000/svg';
const el=(t,a)=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e;};
const $=id=>document.getElementById(id);
const CAP1=Math.floor((B1.w-16)/13)*Math.floor((B1.fl-B1.top-40)/13);
function drawBins(){
 const G=$('bins');G.innerHTML='';
 BK.forEach((b,i)=>{const x=B1.x0+i*(B1.w+B1.g);const g=el('g',{cursor:'pointer'});
  g.appendChild(el('rect',{x,y:B1.top,width:B1.w,height:B1.fl-B1.top+6,rx:8,fill:b.c,'fill-opacity':0.10,stroke:b.c,'stroke-opacity':0.5,'stroke-width':1.5}));
  const t1=el('text',{x:x+B1.w/2,y:B1.top+16,'text-anchor':'middle'});t1.setAttribute('style',`font-size:11px;font-weight:600;fill:${b.c}`);t1.textContent=b.nm;g.appendChild(t1);
  const t2=el('text',{x:x+B1.w/2,y:B1.top+30,'text-anchor':'middle',id:'c1'+i});t2.setAttribute('style',`font-size:10px;fill:${b.c};opacity:.85`);t2.textContent=b.id+' · 0';g.appendChild(t2);
  g.addEventListener('click',()=>binPanel(i,false));G.appendChild(g);});
 FIN.forEach((b,i)=>{const bx=B2[i];const g=el('g',{cursor:'pointer'});
  g.appendChild(el('rect',{x:bx.x,y:B2TOP,width:bx.w,height:B2FL-B2TOP+6,rx:8,fill:b.c,'fill-opacity':0.10,stroke:b.c,'stroke-opacity':0.55,'stroke-width':1.5}));
  const t1=el('text',{x:bx.x+bx.w/2,y:B2TOP+18,'text-anchor':'middle'});t1.setAttribute('style',`font-size:12px;font-weight:600;fill:${b.c}`);t1.textContent=b.nm;g.appendChild(t1);
  const t2=el('text',{x:bx.x+bx.w/2,y:B2TOP+32,'text-anchor':'middle',id:'c2'+i});t2.setAttribute('style',`font-size:10px;fill:${b.c};opacity:.85`);t2.textContent='0개';g.appendChild(t2);
  g.addEventListener('click',()=>binPanel(i,true));G.appendChild(g);});
}
function slot1(bi,k){const cols=Math.floor((B1.w-16)/13);const c=k%cols,r=Math.floor(k/cols);return{x:B1.x0+bi*(B1.w+B1.g)+10+c*13,y:B1.fl-7-r*13};}
function slot2(fi,k){const bx=B2[fi],cols=Math.floor((bx.w-20)/13),c=k%cols,r=Math.floor(k/cols);return{x:bx.x+12+c*13,y:B2FL-7-r*13};}
function cr(p,t){const n=p.length-1,s=Math.min(n-1,Math.floor(t*n)),lt=t*n-s;
 const P=i=>p[Math.max(0,Math.min(n,i))];const p0=P(s-1),p1=P(s),p2=P(s+1),p3=P(s+2),t2=lt*lt,t3=t2*lt;
 const f=(a,b,c2,d2)=>0.5*((2*b)+(-a+c2)*lt+(2*a-5*b+4*c2-d2)*t2+(-a+3*b-3*c2+d2)*t3);
 return[f(p0[0],p1[0],p2[0],p3[0]),f(p0[1],p1[1],p2[1],p3[1])];}
const ease=t=>t<0?0:t>1?1:t*t*(3-2*t);
const hw1=y=>282-(282-16)*Math.max(0,Math.min(1,(y-30)/192));
let flight=[],raf=null,speed=2,t0=0,phase='idle';
const c1=[0,0,0,0,0,0],c2cnt=[0,0],s1k=[0,0,0,0,0,0],s2k=[0,0];
function reset(){
 if(raf)cancelAnimationFrame(raf);raf=null;t0=0;phase='idle';flight=[];
 c1.fill(0);c2cnt.fill(0);s1k.fill(0);s2k.fill(0);
 $('balls').innerHTML='';drawBins();
 $('go').textContent='▶ 1차 분류';
 $('read').textContent='1차: 버킷 분류 → 2차: 관찰 제외 종목만 6축 검사 → 최종 조사 후보';
 $('card').style.display='none';}
function launch1(){
 phase='s1';t0=0;flight=[];
 DATA.forEach((d,i)=>{
  const bi=bkIdx(d.bk);
  const c=el('circle',{r:R[d.tier],fill:secCol(d.sec),stroke:'#fff','stroke-width':1,cx:-30,cy:-30,cursor:'pointer'});
  c.addEventListener('click',()=>stockCard(d));
  $('balls').appendChild(c);
  const x0=110+((i*73)%460),side=x0<340?-1:1,wy=128,wx=340+side*(hw1(wy)-12);
  const k=s1k[bi]++;const sp=k<CAP1?slot1(bi,k):null;
  const endx=sp?sp.x:b1cx(bi),endy=sp?sp.y:B1.fl-30;
  flight.push({d,bi,elc:c,keep:!!sp,start:i*55,dur:2300,flashAt:0.42,flashed:false,arr:false,
   path:[[x0,-14],[(x0+wx)/2,52],[wx,wy],[340,236],[340,262],[(340+b1cx(bi))/2,288],[b1cx(bi),B1.top-12],[endx,(B1.top+endy)/2],[endx,endy]]});});
 raf=requestAnimationFrame(frame);}
function launch2(){
 phase='s2';t0=0;flight=[];$('balls').innerHTML='';
 let j=0;
 DATA.forEach(d=>{
  if(d.bk==='W')return;
  const bi=bkIdx(d.bk),fi=d.sc>=4?0:1;
  const c=el('circle',{r:R[d.tier],fill:secCol(d.sec),stroke:'#fff','stroke-width':1,cx:-30,cy:-30,cursor:'pointer'});
  c.addEventListener('click',()=>stockCard(d));
  $('balls').appendChild(c);
  const k=s2k[fi]++;const cap2=Math.floor((B2[fi].w-20)/13)*Math.floor((B2FL-B2TOP-44)/13);
  const sp=k<cap2?slot2(fi,k):null;
  const fx=B2[fi].x+B2[fi].w/2,endx=sp?sp.x:fx,endy=sp?sp.y:B2FL-30;
  flight.push({d,fi,elc:c,keep:!!sp,start:j*55,dur:2200,flashAt:0.42,flashed:false,arr:false,
   path:[[b1cx(bi),B1.fl-14],[b1cx(bi),B1.fl+24],[(b1cx(bi)+340)/2,500],[340,596],[340,624],[(340+fx)/2,646],[fx,B2TOP-12],[endx,(B2TOP+endy)/2],[endx,endy]]});
  j++;});
 raf=requestAnimationFrame(frame);}
function frame(ts){
 if(!t0)t0=ts;
 const T=(ts-t0)*speed;let busy=false;
 flight.forEach(b=>{
  if(b.arr)return;
  const t=(T-b.start)/b.dur;
  if(t<0){busy=true;return;}
  if(t>=1){b.arr=true;
   const p=b.path[b.path.length-1];
   if(b.keep){b.elc.setAttribute('cx',p[0]);b.elc.setAttribute('cy',p[1]);}
   else b.elc.remove();
   if(phase==='s1'){const bi=b.bi;c1[bi]++;$('c1'+bi).textContent=BK[bi].id+' · '+c1[bi];}
   else{c2cnt[b.fi]++;$('c2'+b.fi).textContent=c2cnt[b.fi]+'개';}
   return;}
  busy=true;
  if(!b.flashed&&t>=b.flashAt){b.flashed=true;flash(b);}
  const p=cr(b.path,ease(t));
  b.elc.setAttribute('cx',p[0]);b.elc.setAttribute('cy',p[1]);});
 if(busy)raf=requestAnimationFrame(frame);
 else{raf=null;finish();}}
function flash(b){
 if(phase==='s1'){const bk=BK[b.bi];
  $('read').innerHTML=`<span style="width:10px;height:10px;border-radius:50%;background:${secCol(b.d.sec)}"></span><b>${b.d.n}</b> → ${bk.rule} → <span class="pill" style="background:${bk.c}22;color:${bk.c}">${bk.nm}</span>`;}
 else{const f=FIN[b.fi];
  $('read').innerHTML=`<span style="width:10px;height:10px;border-radius:50%;background:${secCol(b.d.sec)}"></span><b>${b.d.n}</b> → 6축 <b>${b.d.sc}/6</b> 통과 → <span class="pill" style="background:${f.c}22;color:${f.c}">${f.nm}</span>`;}}
function finish(){
 if(phase==='s1'){phase='s1done';
  const w=c1[5],tot=DATA.length;
  $('go').textContent='▶ 2차 · 6축 검사';
  $('read').innerHTML=`✓ 1차 완료 — 관찰 ${w}개(${Math.round(w/tot*100)}%)는 머물고, ${tot-w}개만 2차로. [2차 · 6축 검사]를 누르세요.`;}
 else if(phase==='s2'){phase='done';
  $('go').textContent='↺ 처음부터';
  $('read').innerHTML=`완료 — ${DATA.length}개 → 1차 통과 ${DATA.length-c1[5]}개 → 최종 조사 후보 <b>${c2cnt[0]}개</b>. 통을 눌러 목록을 보세요. 후보를 깊게 파는 건 사람의 일입니다.`;}}
function fmt(v,suf=''){return v==null?'—':v+suf;}
function stockCard(d){
 const bi=bkIdx(d.bk),bk=BK[bi],fin=d.bk==='W'?null:FIN[d.sc>=4?0:1];
 const checks=d.bk==='W'?'':CHKN.map((n,i)=>`<div style="padding:2px 0;font-size:12.5px"><span style="color:${d.chk[i]?'#1F7A4D':'#A32D2D'};font-weight:600">${d.chk[i]?'✓':'✗'}</span> ${n}</div>`).join('');
 $('card').style.display='block';
 $('card').innerHTML=`<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px">
  <span style="width:12px;height:12px;border-radius:50%;background:${secCol(d.sec)}"></span><b style="font-size:15px">${d.n}</b>
  <span style="color:var(--ter);font-size:12px">${d.c} · ${d.sec}${d.cyc?' · 경기순환':''}</span>
  <span class="pill" style="background:${bk.c}22;color:${bk.c}">1차: ${bk.nm}</span>
  ${fin?`<span class="pill" style="background:${fin.c}22;color:${fin.c}">2차: ${fin.nm} (${d.sc}/6)</span>`:''}</div>
 <div style="font-size:12.5px;color:var(--mut);margin-bottom:8px">PER ${fmt(d.per)} · PBR ${fmt(d.pbr)} · ROE ${fmt(d.roe,'%')} · 이익성장 ${fmt(d.g,'%')} · 배당 ${fmt(d.dy,'%')} · 밸류 퍼센타일 ${fmt(d.vp)}${d.vb==='hist'?' (5년 히스토리)':' (단면)'}</div>${checks}
 <div style="font-size:11px;color:var(--ter);margin-top:6px">조사 우선순위 표시일 뿐, 매수/매도 판정이 아닙니다.</div>`;
 $('card').scrollIntoView({behavior:'smooth',block:'nearest'});}
function binPanel(i,isFin){
 const b=isFin?FIN[i]:BK[i];
 const members=DATA.filter(d=>isFin?(d.bk!=='W'&&(d.sc>=4?0:1)===i):d.bk===b.id)
   .sort((a,b2)=>b2.sc-a.sc||(b2.roe||0)-(a.roe||0));
 const top=members.slice(0,48).map(d=>`<span class="pill" style="background:${secCol(d.sec)}22;color:${secCol(d.sec)};margin:2px 3px 0 0;cursor:pointer" onclick='stockCard(${JSON.stringify(d).replace(/'/g,"&#39;")})'>${d.n}${isFin?' '+d.sc+'/6':''}</span>`).join('');
 $('card').style.display='block';
 $('card').innerHTML=`<b style="color:${b.c}">${b.nm}</b> <span style="color:var(--ter);font-size:12px">${members.length}개 · ${b.rule||b.ds}</span><div style="margin-top:8px">${top}${members.length>48?`<span style="font-size:12px;color:var(--ter)"> 외 ${members.length-48}개</span>`:''}</div>`;
 $('card').scrollIntoView({behavior:'smooth',block:'nearest'});}
window.stockCard=stockCard;
$('go').onclick=()=>{if(raf)return;
 if(phase==='idle'){drawBins();launch1();$('read').textContent='1차 분류 중…';}
 else if(phase==='s1done'){launch2();$('read').textContent='2차 · 6축 검사 중…';}
 else if(phase==='done')reset();};
$('rs').onclick=reset;
$('sp').onclick=()=>{speed=speed===1?2:speed===2?4:speed===4?8:1;$('sp').textContent='속도 '+speed+'x';};
$('q').addEventListener('keydown',e=>{if(e.key!=='Enter')return;
 const v=e.target.value.trim();if(!v)return;
 const d=DATA.find(x=>x.n.includes(v));
 if(d)stockCard(d);else{$('card').style.display='block';$('card').textContent='"'+v+'" 검색 결과 없음 (보통주만 포함)';}});
drawBins();
</script></body></html>'''

if __name__ == '__main__':
    main()
