from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from geoalchemy2.shape import to_shape
from geoalchemy2.functions import ST_AsGeoJSON
from shapely.geometry import mapping

# 数据库连接URL
DATABASE_URL = "postgresql://gis:123456@localhost:5432/gisdb"

# 创建数据库引擎
engine = create_engine(
  DATABASE_URL,
  echo=False,
  pool_pre_ping=True,
  connect_args={
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 5,
  },
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

  def to_geojson(self):
    geometry = None

    if self.geom is not None:
      geometry = mapping(to_shape(self.geom))

    return {
      "type": "Feature",
      "id": self.id,
      "geometry": geometry,
      "properties": self.properties or {}
    }

# 获取会话
def get_session():
  return SessionLocal()


# crud.py
# 添加数据