/* Transaction-price (TP) reference page. Data: data/tp.json (built by monitor/tp.py from config/tp_evidence.json + DAP history). Uses D, lang, esc, fmtTime, fmtMoney, tx, T. */
(function(){
const zh = () => lang==='zh';
const money = v => v==null ? '—' : '$' + Math.round(v).toLocaleString('en-AU');
const pct = v => v==null ? '—' : (v>0?'+':'') + (v*100).toFixed(1) + '%';
const KIND = {
  demo:   {zh:'展车/近新车', en:'Demo / near-new', cls:'b-info',   tip_zh:'经销商展车或近新车挂牌上路价；已上牌、含展车补贴，低于新车成交价，按折算系数上调并以 DAP 封顶', tip_en:'Dealer demo / near-new drive-away asking price; registered and subsidised, so below new-car TP. Uplifted by the conversion factors and capped at DAP'},
  newcar: {zh:'新车·官方优惠', en:'New car · official offer', cls:'b-green', tip_zh:'新车 DAP 减官方现金优惠，或官方 DAP 活动价', tip_en:'New-car DAP less the official cash offer, or the official drive-away campaign price'},
  agency: {zh:'固定价格', en:'Fixed price', cls:'b-muted', tip_zh:'直销 / 代理制固定价格，无公开折让：TP = DAP', tip_en:'Direct-sales / agency fixed price, no public discount: TP = DAP'},
  est:    {zh:'估算', en:'Estimate', cls:'b-medium', tip_zh:'无证据：TP = DAP × 随机系数（0.92–0.96，固定种子）', tip_en:'No evidence: TP = DAP x seeded random factor (0.92–0.96)'},
};
const CONF = c => !c ? '' : `<span class="badge ${/高/.test(c)?'b-green':/低/.test(c)?'b-low':'b-muted'}">${zh()?c:({'高':'High','中':'Medium','低':'Low','低–中':'Low–Med','—':'—'}[c]||c)}</span>`;
const kindTag = k => { const o=KIND[k]||KIND.est; return `<span class="badge ${o.cls}" title="${esc(zh()?o.tip_zh:o.tip_en)}">${zh()?o.zh:o.en}</span>`; };
let OPEN = {};  // evidence panels open state
window.tpToggle = cid => { OPEN[cid]=!OPEN[cid]; const el=document.getElementById('tpev-'+cid); if(el) el.style.display=OPEN[cid]?'':'none'; const b=document.getElementById('tpbt-'+cid); if(b) b.classList.toggle('active',!!OPEN[cid]); };

function evidenceTable(cid){
  const ev=(D.tp.evidence||{})[cid]; if(!ev||!ev.length) return '';
  const rows=ev.map(e=>`<tr><td>${esc(e.variant||'')}</td><td style="min-width:220px;max-width:420px">${esc(e.price||'')}</td><td>${esc(e.price_type||'')}</td><td style="white-space:nowrap">${esc(e.date||'')}</td><td>${esc(e.state||'')}</td><td class="num">${e.km!=null&&e.km!==''?esc(e.km):''}</td><td class="small">${esc(e.note||'')}</td><td>${e.source_url?`<a href="${esc(e.source_url)}" target="_blank" rel="noopener">${zh()?'来源':'source'}</a>`:''}</td></tr>`).join('');
  return `<div id="tpev-${cid}" style="display:${OPEN[cid]?'':'none'};margin-top:8px"><div class="twrap"><table><thead><tr><th>${zh()?'版本':'Variant'}</th><th>${zh()?'价格':'Price'}</th><th>${zh()?'类型':'Type'}</th><th>${zh()?'日期':'Date'}</th><th>${zh()?'州':'State'}</th><th class="num">km</th><th>${zh()?'说明':'Note'}</th><th></th></tr></thead><tbody>${rows}</tbody></table></div></div>`;
}

function groupCard(zkey){
  const rows=(D.tp.groups||{})[zkey]||[]; const own=(D.tp.own||[]).filter(r=>r.zeekr[0]===zkey);
  const zm=(D.zeekr.models||[]).find(m=>m.key===zkey)||{name:'ZEEKR '+zkey};
  const sm=(D.tp.summary||{})[zkey]||{};
  if(!rows.length) return '';
  const tr=(r,isOwn)=>{
    const disc=r.disc_dap; const cls=disc<-0.001?'delta-neg':disc>0.001?'delta-pos':'';
    const name=isOwn?`<b>${esc(r.model)}</b> ${esc(r.variant)}`:`<b>${esc(r.brand)} ${esc(tx(r,'model'))}</b><br><span class="small">${esc(tx(r,'variant'))}</span>`;
    const tier=isOwn?'':(r.tier?` <span class="badge b-${r.tier}">${T('tier_'+r.tier)}</span>`:'');
    const tp=r.kind==='demo'&&r.tp_low!=null&&r.tp_low!==r.tp_high?`<b>${money(r.tp)}</b><br><span class="small">${money(r.tp_low)} – ${money(r.tp_high)}</span>`:`<b>${money(r.tp)}</b>`;
    return `<tr${isOwn?' style="background:var(--green4)"':''}><td style="min-width:150px">${name}${tier}</td><td class="num">${money(r.msrp)}</td><td class="num" title="${esc(tx(r,'dap_src')||'')}">${money(r.dap)}${/估算|Estimate/.test(r.dap_src||'')?'<span class="small" title="'+(zh()?'DAP 为 MSRP + NSW 上路费用估算':'DAP estimated as MSRP + NSW on-roads')+'">*</span>':''}</td><td class="num">${tp}</td><td class="num ${cls}">${pct(r.disc_dap)}</td><td class="num">${pct(r.disc_msrp)}</td><td>${isOwn?`<span class="badge b-green">${zh()?'本品':'Own'}</span>`:CONF(r.confidence)}</td></tr>`;
  };
  const cids=[...new Set(rows.map(r=>r.cid))].filter(c=>(D.tp.evidence||{})[c]);
  const evBtns=cids.length?`<div class="chips" style="margin-top:10px">${cids.map(c=>{ const r=rows.find(x=>x.cid===c); return `<button class="btn${OPEN[c]?' active':''}" id="tpbt-${c}" onclick="tpToggle('${c}')">${zh()?'证据明细':'Evidence'} · ${esc(r.brand)} ${esc(tx(r,'model'))} (${(D.tp.evidence[c]||[]).length})</button>`; }).join('')}</div>${cids.map(evidenceTable).join('')}`:'';
  const med=sm.median_disc_evidence!=null?pct(sm.median_disc_evidence):'—';
  return `<div class="card" style="margin-top:12px"><div class="model-head"><h2 style="margin:0">${esc(zm.name)}</h2><span class="band">${esc(zh()?(zm.segment||''):(zm.segment_en||zm.segment||''))}</span>
    <span class="small" style="margin-left:auto">${zh()?`${sm.n} 个版本 · 有证据 ${sm.n_evidence} · 固定价格 ${sm.n_agency} · 估算 ${sm.n_est} · 有证据版本较 DAP 折扣中位数 ${med}`:`${sm.n} variants · evidence ${sm.n_evidence} · fixed price ${sm.n_agency} · estimates ${sm.n_est} · median discount vs DAP (evidence rows) ${med}`}</span></div>
    <div class="small" style="margin:6px 0 2px">${zh()?'排序：对标强度（直接对标 › 价格参照 › 观察）→ 置信度（高 › 中 › 低–中 › 低）':'Sorted by benchmark strength (core › reference › watch), then confidence (high › medium › low–medium › low)'}</div>
    <div class="twrap hint" data-hint="${zh()?'表格可左右滑动':'Swipe sideways to see more'}"><table class="sticky"><thead><tr><th>${zh()?'车型 / 版本':'Model / variant'}</th><th class="num">MSRP</th><th class="num">DAP</th><th class="num">${zh()?'估计均值 TP':'Estimated mean TP'}</th><th class="num">${zh()?'较 DAP':'vs DAP'}</th><th class="num">${zh()?'较 MSRP':'vs MSRP'}</th><th>${zh()?'置信度':'Confidence'}</th></tr></thead>
    <tbody>${own.map(r=>tr(r,true)).join('')}${rows.map(r=>tr(r,false)).join('')}</tbody></table></div>${evBtns}</div>`;
}

window.renderTP = function(){
  const el=document.getElementById('tp'); if(!el) return;
  if(!D.tp||!D.tp.groups){ el.innerHTML=`<div class="card"><div class="small">${zh()?'尚无成交价数据（data/tp.json 未生成）。':'No transaction-price data yet (data/tp.json not generated).'}</div></div>`; return; }
  const p=D.tp.params||{}; const order=['X','7X','7GT','009','8X','9X'];
  const all=Object.values(D.tp.groups).flat(); const uniq=new Map(); all.forEach(r=>uniq.set(r.cid+'|'+r.variant,r)); const U=[...uniq.values()];
  const cnt=k=>U.filter(r=>r.kind===k).length;
  const kpi=(v,l,cls='')=>`<div class="kpi card ${cls}"><div class="v">${v}</div><div class="l">${l}</div></div>`;
  el.innerHTML=`<div class="note">${zh()
    ? `澳洲没有公开的新车真实成交价数据集。本页按统一方法给出<b>新车成交价（TP）参考</b>：① 有经销商展车 / 近新车挂牌上路价的版本，按展车价 × ${p.uplift_low}–${p.uplift_high}（补回上牌贬值与展车补贴）折算为新车价，并以 DAP 封顶；② 有官方现金优惠或 DAP 活动价的版本，取 DAP 减优惠；③ 直销 / 代理制品牌（Tesla、Polestar、smart、奔驰新车）按固定价格计，TP = DAP；④ 其余无证据版本按 DAP × 0.92–0.96 随机系数估算（固定种子，每次运行结果一致）。DAP 优先取 The Beep 的 NSW 上路价，其次为 MSRP + NSW 上路费用估算（标 *）。证据库人工维护于 <span class="tag">config/tp_evidence.json</span>，证据截至 ${esc(D.tp.as_of||'')}；DAP 随抓取程序每 30 分钟更新。挂牌价为要价，实际成交通常再低 1%–3%。`
    : `Australia has no public dataset of new-car settled prices. This page applies one method to every competitor variant to give a <b>new-car transaction-price (TP) reference</b>: (1) where dealer demo / near-new drive-away asking prices exist, the asking price is converted to a new-car price with factors ${p.uplift_low}–${p.uplift_high} (adding back registration depreciation and demo subsidy) and capped at DAP; (2) where an official cash offer or drive-away campaign exists, DAP less the offer; (3) direct-sales / agency brands (Tesla, Polestar, smart, Mercedes-Benz new cars) are taken at fixed price, TP = DAP; (4) all other variants are estimated as DAP x a seeded random factor of 0.92–0.96. DAP is The Beep's NSW drive-away where available, otherwise MSRP + NSW on-roads (marked *). The evidence file is maintained by hand in <span class="tag">config/tp_evidence.json</span>, evidence as of ${esc(D.tp.as_of||'')}; DAP refreshes with the collector every 30 minutes. Asking prices are offers to sell; settled prices usually sit a further 1–3% lower.`}</div>
  <div class="grid kpis">${kpi(U.length, zh()?'竞品版本数':'Competitor variants')}${kpi(cnt('demo')+cnt('newcar'), zh()?'有价格证据的版本':'Variants with price evidence','ok')}${kpi(cnt('agency'), zh()?'固定价格（TP = DAP）':'Fixed price (TP = DAP)','info')}${kpi(cnt('est'), zh()?'随机估算（待补证据）':'Random estimates (evidence wanted)','warn')}</div>
  ${order.map(groupCard).join('')}
  <div class="card" style="margin-top:12px"><h2>${zh()?'口径说明':'Method notes'}</h2><ul class="small">
    <li>${zh()?'展车 / 近新车挂牌价来自 carsales、CarsGuide、Drive、品牌官方二手站（经销商挂牌，含上路费用）。这些站点禁止自动抓取，证据由人工采集后写入证据库，并非实时。':'Demo / near-new asking prices come from carsales, CarsGuide, Drive and brand-certified used sites (dealer listings, drive-away). Those sites block automated collection, so the evidence is gathered by hand and is not live.'}</li>
    <li>${zh()?'官方优惠来自品牌官网与 The Beep / Zecar 的政策页，按 DAP 扣减；库存车限时折让（如 Tesla 10 月约 5%）到期后不计入。':'Official offers come from brand sites and The Beep / Zecar offer pages and are deducted from DAP; expired inventory discounts (e.g. Tesla, about 5% in October) are not carried forward.'}</li>
    <li>${zh()?'奔驰 GLE / GLS、宝马 X5 处于换代清库期，展车折扣明显高于常态；作长期定价对标时建议另按 −5% 至 −8% 设情景。':'Mercedes-Benz GLE / GLS and BMW X5 are in run-out ahead of new generations, so demo discounts are well above normal; for long-run benchmarking a −5% to −8% scenario is more representative.'}</li>
    <li>${zh()?'折算系数与随机区间可在证据库 params 中调整；更新证据只需在对应车型下增加 variants / offer 条目，站点下次运行自动重算。':'Conversion factors and the random range are set in the params block of the evidence file; to add evidence, append variants / offer entries under the model and the next run recalculates the page.'}</li>
  </ul><div class="small">${zh()?'生成于':'Generated'} ${fmtTime(D.tp.generated)}</div></div>`;
};
})();
