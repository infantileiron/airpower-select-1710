from fastapi import HTTPException
from src.models.entities import Run,Tariff,Pilot,Settlement

def ensure_run(s,i):
 row=s.get(Run,i)
 if not row:raise HTTPException(404,'模型版本不存在')
 return row
def ensure_tariff(s,i):
 row=s.get(Tariff,i)
 if not row:raise HTTPException(404,'电价时段不存在')
 return row
def ensure_pilot(s,i):
 row=s.get(Pilot,i)
 if not row:raise HTTPException(404,'节能试点不存在')
 return row
def ensure_settlement(s,i):
 row=s.get(Settlement,i)
 if not row:raise HTTPException(404,'结算单不存在')
 return row
