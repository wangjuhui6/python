import os
import sys
import traceback
from pathlib import Path

# PyInstaller windowed 模式下 stdout/stderr 为 None，print / uvicorn 会崩溃，网页服务起不来
if getattr(sys, "frozen", False):
  _runtime_log = open(
    os.path.join(os.path.dirname(sys.executable), "runtime.log"),
    "w",
    encoding="utf-8",
    buffering=1,
    errors="replace",
  )
  if sys.stdout is None:
    sys.stdout = _runtime_log
  if sys.stderr is None:
    sys.stderr = _runtime_log


def _error_log_path():
  if getattr(sys, "frozen", False):
    return Path(sys.executable).resolve().parent / "error.log"
  return Path("error.log")


def log_exception():
  traceback.print_exc()
  with open(_error_log_path(), "w", encoding="utf-8") as f:
    traceback.print_exc(file=f)


def pause_console(message="发生错误，按回车键退出..."):
  """仅在有控制台时暂停；windowed 打包没有黑框，错误已写入 error.log。"""
  if not getattr(sys, "frozen", False):
    return
  stdin = sys.stdin
  if stdin is None or not stdin.isatty():
    return
  try:
    input(f"\n{message}")
  except (EOFError, OSError):
    pass


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
  log_exception()
  pause_console()
  sys.exit(1)

# 启动 FastAPI 服务
def run_server():
  try:
    print("开始启动web服务...")
    uvicorn.run(api, host=HOST, port=PORT, log_level="info")
  except Exception:
    log_exception()

# 打开浏览器
def open_browser():
  print("打开浏览器...")
  webbrowser.open(f"http://{HOST}:{PORT}")

# 等服务真正监听后再打开，避免无控制台时页面连不上
def wait_and_open_browser():
  import socket
  import time
  deadline = time.time() + 30
  while time.time() < deadline:
    try:
      with socket.create_connection((HOST, PORT), timeout=0.5):
        open_browser()
        return
    except OSError:
      time.sleep(0.2)
  print("等待 web 服务超时，未自动打开浏览器")

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
    log_exception()
    print(f"错误: {e}")
    pause_console()

# 启动服务
if __name__ == "__main__":
  try:
    start_postgis()
    # 启动web与接口服务
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    threading.Thread(target=wait_and_open_browser, daemon=True).start()
    # 创建托盘图标
    create_tray_icon()
  except Exception:
    log_exception()
    pause_console()
    sys.exit(1)