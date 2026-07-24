from sqlalchemy import text
from postgis.database import engine
from postgis.base.datasets import Dataset
from postgis.base.features import Feature

class DatabaseInitializer:

   def __init__(self):
      print("开始初始化数据库...")

      self.create_extension()

      self.create_tables()

      # self.create_indexes()

      print("数据库初始化完成")

   # ==========================
   # PostGIS扩展
   # ==========================
   def create_extension(self):

      with engine.begin() as conn:

         conn.execute(text("""
            CREATE EXTENSION IF NOT EXISTS postgis;
         """))

   # ==========================
   # 创建表
   # ==========================
   def create_tables(self):
      Dataset.metadata.create_all(bind=engine)
      Feature.metadata.create_all(bind=engine)
