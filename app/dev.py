import uvicorn
from base import HOST, PORT, get_request_path

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
  run_server()