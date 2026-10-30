/* Policy timeline + benchmark (terminal discount) pages. Loaded after the main script; uses D, T, lang, esc, fmtMoney, fmtTime, go. */
(function(){
const TYPES = {
  price_cut:   {zh:'MSRP 下调', en:'MSRP cut',        c:'#B23A3A'},
  price_rise:  {zh:'MSRP 上调', en:'MSRP rise',       c:'#7B857F'},
  driveaway:   {zh:'DAP 政策',  en:'Drive-away offer', c:'#2F6B4F'},
  cashback:    {zh:'现金返还/减价', en:'Cashback / discount', c:'#4F8C6C'},
  finance_rate:{zh:'金融利率',  en:'Finance rate',    c:'#2B5F8A'},
  novated:     {zh:'Novated',  en:'Novated lease',   c:'#5C7FA3'},
  bonus:       {zh:'附加权益',  en:'Bonus / inclusions', c:'#B7791F'},
  launch:      {zh:'上市/新版本', en:'Launch / new variant', c:'#8A5CA3'},
  runout:      {zh:'清库/展车',  en:'Runout / demo',   c:'#A3785C'},
  offer:       {zh:'其他政策',  en:'Other offer',     c:'#9AA39D'},
};
const tname = k => (TYPES[k]||TYPES.offer)[lang];
const tcol = k => (TYPES[k]||TYPES.offer).c;
const MONTHS_ZH = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'];
const MONTHS_EN = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const mname = i => (lang==='zh'?MONTHS_ZH:MONTHS_EN)[i];
const YEAR = 2026;
const dayOf = s => { const d=new Date(s+'T00:00:00Z'); return isNaN(d)?null:d; };
const y0 = Date.UTC(YEAR,0,1), y1 = Date.UTC(YEAR+1,0,1);
const clampYear = (s,e) => { const a=dayOf(s); if(!a) return null; let b=e?dayOf(e):null; const start=Math.max(a.getTime(),y0); const end=Math.min(b?b.getTime()+86400000:(a.getTime()+14*86400000), y1); if(end<=y0||start>=y1) return null; return [start,end,!b]; };
const compName = id => { const c=(D.comps.competitors||[]).find(x=>x.id===id); return c?`${c.brand.split(' (')[0]} ${tx(c,'model').replace(/（.*?）|\(.*?\)/g,'').trim()}`:id; };
const BRAND_EN = {'mercedes-benz':'Mercedes-Benz',bmw:'BMW',audi:'Audi',tesla:'Tesla',byd:'BYD',xpeng:'Xpeng',kia:'Kia',smart:'smart',hyundai:'Hyundai',polestar:'Polestar',volvo:'Volvo',geely:'Geely',zeekr:'ZEEKR',leapmotor:'Leapmotor',deepal:'Deepal',mg:'MG',mini:'Mini',lexus:'Lexus',denza:'Denza',toyota:'Toyota'};
const brandZh = b => lang==='en' ? (BRAND_EN[b]||b) : ((D.bench.brand_zh||{})[b] || b);
const tx = (o,f) => (o && lang==='en' && o[f+'_en']) ? o[f+'_en'] : (o ? (o[f]??'') : '');
const ET = e => tx(e,'title'); const ED = e => tx(e,'detail'); const EM = e => tx(e,'models');
const evName = e => e.brand_name && e.brand ? `${brandZh(e.brand)}` : (e.brand||'');
const eventsIn = (cid) => (D.policy.events||[]).filter(e => (e.cids||[]).includes(cid) && clampYear(e.start,e.end));
const SRC = {thebeep:'The Beep', zecar:'Zecar', baseline:lang==='zh'?'人工核定':'Curated'};
function evLine(e){ return `<div class="item"><div class="t"><span class="badge" style="background:${tcol(e.type)}22;color:${tcol(e.type)}">${tname(e.type)}</span> <a href="${esc(e.url||'#')}" target="_blank" rel="noopener">${esc(ET(e))}</a></div><div class="m"><span>${esc(brandZh(e.brand))}${e.models?' · '+esc(EM(e)):''}</span><span>${esc(e.start||'')}${e.end?' → '+esc(e.end):(lang==='zh'?'（未注明截止）':' (open)')}</span><span class="badge b-muted">${SRC[e.source]||e.source}</span>${e.verified===false?`<span class="badge b-muted" title="${lang==='zh'?'仅聚合页单一来源，未经品牌官网或第二来源核实':'Single aggregator source; not confirmed by brand site or a second source'}">${lang==='zh'?'单一来源':'single source'}</span>`:''}${e.state&&e.state!=='national'?`<span class="badge b-muted">${esc(e.state)}</span>`:''}</div>${e.detail?`<div class="x">${esc(ED(e).slice(0,220))}</div>`:''}</div>`; }

// ---------------------------------------------------------------- month strip (used in prices tab)
window.monthStrip = function(cid){
  const evs = eventsIn(cid);
  const cells = [];
  for(let m=0;m<12;m++){
    const ms=Date.UTC(YEAR,m,1), me=Date.UTC(YEAR,m+1,1);
    const inM = evs.filter(e=>{ const r=clampYear(e.start,e.end); return r && r[0]<me && r[1]>ms; });
    const dots = [...new Set(inM.map(e=>e.type))].slice(0,4).map(t=>`<i style="background:${tcol(t)}"></i>`).join('');
    const now = new Date(); const cur = now.getUTCFullYear()===YEAR && now.getUTCMonth()===m;
    cells.push(`<div class="mcell${inM.length?' has':''}${cur?' cur':''}" title="${esc(mname(m))}: ${inM.map(ET).join(' | ')||'—'}"><span>${m+1}</span><div class="dots">${dots}</div></div>`);
  }
  return `<div class="mstrip" title="${YEAR}">${cells.join('')}</div><div class="small" style="font-size:10px;margin-top:2px">${lang==='zh'?`${YEAR} 年逐月政策（1–12 月）`:`${YEAR} policies by month (1–12)`}</div>`;
};

// ---------------------------------------------------------------- gantt
function dedupe(evs){
  // one bar per policy: curated baseline wins over Zecar over The Beep. Two records of the same type whose
  // start dates are within 31 days and end dates within 7 days (or identical titles) are treated as one policy.
  const rank={baseline:0, zecar:1, thebeep:2};
  const D1=86400000; const t=s=>{ const d=dayOf(s||''); return d?d.getTime():null; };
  const norm=e=>(ET(e)||'').toLowerCase().replace(/[^a-z0-9一-鿿]/g,'');
  const sorted=[...evs].sort((a,b)=>((rank[a.source]??3)-(rank[b.source]??3))||(a.start||'').localeCompare(b.start||''));
  const kept=[];
  for(const e of sorted){
    const es=t(e.start), ee=e.end?t(e.end):null;
    const dup=kept.some(k=>{ if(norm(k)===norm(e)) return true; if(k.type!==e.type) return false; const ks=t(k.start), ke=k.end?t(k.end):null;
      if(es==null||ks==null||Math.abs(es-ks)>31*D1) return false; if(ee==null&&ke==null) return Math.abs(es-ks)<=7*D1; if(ee==null||ke==null) return false; return Math.abs(ee-ke)<=7*D1; });
    if(!dup) kept.push(e);
  }
  return kept;
}
function fitText(t, px){ let acc=0, out=''; for(const ch of t){ acc += ch.charCodeAt(0)>0x2e80 ? 11.2 : 6.3; if(acc>px) return out ? out.replace(/\s+$/,'')+'…' : ''; out+=ch; } return out; }
function gantt(cids, types){
  const W=1240, L=168, R=14, laneH=30, barH=22, rowPad=10, top=40;
  const ms = []; for(let m=0;m<12;m++) ms.push(Date.UTC(YEAR,m,1)); ms.push(y1);
  const x = t => L + (t-y0)/(y1-y0)*(W-L-R);
  let y = top; const rows=[]; const bars=[];
  cids.forEach((cid,ri)=>{
    const evs = dedupe(eventsIn(cid).filter(e=>!types.size||types.has(e.type))).map(e=>({e, r:clampYear(e.start,e.end)})).filter(o=>o.r).sort((a,b)=>a.r[0]-b.r[0]||b.r[1]-a.r[1]);
    const lanes=[];
    const placed = evs.map(o=>{ let li=lanes.findIndex(end=>end<=o.r[0]); if(li<0){ li=lanes.length; lanes.push(0);} lanes[li]=o.r[1]+3*86400000; return {...o, lane:li}; });
    const n=Math.max(1,lanes.length); const h=n*laneH+rowPad;
    if(ri%2) rows.push(`<rect x="0" y="${y}" width="${W}" height="${h}" fill="var(--surface2)" opacity="0.55"/>`);
    rows.push(`<line x1="0" x2="${W}" y1="${y+h}" y2="${y+h}" stroke="var(--line)"/>`);
    rows.push(`<text x="${L-12}" y="${y+h/2-2}" text-anchor="end" font-size="13" font-weight="650" fill="var(--ink)">${esc(compName(cid))}</text><text x="${L-12}" y="${y+h/2+13}" text-anchor="end" font-size="10.5" fill="var(--muted)">${placed.length} ${lang==='zh'?'项政策':'policies'}</text>`);
    for(const p of placed){
      const x1=x(p.r[0]), x2=Math.max(x(p.r[1]), x1+8), yy=y+rowPad/2+p.lane*laneH+(laneH-barH)/2;
      const col=tcol(p.e.type); const open=p.r[2]; const w=x2-x1;
      const label = w>44 ? esc(fitText(ET(p.e), w-12)) : '';
      bars.push(`<a href="${esc(p.e.url||'#')}" target="_blank"><rect x="${x1}" y="${yy}" width="${w}" height="${barH}" rx="4" fill="${col}" opacity="${open?0.5:0.92}"${open?' stroke="'+col+'" stroke-dasharray="3 2"':''}><title>${esc(ET(p.e))}\n${esc(p.e.start)}${p.e.end?' → '+esc(p.e.end):(lang==='zh'?'（未注明截止）':' (open)')}\n${esc(tname(p.e.type))} · ${esc(SRC[p.e.source]||p.e.source)}</title></rect>${label?`<text x="${x1+6}" y="${yy+barH/2+4}" font-size="11" fill="#fff" style="pointer-events:none">${label}</text>`:''}</a>`);
    }
    y += h;
  });
  const H = y + 22;
  const header = `<rect x="${L}" y="${top-28}" width="${W-L-R}" height="24" rx="4" fill="var(--green4)"/>` + ms.slice(0,12).map((m,i)=>`<line x1="${x(m)}" x2="${x(m)}" y1="${top-4}" y2="${y}" stroke="var(--line)"${i%3===0?' stroke-width="1.6"':' stroke-dasharray="2 3"'}/><text x="${(x(m)+x(ms[i+1]))/2}" y="${top-11}" text-anchor="middle" font-size="12" font-weight="600" fill="var(--greenInk)">${mname(i)}</text>`).join('') + `<line x1="${x(y1)}" x2="${x(y1)}" y1="${top-4}" y2="${y}" stroke="var(--line)" stroke-width="1.6"/>`;
  const today = Date.now(); const todayLine = (today>y0&&today<y1)?`<line x1="${x(today)}" x2="${x(today)}" y1="${top-4}" y2="${y}" stroke="var(--bad)" stroke-width="1.5" stroke-dasharray="5 3"/><rect x="${x(today)-18}" y="${y+4}" width="36" height="16" rx="8" fill="var(--bad)"/><text x="${x(today)}" y="${y+16}" text-anchor="middle" font-size="10.5" fill="#fff">${lang==='zh'?'今日':'today'}</text>`:'';
  return `<svg viewBox="0 0 ${W} ${H}" class="gantt" role="img">${rows.join('')}${header}${bars.join('')}${todayLine}</svg>`;
}

// ---------------------------------------------------------------- timeline page
const TL = { cids: null, types: new Set(), brand: '' };
window.renderTimeline = function(){
  if(!D.policy){ document.getElementById('timeline').innerHTML='<div class="small">—</div>'; return; }
  if(!TL.cids) TL.cids = [...(D.bench.focus_three||[])];
  const pool = D.bench.focus_pool||[];
  const chips = pool.map(c=>`<button class="btn${TL.cids.includes(c)?' active':''}" data-cid="${c}">${esc(compName(c))}</button>`).join(' ');
  const typeChips = Object.keys(TYPES).map(t=>`<button class="btn tchip${TL.types.has(t)?' active':''}" data-t="${t}" style="border-color:${tcol(t)}55"><i style="display:inline-block;width:9px;height:9px;border-radius:2px;background:${tcol(t)};margin-right:5px;vertical-align:middle"></i>${tname(t)}</button>`).join(' ');
  const legend = `<div class="small" style="margin:6px 0 4px">${lang==='zh'?'颜色 = 政策类型；虚线浅色条 = 未注明截止日期（按 14 天显示）；同一政策在多个来源重复出现时只保留一条；点击色条打开来源。':'Colour = policy type; dashed faded bar = no end date stated (shown as 14 days); a policy listed by several sources is drawn once; click a bar to open the source.'}</div>`;
  // month-by-month table: rows = months, columns = selected competitors
  const cellFor=(cid,m)=>{ const ms=Date.UTC(YEAR,m,1), me=Date.UTC(YEAR,m+1,1); const inM=dedupe(eventsIn(cid).filter(e=>(!TL.types.size||TL.types.has(e.type)))).filter(e=>(()=>{const r=clampYear(e.start,e.end);return r&&r[0]<me&&r[1]>ms;})()).sort((a,b)=>(a.start||'').localeCompare(b.start||'')); return inM.map(e=>`<div class="tlc"><span class="badge" style="background:${tcol(e.type)}22;color:${tcol(e.type)}">${tname(e.type)}</span> <a href="${esc(e.url||'#')}" target="_blank" rel="noopener" title="${esc(ED(e)||'')}">${esc(ET(e).slice(0,90))}</a> <span class="small">${esc(e.start||'')}${e.end?'→'+esc(e.end):''}</span></div>`).join('')||'<span class="small">—</span>'; };
  const now=new Date(); const curM=now.getUTCFullYear()===YEAR?now.getUTCMonth():-1;
  const rows=[]; for(let m=0;m<12;m++) rows.push(`<tr${m===curM?' class="curm"':''}><th style="white-space:nowrap">${mname(m)}</th>${TL.cids.map(cid=>`<td>${cellFor(cid,m)}</td>`).join('')}</tr>`);
  // all events list by brand for the year
  const brands=[...new Set((D.policy.events||[]).filter(e=>clampYear(e.start,e.end)).map(e=>e.brand))].sort();
  const all=(D.policy.events||[]).filter(e=>clampYear(e.start,e.end)&&(!TL.brand||e.brand===TL.brand)).sort((a,b)=>(b.start||'').localeCompare(a.start||''));
  document.getElementById('timeline').innerHTML = `
  <div class="card"><h2>${lang==='zh'?`${YEAR} 年竞品政策时间线`:`${YEAR} competitor policy timeline`}</h2>
    <div class="small" style="margin-bottom:8px">${lang==='zh'?'数据 = The Beep 与 Zecar 政策聚合页（每 30 分钟抓取，含起止日期）+ 人工核定基线；按车型关键词归类。默认展示与 7X 最贴近的三个竞品，可点选切换。':'Data = The Beep and Zecar offer feeds (every 30 min, with start/end dates) + curated baseline; mapped to models by keyword. Default shows the three closest 7X rivals; click to change.'}</div>
    <div class="filters" id="tl_cids">${chips}</div>
    <div class="filters" id="tl_types">${typeChips}</div>
    ${legend}
    <div class="twrap hint" data-hint="${lang==='zh'?'图表可左右滑动':'Swipe sideways to scroll the chart'}">${gantt(TL.cids, TL.types)}</div>
  </div>
  <div class="card" style="margin-top:12px"><h2>${lang==='zh'?'逐月政策明细':'Month-by-month detail'}</h2><div class="twrap"><table class="tlt sticky"><thead><tr><th style="width:60px"></th>${TL.cids.map(c=>`<th>${esc(compName(c))}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div></div>
  <div class="card" style="margin-top:12px"><h2>${lang==='zh'?`${YEAR} 年全部政策记录`:`All ${YEAR} policy records`} <span class="small">${all.length}</span></h2>
    <div class="filters"><select id="tl_brand"><option value="">${lang==='zh'?'品牌：全部':'Brand: all'}</option>${brands.map(b=>`<option value="${b}" ${TL.brand===b?'selected':''}>${esc(brandZh(b))}</option>`).join('')}</select><span class="small">${lang==='zh'?'来源更新：':'Feeds updated: '}${fmtTime(D.policy.updated)} · ${D.policy.n_sources_ok}/${D.policy.n_sources} ${lang==='zh'?'个聚合页正常':'feeds ok'}</span></div>
    ${all.slice(0,250).map(evLine).join('')}
  </div>`;
  document.querySelectorAll('#tl_cids .btn').forEach(b=>b.onclick=()=>{ const c=b.dataset.cid; const i=TL.cids.indexOf(c); if(i>=0){ if(TL.cids.length>1) TL.cids.splice(i,1);} else if(TL.cids.length<6) TL.cids.push(c); renderTimeline(); });
  document.querySelectorAll('#tl_types .btn').forEach(b=>b.onclick=()=>{ const t=b.dataset.t; TL.types.has(t)?TL.types.delete(t):TL.types.add(t); renderTimeline(); });
  document.getElementById('tl_brand').onchange=e=>{ TL.brand=e.target.value; renderTimeline(); };
};

// ---------------------------------------------------------------- benchmark page
function spark(series){ if(!series||series.length<2) return ''; const vals=series.map(p=>p[1]); const min=Math.min(...vals), max=Math.max(...vals); const w=90,h=22; const pts=series.map((p,i)=>`${(i/(series.length-1))*w},${h-2-(max===min?h/2:(p[1]-min)/(max-min)*(h-4))}`).join(' '); return `<svg width="${w}" height="${h}" style="vertical-align:middle"><polyline points="${pts}" fill="none" stroke="var(--green)" stroke-width="1.5"/></svg>`; }
const money = v => v==null?'—':'$'+Number(v).toLocaleString('en-AU');
const BZ = b => lang==='zh' ? String(b||'').replace('Mercedes-Benz','奔驰').replace('BMW','宝马').replace('Audi','奥迪') : String(b||'');
  const ML = m => lang==='en' ? (m.label_en||m.label) : m.label;
window.renderBenchmark = function(){
  const G = D.german, dap = (D.dap&&D.dap.models)||{};
  if(!G){ document.getElementById('benchmark').innerHTML='<div class="small">—</div>'; return; }
  const zh = lang==='zh';
  // live DAP table
  const order = ['zeekr','german','core'];
  const gname={zeekr:zh?'ZEEKR':'ZEEKR',german:zh?'奔驰 / 宝马 / 奥迪':'Mercedes-Benz / BMW / Audi',core:zh?'核心竞品':'Core rivals'}; let lastG=null;
  const dapRows = Object.entries(dap).sort((a,b)=>order.indexOf(a[1].group)-order.indexOf(b[1].group)).flatMap(([slug,m])=>{ const hdr = m.group!==lastG ? `<tr><td colspan="8" style="background:var(--green4);color:var(--greenInk);font-weight:600">${gname[m.group]||m.group}</td></tr>` : ''; lastG=m.group; return [hdr, ...Object.entries(m.variants||{}).map(([v,st])=>{ const nsw=st.NSW||[], vic=st.VIC||[]; const cur=nsw.length?nsw[nsw.length-1]:null, first=nsw.length?nsw[0]:null; const d=cur&&first?cur[1]-first[1]:0; return `<tr><td><b>${esc(ML(m))}</b></td><td>${esc(v)}</td><td class="num">${cur?money(cur[1]):'—'}</td><td class="num">${vic.length?money(vic[vic.length-1][1]):'—'}</td><td class="num ${d<0?'delta-neg':d>0?'delta-pos':''}">${d?((d>0?'+':'−')+money(Math.abs(d))):'—'}</td><td>${spark(nsw)}</td><td class="small">${first?first[0]:''}${cur&&cur[0]!==first?.[0]?' → '+cur[0]:''}</td>${m.last_error?`<td class="status-bad small">${esc(m.last_error)}</td>`:'<td></td>'}</tr>`; })]; }).join('');
  // live German offers
  const live = (D.policy?.events||[]).filter(e=>['mercedes-benz','bmw','audi'].includes(e.brand)&&e.source!=='baseline'&&clampYear(e.start,e.end)).sort((a,b)=>(b.start||'').localeCompare(a.start||''));
  const q4 = G.q4_official.map(r=>`<tr><td style="white-space:nowrap">${esc(BZ(r.brand))}</td><td>${esc(tx(r,'model'))}</td><td class="num">${money(r.rrp)}</td><td class="num">${money(r.normal_da)}</td><td class="num">${r.offer_da?money(r.offer_da):'—'}</td><td class="num ${r.pct?'delta-neg':''}">${r.disc?`${money(r.disc)}（−${r.pct}%）`:'—'}</td><td class="small">${esc(tx(r,'valid'))}</td><td class="small">${esc(tx(r,'note')||'')} ${r.src?`<a href="${esc(r.src)}" target="_blank" rel="noopener">↗</a>`:''}</td></tr>`).join('');
  const lst = G.listings_q4.slice().sort((a,b)=>(b.pct||0)-(a.pct||0)).map(r=>`<tr><td style="white-space:nowrap">${esc(BZ(r.brand))}</td><td>${esc(tx(r,'model'))}</td><td class="num">${r.km!=null?Number(r.km).toLocaleString():'—'}</td><td>${esc(r.loc)}</td><td class="num">${money(r.ref_da)}</td><td class="num">${money(r.ask_da)}</td><td class="num delta-neg"><b>${r.pct!=null?'−'+r.pct+'%':'—'}</b></td><td class="small">${esc(tx(r,'hist')||'')} ${r.src?`<a href="${esc(r.src)}" target="_blank" rel="noopener">↗</a>`:''}</td></tr>`).join('');
  const cuts = G.rrp_cuts_2026.map(r=>`<tr><td style="white-space:nowrap">${esc(r.date)}</td><td>${esc(BZ(r.brand))} ${esc(tx(r,'model'))}</td><td class="num">${r.from?`${money(r.from)} → ${money(r.to)}`:(r.to?`${zh?'上市定价':'launch'} ${money(r.to)}`:'—')}</td><td class="num delta-neg">${r.pct?'−'+r.pct+'%':'—'}</td><td class="small">${esc(tx(r,'note')||'')} ${r.src?`<a href="${esc(r.src)}" target="_blank" rel="noopener">↗</a>`:''}</td></tr>`).join('');
  const fin = G.finance_timeline.map(r=>`<tr><td style="white-space:nowrap">${esc(BZ(r.brand))}</td><td style="white-space:nowrap">${esc(tx(r,'period'))}</td><td>${esc(tx(r,'offer'))} ${r.src?`<a href="${esc(r.src)}" target="_blank" rel="noopener">↗</a>`:''}</td></tr>`).join('');
  const bars = G.q4_official.filter(r=>r.pct).sort((a,b)=>b.pct-a.pct).map(r=>[`${BZ(r.brand)} ${tx(r,'model').replace(/（.*?）|\(.*?\)/g,'').trim()}`, r.pct]);
  const lbars = G.listings_q4.filter(r=>r.pct!=null).sort((a,b)=>b.pct-a.pct).map(r=>[`${BZ(r.brand)} ${tx(r,'model').replace(/（.*?）|\(.*?\)/g,'').trim()}`, r.pct]);
  const hb = pairs => { const max=Math.max(1,...pairs.map(p=>p[1])); return pairs.map(p=>`<div class="bar-row" style="grid-template-columns:260px 1fr 56px"><div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(p[0])}">${esc(p[0])}</div><div><div class="bar" style="width:${100*p[1]/max}%;background:var(--bad)"></div></div><div class="n">−${p[1]}%</div></div>`).join(''); };
  document.getElementById('benchmark').innerHTML = `
  <div class="note">${zh?'奔驰、宝马、奥迪在 7X / 7GT 价格带的终端价格证据。前半部分为 2026-10-21 人工核定的基线（第四季度官方政策、展车挂牌价、MSRP 调整、金融贴息演变）；后半部分为实时监控（每 30 分钟）：The Beep 各州 DAP 与三个品牌的现行政策。MSRP = 厂商指导价（不含上路费用）；DAP = 上路价（drive-away price）。':'Terminal-price evidence for Mercedes-Benz, BMW and Audi in the 7X / 7GT band. First the curated baseline as at 2026-10-21; then live monitoring (every 30 min) of state DAP from The Beep and current offers. MSRP = list price before on-roads; DAP = drive-away price.'}</div>
  <div class="card"><h2>${zh?'基线一：2026 年第四季度官方政策（2026-10-21 核定）':'Baseline 1: Q4 2026 official offers (as at 2026-10-21)'}</h2>
    <div class="twrap"><table><thead><tr><th>${zh?'品牌':'Brand'}</th><th>${zh?'车型 / 政策':'Model / offer'}</th><th class="num">MSRP</th><th class="num">${zh?'常规 DAP':'Normal DAP'}</th><th class="num">${zh?'政策 DAP':'Offer DAP'}</th><th class="num">${zh?'折扣':'Discount'}</th><th>${zh?'有效期':'Valid'}</th><th>${zh?'说明':'Note'}</th></tr></thead><tbody>${q4}</tbody></table></div><h3>${zh?'官方政策折扣幅度（对常规 DAP）':'Official-offer discount vs normal DAP'}</h3>${hb(bars)}</div>
  <div class="card" style="margin-top:12px"><h2>${zh?'基线二：展车 / 近新车挂牌价（2026-10-21 快照）':'Baseline 2: demo / near-new listings (snapshot 2026-10-21)'}</h2>
    <div class="twrap"><table><thead><tr><th>${zh?'品牌':'Brand'}</th><th>${zh?'车型':'Model'}</th><th class="num">km</th><th>${zh?'地点':'Location'}</th><th class="num">${zh?'常规 DAP':'Normal DAP'}</th><th class="num">${zh?'挂牌 DAP':'Asking DAP'}</th><th class="num">${zh?'折扣':'Discount'}</th><th>${zh?'调价轨迹':'Price history'}</th></tr></thead><tbody>${lst}</tbody></table></div>
    <h3>${zh?'折扣分布':'Discount distribution'}</h3>${hb(lbars)}
    <div class="small">${zh?'折扣以常规 DAP 为基准；展车价格为经销商挂牌价，非成交价。drive.com.au 等挂牌平台对自动抓取封锁，此部分为人工快照。':'Discount vs normal DAP; asking prices, not transaction prices. Listing sites block automated clients, so this section is a manual snapshot.'}</div></div>
  <div class="grid two" style="margin-top:12px">
    <div class="card"><h2>${zh?'基线三：2026 年官方 MSRP 调整':'Baseline 3: 2026 MSRP changes'}</h2><div class="twrap"><table><thead><tr><th>${zh?'日期':'Date'}</th><th>${zh?'车型':'Model'}</th><th class="num">MSRP</th><th class="num">%</th><th>${zh?'说明':'Note'}</th></tr></thead><tbody>${cuts}</tbody></table></div></div>
    <div class="card"><h2>${zh?'基线四：金融贴息演变':'Baseline 4: finance subvention timeline'}</h2><div class="twrap"><table><thead><tr><th>${zh?'品牌':'Brand'}</th><th>${zh?'时间':'Period'}</th><th>${zh?'政策':'Offer'}</th></tr></thead><tbody>${fin}</tbody></table></div></div>
  </div>
  <div class="card" style="margin-top:12px"><h2>${zh?'证据局限':'Limitations'}</h2><ul class="small">${((lang==='en'&&G.gaps_en)||G.gaps||[]).map(g=>`<li>${esc(g)}</li>`).join('')}</ul></div>
  <div class="card" style="margin-top:12px"><h2>${zh?'实时监控：DAP（NSW / VIC）':'Live: DAP (NSW / VIC)'} <span class="small">${D.dap?fmtTime(D.dap.updated):''}</span></h2>
    <div class="twrap"><table class="sticky"><thead><tr><th>${zh?'车型':'Model'}</th><th>${zh?'版本':'Variant'}</th><th class="num">NSW DAP</th><th class="num">VIC DAP</th><th class="num">${zh?'较首次记录':'vs first seen'}</th><th>${zh?'走势（NSW）':'Trend (NSW)'}</th><th>${zh?'记录期间':'Window'}</th><th></th></tr></thead><tbody>${dapRows}</tbody></table></div>
    <div class="small" style="margin-top:6px">${zh?'来源：thebeep.com.au 车型页 JSON-LD（各州上路价，按日记录，价格变化时新增记录点）。':'Source: thebeep.com.au model pages (state drive-away prices; a point is recorded per day when the price changes).'}</div></div>
  <div class="card" style="margin-top:12px"><h2>${zh?'实时监控：奔驰、宝马、奥迪现行政策':'Live: current Mercedes-Benz / BMW / Audi offers'} <span class="small">${live.length}</span></h2>${live.map(evLine).join('')||`<div class="small">—</div>`}</div>`;
};
})();
