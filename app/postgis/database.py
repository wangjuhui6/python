from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# 数据库连接URL
DATABASE_URL = "postgresql://gis:123456@localhost:5432/gisdb"

# 创建数据库引擎
engine = create_engine(
  DATABASE_URL,
  echo=False,
  pool_pre_ping=True
)

# 创建会话
SessionLocal = sessionmaker(
  bind=engine,
  autoflush=False,
  autocommit=False
)

# 创建基类
class Base(DeclarativeBase):
  
  def to_dict(self):
    return {
      c.name: getattr(self, c.name)
      for c in self.__table__.columns
    }

# 获取会话
def get_session():
  return SessionLocal()


# crud.py
# 添加数据