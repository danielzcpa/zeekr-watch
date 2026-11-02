/* Deliveries page: monthly VFACTS/EVC model sales (CarExpert Sales Atlas) + BEV monthly table (The Driven). Uses D, lang, esc, fmtTime, tx. */
(function(){
const zh = () => lang==='zh';
const MON = i => zh() ? `${i}月` : ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][i-1];
const num = v => v==null ? '—' : Number(v).toLocaleString('en-AU');
const pct = v => v==null ? '—' : (v>0?'+':'') + v.toFixed(1) + '%';

function monthsAvail(){
  const s = new Set();
  Object.keys((D.sales&&D.sales.months)||{}).forEach(m=>s.add(m));
  Object.values((D.ev&&D.ev.models)||{}).forEach(o=>Object.keys(o).forEach(m=>s.add(m)));
  return [...s].sort();
}
// series for a competitor id (or zeekr key): {months:{m:units}, src:'bev'|'vfacts'|'combined'|null, ytd, yoy, label}
function seriesFor(cid, isZeekr){
  const smap = D.smap||{}; const ev = (D.ev&&D.ev.models)||{}; const months = (D.sales&&D.sales.months)||{};
  const dname = isZeekr ? (smap.zeekr_driven||{})[cid] : (smap.driven||{})[cid];
  const amap = isZeekr ? (smap.zeekr||{})[cid] : (smap.competitors||{})[cid];
  const out = {months:{}, src:null, ytd:null, yoy:null, combined:false};
  if(dname){
    const names = Array.isArray(dname)?dname:[dname];
    let any=false;
    names.forEach(n=>{ const o=ev[n]; if(o){ any=true; Object.entries(o).forEach(([m,u])=>{ out.months[m]=(out.months[m]||0)+u; }); } });
    if(any){ out.src='bev'; const yr=D.ev.year||''; out.ytd=Object.entries(out.months).filter(([m])=>m.startsWith(yr)).reduce((a,[,u])=>a+u,0); }
  }
  if(amap){
    const ref = Array.isArray(amap)?amap:amap.ref; const combined = !Array.isArray(amap)&&amap.combined;
    const key = ref.join('|');
    Object.entries(months).sort().forEach(([m,rec])=>{ const r=rec.models[key]; if(!r) return;
      if(out.src!=='bev'){ out.months[m]=r.units; out.src = combined?'combined':'vfacts'; out.ytd=r.ytd; out.combined=combined; }
      else if(!combined && out.months[m]==null && r.units!=null){ out.months[m]=r.units; }
      if(m===D.sales.latest){ if(!(combined && out.src==='bev')) out.yoy=r.yoy; out.atlas={units:r.units, ytd:r.ytd, combined}; }
    });
  }
  if(!Object.keys(out.months).length){ out.src=null; out.ytd=null; }
  return out;
}
function spark(ms, obj){ const vals=ms.map(m=>obj[m]??null); const has=vals.filter(v=>v!=null); if(has.length<2) return ''; const max=Math.max(...has,1); const w=96,h=22; const pts=ms.map((m,i)=>obj[m]==null?null:`${(i/(ms.length-1))*w},${h-2-(obj[m]/max)*(h-4)}`).filter(Boolean).join(' '); return `<svg width="${w}" height="${h}" style="vertical-align:middle"><polyline points="${pts}" fill="none" stroke="var(--green)" stroke-width="1.5"/></svg>`; }

function lineChart(rows, ms, minW){
  // rows: [{label, months:{}, color}]
  const W=1100, H=300, L=60, R=20, T=16, B=34; const max=Math.max(1,...rows.flatMap(r=>ms.map(m=>r.months[m]||0)));
  const x=i=>L+(i/(Math.max(1,ms.length-1)))*(W-L-R); const y=v=>T+(1-v/max)*(H-T-B);
  const grid=[0,0.25,0.5,0.75,1].map(f=>`<line x1="${L}" x2="${W-R}" y1="${y(max*f)}" y2="${y(max*f)}" stroke="var(--line)"/><text x="${L-6}" y="${y(max*f)+4}" text-anchor="end" font-size="10" fill="var(--muted)">${num(Math.round(max*f))}</text>`).join('');
  const xl=ms.map((m,i)=>`<text x="${x(i)}" y="${H-10}" text-anchor="middle" font-size="11" fill="var(--muted)">${MON(+m.slice(5))}</text>`).join('');
  const lines=rows.map(r=>{ const pts=ms.map((m,i)=>r.months[m]==null?null:[x(i),y(r.months[m])]); const d=pts.map((p,i)=>p?`${i&&pts[i-1]?'L':'M'}${p[0]},${p[1]}`:'').join(' '); return `<path d="${d}" fill="none" stroke="${r.color}" stroke-width="${r.bold?3:2}"/>${pts.map((p,i)=>p?`<circle cx="${p[0]}" cy="${p[1]}" r="3" fill="${r.color}"><title>${esc(r.label)} ${ms[i]}: ${num(rows.find(x=>x===r).months[ms[i]])}</title></circle>`:'').join('')}`; }).join('');
  const legend=rows.map(r=>`<span class="badge" style="background:${r.bold?'var(--surface2)':r.color+'22'};color:${r.color};margin-right:6px;${r.bold?'font-weight:700':''}"><i style="display:inline-block;width:10px;height:3px;background:${r.color};vertical-align:middle;margin-right:4px"></i>${esc(r.label)}</span>`).join('');
  return `<div class="twrap hint" data-hint="${zh()?'图表可左右滑动':'Swipe sideways'}"><svg viewBox="0 0 ${W} ${H}" style="width:100%;min-width:${minW||700}px;display:block">${grid}${xl}${lines}</svg></div><div style="margin-top:6px">${legend}</div>`;
}
const PALETTE=['#2F6B4F','#B23A3A','#2B5F8A','#B7791F','#8A5CA3','#4F8C6C','#A3785C','#5C7FA3','#7B857F'];

window.renderDeliveries = function(){
  const el=document.getElementById('deliveries'); if(!el) return;
  if(!D.sales||!D.sales.months||!Object.keys(D.sales.months).length){ el.innerHTML=`<div class="small">—</div>`; return; }
  const ms=monthsAvail(); const latest=D.sales.latest; const L=D.sales.months[latest];
  const srcTag = s => s==='bev' ? `<span class="badge b-green" title="${zh()?'The Driven 纯电月度表（EVC/VFACTS）':'The Driven BEV monthly table (EVC/VFACTS)'}">BEV</span>` : s==='combined' ? `<span class="badge b-medium" title="${zh()?'VFACTS 将燃油与纯电版合并申报':'VFACTS reports ICE and EV versions together'}">${zh()?'合并':'ICE+EV'}</span>` : s==='vfacts' ? `<span class="badge b-muted">VFACTS</span>` : `<span class="badge b-muted">${zh()?'未申报':'n/a'}</span>`;
  // ---- market section
  const fuel=L.fuel_mix||{}, buyer=L.buyer_type||{};
  const evTotal={}; Object.entries((D.ev&&D.ev.models)||{}).filter(([n])=>!/^total/i.test(n)).map(([,o])=>o).forEach(o=>Object.entries(o).forEach(([m,u])=>{ evTotal[m]=(evTotal[m]||0)+u; }));
  const evMs=Object.keys(evTotal).sort();
  const fuelRows=Object.entries(fuel).map(([k,v])=>`<tr><td>${esc(k)}</td><td class="num">${num(v.units)}</td><td class="num">${v.share}%</td></tr>`).join('');
  const buyerRows=Object.entries(buyer).map(([k,v])=>`<tr><td>${esc(k)}</td><td class="num">${num(v.units)}</td><td class="num">${v.share}%</td></tr>`).join('');
  const zk=(D.ev&&D.ev.brands&&D.ev.brands['Zeekr'])||{}; const zkShare={}; Object.keys(zk).forEach(m=>{ if(evTotal[m]) zkShare[m]=+(100*zk[m]/evTotal[m]).toFixed(2); });
  const brands=(D.ev&&D.ev.brands)||{}; const topBrands=Object.entries(brands).filter(([n])=>!/^total/i.test(n)).sort((a,b)=>(b[1][latest]||0)-(a[1][latest]||0)).slice(0,10);
  const brandRows=topBrands.map(([b,o])=>`<tr><td><b>${esc(b)}</b></td>${evMs.map(m=>`<td class="num">${num(o[m])}</td>`).join('')}<td class="num"><b>${num(Object.values(o).reduce((a,x)=>a+x,0))}</b></td></tr>`).join('');
  // ---- per ZEEKR model groups
  const tierOrder={core:0,reference:1,watch:2};
  const groups=D.zeekr.models.map(zm=>{
    const comps=D.comps.competitors.filter(c=>c.zeekr.includes(zm.key)).sort((a,b)=>tierOrder[a.tier]-tierOrder[b.tier]);
    const rows=[]; const zs=seriesFor(zm.key,true); rows.push({label:zm.name, s:zs, isZ:true, tier:''});
    comps.forEach(c=>{ const s=seriesFor(c.id,false); rows.push({label:`${c.brand} ${tx(c,'model')}`, s, tier:c.tier, c}); });
    const mom = s => { const have=ms.filter(m=>s.months[m]!=null); if(have.length<2) return null; const a=s.months[have[have.length-2]], b=s.months[have[have.length-1]]; return a>0 ? (b/a-1)*100 : null; };
    const tbl=rows.map(r=>{ const mm=mom(r.s); return `<tr${r.isZ?' style="background:var(--green4)"':''}><td style="white-space:nowrap"><b>${esc(r.label)}</b>${r.tier?` <span class="badge b-${r.tier}">${T('tier_'+r.tier)}</span>`:''}</td><td>${srcTag(r.s.src)}</td>${ms.map(m=>`<td class="num">${num(r.s.months[m])}</td>`).join('')}<td class="num"><b>${num(r.s.ytd)}</b></td><td class="num ${mm>0?'delta-pos':mm<0?'delta-neg':''}">${pct(mm)}</td><td>${spark(ms,r.s.months)}</td></tr>`; }).join('');
    const chartRows=rows.filter(r=>r.s.src&&Object.keys(r.s.months).length>(r.isZ?0:1)&&Object.values(r.s.months).some(v=>v>0)).sort((a,b)=>(b.isZ?1e9:(b.s.ytd||0))-(a.isZ?1e9:(a.s.ytd||0))).slice(0,7).map((r,i)=>({label:r.label, months:r.s.months, color:r.isZ?'var(--ink)':PALETTE[i%PALETTE.length], bold:r.isZ}));
    return `<div class="card" style="margin-top:12px"><div class="model-head"><h2 style="margin:0">${esc(zm.name)}</h2><span class="band">${esc(zh()?zm.segment:zm.segment_en)}</span></div>
      <div class="twrap hint" data-hint="${zh()?'表格可左右滑动':'Swipe sideways to see more'}"><table class="sticky"><thead><tr><th>${zh()?'车型':'Model'}</th><th>${zh()?'口径':'Basis'}</th>${ms.map(m=>`<th class="num">${MON(+m.slice(5))}</th>`).join('')}<th class="num">YTD</th><th class="num">${zh()?'环比':'MoM'}</th><th>${zh()?'走势':'Trend'}</th></tr></thead><tbody>${tbl}</tbody></table></div>
      ${chartRows.length?`<h3>${zh()?'月度交付量走势':'Monthly deliveries'}</h3>${lineChart(chartRows, ms)}`:`<div class="small">${zh()?'该车型尚未上市，无交付数据。':'Not yet on sale; no deliveries reported.'}</div>`}</div>`;
  }).join('');
  el.innerHTML=`<div class="note">${zh()
    ? `交付量 = VFACTS / EVC 月度上报销量（CarExpert New Car Sales Atlas，每月初随 VFACTS 发布，抓取程序每 30 分钟检查并在新月份发布后自动入库）；纯电车型的逐月历史来自 The Driven 的 2026 年纯电月度表。标注"合并"的车型为 VFACTS 将燃油与纯电版本合并申报；smart、Lexus LM、未上市车型无申报数据。最新月份：${esc(L.label)}，全市场 ${num(L.total)} 台。`
    : `Deliveries = monthly VFACTS / EVC reported sales (CarExpert New Car Sales Atlas, published with VFACTS at the start of each month; the collector checks every 30 minutes and stores a new month as soon as it appears). Month-by-month history for BEVs comes from The Driven's 2026 BEV monthly table. "ICE+EV" marks lines VFACTS reports combined; smart, Lexus LM and unreleased models have no reported data. Latest month: ${esc(L.label)}, market total ${num(L.total)}.`}</div>
  <div class="grid two">
    <div class="card"><h2>${zh()?'纯电（BEV）月度交付量 · 2026':'BEV deliveries by month · 2026'}</h2>${lineChart([{label:zh()?'全澳 BEV 合计':'Australia BEV total', months:evTotal, color:'#2F6B4F', bold:true}], evMs, 0)}
      <h3>${zh()?'ZEEKR 月度纯电交付与份额':'ZEEKR monthly BEV deliveries and share'}</h3>${lineChart([{label:zh()?'ZEEKR 交付量':'ZEEKR deliveries', months:zk, color:'var(--ink)', bold:true}], evMs, 0)}<div class="small" style="margin-top:4px">${zh()?'ZEEKR 占全澳 BEV 份额：':'ZEEKR share of Australian BEV: '}${evMs.map(m=>`${MON(+m.slice(5))} ${zkShare[m]!=null?zkShare[m]+'%':'—'}`).join(' · ')}</div>
      <h3>${zh()?'品牌 BEV 月度（前 10）':'BEV by brand (top 10)'}</h3><div class="twrap"><table class="sticky"><thead><tr><th>${zh()?'品牌':'Brand'}</th>${evMs.map(m=>`<th class="num">${MON(+m.slice(5))}</th>`).join('')}<th class="num">YTD</th></tr></thead><tbody>${brandRows}</tbody></table></div></div>
    <div class="card"><h2>${esc(L.label)} · ${zh()?'全市场结构':'Market structure'}</h2>
      <h3>${zh()?'燃料类型':'Fuel mix'}</h3><div class="twrap"><table><thead><tr><th>${zh()?'类型':'Type'}</th><th class="num">${zh()?'台数':'Units'}</th><th class="num">${zh()?'份额':'Share'}</th></tr></thead><tbody>${fuelRows}</tbody></table></div>
      <h3>${zh()?'买家类型（VFACTS 口径）':'Buyer type (VFACTS)'}</h3><div class="twrap"><table><thead><tr><th>${zh()?'类型':'Type'}</th><th class="num">${zh()?'台数':'Units'}</th><th class="num">${zh()?'份额':'Share'}</th></tr></thead><tbody>${buyerRows}</tbody></table></div>
      <div class="small">${zh()?'来源：':'Source: '}<a href="${esc(L.source)}" target="_blank" rel="noopener">CarExpert New Car Sales Atlas</a> · ${fmtTime(L.fetched)}${D.ev?` · <a href="${esc(D.ev.source)}" target="_blank" rel="noopener">The Driven</a> ${fmtTime(D.ev.updated)}`:''}</div></div>
  </div>
  ${groups}`;
};
})();
