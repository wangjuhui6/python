# postgis 数据库
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DATABASE_URL = (
  "postgresql://gis:123456@localhost:5432/gisdb"
)

engine=create_engine(
  DATABASE_URL
)

SessionLocal=sessionmaker(
  bind=engine
)

# 创建表
def create_table(name: str):
  try:
    with engine.connect() as conn:
      conn.execute(text(f"CREATE TABLE IF NOT EXISTS {name} (id SERIAL PRIMARY KEY, name VARCHAR(255) NOT NULL)"))
    return True
  except Exception as e:
    print(e)
    return False

# 查询表
def query_table(name: str):
  try:
    with engine.connect() as conn:
      result = conn.execute(text(f"SELECT * FROM {name}"))
    return result.fetchall()
  except Exception as e:
    print(e)
    return False

# 删除表
def delete_table(name: str):
  try:
    with engine.connect() as conn:
      conn.execute(text(f"DROP TABLE IF EXISTS {name}"))
    return True
  except Exception as e:
    print(e)
    return False

# 查询所有表
def query_all_tables():
  try:
    with engine.connect() as conn:
      result = conn.execute(
        text("""
          SELECT table_name
          FROM pg_tables
          WHERE schemaname='public'
        """)
      )
      return [row.table_name for row in result]
  except Exception as e:
    print(e)
    return False

# 动态创建表 读取有哪些表
# 每次创建分类时需要检查是否存在该表，不存在则创建 同步创建 点线面以及其他相关的点
# 确定其他参数如何存储 决定表创建字段
# 添加删除表 以及合并表 将某个表里的数据合并到另一个表里
# 尝试添加数据
# 读取各种数据格式 将数据分类添加进去
# 页面展示数据 展示在地图上 增删改查数据
# 导出表
# 将数据处理成mbtiles格式
# 如何将不同的数据添加进不同层级的mbtiles（pbf）
# 读取mbtiles数据 展示在地图上
# 创建栅格表 添加栅格数据
# 读取栅格数据 展示在地图上
# 尝试 添加模型

# 将表数据生成mbtiles时 考虑让用户子集手动决定不同类型数据的层级

# create_table_fun (name) 
  # CREA

# create_table_sql = """
# CREATE TABLE IF NOT EXISTS postgis_version (
#   id SERIAL PRIMARY KEY,
#   version VARCHAR(255) NOT NULL
# )
# """
