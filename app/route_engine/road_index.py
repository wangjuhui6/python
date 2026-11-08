import hashlib
import math
import os
import sqlite3
import threading
from pathlib import Path

import osmium

from base import get_writable_dir

_lock = threading.Lock()
_NAME_KEYS = ("name:zh", "name", "alt_name", "short_name", "official_name")
_INDEX_VERSION = "3"
_POI_TAGS = (
  (("barrier", "toll_booth"), "收费站"),
  (("highway", "toll_gantry"), "收费站"),
  (("highway", "services"), "服务区"),
  (("highway", "rest_area"), "停车区"),
  (("amenity", "fuel"), "加油站"),
)


def _index_path(pbf):
  stat = os.stat(pbf)
  folder = os.path.join(get_writable_dir(), "data", "route-index")
  os.makedirs(folder, exist_ok=True)
  digest = hashlib.sha1(os.path.normcase(os.path.abspath(pbf)).encode("utf-8")).hexdigest()[:8]
  return os.path.join(folder, f"{digest}-{stat.st_size}-{stat.st_mtime_ns}.sqlite")


def _connect(path, readonly=False):
  if not readonly:
    return sqlite3.connect(path)
  return sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)


def _ready(path):
  if not os.path.isfile(path) or os.path.getsize(path) == 0:
    return False
  try:
    conn = _connect(path, readonly=True)
    row = conn.execute("SELECT v FROM meta WHERE k = 'ready'").fetchone()
    conn.close()
  except sqlite3.Error:
    return False
  return bool(row and row[0] == _INDEX_VERSION)


def _labels(tags):
  found = []
  for key in _NAME_KEYS:
    value = tags.get(key) or ""
    for part in str(value).replace("；", ";").split(";"):
      name = part.strip()
      if name and name not in found:
        found.append(name)
  ref = tags.get("ref") or ""
  for part in str(ref).replace("；", ";").split(";"):
    name = part.strip()
    if name and name not in found:
      found.append(name)
  return found


def _dist_km(a, b):
  radius = 6371.0
  lon1, lat1, lon2, lat2 = map(math.radians, (a[0], a[1], b[0], b[1]))
  dlon = lon2 - lon1
  dlat = lat2 - lat1
  arc = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
  return 2 * radius * math.asin(math.sqrt(arc))


def _sample_shape(coords):
  # 长路不能只留中点，否则途径点会落到远离行程的位置。
  if len(coords) <= 2:
    return coords
  kept = [coords[0]]
  travelled = 0.0
  for index in range(1, len(coords)):
    travelled += _dist_km(coords[index - 1], coords[index])
    if travelled >= 0.25:
      kept.append(coords[index])
      travelled = 0.0
  if kept[-1] != coords[-1]:
    kept.append(coords[-1])
  if len(kept) > 24:
    step = (len(kept) - 1) / 23
    kept = [kept[min(len(kept) - 1, round(index * step))] for index in range(24)]
  return kept


def _encode_shape(coords):
  return ";".join(f"{lng:.6f},{lat:.6f}" for lng, lat in coords)


def _parse_shape(text, lng, lat):
  points = []
  for part in (text or "").split(";"):
    if "," not in part:
      continue
    raw_lng, raw_lat = part.split(",", 1)
    try:
      points.append((float(raw_lng), float(raw_lat)))
    except ValueError:
      continue
  return points or [(lng, lat)]


def _poi_label(tags):
  for (key, value), label in _POI_TAGS:
    if tags.get(key) == value:
      return label
  return ""


def _kind(tags):
  poi = _poi_label(tags)
  if poi:
    return poi
  if tags.get("highway"):
    return "highway"
  if tags.get("place"):
    return "place"
  return tags.get("amenity") or tags.get("tourism") or tags.get("shop") or "other"


def _names_for(tags):
  names = _labels(tags)
  poi = _poi_label(tags)
  if poi and poi not in names and not any(poi in name for name in names):
    names.append(poi)
  return names


def _scan(pbf, storage, conn):
  batch = []

  def flush():
    if not batch:
      return
    conn.executemany(
      "INSERT INTO place (name, lng, lat, kind, west, south, east, north, shape) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
      batch,
    )
    batch.clear()

  for obj in osmium.FileProcessor(pbf).with_locations(storage=storage):
    if obj.is_node():
      if len(obj.tags) == 0 or not obj.location.valid():
        continue
      names = _names_for(obj.tags)
      if not names:
        continue
      lng = float(obj.location.lon)
      lat = float(obj.location.lat)
      kind = _kind(obj.tags)
      shape = _encode_shape([(lng, lat)])
      for name in names:
        batch.append((name, lng, lat, kind, lng, lat, lng, lat, shape))
    elif obj.is_way():
      if len(obj.tags) == 0:
        continue
      names = _names_for(obj.tags)
      if not names:
        continue
      coords = []
      for node in obj.nodes:
        if node.location.valid():
          coords.append((float(node.location.lon), float(node.location.lat)))
      if not coords:
        continue
      lng, lat = coords[len(coords) // 2]
      west = min(item[0] for item in coords)
      east = max(item[0] for item in coords)
      south = min(item[1] for item in coords)
      north = max(item[1] for item in coords)
      kind = _kind(obj.tags)
      shape = _encode_shape(_sample_shape(coords))
      for name in names:
        batch.append((name, lng, lat, kind, west, south, east, north, shape))
    if len(batch) >= 4000:
      flush()
  flush()


def _build(pbf, dest):
  tmp = f"{dest}.{os.getpid()}.tmp"
  try:
    os.remove(tmp)
  except OSError:
    pass
  conn = sqlite3.connect(tmp, timeout=30)
  try:
    conn.execute("CREATE TABLE meta (k TEXT PRIMARY KEY, v TEXT)")
    conn.execute(
      "CREATE TABLE place (name TEXT, lng REAL, lat REAL, kind TEXT, west REAL, south REAL, east REAL, north REAL, shape TEXT)"
    )
    try:
      _scan(pbf, "flex_mem", conn)
    except MemoryError:
      conn.execute("DELETE FROM place")
      _scan(pbf, "sparse_file_array", conn)
    conn.execute("CREATE INDEX idx_place_name ON place (name)")
    conn.execute("INSERT INTO meta (k, v) VALUES ('ready', ?)", (_INDEX_VERSION,))
    conn.commit()
  finally:
    conn.close()
  os.replace(tmp, dest)


def ensure_index(pbf):
  if not pbf or not os.path.isfile(pbf):
    raise OSError("找不到路网文件")
  dest = _index_path(pbf)
  if _ready(dest):
    return dest
  with _lock:
    if _ready(dest):
      return dest
    _build(pbf, dest)
  return dest


def search_places(pbf, query: str, bounds=None):
  name = (query or "").replace("\u3000", " ").strip()
  if len(name) < 2:
    return []
  dest = ensure_index(pbf)
  where = "name = ?"
  args = [name]
  if bounds:
    west, south, east, north = bounds
    where += " AND east >= ? AND west <= ? AND north >= ? AND south <= ?"
    args.extend((west, east, south, north))
  conn = _connect(dest, readonly=True)
  try:
    rows = conn.execute(
      f"SELECT name, lng, lat, kind, west, south, east, north, shape FROM place WHERE {where} LIMIT 800",
      args,
    ).fetchall()
    if not rows and bounds:
      rows = conn.execute(
        "SELECT name, lng, lat, kind, west, south, east, north, shape FROM place WHERE name = ? LIMIT 800",
        (name,),
      ).fetchall()
    if not rows:
      like = "%" + name.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
      rows = conn.execute(
        "SELECT name, lng, lat, kind, west, south, east, north, shape FROM place WHERE name LIKE ? ESCAPE '\\' LIMIT 200",
        (like,),
      ).fetchall()
  finally:
    conn.close()
  found = []
  for label, lng, lat, kind, west, south, east, north, shape in rows:
    found.append({
      "lng": lng,
      "lat": lat,
      "label": label,
      "kind": kind or "",
      "bbox": (south, north, west, east),
      "shape": _parse_shape(shape, lng, lat),
    })
  return found
