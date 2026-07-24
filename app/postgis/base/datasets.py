from sqlalchemy import String, Integer, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from geoalchemy2 import Geometry
from datetime import datetime
from postgis.database import Base

class Dataset(Base):
  __tablename__ = "datasets"

  id: Mapped[int] = mapped_column(primary_key=True)

  name: Mapped[str] = mapped_column(String(255), nullable=False)

  code: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

  srid: Mapped[str] = mapped_column(String(255), nullable=False)

  description: Mapped[str] = mapped_column(Text)

  mapping: Mapped[dict] = mapped_column(JSONB, default={})

  created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now())