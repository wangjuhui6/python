import sys
import traceback


def pause_console(message="发生错误，按回车键退出..."):
  """双击运行打包后的 exe 时，进程退出会立刻关掉控制台，暂停以便查看日志。"""
  if getattr(sys, "frozen", False):
    try:
      input(f"\n{message}")
    except (EOFError, OSError):
      import time
      time.sleep(10)


try:
  import threading
  import uvicorn
  from api.start import api
  import webbrowser
  import pystray
  from PIL import Image
  from pystray import MenuItem as item
  from base import HOST, PORT, get_request_path
  from dev import start_postgis
except Exception:
  traceback.print_exc()
  pause_console()
  sys.exit(1)

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
    traceback.print_exc()
    with open("error.log", "w") as f:
        traceback.print_exc(file=f)
    print(f"错误: {e}")
    pause_console()

# 启动服务
if __name__ == "__main__":
  try:
    start_postgis()
    # 启动web与接口服务
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    # 创建托盘图标
    create_tray_icon()
  except Exception:
    traceback.print_exc()
    pause_console()
    sys.exit(1)