from sqlalchemy import Column,Integer,String,Float,JSON,Text,ForeignKey,UniqueConstraint
from src.config.database import Base
class User(Base):
 __tablename__='users'
 id=Column(Integer,primary_key=True);email=Column(String(100),unique=True);password=Column(String(200));role=Column(String(20))
class Sample(Base):
 __tablename__='samples'
 id=Column(Integer,primary_key=True);hour=Column(String(30),unique=True,nullable=False);pressure=Column(Float);flow=Column(Float);temperature=Column(Float);machines=Column(Integer);sensor_noise=Column(Float);kwh=Column(Float);note=Column(Text,default='')
class Run(Base):
 __tablename__='runs'
 id=Column(Integer,primary_key=True);name=Column(String(100));features=Column(JSON);alphas=Column(JSON);state=Column(String(20),default='queued');result=Column(JSON);error=Column(Text,default='')
class Review(Base):
 __tablename__='reviews'
 id=Column(Integer,primary_key=True);run_id=Column(Integer,ForeignKey('runs.id'));title=Column(String(100));finding=Column(Text);action=Column(Text);status=Column(String(20),default='draft')
class Tariff(Base):
 __tablename__='tariffs'
 id=Column(Integer,primary_key=True);name=Column(String(100));start_hour=Column(String(30),nullable=False);end_hour=Column(String(30),nullable=False);price=Column(Float,nullable=False)
class Pilot(Base):
 __tablename__='pilots'
 # settlement_id 为逻辑关联（无DB外键），避免与 settlements 形成循环外键；指向由服务层保证
 id=Column(Integer,primary_key=True);name=Column(String(100));run_id=Column(Integer,ForeignKey('runs.id'));start_hour=Column(String(30),nullable=False);end_hour=Column(String(30),nullable=False);status=Column(String(20),default='open');settlement_id=Column(Integer,nullable=True)
class Settlement(Base):
 __tablename__='settlements'
 id=Column(Integer,primary_key=True);pilot_id=Column(Integer,ForeignKey('pilots.id'),nullable=False);state=Column(String(20),default='failed');total_kwh=Column(Float,default=0);total_amount=Column(Float,default=0);basis_checksum=Column(String(80),default='');gaps=Column(JSON,default=list);created=Column(String(40))
class SettlementHour(Base):
 __tablename__='settlement_hours'
 __table_args__=(UniqueConstraint('settlement_id','hour',name='uq_settlement_hour'),)
 id=Column(Integer,primary_key=True);settlement_id=Column(Integer,ForeignKey('settlements.id'),nullable=False);hour=Column(String(30),nullable=False);baseline_kwh=Column(Float);actual_kwh=Column(Float);saved_kwh=Column(Float);price=Column(Float);amount=Column(Float)
class Audit(Base):
 __tablename__='audits'
 id=Column(Integer,primary_key=True);actor=Column(String(100));action=Column(String(200));created=Column(String(40))
