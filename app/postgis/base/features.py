from sqlalchemy import String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from geoalchemy2 import Geometry
from datetime import datetime
from postgis.database import Base
from geoalchemy2.shape import to_shape

class Feature(Base):
  __tablename__ = "features"

  id: Mapped[int] = mapped_column(primary_key=True)

  dataset_id: Mapped[int] = mapped_column(Integer, index=True)

  geom = mapped_column(
    Geometry(
      geometry_type="Geometry",
      srid=4326
    )
  )

  properties = mapped_column(JSONB)

  created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())

  updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())

  def to_dict(self):

    result = {}

    for column in self.__table__.columns:
      value = getattr(self, column.name)
      # geom 特殊处理
      if column.name == "geom" and value is not None:
        value = to_shape(value).wkt
        # 例如：POINT(116 39)
      
      result[column.name] = value
    return result