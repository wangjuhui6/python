from sqlalchemy import text
from postgis.database import engine

class DatabaseInitializer:

   def __init__(self):
      print("开始初始化数据库...")

      self.create_extension()

      self.create_tables()

      self.create_indexes()

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
      with engine.begin() as conn:
         
         # 数据源表
         # id 自增
         # name 名称
         # code 编码
         # srid 坐标系
         # description 描述
         # mapping 字段映射 json
         # created_at 创建时间
         conn.execute(text("""
            CREATE TABLE IF NOT EXISTS datasets (

               id BIGSERIAL PRIMARY KEY,

               name VARCHAR(100) NOT NULL,

               code VARCHAR(100) UNIQUE,

               srid VARCHAR(100) NOT NULL,

               description TEXT,

               mapping JSONB DEFAULT '{}',

               created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
         """))

         # 矢量数据表
         # id 自增
         # dataset_id 数据源id
         # layer 图层 道路 面 poi 等
         # class 类 水系 建筑 土地 海洋 等
         # type 类型 更精细的分类 国道 小道 等
         # layer VARCHAR(100),
         # class VARCHAR(50),
         # type VARCHAR(50),
         # geom 几何体
         # properties 属性
         # created_at 创建时间
         # updated_at 更新时间
         conn.execute(text("""
            CREATE TABLE IF NOT EXISTS features (

               id BIGSERIAL PRIMARY KEY,

               dataset_id BIGINT REFERENCES datasets(id) ON DELETE CASCADE,

               geom geometry(Geometry,4326) NOT NULL,

               properties JSONB DEFAULT '{}',

               created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

               updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

            );
         """))

    # ==========================
    # 创建索引
    # ==========================
   def create_indexes(self):
      with engine.begin() as conn:
         # 空间索引
         conn.execute(text("""
            CREATE INDEX IF NOT EXISTS
            idx_features_geom
            ON features
            USING GIST(geom);
         """))

         # 数据集查询
         conn.execute(text("""
            CREATE INDEX IF NOT EXISTS
            idx_features_dataset
            ON features(dataset_id);
         """))

         # class + type
         conn.execute(text("""
            CREATE INDEX IF NOT EXISTS
            idx_features_class_type
            ON features(class,type);
         """))

         # JSON查询
         conn.execute(text("""
            CREATE INDEX IF NOT EXISTS
            idx_features_properties
            ON features
            USING GIN(properties);
         """))



         # # 规则查询
         # conn.execute(text("""
         #    CREATE INDEX IF NOT EXISTS
         #    idx_layer_rules_class_type
         #    ON layer_rules(class,type);
         # """))
