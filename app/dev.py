import uvicorn
import subprocess
import os
from base import HOST, PORT, get_request_path
from postgis.database import engine
import time
from postgis.initializer import DatabaseInitializer
import threading

# 通过docker启动postgis
def start_postgis():
  try:
    postgis_path = get_request_path("docker-compose.yml")
    compose_dir = os.path.dirname(postgis_path)
    subprocess.run(
      ["docker-compose", "up", "-d"],
      cwd=compose_dir,      # docker-compose.yml 所在目录
      check=True
    )
    print("postgis服务已启动")
    wait_postgis()
    print("数据库已启动")
    init_database()
  except Exception as e:
    print("postgis服务启动失败")
    print(type(e))
    print(e)

# 查看数据库是否启动成功
def wait_postgis():
  while True:
    try:
      with engine.connect():
        break
    except:
      time.sleep(1)

# 创建表
def init_database():
  DatabaseInitializer()

# 启动 FastAPI 服务
def run_server():
  print("开始启动web服务...")
  uvicorn.run(
    'api.start:api', 
      host=HOST, 
      port=PORT, 
      log_level="info",
      reload=True
    )

# 启动服务
if __name__ == "__main__":
  threading.Thread(
    target=start_postgis,
    daemon=True
  ).start()
  run_server()