from sqlalchemy import text
from postgis.database import engine
from postgis.base.datasets import Dataset
from postgis.base.features import Feature

class DatabaseInitializer:

   def __init__(self):
      print("开始初始化数据库...")

      self.create_extension()

      self.create_tables()

      self.create_indexes()

      self.migrate_columns()

      self.migrate_properties_json()

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

   def create_indexes(self):
      with engine.begin() as conn:
         conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_features_dataset_id ON features (dataset_id);
         """))
         conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_features_geom ON features USING GIST (geom);
         """))

   def migrate_columns(self):
      with engine.begin() as conn:
         conn.execute(text("""
            ALTER TABLE datasets
            ADD COLUMN IF NOT EXISTS categories JSONB DEFAULT '[]'::jsonb;
         """))

   def migrate_properties_json(self):
      # 旧导入把 tag 写成了 JSON 字符串，分类条件匹配不到
      with engine.begin() as conn:
         conn.execute(text("""
            UPDATE features
            SET properties = (trim(properties #>> '{}'))::jsonb
            WHERE jsonb_typeof(properties) = 'string'
              AND left(trim(properties #>> '{}'), 1) IN ('{', '[');
         """))
