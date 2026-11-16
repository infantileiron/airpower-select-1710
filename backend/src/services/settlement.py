import json,hashlib
from datetime import datetime,timedelta,timezone
from fastapi import HTTPException
from src.models.entities import Sample,Tariff,Pilot,Run,Settlement,SettlementHour
HOUR_FMT='%Y-%m-%dT%H:00'
def parse_hour(v):return datetime.strptime(v,HOUR_FMT)
def period_hours(start,end):
 d0,d1=parse_hour(start),parse_hour(end)
 if d1<=d0:raise HTTPException(422,'结束小时须晚于开始小时')
 n=int((d1-d0).total_seconds()//3600)+1
 return [(d0+timedelta(hours=i)).strftime(HOUR_FMT) for i in range(n)]
def dump_columns(row):
 return {c.name:getattr(row,c.name) for c in row.__table__.columns}
def window_tariffs(s,pilot):
 d0,d1=parse_hour(pilot.start_hour),parse_hour(pilot.end_hour)
 return [t for t in s.query(Tariff).order_by(Tariff.id).all() if parse_hour(t.start_hour)<=d1 and parse_hour(t.end_hour)>=d0]
def basis_checksum(s,pilot):
 # 同一批完整依据的指纹：试点时段内的全部样本与窗口重叠的全部生效电价，按主键排序、固定列序
 samples=[dump_columns(r) for r in s.query(Sample).filter(Sample.hour>=pilot.start_hour,Sample.hour<=pilot.end_hour).order_by(Sample.hour).all()]
 tariffs=[dump_columns(r) for r in window_tariffs(s,pilot)]
 payload={'pilot_id':pilot.id,'start':pilot.start_hour,'end':pilot.end_hour,'samples':samples,'tariffs':tariffs}
 return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False,default=str).encode()).hexdigest()
def find_gaps(hours,sample_map,tariffs):
 gaps=[]
 for h in hours:
  if h not in sample_map:gaps.append({'type':'sample_missing','hour':h,'detail':'该小时缺少实测样本，不得把缺失耗电当作零'})
 spans=sorted((parse_hour(t.start_hour),parse_hour(t.end_hour),t) for t in tariffs)
 for a,b in zip(spans,spans[1:]):
  if b[0]<=a[1]:
   h=max(a[0],b[0]).strftime(HOUR_FMT)
   gaps.append({'type':'price_overlap','hour':h,'detail':f"电价时段重叠：#{a[2].id}「{a[2].name}」与 #{b[2].id}「{b[2].name}」"})
 def price_at(h):
  d=parse_hour(h)
  hit=[t for t in tariffs if parse_hour(t.start_hour)<=d<=parse_hour(t.end_hour)]
  return hit[0] if len(hit)==1 else None
 for h in hours:
  if price_at(h) is None:
   overlap=any(g['type']=='price_overlap' and g['hour']==h for g in gaps)
   if not overlap:gaps.append({'type':'price_missing','hour':h,'detail':'该小时没有唯一生效电价（缺价或多价）'})
 return gaps,price_at
def frozen_baseline(run,hour,sample):
 r=run.result
 coeff={c['feature']:float(c['original_unit']) for c in r['coefficients']}
 base=float(r['intercept_original'])
 return base+sum(coeff[f]*float(getattr(sample,f)) for f in r['features'])
def settle_pilot(s,pilot,client_checksum=''):
 run=s.get(Run,pilot.run_id)
 if run is None or run.state!='done':raise HTTPException(409,'试点须关联计算成功（done）的模型版本')
 # 行级锁定时段内样本与全部电价：并发修订必须等待本事务结束，结算只采用同一批完整依据
 rows=s.query(Sample).filter(Sample.hour>=pilot.start_hour,Sample.hour<=pilot.end_hour).order_by(Sample.hour).with_for_update().all()
 s.query(Tariff).order_by(Tariff.id).with_for_update().all()
 checksum=basis_checksum(s,pilot)
 if client_checksum and client_checksum!=checksum:
  raise HTTPException(409,'结算依据已被修订（样本或电价变化），请刷新后用最新完整依据重试；本次拒绝重算，未混用新旧数据')
 hours=period_hours(pilot.start_hour,pilot.end_hour)
 sample_map={r.hour:r for r in rows}
 tariffs=window_tariffs(s,pilot)
 gaps,price_at=find_gaps(hours,sample_map,tariffs)
 record=Settlement(pilot_id=pilot.id,basis_checksum=checksum,created=datetime.now(timezone.utc).isoformat())
 if gaps:
  record.state='failed';record.gaps=gaps;record.total_kwh=0;record.total_amount=0
  s.add(record);s.flush();pilot.settlement_id=record.id;s.flush()
  return record,[]
 details=[];total_kwh=0.0;total_amount=0.0
 for h in hours:
  sample=sample_map[h];tariff=price_at(h)
  baseline=round(frozen_baseline(run,h,sample),4);actual=round(float(sample.kwh),4);saved=round(baseline-actual,4)
  price=float(tariff.price);amount=round(saved*price,4) # 负收益照计：saved<0 时 amount 为负
  total_kwh+=saved;total_amount+=amount # 合计等于逐小时入账值之和，便于核对
  details.append(SettlementHour(hour=h,baseline_kwh=baseline,actual_kwh=actual,saved_kwh=saved,price=price,amount=amount))
 record.state='settled';record.gaps=[];record.total_kwh=round(total_kwh,4);record.total_amount=round(total_amount,4)
 s.add(record);s.flush()
 for d in details:d.settlement_id=record.id;s.add(d)
 pilot.settlement_id=record.id;s.flush()
 return record,details
def hour_dump(d):
 return {'hour':d.hour,'baseline_kwh':d.baseline_kwh,'actual_kwh':d.actual_kwh,'saved_kwh':d.saved_kwh,'price':d.price,'amount':d.amount}
def settlement_dump(s,record):
 out={c.name:getattr(record,c.name) for c in record.__table__.columns}
 if record.state=='settled':
  out['hours']=[hour_dump(d) for d in s.query(SettlementHour).filter_by(settlement_id=record.id).order_by(SettlementHour.hour).all()]
 return out
