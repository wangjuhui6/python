# 用绿色版 Java + planetiler 把 osm.pbf 切成 mbtiles。用户电脑不需要安装 Java。
import os
import re
import subprocess
import threading

from base import get_writable_dir

_lock = threading.Lock()
_proc = None
_job = {
  "status": "idle",
  "message": "",
  "output": "",
  "log": [],
}


def tool_dir():
  path = os.path.join(get_writable_dir(), "tools", "planetiler")
  os.makedirs(path, exist_ok=True)
  return path


def _first_file(paths):
  for path in paths:
    if path and os.path.isfile(path):
      return path
  return ""


def find_java():
  return _first_file([
    os.path.join(tool_dir(), "jdk", "bin", "java.exe"),
    os.path.join(tool_dir(), "jdk", "bin", "java"),
  ])


def find_jar():
  return _first_file([
    os.path.join(tool_dir(), "planetiler.jar"),
  ])


def environment():
  java = find_java()
  jar = find_jar()
  return {
    "ready": bool(java and jar),
    "java": java,
    "jar": jar,
    "toolDir": tool_dir(),
  }


def status():
  with _lock:
    logs = list(_job["log"][-200:])
    return {
      "status": _job["status"],
      "message": _job["message"],
      "output": _job["output"],
      "log": logs,
    }


_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _output_uri(path):
  # D:/lint/a.mbtiles 会被当成协议名 D，要写成 file URI
  if len(path) >= 2 and path[1] == ":":
    return "file:///" + path.replace("\\", "/")
  return path


def _append(line):
  text = _ANSI.sub("", line or "").strip()
  if not text:
    return
  with _lock:
    _job["log"].append(text)
    if len(_job["log"]) > 400:
      del _job["log"][: len(_job["log"]) - 400]
    _job["message"] = text


def _run(java, jar, input_file, output_path, maxzoom, memory_gb):
  global _proc
  cache = os.path.join(tool_dir(), "sources")
  tmp = os.path.join(tool_dir(), "tmp")
  os.makedirs(cache, exist_ok=True)
  os.makedirs(tmp, exist_ok=True)
  os.makedirs(os.path.dirname(output_path), exist_ok=True)
  cmd = [
    java,
    f"-Xmx{memory_gb}g",
    "-Dfile.encoding=UTF-8",
    "-jar",
    jar,
    f"--osm-path={input_file}",
    f"--output={_output_uri(output_path)}",
    f"--maxzoom={maxzoom}",
    f"--download-dir={cache}",
    f"--tmpdir={tmp}",
    "--download",
    "--download-osm-tile-weights=false",
    "--water-polygons-url=https://ftp.fau.de/pub/openstreetmapdata.com-archive/2026-08-25/water-polygons-split-3857.zip",
    "--http-timeout=PT180S",
    "--color=false",
    "--force",
  ]
  env = os.environ.copy()
  env.pop("JAVA_TOOL_OPTIONS", None)
  flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
  try:
    proc = subprocess.Popen(
      cmd,
      cwd=os.path.dirname(output_path) or None,
      env=env,
      stdout=subprocess.PIPE,
      stderr=subprocess.STDOUT,
      text=True,
      encoding="utf-8",
      errors="replace",
      creationflags=flags,
    )
  except OSError as exc:
    with _lock:
      _job["status"] = "error"
      _job["message"] = str(exc)
    return

  with _lock:
    _proc = proc

  if proc.stdout is not None:
    for line in proc.stdout:
      _append(line)

  code = proc.wait()
  with _lock:
    _proc = None
    if _job["status"] == "running":
      if code == 0 and os.path.isfile(output_path):
        _job["status"] = "done"
        _job["message"] = "转换完成"
      else:
        _job["status"] = "error"
        _job["message"] = f"转换失败，退出码 {code}"


def start(input_file, output_path, maxzoom=14, memory_gb=6):
  pbf = os.path.abspath((input_file or "").strip().strip('"'))
  output = os.path.abspath((output_path or "").strip().strip('"'))
  if not pbf or not os.path.isfile(pbf):
    return {"started": False, "message": "请选择存在的 .pbf 文件"}
  if not pbf.lower().endswith(".pbf"):
    return {"started": False, "message": "请选择 .osm.pbf 或 .pbf 文件"}
  if not output.lower().endswith(".mbtiles"):
    return {"started": False, "message": "保存文件名需要以 .mbtiles 结尾"}
  try:
    maxzoom = int(maxzoom)
    memory_gb = int(memory_gb)
  except (TypeError, ValueError):
    return {"started": False, "message": "最大级别和内存需要是整数"}
  if maxzoom < 0 or maxzoom > 15:
    return {"started": False, "message": "最大级别请设在 0 到 15"}
  if memory_gb < 1 or memory_gb > 64:
    return {"started": False, "message": "内存请设在 1 到 64 GB"}

  java = find_java()
  jar = find_jar()
  if not jar or not java:
    return {
      "started": False,
      "message": f"还没放好转换程序。请把 planetiler.jar 和 Java 21 绿色版放到 {tool_dir()}",
    }

  with _lock:
    if _job["status"] == "running":
      return {"started": False, "message": "已有转换任务在进行"}
    _job["status"] = "running"
    _job["message"] = "正在转换"
    _job["output"] = output
    _job["log"] = []

  threading.Thread(
    target=_run,
    args=(java, jar, pbf, output, maxzoom, memory_gb),
    daemon=True,
  ).start()
  return {"started": True, "message": "已开始转换", "output": output}


def stop():
  global _proc
  with _lock:
    proc = _proc
    running = _job["status"] == "running"
  if not running or proc is None:
    return {"stopped": False, "message": "当前没有进行中的转换"}
  proc.terminate()
  with _lock:
    if _job["status"] == "running":
      _job["status"] = "error"
      _job["message"] = "已停止"
  return {"stopped": True, "message": "已停止"}
