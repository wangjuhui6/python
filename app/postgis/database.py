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

def get_keys_values_str(data: dict):
  keys_str = ", ".join(data.keys())
  values_str = ", ".join([f"'{value}'" for value in data.values()])
  return [keys_str, values_str]

def get_keys_values_str_edit(data: dict):
  _str = ""
  _id = 0
  for key in data.keys():
    if key == 'id':
      _id = data[key]
    else:
      _str += f"{key} = '{data[key]}',"
  return [_str[:-1], _id]

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
      result = conn.execute(
        text(f"SELECT * FROM {name}")
      )
      rows = result.fetchall()
      return [row._asdict() for row in rows]
  except Exception as e:
    return False

# 删除表
def delete_table(name: str):
  try:
    with engine.begin() as conn:
      conn.execute(text(f"""
        DROP TABLE IF EXISTS {name} CASCADE
      """))
    return True
  except Exception as e:
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

# 添加数据
def add_data(table: str, data: dict):
  str_data = get_keys_values_str(data)
  keys_str=str_data[0]
  values_str=str_data[1]
  try:
    with engine.begin() as conn:
      conn.execute(text(f"INSERT INTO {table} ({keys_str}) VALUES ({values_str})"))
    return {
      'status': True,
      'msg': '添加数据成功'
    }
  except Exception as e:
    return {
      'status': False,
      'msg': str(e)
    }

# 编辑数据
def edit_data(table: str, data: dict):
  _str, _id = get_keys_values_str_edit(data)
  try:
    with engine.begin() as conn:
      conn.execute(text(f"UPDATE {table} SET {_str} WHERE id = {_id}"))
    return {
      'status': True,
      'msg': '编辑数据成功'
    }
  except Exception as e:
    return {
      'status': False,
      'msg': str(e)
    }

# 查询数据
def query_data(table: str, data: dict):
  try:
    with engine.connect() as conn:
      result = conn.execute(text(f"SELECT * FROM {table} WHERE {','.join(data.keys())} = {','.join(data.values())}"))
    return result.fetchall()
  except Exception as e:
    print(e)
    return False

# 删除数据
def delete_data(table: str, data: dict):
  try:
    with engine.begin() as conn:
      conn.execute(text(f"DELETE FROM {table} WHERE id = {data['id']}"))
    return {
      'status': True,
      'msg': '删除数据成功'
    }
  except Exception as e:
    return {
      'status': False,
      'msg': str(e)
    }

# 查询所有数据
def query_all_data(table: str):
  try:
    with engine.connect() as conn:
      result = conn.execute(text(f"SELECT * FROM {table}"))
    return result.fetchall()
  except Exception as e:
    print(e)
    return False

# 查询数据条数
def query_data_count(table: str):
  try:
    with engine.connect() as conn:
      result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
    return result.fetchone()[0]
  except Exception as e:
    print(e)
    return 0

# 查询数据分页
def query_data_page(table: str, page: int, page_size: int):
  try:
    with engine.connect() as conn:
      result = conn.execute(text(f"SELECT * FROM {table} LIMIT {page_size} OFFSET {(page - 1) * page_size}"))
    return result.fetchall()
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
