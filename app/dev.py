import uvicorn
import subprocess
import os
import shutil
from base import HOST, PORT, get_base_path, get_request_path, get_writable_dir
from postgis.database import engine
import time
from postgis.initializer import DatabaseInitializer
import threading

POSTGIS_IMAGE = "postgis/postgis:16-3.5"
POSTGIS_IMAGE_TAR = os.path.join("vendor", "postgis", "postgis-16-3.5.tar")

def _first_existing(relative_path: str):
  for root in (get_writable_dir(), get_base_path()):
    path = os.path.join(root, relative_path)
    if os.path.isfile(path):
      return path
  return os.path.join(get_writable_dir(), relative_path)

def _docker_ready():
  docker = shutil.which("docker")
  if not docker:
    raise RuntimeError("未找到 docker。单机环境需要先安装并启动 Docker Desktop，镜像用本地离线包导入，不再从网上拉取。")
  result = subprocess.run([docker, "info"], capture_output=True, text=True)
  if result.returncode != 0:
    detail = (result.stderr or result.stdout or "").strip()
    raise RuntimeError("Docker 未启动。请先打开 Docker Desktop。\n" + detail)

def _image_present():
  result = subprocess.run(
    ["docker", "image", "inspect", POSTGIS_IMAGE],
    capture_output=True,
  )
  return result.returncode == 0

def _ensure_postgis_image():
  """单机不访问镜像仓库：本机已有镜像就直接用，否则从离线 tar 导入。"""
  _docker_ready()
  if _image_present():
    print(f"使用本机已有镜像 {POSTGIS_IMAGE}")
    return
  tar = _first_existing(POSTGIS_IMAGE_TAR)
  if not os.path.isfile(tar):
    raise RuntimeError(
      "本机没有 PostGIS 镜像，也没有离线包。\n"
      f"请把离线包放到：{tar}\n"
      "在有网络的机器上导出一次：\n"
      f"  docker pull {POSTGIS_IMAGE}\n"
      f"  docker save -o postgis-16-3.5.tar {POSTGIS_IMAGE}"
    )
  print(f"正在从本地导入 PostGIS 镜像：{tar}")
  subprocess.run(["docker", "load", "-i", tar], check=True)
  if not _image_present():
    raise RuntimeError(f"镜像已导入，但没有找到标签 {POSTGIS_IMAGE}")

def _compose_up():
  compose_file = _first_existing("docker-compose.yml")
  if not os.path.isfile(compose_file):
    compose_file = get_request_path("docker-compose.yml")
  project_dir = get_writable_dir()
  os.makedirs(os.path.join(project_dir, "postgis-data"), exist_ok=True)
  common = ["--project-directory", project_dir, "-f", compose_file, "up", "-d"]
  if shutil.which("docker"):
    version = subprocess.run(["docker", "compose", "version"], capture_output=True)
    if version.returncode == 0:
      # never：镜像已在本机时不要再访问仓库
      subprocess.run(["docker", "compose", *common, "--pull", "never"], check=True)
      return
  if shutil.which("docker-compose"):
    subprocess.run(["docker-compose", *common], check=True)
    return
  raise RuntimeError("未找到 docker compose 或 docker-compose")

# 通过本地镜像启动 postgis，不从仓库拉取
def start_postgis():
  try:
    _ensure_postgis_image()
    _compose_up()
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