# 用外部 mbtiles + style.json 提供底图。这两个文件不打进 exe。
import json
import os
import sqlite3
import threading

from base import HOST, PORT, get_writable_dir

_lock = threading.Lock()
_conn = None
_state = {
  "running": False,
  "mbtiles": "",
  "style": "",
  "message": "",
  "minzoom": 0,
  "maxzoom": 14,
  "center": None,
}


def basemap_dir():
  path = os.path.join(get_writable_dir(), "tools", "basemap")
  os.makedirs(path, exist_ok=True)
  return path


def _config_path():
  return os.path.join(basemap_dir(), "service.json")


def _read_config():
  path = _config_path()
  if not os.path.isfile(path):
    return {}
  try:
    with open(path, encoding="utf-8") as f:
      data = json.load(f)
    return data if isinstance(data, dict) else {}
  except (OSError, json.JSONDecodeError):
    return {}


def _write_config(mbtiles, style):
  with open(_config_path(), "w", encoding="utf-8") as f:
    json.dump({"mbtiles": mbtiles, "style": style}, f, ensure_ascii=False, indent=2)


def _default_mbtiles():
  folder = basemap_dir()
  named = os.path.join(folder, "data.mbtiles")
  if os.path.isfile(named):
    return named
  found = [
    os.path.join(folder, name)
    for name in os.listdir(folder)
    if name.lower().endswith(".mbtiles")
  ]
  if len(found) == 1:
    return found[0]
  return ""


def _default_style():
  path = os.path.join(basemap_dir(), "style.json")
  return path if os.path.isfile(path) else ""


def resolved_paths():
  saved = _read_config()
  mbtiles = (saved.get("mbtiles") or "").strip() or _default_mbtiles()
  style = (saved.get("style") or "").strip() or _default_style()
  return mbtiles, style


def public_origin():
  host = "127.0.0.1" if HOST in ("localhost", "0.0.0.0", "") else HOST
  return f"http://{host}:{PORT}"


def _metadata(conn):
  meta = {}
  try:
    rows = conn.execute("SELECT name, value FROM metadata").fetchall()
  except sqlite3.Error:
    return meta
  for name, value in rows:
    meta[name] = value
  if "json" in meta:
    try:
      parsed = json.loads(meta["json"])
      if isinstance(parsed, dict):
        meta.update({k: v for k, v in parsed.items() if k not in meta})
    except json.JSONDecodeError:
      pass
  return meta


def _zoom(meta, key, fallback):
  try:
    return int(float(meta.get(key)))
  except (TypeError, ValueError):
    return fallback


def _center(meta):
  raw = meta.get("center")
  if isinstance(raw, str):
    parts = [p.strip() for p in raw.split(",")]
    try:
      if len(parts) >= 2:
        return [float(parts[0]), float(parts[1])]
    except ValueError:
      return None
  if isinstance(raw, (list, tuple)) and len(raw) >= 2:
    try:
      return [float(raw[0]), float(raw[1])]
    except (TypeError, ValueError):
      return None
  return None


def status():
  mbtiles, style = resolved_paths()
  with _lock:
    running = _state["running"]
    message = _state["message"]
  return {
    "dir": basemap_dir(),
    "mbtiles": mbtiles,
    "style": style,
    "mbtilesReady": os.path.isfile(mbtiles) if mbtiles else False,
    "styleReady": os.path.isfile(style) if style else False,
    "running": running,
    "message": message,
    "origin": public_origin(),
    "styleUrl": f"{public_origin()}/basemap/style.json",
    "tileUrl": f"{public_origin()}/basemap/tiles/{{z}}/{{x}}/{{y}}.pbf",
  }


def start(mbtiles, style):
  global _conn
  mbtiles = os.path.abspath((mbtiles or "").strip().strip('"'))
  style = os.path.abspath((style or "").strip().strip('"'))
  if not mbtiles or not os.path.isfile(mbtiles):
    return {"started": False, "message": "请选择存在的 .mbtiles 文件"}
  if not mbtiles.lower().endswith(".mbtiles"):
    return {"started": False, "message": "底图数据需要是 .mbtiles"}
  if not style or not os.path.isfile(style):
    return {"started": False, "message": "请选择存在的样式 json"}
  if not style.lower().endswith(".json"):
    return {"started": False, "message": "样式需要是 .json 文件"}
  try:
    with open(style, encoding="utf-8") as f:
      doc = json.load(f)
  except (OSError, json.JSONDecodeError):
    return {"started": False, "message": "样式 json 无法读取"}
  if not isinstance(doc, dict) or not isinstance(doc.get("layers"), list):
    return {"started": False, "message": "样式 json 里没有 layers"}

  conn = sqlite3.connect(mbtiles, check_same_thread=False)
  meta = _metadata(conn)
  _write_config(mbtiles, style)
  with _lock:
    global_conn = _conn
    _conn = conn
    _state["running"] = True
    _state["mbtiles"] = mbtiles
    _state["style"] = style
    _state["message"] = "底图服务已启动"
    _state["minzoom"] = _zoom(meta, "minzoom", 0)
    _state["maxzoom"] = _zoom(meta, "maxzoom", 14)
    _state["center"] = _center(meta)
  if global_conn is not None and global_conn is not conn:
    global_conn.close()
  return {"started": True, "message": "底图服务已启动"}


def stop():
  global _conn
  with _lock:
    conn = _conn
    _conn = None
    _state["running"] = False
    _state["message"] = "已停止"
  if conn is not None:
    conn.close()
  return {"stopped": True, "message": "已停止"}


def tile(z, x, y):
  with _lock:
    conn = _conn
    running = _state["running"]
  if not running or conn is None:
    return None
  try:
    tms_y = (1 << int(z)) - 1 - int(y)
    row = conn.execute(
      "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
      (int(z), int(x), tms_y),
    ).fetchone()
  except sqlite3.Error:
    return None
  if not row:
    return b""
  return row[0]


def style_document():
  with _lock:
    if not _state["running"]:
      return None
    style_path = _state["style"]
    minzoom = _state["minzoom"]
    maxzoom = _state["maxzoom"]
    center = _state["center"]
  try:
    with open(style_path, encoding="utf-8") as f:
      doc = json.load(f)
  except (OSError, json.JSONDecodeError):
    return None
  if not isinstance(doc, dict):
    return None
  origin = public_origin()
  tiles = [f"{origin}/basemap/tiles/{{z}}/{{x}}/{{y}}.pbf"]
  sources = doc.get("sources")
  if isinstance(sources, dict):
    for source in sources.values():
      if not isinstance(source, dict) or source.get("type") != "vector":
        continue
      source.pop("url", None)
      source["tiles"] = tiles
      source["minzoom"] = minzoom
      source["maxzoom"] = maxzoom
  glyphs = doc.get("glyphs")
  if isinstance(glyphs, str) and "://" not in glyphs:
    doc["glyphs"] = f"{origin}/basemap/{glyphs.lstrip('/')}"
  if center and not doc.get("center"):
    doc["center"] = center
  return doc


def asset_path(rel):
  rel = (rel or "").replace("\\", "/").lstrip("/")
  if not rel or ".." in rel.split("/"):
    return ""
  with _lock:
    if not _state["running"]:
      return ""
    style_path = _state["style"]
  root = os.path.realpath(os.path.dirname(style_path))
  target = os.path.realpath(os.path.join(root, rel))
  if os.path.normcase(target) != os.path.normcase(root) and not os.path.normcase(target).startswith(os.path.normcase(root) + os.sep):
    return ""
  if os.path.isfile(target):
    return target
  return ""
