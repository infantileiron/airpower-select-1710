import json
from fastapi import APIRouter,Depends,HTTPException,Response
from sqlalchemy.exc import IntegrityError
from src.config.database import db
from src.models.entities import Tariff,Pilot,Settlement,SettlementHour
from src.schemas.business import TariffInput,PilotInput,SettleInput
from src.middlewares.auth import current,editor
from src.services.business import audit,dump
from src.services.settlement import settle_pilot,settlement_dump,basis_checksum,period_hours
from src.controllers.business import ensure_run,ensure_tariff,ensure_pilot,ensure_settlement
router=APIRouter()
# ---------- 分时电价 ----------
@router.get('/tariffs')
def tariffs(u=Depends(current),s=Depends(db)):return [dump(r) for r in s.query(Tariff).order_by(Tariff.start_hour,Tariff.id).all()]
@router.post('/tariffs')
def create_tariff(data:TariffInput,u=Depends(editor),s=Depends(db)):
 r=Tariff(**data.model_dump());s.add(r)
 try:s.commit()
 except IntegrityError:s.rollback();raise HTTPException(409,'电价时段保存冲突')
 audit(s,u,'维护电价 '+str(r.id));return dump(r)
@router.put('/tariffs/{i}')
def edit_tariff(i:int,data:TariffInput,u=Depends(editor),s=Depends(db)):
 r=ensure_tariff(s,i)
 # 与结算事务相同的全表行锁：电价修订与结算互斥，结算期间修订要么在同一批依据前完成，要么等待后由结算指纹拒绝旧依据
 s.query(Tariff).with_for_update().all()
 for k,v in data.model_dump().items():setattr(r,k,v)
 s.commit();audit(s,u,'修订电价 '+str(i));return dump(r)
# ---------- 节能试点 ----------
@router.get('/pilots')
def pilots(u=Depends(current),s=Depends(db)):
 out=[]
 for r in s.query(Pilot).order_by(Pilot.id.desc()).all():
  d=dump(r);d['basis_checksum']=basis_checksum(s,r);out.append(d)
 return out
@router.post('/pilots')
def create_pilot(data:PilotInput,u=Depends(editor),s=Depends(db)):
 run=ensure_run(s,data.run_id)
 if run.state!='done':raise HTTPException(409,'试点只能关联计算成功（done）的模型版本')
 r=Pilot(**data.model_dump());s.add(r);s.commit();audit(s,u,'创建节能试点 '+str(r.id))
 d=dump(r);d['basis_checksum']=basis_checksum(s,r);return d
@router.get('/pilots/{i}')
def pilot_detail(i:int,u=Depends(current),s=Depends(db)):
 r=ensure_pilot(s,i);d=dump(r);d['basis_checksum']=basis_checksum(s,r);d['hours']=period_hours(r.start_hour,r.end_hour)
 if r.settlement_id:d['settlement']=settlement_dump(s,ensure_settlement(s,r.settlement_id))
 return d
# ---------- 结算 ----------
@router.post('/pilots/{i}/settle')
def settle(i:int,data:SettleInput,u=Depends(editor),s=Depends(db)):
 pilot=ensure_pilot(s,i)
 s.refresh(pilot,with_for_update=True)
 # 重试不重复记账：已结算试点拒绝再次结算，后续修订不改变已入账收益
 if pilot.settlement_id:
  prev=ensure_settlement(s,pilot.settlement_id)
  if prev.state=='settled':raise HTTPException(409,'该试点已结算入账，后续样本/电价修订不再改变已结算收益')
 try:
  record,details=settle_pilot(s,pilot,data.basis_checksum)
  s.commit()
 except HTTPException:
  s.rollback();raise
 except IntegrityError:
  s.rollback();raise HTTPException(409,'结算并发冲突或重复入账，请重试')
 if record.state=='settled':audit(s,u,'试点结算入账 '+str(pilot.id)+' 单据'+str(record.id))
 else:audit(s,u,'试点结算失败(缺口) '+str(pilot.id)+' 单据'+str(record.id))
 return settlement_dump(s,record)
@router.get('/settlements')
def settlements(u=Depends(current),s=Depends(db)):return [settlement_dump(s,r) for r in s.query(Settlement).order_by(Settlement.id.desc()).all()]
@router.get('/settlements/{i}')
def settlement_detail(i:int,u=Depends(current),s=Depends(db)):return settlement_dump(s,ensure_settlement(s,i))
@router.get('/settlements/{i}/hours')
def settlement_hours(i:int,u=Depends(current),s=Depends(db)):
 ensure_settlement(s,i)
 return [{'settlement_id':i,**{c.name:getattr(r,c.name) for c in r.__table__.columns if c.name not in ('id','settlement_id')}} for r in s.query(SettlementHour).filter_by(settlement_id=i).order_by(SettlementHour.hour).all()]
@router.get('/settlements/{i}/export')
def export_settlement(i:int,u=Depends(current),s=Depends(db)):
 r=ensure_settlement(s,i)
 if r.state!='settled':raise HTTPException(409,'仅已结算单据可导出')
 payload=settlement_dump(s,r)
 return Response(json.dumps(payload,ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="airpower-settlement-{i}.json"'})
