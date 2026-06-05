import os

HOST = 'localhost'
PORT = 21006

def get_request_path(relative_path: str):
  # 获取资源文件
  base_path = os.path.dirname(os.path.abspath(__file__))
  return os.path.join(base_path, relative_path)
