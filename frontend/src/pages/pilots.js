import {api,post} from '../api/client.js';
import {state} from '../stores/session.js';
import {esc} from '../utils/html.js';
import {badge} from '../components/common/status.js';
import {field,select} from '../components/common/fields.js';
import {table} from '../components/common/table.js';
import {GAP_TYPES} from '../constants/enums.js';
const short=v=>v?String(v).slice(0,10)+'…':'';
const money=v=>(v<0?'-':'')+'¥'+Math.abs(v).toFixed(4);
function tariff_block(){
 return `<h3>分时电价（按生效时段）</h3><p class="notice">电价时段不得重叠；试点每个小时须恰好命中一个电价，否则结算失败并列出缺口。结算期间修订会与结算互斥，依据变化后须用最新整批依据重试。</p>${table(['ID','名称','生效起','生效止','电价 ¥/kWh'],state.tariffs.map(t=>[t.id,t.name,t.start_hour,t.end_hour,t.price.toFixed(4)]))}`;
}
function pilot_article(p){
 const readonly=state.user.role==='viewer';
 const settled=p.settlement_id&&state.settlements.find(x=>x.id===p.settlement_id)?.state==='settled';
 let line='<p class="eyebrow">尚未结算</p>';
 if(p.settlement_id){
  const st=state.settlements.find(x=>x.id===p.settlement_id);
  if(st)line=st.state==='settled'?`<p class="notice">已结算入账：节电量 ${st.total_kwh} kWh / 收益 ${money(st.total_amount)} · 单据 #${st.id} · 依据 ${short(st.basis_checksum)}</p>`:`<p class="error">结算失败：${st.gaps.length} 项缺口 · 单据 #${st.id} · 补齐后可重试</p>`;
 }
 return `<article class="rec"><h3>${esc(p.name)} ${badge(p.settlement_id?'已关联单据':'待结算')}</h3><p>成功模型版本 #${p.run_id} · 试点 ${esc(p.start_hour)} 至 ${esc(p.end_hour)}</p><p class="member-line">当前依据指纹 ${esc(p.basis_checksum)}</p>${line}<p><button data-pilot="${p.id}">核对明细</button> <button data-settle="${p.id}" ${readonly||settled?'disabled':''}>${readonly?'观察员只读':settled?'已入账不可重算':p.settlement_id?'补齐后重试结算':'发起结算'}</button></p></article>`;
}
function detail_block(){
 const d=state.pilotDetail;if(!d)return '';
 const st=d.settlement;
 if(!st)return `<h3>试点 #${d.id} 依据预览</h3><p class="notice">窗口共 ${d.hours.length} 个整点小时；当前依据指纹 ${esc(d.basis_checksum)}。发起结算将按冻结模型参数逐小时计算基准耗电。</p>`;
 if(st.state==='failed')return `<h3>结算单据 #${st.id} · 失败缺口</h3><p class="error">本次未入账、不留半份账；补齐下列缺口后重试。</p>${table(['缺口类型','小时','说明'],st.gaps.map(g=>[GAP_TYPES[g.type]||g.type,g.hour,g.detail]))}<p class="member-line">依据指纹 ${esc(st.basis_checksum)}</p>`;
 return `<h3>结算单据 #${st.id} · 逐小时入账依据</h3><p class="notice">基准耗电由成功版本冻结参数（原单位系数+截距）按当小时工况计算；节电=基准−实测，乘以当小时电价，负收益照计。合计为逐小时之和，已入账收益不随后续修订变化。</p>${table(['小时','基准kWh','实测kWh','节电kWh','电价','收益'],st.hours.map(x=>[x.hour,x.baseline_kwh,x.actual_kwh,x.saved_kwh,x.price,money(x.amount)]))}<div class="metrics"><div><strong>${st.total_kwh}</strong>合计节电 / kWh</div><div><strong>${money(st.total_amount)}</strong>合计收益</div></div><p class="member-line">依据指纹 ${esc(st.basis_checksum)}</p><button data-settlement-export="${st.id}">导出结算单据</button>`;
}
export function render(){
 const done=state.runs.filter(r=>r.state==='done');
 return `<div class="split"><section class="panel"><h2>节能试点 · 分时电价收益结算</h2><p class="notice">试点须关联计算成功（done）的模型版本。基准耗电用该版本冻结系数按试点各小时工况重算；与实测之差乘当小时电价，负收益照计。样本缺小时、电价缺价或重叠都会令结算失败并列出缺口。</p>${tariff_block()}<h3 style="margin-top:26px">试点列表</h3>${state.pilots.map(pilot_article).join('')||'<p>尚无试点。在右侧创建第一个试点。</p>'}${detail_block()}</section><aside class="side"><h2>维护分时电价</h2><form id="tariff">${field('电价ID（修订时填写）','record_id','number','min=1')}${field('时段名称','name','text','required placeholder=峰段/谷段')}${field('生效起（整点）','start_hour','datetime-local','required step=3600')}${field('生效止（整点，含）','end_hour','datetime-local','required step=3600')}${field('电价 / ¥每kWh','price','number','required min=0 max=100 step=0.0001')}<button class="primary">保存电价时段</button></form><h2 style="margin-top:24px">创建节能试点</h2><form id="pilot">${field('试点名称','name','text','required')}${select('关联成功模型版本','run_id',done.map(r=>[r.id,'#'+r.id+' '+r.name]))}${field('试点起（整点）','start_hour','datetime-local','required step=3600')}${field('试点止（整点，含）','end_hour','datetime-local','required step=3600')}<button class="primary" ${done.length?'':'disabled'}>${done.length?'创建试点':'先完成模型计算'}</button></form></aside></div>`;
}
export async function bind(run,load,renderAll,feedback){
 document.querySelectorAll('[data-pilot]').forEach(b=>b.onclick=()=>run(async()=>{state.pilotDetail=await api('/pilots/'+b.dataset.pilot);renderAll()}));
 document.querySelectorAll('[data-settle]').forEach(b=>b.onclick=()=>run(async()=>{
  if(b.disabled)return;
  const pilot=state.pilots.find(x=>x.id===Number(b.dataset.settle));
  try{await post('/pilots/'+pilot.id+'/settle',{basis_checksum:pilot.basis_checksum});}
  catch(e){await load();renderAll();throw e}
  await load();state.pilotDetail=await api('/pilots/'+pilot.id);renderAll();
 }));
 document.querySelectorAll('[data-settlement-export]').forEach(b=>b.onclick=()=>run(async()=>{
  const d=await api('/settlements/'+b.dataset.settlementExport+'/export');
  const u=URL.createObjectURL(new Blob([JSON.stringify(d,null,2)],{type:'application/json'}));
  const a=document.createElement('a');a.href=u;a.download='airpower-settlement-'+b.dataset.settlementExport+'.json';a.click();URL.revokeObjectURL(u);
 }));
 for(const id of ['tariff','pilot']){
  const f=document.getElementById(id);if(!f)continue;
  f.onsubmit=e=>{e.preventDefault();run(async()=>{
   const d=Object.fromEntries(new FormData(f));
   for(const k of ['record_id','price','run_id'])if(k in d&&d[k]!=='')d[k]=Number(d[k]);
   const record=d.record_id;delete d.record_id;
   if(id==='tariff'){record?await api('/tariffs/'+record,{method:'PUT',body:JSON.stringify(d)}):await post('/tariffs',d)}
   else await post('/pilots',d);
   await load();renderAll();
  })};
 }
}
