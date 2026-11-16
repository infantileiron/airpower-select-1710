import os
os.environ.setdefault('DATABASE_URL','sqlite:////tmp/airpower_settlement_test.db')
os.environ.setdefault('REDIS_URL','redis://localhost:6379/0')
os.environ.setdefault('JWT_SECRET','test-secret-3110')
import math,random
from datetime import datetime,timedelta
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from src.config.database import Base
from src.models import entities
from src.models.entities import User,Sample,Run,Tariff,Pilot,Settlement,SettlementHour
from src.services.analysis import choose
from src.utils.security import hash_password,token
import src.config.database as dbmod
from src.main import app
from src.routes.api import db as api_db
from src.routes.settlement import db as st_db
ENGINE=create_engine('sqlite:////tmp/airpower_settlement_test.db',connect_args={'check_same_thread':False,'timeout':30})
TEST_SESSION=sessionmaker(bind=ENGINE,expire_on_commit=False)
@pytest.fixture()
def session():
 Base.metadata.drop_all(ENGINE);Base.metadata.create_all(ENGINE)
 with TEST_SESSION() as s:
  for role in ('admin','analyst','viewer'):
   s.add(User(email=role+'@demo.local',role=role,password=hash_password('Demo123!')))
  s.commit();yield s
def override_db():
 with TEST_SESSION() as s:yield s
app.dependency_overrides[api_db]=override_db
app.dependency_overrides[st_db]=override_db
@pytest.fixture()
def client():
 with TestClient(app) as c:yield c
def auth(s,role='analyst'):
 u=s.query(User).filter_by(email=role+'@demo.local').first()
 return {'Authorization':'Bearer '+token(u)}
# ---------- 构造数据：60小时连续样本 + 成功模型版本 ----------
def make_samples(s,n=60,seed=7):
 rng=random.Random(seed);rows=[]
 for i in range(n):
  hour=(datetime(2026,11,1)+timedelta(hours=i)).strftime('%Y-%m-%dT%H:00')
  flow=round(8+3*math.sin(i*math.pi/12)+rng.uniform(-1,1),3);pressure=round(rng.uniform(5.8,7.5),3)
  temp=round(22+5*math.sin(i*math.pi/12)+rng.uniform(-2,2),3);machines=2+i%4;noise=round(rng.uniform(-3,3),3)
  kwh=round(40+14*flow+5*machines+2*pressure+.15*temp+rng.gauss(0,2.5),3)
  r=Sample(hour=hour,flow=flow,pressure=pressure,temperature=temp,machines=machines,sensor_noise=noise,kwh=kwh,note='test')
  s.add(r);rows.append({'hour':hour,'flow':flow,'pressure':pressure,'temperature':temp,'machines':machines,'sensor_noise':noise,'kwh':kwh})
 s.commit();return rows
def done_run(s,rows):
 result=choose(rows,['pressure','flow','temperature','machines'],[.1,1.,10.])
 run=Run(name='冻结版本',features=['pressure','flow','temperature','machines'],alphas=[.1,1.,10.],state='done',result={**result,'snapshot':rows})
 s.add(run);s.commit();return run
def tariffs_full(s,start,end,peak=1.2,valley=.4):
 # 峰段(偶数小时)与谷段(奇数小时)无缝衔接
 s.add(Tariff(name='峰段',start_hour=start,end_hour=end,price=peak))
 s.commit();p=s.query(Tariff).first()
 # 用两个时段覆盖全部小时：前半峰、后半谷，保证不重叠不缺价
 d0=datetime.fromisoformat(start);d1=datetime.fromisoformat(end);mid=(d0+(d1-d0)/2).replace(minute=0,second=0,microsecond=0)
 s.delete(p);s.commit()
 s.add(Tariff(name='峰段',start_hour=start,end_hour=(mid-timedelta(hours=1)).strftime('%Y-%m-%dT%H:00'),price=peak))
 s.add(Tariff(name='谷段',start_hour=mid.strftime('%Y-%m-%dT%H:00'),end_hour=end,price=valley))
 s.commit()
H0,H1='2026-11-02T00:00','2026-11-03T11:00' # 36小时试点窗（样本覆盖11-01起60h）
def fresh_checksum(s,pilot_id):
 p=s.get(Pilot,pilot_id);s.expire_all()
 from src.services.settlement import basis_checksum
 return basis_checksum(s,p)
# ---------- 用例 ----------
def test_settle_success_hourly_and_total(session,client):
 rows=make_samples(session);run=done_run(session,rows);tariffs_full(session,H0,H1)
 h=auth(session)
 p=client.post('/pilots',json={'name':'空载试点','run_id':run.id,'start_hour':H0,'end_hour':H1},headers=h).json()
 r=client.post(f"/pilots/{p['id']}/settle",json={'basis_checksum':p['basis_checksum']},headers=h).json()
 assert r['state']=='settled' and not r['gaps']
 hours=r['hours'];assert len(hours)==36
 expected=sum(round((d['baseline_kwh']-d['actual_kwh'])*d['price'],4) for d in hours)
 assert abs(r['total_amount']-round(expected,4))<1e-6
 assert abs(sum(d['amount'] for d in hours)-r['total_amount'])<1e-6
 detail=client.get(f"/settlements/{r['id']}/hours",headers=h).json()
 assert len(detail)==36 and set(detail[0])=={'settlement_id','hour','baseline_kwh','actual_kwh','saved_kwh','price','amount'}
def test_negative_revenue_counted(session,client):
 rows=make_samples(session);run=done_run(session,rows);tariffs_full(session,H0,H1)
 # 把试点窗内实测耗电整体抬高，制造 saved<0 的负收益小时
 for r in session.query(Sample).filter(Sample.hour>=H0,Sample.hour<=H1).all():r.kwh=r.kwh+50
 session.commit()
 h=auth(session)
 p=client.post('/pilots',json={'name':'负收益试点','run_id':run.id,'start_hour':H0,'end_hour':H1},headers=h).json()
 out=client.post(f"/pilots/{p['id']}/settle",json={'basis_checksum':p['basis_checksum']},headers=h).json()
 assert out['state']=='settled'
 assert any(d['amount']<0 for d in out['hours'])
 assert abs(sum(d['amount'] for d in out['hours'])-out['total_amount'])<1e-6
def test_missing_sample_fails_with_gap(session,client):
 rows=make_samples(session);run=done_run(session,rows);tariffs_full(session,H0,H1)
 session.query(Sample).filter_by(hour='2026-11-02T05:00').delete();session.commit()
 h=auth(session)
 p=client.post('/pilots',json={'name':'缺样本试点','run_id':run.id,'start_hour':H0,'end_hour':H1},headers=h).json()
 r=client.post(f"/pilots/{p['id']}/settle",json={'basis_checksum':p['basis_checksum']},headers=h).json()
 assert r['state']=='failed'
 gap=r['gaps'][0];assert gap['type']=='sample_missing' and gap['hour']=='2026-11-02T05:00'
 assert session.query(SettlementHour).count()==0 # 失败不留半份账
 # 补齐后重试成功，且不重复记账
 miss=dict(hour='2026-11-02T05:00',pressure=6.5,flow=9.0,temperature=22.0,machines=3,sensor_noise=0.0,kwh=200.0,note='补录')
 client.post('/samples',json=miss,headers=h)
 p2=client.get(f"/pilots/{p['id']}",headers=h).json()
 r2=client.post(f"/pilots/{p['id']}/settle",json={'basis_checksum':p2['basis_checksum']},headers=h).json()
 assert r2['state']=='settled'
 assert session.query(Settlement).filter_by(pilot_id=p['id']).count()==2
 assert session.query(SettlementHour).filter_by(settlement_id=r2['id']).count()==36
 assert session.get(Pilot,p['id']).settlement_id==r2['id']
def test_missing_price_and_overlap_fail(session,client):
 rows=make_samples(session);run=done_run(session,rows)
 h=auth(session)
 # 仅覆盖前半段，后半段缺价
 t=client.post('/tariffs',json={'name':'仅峰段','start_hour':H0,'end_hour':'2026-11-02T12:00','price':1.2},headers=h).json()
 p=client.post('/pilots',json={'name':'缺价试点','run_id':run.id,'start_hour':H0,'end_hour':H1},headers=h).json()
 r=client.post(f"/pilots/{p['id']}/settle",json={'basis_checksum':p['basis_checksum']},headers=h).json()
 assert r['state']=='failed'
 assert any(g['type']=='price_missing' for g in r['gaps'])
 # 再加入一个与既有时段重叠的电价
 client.post('/tariffs',json={'name':'重叠时段','start_hour':'2026-11-02T10:00','end_hour':H1,'price':.8},headers=h)
 p2=client.get(f"/pilots/{p['id']}",headers=h).json()
 r2=client.post(f"/pilots/{p['id']}/settle",json={'basis_checksum':p2['basis_checksum']},headers=h).json()
 types={g['type'] for g in r2['gaps']}
 assert 'price_overlap' in types and 'price_missing' in types
def test_retry_settled_is_idempotent_and_immutable(session,client):
 rows=make_samples(session);run=done_run(session,rows);tariffs_full(session,H0,H1)
 h=auth(session)
 p=client.post('/pilots',json={'name':'冻结入账试点','run_id':run.id,'start_hour':H0,'end_hour':H1},headers=h).json()
 r1=client.post(f"/pilots/{p['id']}/settle",json={'basis_checksum':p['basis_checksum']},headers=h).json()
 before=r1['total_amount']
 # 重复结算请求：拒绝，不产生第二份账
 resp=client.post(f"/pilots/{p['id']}/settle",json={'basis_checksum':p['basis_checksum']},headers=h)
 assert resp.status_code==409
 assert session.query(Settlement).filter_by(pilot_id=p['id'],state='settled').count()==1
 # 结算后修订样本与电价，已结算收益不变
 target=session.query(Sample).filter_by(hour=H0).first();target.kwh=target.kwh+30;session.commit()
 t=session.query(Tariff).first();t.price=t.price+0.5;session.commit()
 again=client.post(f"/pilots/{p['id']}/settle",json={'basis_checksum':'whatever'},headers=h)
 assert again.status_code==409
 kept=client.get(f"/settlements/{r1['id']}",headers=h).json()
 assert kept['total_amount']==before and kept['state']=='settled'
def test_stale_basis_checksum_rejected_no_mix(session,client):
 rows=make_samples(session);run=done_run(session,rows);tariffs_full(session,H0,H1)
 h=auth(session)
 p=client.post('/pilots',json={'name':'竞争试点','run_id':run.id,'start_hour':H0,'end_hour':H1},headers=h).json()
 stale=p['basis_checksum']
 # 页面拿到依据后、提交结算前，并发修订先落地
 target=session.query(Sample).filter_by(hour=H0).first();target.kwh=target.kwh+15;session.commit()
 resp=client.post(f"/pilots/{p['id']}/settle",json={'basis_checksum':stale},headers=h)
 assert resp.status_code==409 and '拒绝重算' in resp.json()['detail']
 assert session.query(Settlement).filter_by(pilot_id=p['id']).count()==0 # 拒绝时不留任何单据
 # 用最新完整依据重试成功
 p2=client.get(f"/pilots/{p['id']}",headers=h).json()
 ok=client.post(f"/pilots/{p['id']}/settle",json={'basis_checksum':p2['basis_checksum']},headers=h).json()
 assert ok['state']=='settled'
def test_checksum_scoped_to_pilot_window(session,client):
 rows=make_samples(session);run=done_run(session,rows);tariffs_full(session,H0,H1)
 h=auth(session)
 p=client.post('/pilots',json={'name':'依据作用域试点','run_id':run.id,'start_hour':H0,'end_hour':H1},headers=h).json()
 before=p['basis_checksum']
 # 窗口外的电价修订不改变依据指纹
 out=client.post('/tariffs',json={'name':'无关时段','start_hour':'2026-12-20T00:00','end_hour':'2026-12-20T08:00','price':3.0},headers=h).json()
 after_out=client.get(f"/pilots/{p['id']}",headers=h).json()['basis_checksum']
 assert after_out==before
 client.put(f"/tariffs/{out['id']}",json={'name':'无关时段','start_hour':'2026-12-20T00:00','end_hour':'2026-12-20T08:00','price':1.5},headers=h)
 assert client.get(f"/pilots/{p['id']}",headers=h).json()['basis_checksum']==before
 # 窗口内电价修订改变指纹，旧依据被拒绝
 inside=session.query(Tariff).filter_by(name='峰段').first()
 client.put(f"/tariffs/{inside.id}",json={'name':'峰段','start_hour':inside.start_hour,'end_hour':inside.end_hour,'price':1.7},headers=h)
 assert client.get(f"/pilots/{p['id']}",headers=h).json()['basis_checksum']!=before
 resp=client.post(f"/pilots/{p['id']}/settle",json={'basis_checksum':before},headers=h)
 assert resp.status_code==409
def test_tariff_revision_then_recompute_uses_new_batch(session,client):
 rows=make_samples(session);run=done_run(session,rows);tariffs_full(session,H0,H1,peak=1.0,valley=.5)
 h=auth(session)
 p=client.post('/pilots',json={'name':'电价修订试点','run_id':run.id,'start_hour':H0,'end_hour':H1},headers=h).json()
 r1=client.post(f"/pilots/{p['id']}/settle",json={'basis_checksum':p['basis_checksum']},headers=h).json()
 assert r1['state']=='settled'
 # 新试点验证电价修订后整批重算：另一试点用同一窗口，修订电价后按新价结算
 t=session.query(Tariff).filter_by(name='峰段').first()
 client.put(f"/tariffs/{t.id}",json={'name':'峰段','start_hour':t.start_hour,'end_hour':t.end_hour,'price':2.0},headers=h)
 p2=client.post('/pilots',json={'name':'电价修订试点二','run_id':run.id,'start_hour':H0,'end_hour':H1},headers=h).json()
 r2=client.post(f"/pilots/{p2['id']}/settle",json={'basis_checksum':p2['basis_checksum']},headers=h).json()
 # 峰段小时单价已变为2.0
 peak_hours=[d for d in r2['hours'] if d['price']==2.0]
 assert peak_hours and all(abs(d['amount']-round(d['saved_kwh']*2.0,4))<1e-6 for d in peak_hours)
def test_pilot_requires_done_run(session,client):
 h=auth(session)
 run=Run(name='未完成',features=['flow'],alphas=[1.],state='queued',result={});session.add(run);session.commit()
 resp=client.post('/pilots',json={'name':'非法试点','run_id':run.id,'start_hour':H0,'end_hour':H1},headers=h)
 assert resp.status_code==409 # 创建即拒绝，未成功版本不能关联试点
 missing=client.post('/pilots',json={'name':'幽灵版本','run_id':9999,'start_hour':H0,'end_hour':H1},headers=h)
 assert missing.status_code==404
def test_concurrent_revision_never_mixes_basis(session,client):
 from src.services.settlement import settle_pilot
 rows=make_samples(session);run=done_run(session,rows);tariffs_full(session,H0,H1)
 h=auth(session)
 p=client.post('/pilots',json={'name':'并发试点','run_id':run.id,'start_hour':H0,'end_hour':H1},headers=h).json()
 import threading
 sA=TEST_SESSION();pilot=sA.get(Pilot,p['id'])
 record,_=settle_pilot(sA,pilot,p['basis_checksum']) # 事务开启、尚未提交
 old_hour=sA.query(SettlementHour).filter_by(settlement_id=record.id,hour=H0).first()
 old_actual=old_hour.actual_kwh
 errors=[]
 def revise():
  try:
   sB=TEST_SESSION();row=sB.query(Sample).filter_by(hour=H0).first()
   row.kwh=row.kwh+25;sB.commit();sB.close()
  except Exception as e:errors.append(e)
 t=threading.Thread(target=revise);t.start();t.join(10)
 sA.commit();sA.close();t.join(10)
 assert not errors and not t.is_alive()
 # 入账逐小时依据固定为修订前数据，修订在结算提交后才落地，二者未混用
 kept=client.get(f"/settlements/{record.id}/hours",headers=h).json()
 assert kept[0]['actual_kwh']==old_actual
 assert session.query(Sample).filter_by(hour=H0).first().kwh==old_actual+25
 assert len(kept)==36 # 完整入账，无半份账
 assert session.query(SettlementHour).filter_by(settlement_id=record.id).count()==36
def test_full_flow_via_login_and_legacy_endpoints(session,client):
 # 真实登录拿 token，串联电价→试点→失败→补齐→成功→幂等，并回归旧接口
 rows=make_samples(session);run=done_run(session,rows)
 login=client.post('/auth/login',json={'email':'analyst@demo.local','password':'Demo123!'}).json()
 h={'Authorization':'Bearer '+login['token']}
 assert client.get('/samples',headers=h).status_code==200
 assert client.get('/runs',headers=h).status_code==200
 assert client.get('/reviews',headers=h).status_code==200
 # 先只建一个不覆盖全程的电价，结算须报缺价
 client.post('/tariffs',json={'name':'峰段','start_hour':H0,'end_hour':'2026-11-02T10:00','price':1.1},headers=h)
 p=client.post('/pilots',json={'name':'端到端试点','run_id':run.id,'start_hour':H0,'end_hour':H1},headers=h).json()
 r=client.post(f"/pilots/{p['id']}/settle",json={'basis_checksum':p['basis_checksum']},headers=h).json()
 assert r['state']=='failed' and any(g['type']=='price_missing' for g in r['gaps'])
 # 补齐谷段覆盖剩余小时（与峰段首尾相接不重叠）
 client.post('/tariffs',json={'name':'谷段','start_hour':'2026-11-02T11:00','end_hour':H1,'price':.45},headers=h)
 p2=client.get(f"/pilots/{p['id']}",headers=h).json()
 ok=client.post(f"/pilots/{p['id']}/settle",json={'basis_checksum':p2['basis_checksum']},headers=h).json()
 assert ok['state']=='settled' and len(ok['hours'])==36
 # 结算单列表与逐小时接口一致
 lst=client.get('/settlements',headers=h).json()
 assert any(x['id']==ok['id'] and x['state']=='settled' for x in lst)
 hrs=client.get(f"/settlements/{ok['id']}/hours",headers=h).json()
 assert len(hrs)==36
 # 再次结算被拒，不重复记账
 assert client.post(f"/pilots/{p['id']}/settle",json={'basis_checksum':p2['basis_checksum']},headers=h).status_code==409
def test_viewer_readonly(session,client):
 rows=make_samples(session);run=done_run(session,rows)
 h=auth(session,'viewer')
 assert client.post('/tariffs',json={'name':'x','start_hour':H0,'end_hour':H1,'price':1.},headers=h).status_code==403
 assert client.get('/tariffs',headers=h).status_code==200
def test_validation_errors(session,client):
 h=auth(session);run=done_run(session,make_samples(session))
 bad=client.post('/pilots',json={'name':'x','run_id':run.id,'start_hour':H1,'end_hour':H0},headers=h)
 assert bad.status_code==422
 bad2=client.post('/tariffs',json={'name':'x','start_hour':H0,'end_hour':H1,'price':-1},headers=h)
 assert bad2.status_code==422
def test_export_only_settled(session,client):
 rows=make_samples(session);run=done_run(session,rows);tariffs_full(session,H0,H1)
 h=auth(session)
 p=client.post('/pilots',json={'name':'导出试点','run_id':run.id,'start_hour':H0,'end_hour':H1},headers=h).json()
 r=client.post(f"/pilots/{p['id']}/settle",json={'basis_checksum':p['basis_checksum']},headers=h).json()
 resp=client.get(f"/settlements/{r['id']}/export",headers=h)
 assert resp.status_code==200 and resp.headers['content-disposition'].endswith(f'airpower-settlement-{r["id"]}.json"')
 payload=resp.json();assert payload['total_amount']==r['total_amount'] and len(payload['hours'])==36
