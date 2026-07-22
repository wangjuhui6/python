from sqlalchemy import text
from postgis.database import engine

class DatabaseInitializer:

   def __init__(self):
      print("开始初始化数据库...")

      self.create_extension()

      # self.create_tables()

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
