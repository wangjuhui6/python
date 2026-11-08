import json
import hashlib
import os
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque

from base import get_base_path, get_writable_dir

PORT = 8998
ADMIN_PORT = 8999
PROFILES = ("car", "foot", "bike")
DEFAULT_BASEMAP = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
_listen_port = PORT
_admin_port = ADMIN_PORT
_index_started_for = ""

def _vendor():
  # 开发时在项目里；打包后也可以把同一份目录放在 exe 旁边。
  for root in (get_base_path(), get_writable_dir()):
    path = os.path.join(root, "vendor", "graphhopper")
    if os.path.isfile(os.path.join(path, "graphhopper-web.jar")):
      return path
  return os.path.join(get_base_path(), "vendor", "graphhopper")

_lock = threading.Lock()
_proc = None
_pid = None
_lines = deque(maxlen=40)
_state = {
  "phase": "stopped",
  "message": "尚未启动",
  "pbf": "",
  "port": PORT,
  "elevation": False,
}


def _work_dir():
  path = os.path.join(get_writable_dir(), "data", "route-work")
  os.makedirs(os.path.join(path, "logs"), exist_ok=True)
  os.makedirs(os.path.join(path, "srtm"), exist_ok=True)
  return path


def _state_path():
  return os.path.join(_work_dir(), "engine-state.json")


def _pid_alive(pid):
  if not pid:
    return False
  pid = int(pid)
  if os.name == "nt":
    import ctypes
    kernel = ctypes.windll.kernel32
    handle = kernel.OpenProcess(0x1000, False, pid)
    if handle:
      kernel.CloseHandle(handle)
      return True
    return kernel.GetLastError() == 5
  try:
    os.kill(pid, 0)
  except OSError:
    return False
  return True


def _info_ok(port=None):
  port = _listen_port if port is None else port
  try:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/info", timeout=2) as resp:
      if resp.status != 200:
        return False
      data = json.loads(resp.read().decode("utf-8", "replace"))
      return bool(data.get("profiles"))
  except Exception:
    return False


def _remember(line):
  text = line.strip()
  if not text:
    return
  with _lock:
    _lines.append(text)
    lowered = text.lower()
    if _state["phase"] == "starting" and ("creating graph" in lowered or "importing" in lowered):
      if _state.get("elevation"):
        _state["message"] = "正在建立带高程的路网，第一次需要联网，会比较久"
      else:
        _state["message"] = "正在用本地路网建立路线，不需要联网，第一次会比较久"


def _read_logs(proc):
  stream = proc.stdout
  if stream is None:
    return
  for line in stream:
    _remember(line)


def _kill_pid(pid):
  if not pid or not _pid_alive(pid):
    return
  subprocess.run(
    ["taskkill", "/PID", str(pid), "/T", "/F"],
    capture_output=True,
    text=True,
  )


def _same_pbf(pbf):
  current = _state.get("pbf") or ""
  if not current:
    return False
  return os.path.normcase(os.path.abspath(current)) == os.path.normcase(os.path.abspath(pbf))


def _cache_ready(path):
  needed = ("properties", "edges", "nodes", "geometry")
  return all(os.path.isfile(os.path.join(path, name)) for name in needed)


def _cache_dir(pbf, elevation):
  # 配套缓存是带高程建出来的，只有开启高程且文件名、大小一致时才能直接用。
  if elevation:
    try:
      meta_path = os.path.join(_vendor(), "graph-cache.json")
      bundled_cache = os.path.join(_vendor(), "graph-cache")
      with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
      same_name = os.path.basename(pbf) == meta.get("file_name")
      same_size = os.path.getsize(pbf) == int(meta.get("size") or -1)
      if same_name and same_size and _cache_ready(bundled_cache):
        return bundled_cache
    except (OSError, ValueError, json.JSONDecodeError):
      pass
  digest = hashlib.sha1(os.path.normcase(os.path.abspath(pbf)).encode("utf-8")).hexdigest()[:16]
  folder = digest + "-ele" if elevation else digest
  path = os.path.join(get_writable_dir(), "data", "route-cache", folder)
  os.makedirs(path, exist_ok=True)
  return path


def _using_bundled_cache(cache):
  bundled = os.path.join(_vendor(), "graph-cache")
  return os.path.normcase(os.path.abspath(cache)) == os.path.normcase(os.path.abspath(bundled))


def _total_ram_bytes():
  if os.name != "nt":
    return 0
  import ctypes
  class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
      ("dwLength", ctypes.c_ulong),
      ("dwMemoryLoad", ctypes.c_ulong),
      ("ullTotalPhys", ctypes.c_ulonglong),
      ("ullAvailPhys", ctypes.c_ulonglong),
      ("ullTotalPageFile", ctypes.c_ulonglong),
      ("ullAvailPageFile", ctypes.c_ulonglong),
      ("ullTotalVirtual", ctypes.c_ulonglong),
      ("ullAvailVirtual", ctypes.c_ulonglong),
      ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]
  stat = MEMORYSTATUSEX()
  stat.dwLength = ctypes.sizeof(stat)
  if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
    return 0
  return int(stat.ullTotalPhys)


def _heap_for(pbf):
  size = os.path.getsize(pbf)
  if size > 800 * 1024 * 1024:
    want_mb = 8192
  elif size > 300 * 1024 * 1024:
    want_mb = 4096
  else:
    want_mb = 2048
  total = _total_ram_bytes()
  if total:
    # 固定要 2G/4G/8G 时，内存小的电脑会在 Java 启动阶段直接退出（退出码 1）。
    cap_mb = max(768, int(total * 0.4 / (1024 * 1024)))
    want_mb = min(want_mb, cap_mb)
  if want_mb % 1024 == 0:
    return f"{want_mb // 1024}g"
  return f"{want_mb}m"


def _ensure_files():
  root = _vendor()
  missing = []
  if not os.path.isfile(os.path.join(root, "jdk", "bin", "java.exe")):
    missing.append("Java")
  if not os.path.isfile(os.path.join(root, "graphhopper-web.jar")):
    missing.append("路线引擎")
  if not os.path.isfile(os.path.join(root, "config-example.yml")):
    missing.append("引擎配置")
  if missing:
    raise ValueError("路线引擎文件不完整，缺少：" + "、".join(missing))


def _write_state(pid, pbf):
  payload = {"pid": pid, "pbf": pbf, "port": _listen_port, "elevation": bool(_state.get("elevation"))}
  with open(_state_path(), "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False)


def _clear_state():
  try:
    os.remove(_state_path())
  except OSError:
    pass


def _index_key(pbf):
  try:
    stat = os.stat(pbf)
  except OSError:
    return ""
  return f"{os.path.normcase(os.path.abspath(pbf))}|{stat.st_size}|{stat.st_mtime_ns}"


def _warm_index(pbf, key):
  global _index_started_for
  try:
    from route_engine.road_index import ensure_index
    ensure_index(pbf)
  except Exception:
    with _lock:
      if _index_started_for == key:
        _index_started_for = ""


def _schedule_index(pbf):
  global _index_started_for
  key = _index_key(pbf) if pbf else ""
  if not key or _index_started_for == key:
    return
  _index_started_for = key
  threading.Thread(target=_warm_index, args=(pbf, key), daemon=True).start()


def _adopt():
  global _pid, _listen_port, _admin_port
  if _pid and _pid_alive(_pid):
    _schedule_index(_state.get("pbf") or "")
    return
  path = _state_path()
  if not os.path.isfile(path):
    return
  try:
    with open(path, "r", encoding="utf-8") as f:
      saved = json.load(f)
  except (OSError, json.JSONDecodeError):
    return
  pid = saved.get("pid")
  port = int(saved.get("port") or PORT)
  if not _pid_alive(pid) or not _info_ok(port):
    return
  _pid = int(pid)
  _listen_port = port
  _admin_port = port + 1
  _state["phase"] = "ready"
  _state["pbf"] = saved.get("pbf") or ""
  _state["message"] = "路线服务已就绪"
  _state["port"] = port
  _state["elevation"] = bool(saved.get("elevation"))
  _schedule_index(_state.get("pbf") or "")


def _watch(proc, pbf, port, log_path, log_offset):
  ready = False
  while True:
    if _info_ok(port):
      ready = True
      break
    if proc.poll() is not None:
      break
    time.sleep(1)
  time.sleep(0.3)
  warmed = ""
  with _lock:
    if _proc is not proc:
      return
    if ready:
      _state["phase"] = "ready"
      _state["message"] = "路线服务已就绪"
      _state["pbf"] = pbf
      _state["port"] = port
      warmed = pbf
    else:
      _state["phase"] = "failed"
      _state["message"] = _failure_text(proc.returncode, log_path, log_offset)
  if warmed:
    _schedule_index(warmed)


def _stop_locked():
  global _proc, _pid
  proc = _proc
  pid = _pid
  _proc = None
  _pid = None
  _state["phase"] = "stopped"
  _state["message"] = "路线服务已停止"
  _clear_state()
  if proc is not None and proc.poll() is None:
    _kill_pid(proc.pid)
    try:
      proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
      pass
  elif pid:
    _kill_pid(pid)


def _has_setting(text, key):
  for line in text.splitlines():
    stripped = line.strip()
    if stripped.startswith("#"):
      continue
    if stripped.startswith(key):
      return True
  return False


def _disable_elevation(text):
  # 高程瓦片要联网下载。没有现成缓存时去掉高程，只靠本地路网文件建图。
  text = text.replace(
    "custom_model_files: [foot.json, foot_elevation.json]",
    "custom_model_files: [foot.json]",
  )
  text = text.replace(
    "custom_model_files: [bike.json, bike_elevation.json]",
    "custom_model_files: [bike.json]",
  )
  text = text.replace("hike_rating, average_slope,", "hike_rating,")
  lines = []
  for line in text.splitlines(keepends=True):
    if line.strip() == "graph.elevation.provider: srtm":
      line = line.replace("graph.elevation.provider: srtm", "# graph.elevation.provider: srtm", 1)
    lines.append(line)
  return "".join(lines)


def _reset_incomplete_cache(cache):
  if _cache_ready(cache):
    return
  for name in os.listdir(cache):
    path = os.path.join(cache, name)
    if os.path.isdir(path):
      shutil.rmtree(path, ignore_errors=True)
    else:
      try:
        os.remove(path)
      except OSError:
        pass


def _runtime_config(work, app_port, admin_port, read_only, elevation):
  with open(os.path.join(_vendor(), "config-example.yml"), "r", encoding="utf-8") as f:
    text = f.read()
  text = text.replace("port: 8989", f"port: {app_port}\n    bind_host: 127.0.0.1", 1)
  text = text.replace("port: 8990", f"port: {admin_port}\n    bind_host: 127.0.0.1", 1)
  if not elevation:
    text = _disable_elevation(text)
  if not _has_setting(text, "graph.locktype:"):
    text = text.replace(
      "graph.dataaccess.default_type: RAM\n",
      "graph.dataaccess.default_type: RAM\n  graph.locktype: simple\n",
      1,
    )
  # 随程序拷走的路网缓存只读打开。默认要写锁，换到没有写入权限的目录会直接退出。
  if read_only and not _has_setting(text, "graph.read_only:"):
    text = text.replace(
      "graph.dataaccess.default_type: RAM\n",
      "graph.dataaccess.default_type: RAM\n  graph.read_only: true\n",
      1,
    )
  path = os.path.join(work, "config.yml")
  with open(path, "w", encoding="utf-8", newline="\n") as f:
    f.write(text)
  return path


def _port_free(port):
  import socket
  sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  try:
    sock.bind(("0.0.0.0", port))
    return True
  except OSError:
    return False
  finally:
    sock.close()


def _pick_ports():
  for port in range(PORT, PORT + 200, 2):
    if _port_free(port) and _port_free(port + 1):
      return port, port + 1
  raise ValueError("没有可用的路线服务端口")


def _java_env():
  env = os.environ.copy()
  # 别的电脑上如果装过 Java，这两个变量会附加到本次启动上，内置 JDK 会因此直接退出。
  for key in ("JAVA_TOOL_OPTIONS", "_JAVA_OPTIONS", "JDK_JAVA_OPTIONS", "JAVA_OPTIONS"):
    env.pop(key, None)
  jdk = os.path.join(_vendor(), "jdk")
  env["JAVA_HOME"] = jdk
  env["PATH"] = os.path.join(jdk, "bin") + os.pathsep + env.get("PATH", "")
  return env


def _hidden_flags():
  return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _check_java():
  java = os.path.join(_vendor(), "jdk", "bin", "java.exe")
  try:
    proc = subprocess.run(
      [java, "-version"],
      capture_output=True,
      text=True,
      encoding="utf-8",
      errors="replace",
      env=_java_env(),
      stdin=subprocess.DEVNULL,
      creationflags=_hidden_flags(),
      timeout=20,
    )
  except subprocess.TimeoutExpired as exc:
    raise ValueError("路线引擎没有响应") from exc
  except OSError as exc:
    raise ValueError(f"路线引擎无法启动：{exc}") from exc
  if proc.returncode != 0:
    detail = _pick_error_line((proc.stderr or "").splitlines() + (proc.stdout or "").splitlines())
    raise ValueError("路线引擎无法启动：" + (detail or "内置 Java 启动失败"))


def _pick_error_line(lines):
  useful = []
  for line in lines:
    text = line.strip()
    if not text or len(text) > 300:
      continue
    if text.startswith("Picked up "):
      continue
    useful.append(text)
  for text in reversed(useful):
    lowered = text.lower()
    if any(key in lowered for key in ("error", "exception", "failed", "could not", "无法", "address already")):
      return text
  return useful[-1] if useful else ""


def _failure_text(code, log_path, log_offset):
  lines = list(_lines)
  if not lines:
    try:
      with open(log_path, "r", encoding="utf-8", errors="replace") as f:
        f.seek(log_offset)
        lines = f.read().splitlines()
    except OSError:
      lines = []
  detail = _pick_error_line(lines)
  lowered = detail.lower()
  if "could not reserve enough space" in lowered or "out of memory" in lowered or "outofmemory" in lowered:
    return "路线服务启动失败：这台电脑可用内存不够，请关闭其他程序后重试"
  if "address already in use" in lowered or "bindexception" in lowered:
    return "路线服务启动失败：端口被占用，请重试"
  if "read lock" in lowered or "write lock" in lowered or "access is denied" in lowered:
    return "路线服务启动失败：路网缓存无法读写。请把程序放到当前用户可写的目录，并带上完整的 graph-cache"
  if "unknownhost" in lowered or "connect timed out" in lowered or ("elevation" in lowered and "download" in lowered):
    return "路线服务启动失败：高程数据下载失败。请联网后重试，或关闭高程后再启动"
  if detail:
    return f"路线服务启动失败（退出码 {code}）：{detail}"
  return f"路线服务启动失败（退出码 {code}）"


def _spawn_locked(pbf, elevation):
  global _proc, _pid, _listen_port, _admin_port
  _ensure_files()
  _check_java()
  work = _work_dir()
  elevation = bool(elevation)
  cache = _cache_dir(pbf, elevation)
  srtm = os.path.join(work, "srtm")
  heap = _heap_for(pbf)
  app_port, admin_port = _pick_ports()
  _listen_port = app_port
  _admin_port = admin_port
  read_only = elevation and _using_bundled_cache(cache)
  if not read_only:
    _reset_incomplete_cache(cache)
  config = _runtime_config(work, app_port, admin_port, read_only, elevation)
  java = os.path.join(_vendor(), "jdk", "bin", "java.exe")
  cmd = [
    java,
    f"-Xmx{heap}",
    "-Xms256m",
    "--enable-native-access=ALL-UNNAMED",
    "-Dfile.encoding=UTF-8",
    f"-Ddw.graphhopper.datareader.file={pbf.replace(os.sep, '/')}",
    f"-Ddw.graphhopper.graph.location={cache.replace(os.sep, '/')}",
    f"-Ddw.graphhopper.graph.elevation.cache_dir={srtm.replace(os.sep, '/')}",
    "-jar",
    os.path.join(_vendor(), "graphhopper-web.jar"),
    "server",
    config,
  ]
  log_path = os.path.join(work, "logs", "graphhopper.log")
  log_offset = os.path.getsize(log_path) if os.path.isfile(log_path) else 0
  _lines.clear()
  _state["phase"] = "starting"
  _state["pbf"] = pbf
  _state["port"] = app_port
  _state["elevation"] = elevation
  if read_only:
    _state["message"] = "正在启动路线服务"
  elif elevation:
    _state["message"] = "正在建立带高程的路网，第一次需要联网，会比较久"
  else:
    _state["message"] = "正在用本地路网建立路线，不需要联网，第一次会比较久"
  try:
    proc = subprocess.Popen(
      cmd,
      cwd=work,
      env=_java_env(),
      stdin=subprocess.DEVNULL,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      text=True,
      encoding="utf-8",
      errors="replace",
      bufsize=1,
      creationflags=_hidden_flags(),
    )
  except OSError as exc:
    _state["phase"] = "failed"
    _state["message"] = f"路线服务启动失败：{exc}"
    raise ValueError(_state["message"]) from exc
  _proc = proc
  _pid = proc.pid
  _write_state(proc.pid, pbf)
  threading.Thread(target=_read_logs, args=(proc,), daemon=True).start()
  threading.Thread(target=_watch, args=(proc, pbf, app_port, log_path, log_offset), daemon=True).start()


def _snapshot():
  return {
    "phase": _state["phase"],
    "message": _state["message"],
    "pbf": _state["pbf"],
    "elevation": bool(_state.get("elevation")),
    "port": _listen_port,
    "profiles": [
      {"id": "car", "label": "驾车"},
      {"id": "foot", "label": "步行"},
      {"id": "bike", "label": "骑行"},
    ],
    "log": list(_lines)[-12:],
  }


def current_pbf():
  with _lock:
    _adopt()
    return _state.get("pbf") or ""


def status():
  with _lock:
    _adopt()
    if _pid and not _pid_alive(_pid) and _state["phase"] in ("ready", "starting"):
      _state["phase"] = "stopped"
      _state["message"] = "路线服务已停止"
      _clear_state()
    return _snapshot()


def defaults():
  known = r"D:\lint\guangdong-261025.osm.pbf"
  pbf = known if os.path.isfile(known) else ""
  return {
    "basemap": DEFAULT_BASEMAP,
    "pbf_path": pbf,
    "profiles": status()["profiles"],
  }


def start(pbf_path: str, elevation: bool = False):
  pbf = os.path.abspath((pbf_path or "").strip().strip('"'))
  elevation = bool(elevation)
  if not pbf or not os.path.isfile(pbf):
    raise ValueError("找不到路网文件")
  if not pbf.lower().endswith((".pbf", ".osm")):
    raise ValueError("请选择 .pbf 或 .osm 路网文件")
  _ensure_files()
  with _lock:
    _adopt()
    alive = _pid_alive(_pid)
    same = alive and _same_pbf(pbf) and bool(_state.get("elevation")) == elevation
    if same and _state["phase"] in ("ready", "starting"):
      return _snapshot()
    _stop_locked()
    _spawn_locked(pbf, elevation)
    return _snapshot()


def stop():
  with _lock:
    _adopt()
    _stop_locked()
    return _snapshot()


def _route_url(profile, points, hints=None):
  query = [("profile", profile), ("locale", "zh_CN"), ("points_encoded", "false"), ("instructions", "true")]
  for lng, lat in points:
    query.append(("point", f"{lat},{lng}"))
  if hints and any(hints):
    for hint in hints:
      query.append(("point_hint", hint or ""))
  return f"http://127.0.0.1:{_listen_port}/route?{urllib.parse.urlencode(query)}"


def _feature_collection(profile, coords, distance, time_ms, instructions):
  return {
    "type": "FeatureCollection",
    "features": [{
      "type": "Feature",
      "properties": {
        "kind": "route",
        "profile": profile,
        "distance": distance,
        "time": time_ms,
        "instructions": instructions,
      },
      "geometry": {"type": "LineString", "coordinates": coords},
    }],
  }


def plan(profile: str, points, names=None, hints=None):
  if profile not in PROFILES:
    raise ValueError("不支持的出行方式")
  if not isinstance(points, list) or len(points) < 2:
    raise ValueError("至少需要起点和终点")
  cleaned = []
  for item in points:
    if not isinstance(item, (list, tuple)) or len(item) < 2:
      raise ValueError("坐标格式不正确")
    lng = float(item[0])
    lat = float(item[1])
    if not (-180 <= lng <= 180 and -90 <= lat <= 90):
      raise ValueError("坐标超出范围")
    cleaned.append((lng, lat))
  with _lock:
    _adopt()
    ready = _state["phase"] == "ready" and _pid_alive(_pid)
  if not ready:
    raise ValueError("请先启动路线服务")
  if hints is not None and len(hints) != len(cleaned):
    hints = None
  url = _route_url(profile, cleaned, hints)
  try:
    with urllib.request.urlopen(url, timeout=120) as resp:
      payload = json.loads(resp.read().decode("utf-8", "replace"))
  except urllib.error.HTTPError as exc:
    raw = exc.read().decode("utf-8", "replace")
    try:
      message = json.loads(raw).get("message") or raw
    except json.JSONDecodeError:
      message = raw or "路线计算失败"
    raise ValueError(message) from exc
  except urllib.error.URLError as exc:
    raise ValueError("路线服务没有响应") from exc
  paths = payload.get("paths") or []
  if not paths:
    raise ValueError(payload.get("message") or "没有找到路线")
  path = paths[0]
  coords = []
  for item in (path.get("points") or {}).get("coordinates") or []:
    if len(item) >= 2:
      coords.append([item[0], item[1]])
  instructions = []
  for item in path.get("instructions") or []:
    instructions.append({
      "text": item.get("text") or "",
      "distance": item.get("distance") or 0,
      "time": item.get("time") or 0,
    })
  distance = path.get("distance") or 0
  time_ms = path.get("time") or 0
  return {
    "distance": distance,
    "time": time_ms,
    "coordinates": coords,
    "instructions": instructions,
    "geojson": _feature_collection(profile, coords, distance, time_ms, instructions),
  }
