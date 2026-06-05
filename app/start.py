import threading
import uvicorn
from api.start import api
import webbrowser
import pystray
from PIL import Image
from pystray import MenuItem as item
import os
import sys
from base import HOST, PORT, get_request_path

# 启动 FastAPI 服务
def run_server():
  print("开始启动web服务...")
  uvicorn.run(api, host=HOST, port=PORT, log_level="info")

# 打开浏览器
def open_browser():
  print("打开浏览器...")
  webbrowser.open(f"http://{HOST}:{PORT}")

# 退出程序
def quit_app(icon):
  print("退出程序...")
  icon.stop()
  sys.exit(0)

# 创建托盘图标
def create_tray_icon():
  try:
    icon_path = get_request_path("icon.ico")
    # 加载图片
    image = Image.open(icon_path)
    menu = (
        item("打开 Map Tool", open_browser),
        item("退出", quit_app),
    )
    icon = pystray.Icon("Map Tool", image, menu=menu)
    icon.run()
  except Exception as e:
    import traceback
    with open("error.log", "w") as f:
        traceback.print_exc(file=f)
    print(f"错误: {e}")

# 启动服务
if __name__ == "__main__":
  # 启动web与接口服务
  server_thread = threading.Thread(target=run_server, daemon=True)
  server_thread.start()
  # 创建托盘图标
  icon = create_tray_icon()