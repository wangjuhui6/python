import json
import math
import urllib.parse
import urllib.request

from llm.engine import chat
from route_engine.road_index import search_boxes, search_places
from route_engine.service import current_pbf, plan

_USER_AGENT = "local-route-app/1.0"


def _http_json(url: str, timeout: int = 20):
  request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT, "Accept-Language": "zh-CN"})
  with urllib.request.urlopen(request, timeout=timeout) as resp:
    return json.loads(resp.read().decode("utf-8", "replace"))


def _parse_places(text: str) -> list[str]:
  raw = (text or "").strip()
  start = raw.find("{")
  end = raw.rfind("}")
  if start < 0 or end <= start:
    raise ValueError("模型没有返回可用的地点列表")
  try:
    data = json.loads(raw[start:end + 1])
  except json.JSONDecodeError as exc:
    raise ValueError("模型返回的地点无法解析") from exc
  places = []
  for item in data.get("places") or []:
    name = str(item or "").strip()
    if name and name not in places:
      places.append(name)
  return places[:12]


def _area_hint(lng: float, lat: float) -> str:
  query = urllib.parse.urlencode({
    "format": "jsonv2",
    "lat": lat,
    "lon": lng,
    "zoom": 10,
    "accept-language": "zh",
  })
  try:
    data = _http_json(f"https://nominatim.openstreetmap.org/reverse?{query}", timeout=4)
  except Exception:
    return ""
  address = data.get("address") or {}
  return address.get("city") or address.get("town") or address.get("county") or address.get("state") or ""


def _km(lng1, lat1, lng2, lat2):
  radius = 6371.0
  lon1, lat1r, lon2, lat2r = map(math.radians, (lng1, lat1, lng2, lat2))
  dlon = lon2 - lon1
  dlat = lat2r - lat1r
  arc = math.sin(dlat / 2) ** 2 + math.cos(lat1r) * math.cos(lat2r) * math.sin(dlon / 2) ** 2
  return 2 * radius * math.asin(math.sqrt(arc))


def _name_key(query: str) -> str:
  name = (query or "").split()[0].strip()
  for suffix in ("步行街", "商业街", "地铁站", "火车站", "汽车站"):
    if name.endswith(suffix) and len(name) > len(suffix) + 1:
      return name[:-len(suffix)]
  return name


def _is_road(name: str) -> bool:
  return any(mark in (name or "") for mark in ("路", "街", "大道", "高速", "公路", "巷", "桥"))


def _is_expressway(name: str) -> bool:
  return "高速" in (name or "")


def _is_toll_name(name: str) -> bool:
  return "收费" in (name or "")


def _toll_gate(prev_name: str, next_name: str, query: str, next_rows=None) -> str:
  # 收费站后面是高速，就一定是入口。只有后面不是高速、前面已经在高速上，才是出口。
  if not _is_toll_name(query):
    return ""
  labels = [row.get("label") or "" for row in (next_rows or []) if row.get("label")]
  followed_by_highway = _is_expressway(next_name) or (bool(labels) and all(_is_expressway(label) for label in labels))
  if followed_by_highway or "入口" in (query or ""):
    return "enter"
  if _is_expressway(prev_name) or "出口" in (query or ""):
    return "exit"
  return ""


def _along(origin, dest, lng, lat):
  dx = dest[0] - origin[0]
  dy = dest[1] - origin[1]
  denom = dx * dx + dy * dy
  if denom <= 1e-18:
    return 0.0
  return ((lng - origin[0]) * dx + (lat - origin[1]) * dy) / denom


def _cross_km(origin, dest, lng, lat):
  along = _along(origin, dest, lng, lat)
  clamped = max(0.0, min(1.0, along))
  px = origin[0] + (dest[0] - origin[0]) * clamped
  py = origin[1] + (dest[1] - origin[1]) * clamped
  return _km(lng, lat, px, py), along


def _limit_km(origin, dest):
  # 允许离开最短路径几公里，才能把指定道路拉进路线；太远的同名路仍然不要。
  direct = _km(origin[0], origin[1], dest[0], dest[1])
  return max(3.0, min(6.0, direct * 0.25))


def _viewbox(origin, dest):
  direct = _km(origin[0], origin[1], dest[0], dest[1])
  margin = max(3.0, min(12.0, direct * 0.45))
  mid_lat = (origin[1] + dest[1]) / 2
  dlat = margin / 111.0
  dlng = margin / max(20.0, 111.0 * math.cos(math.radians(mid_lat)))
  min_lng = min(origin[0], dest[0]) - dlng
  max_lng = max(origin[0], dest[0]) + dlng
  min_lat = min(origin[1], dest[1]) - dlat
  max_lat = max(origin[1], dest[1]) + dlat
  return f"{min_lng},{max_lat},{max_lng},{min_lat}"


def _closest_rect(origin, dest, west, south, east, north):
  best = None
  best_distance = None
  for step in range(25):
    ratio = step / 24
    lng = origin[0] + (dest[0] - origin[0]) * ratio
    lat = origin[1] + (dest[1] - origin[1]) * ratio
    clamped_lng = min(max(lng, west), east)
    clamped_lat = min(max(lat, south), north)
    distance = _km(lng, lat, clamped_lng, clamped_lat)
    if best_distance is None or distance < best_distance:
      best = (clamped_lng, clamped_lat)
      best_distance = distance
  return best


def _thin_route(coords, step_km=0.15):
  if len(coords) < 3:
    return [tuple(item[:2]) for item in coords]
  kept = [tuple(coords[0][:2])]
  travelled = 0.0
  for index in range(1, len(coords)):
    point = tuple(coords[index][:2])
    travelled += _km(kept[-1][0], kept[-1][1], point[0], point[1])
    if travelled >= step_km:
      kept.append(point)
      travelled = 0.0
  last = tuple(coords[-1][:2])
  if kept[-1] != last:
    kept.append(last)
  return kept


def _segment_distance(lng, lat, start, end):
  lat_scale = max(0.2, math.cos(math.radians((start[1] + end[1]) / 2)))
  ax = start[0] * 111.0 * lat_scale
  ay = start[1] * 111.0
  bx = end[0] * 111.0 * lat_scale
  by = end[1] * 111.0
  px = lng * 111.0 * lat_scale
  py = lat * 111.0
  dx = bx - ax
  dy = by - ay
  length_sq = dx * dx + dy * dy
  if length_sq <= 1e-12:
    return _km(lng, lat, start[0], start[1]), 0.0
  ratio = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
  nearest_x = ax + dx * ratio
  nearest_y = ay + dy * ratio
  distance = math.hypot(px - nearest_x, py - nearest_y)
  return distance, math.sqrt(length_sq) * ratio


def _spread_on_path(shape, path, limit=8):
  # 一条路或一个点位在路线附近可能有多处，先留几个，再挑靠近上一段路的。
  if not shape or len(path) < 2:
    return []
  lengths = _polyline_lengths(path)
  total = lengths[-1] or 1.0
  scored = []
  for lng, lat in shape:
    best_distance = None
    best_along = 0.0
    for index in range(1, len(path)):
      distance, offset = _segment_distance(lng, lat, path[index - 1], path[index])
      along = lengths[index - 1] + offset
      if best_distance is None or distance < best_distance:
        best_distance = distance
        best_along = along
    scored.append((best_distance, best_along / total, lng, lat))
  nearest = min(item[0] for item in scored)
  band = [item for item in scored if item[0] <= nearest + 0.15]
  band.sort(key=lambda item: item[1])
  if len(band) > limit:
    step = (len(band) - 1) / (limit - 1)
    band = [band[min(len(band) - 1, round(index * step))] for index in range(limit)]
  return band


def _expand_candidate(item, route, origin, dest):
  shape = item.get("shape") or [(item["lng"], item["lat"])]
  path = route if route and len(route) >= 2 else [origin, dest]
  spots = _spread_on_path(shape, path)
  made = []
  for distance, along, lng, lat in spots:
    copy = dict(item)
    copy["lng"] = lng
    copy["lat"] = lat
    copy["route_dist"] = distance
    copy["route_along"] = along
    copy["snapped"] = True
    copy["road_shape"] = shape
    copy.pop("shape", None)
    made.append(copy)
  return made


def _shape_dist(lng, lat, shape):
  best = None
  for point in shape or []:
    distance = _km(lng, lat, point[0], point[1])
    if best is None or distance < best:
      best = distance
  return best if best is not None else 1e9


def _pick(candidates, query: str, origin, dest, limit: float, previous=None):
  poi = next((word for word in ("收费站", "服务区", "停车区", "加油站") if word in (query or "")), "")
  direct = max(_km(origin[0], origin[1], dest[0], dest[1]), 1.0)
  prev_along = previous.get("route_along") or 0.0 if previous else 0.0
  prev_shape = None
  if previous:
    prev_shape = previous.get("road_shape") or [(previous["lng"], previous["lat"])]
  viable = []
  for item in candidates:
    if item.get("route_dist") is not None:
      cross = item["route_dist"]
      along = item.get("route_along")
      if along is None:
        along = 0.5
      if along < 0:
        beyond = abs(along) * direct
      elif along > 1:
        beyond = (along - 1) * direct
      else:
        beyond = 0.0
    else:
      cross, along = _cross_km(origin, dest, item["lng"], item["lat"])
      if along < 0:
        beyond = _km(item["lng"], item["lat"], origin[0], origin[1])
      elif along > 1:
        beyond = _km(item["lng"], item["lat"], dest[0], dest[1])
      else:
        beyond = 0.0
    if cross > limit or beyond > limit:
      continue
    viable.append((cross, along, item))
  if not viable:
    return None
  nearest = min(item[0] for item in viable)
  pool = [item for item in viable if item[0] <= nearest + 0.6]
  forward = [item for item in pool if item[1] + 0.02 >= prev_along]
  pool = forward or pool
  def rank(entry):
    cross, along, item = entry
    prev_dist = _shape_dist(item["lng"], item["lat"], prev_shape) if prev_shape else 0
    poi_miss = 1 if poi and item.get("kind") != poi else 0
    return (poi_miss, prev_dist, along, cross)
  return min(pool, key=rank)[2]


def _route_bounds(route, origin, dest):
  points = [tuple(item[:2]) for item in route] if route else [origin, dest]
  lngs = [item[0] for item in points]
  lats = [item[1] for item in points]
  pad_lat = 3.0 / 111.0
  mid_lat = sum(lats) / len(lats)
  pad_lng = 3.0 / max(20.0, 111.0 * math.cos(math.radians(mid_lat)))
  return (min(lngs) - pad_lng, min(lats) - pad_lat, max(lngs) + pad_lng, max(lats) + pad_lat)


def _search_local(query: str, bounds=None):
  pbf = current_pbf()
  if not pbf:
    return []
  try:
    return search_places(pbf, query, bounds, exact=True)
  except OSError as exc:
    raise ValueError("无法读取路网文件") from exc
  except Exception as exc:
    raise ValueError("无法从路网文件读取道路名称") from exc


def _roads_in_box(boxes):
  pbf = current_pbf()
  if not pbf or not boxes:
    return []
  try:
    return search_boxes(pbf, boxes, limit=150)
  except Exception:
    return []


def _search_nominatim(query: str, viewbox: str = "", bounded: bool = False):
  params = {
    "q": query,
    "format": "jsonv2",
    "limit": 6,
    "accept-language": "zh",
    "countrycodes": "cn",
  }
  if viewbox:
    params["viewbox"] = viewbox
    if bounded:
      params["bounded"] = 1
  rows = _http_json("https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params), timeout=4)
  found = []
  for row in rows or []:
    box = row.get("boundingbox") or []
    bbox = None
    if len(box) == 4:
      south, north, west, east = (float(value) for value in box)
      bbox = (south, north, west, east)
    found.append({
      "lng": float(row["lon"]),
      "lat": float(row["lat"]),
      "label": row.get("display_name") or query,
      "kind": row.get("category") or row.get("class") or "",
      "bbox": bbox,
    })
  return found


def _geocode(query: str, origin, dest, route=None, previous=None):
  viewbox = _viewbox(origin, dest)
  limit = _limit_km(origin, dest)
  bounds = _route_bounds(route, origin, dest)
  queries = [query]
  key = _name_key(query)
  if key and key not in queries:
    queries.append(key)
  candidates = []
  seen = set()

  def add(rows):
    for row in rows:
      mark = (round(row["lng"], 4), round(row["lat"], 4), round(row.get("route_along") or 0, 3))
      if mark in seen:
        continue
      seen.add(mark)
      candidates.append(row)

  for item_query in queries:
    rows = _search_local(item_query, bounds)
    for row in rows:
      add(_expand_candidate(row, route, origin, dest))
  picked = _pick(_forward_only(candidates, route, origin, dest), query, origin, dest, limit, previous)
  if picked:
    return picked
  for bounded in (True, False):
    for item_query in queries:
      try:
        rows = _search_nominatim(item_query, viewbox, bounded)
      except Exception:
        continue
      for row in rows:
        add(_expand_candidate(row, route, origin, dest))
    if _pick(_forward_only(candidates, route, origin, dest), query, origin, dest, limit, previous):
      break
  return _pick(_forward_only(candidates, route, origin, dest), query, origin, dest, limit, previous)


def _polyline_lengths(coords):
  lengths = [0.0]
  for index in range(1, len(coords)):
    prev = coords[index - 1]
    nxt = coords[index]
    lengths.append(lengths[-1] + _km(prev[0], prev[1], nxt[0], nxt[1]))
  return lengths


def _point_at(coords, lengths, distance):
  if not coords:
    return 0.0, 0.0
  if distance <= 0:
    return coords[0][0], coords[0][1]
  if distance >= lengths[-1]:
    return coords[-1][0], coords[-1][1]
  for index in range(1, len(coords)):
    if lengths[index] < distance:
      continue
    span = lengths[index] - lengths[index - 1]
    ratio = 0.0 if span <= 1e-9 else (distance - lengths[index - 1]) / span
    prev = coords[index - 1]
    nxt = coords[index]
    return prev[0] + (nxt[0] - prev[0]) * ratio, prev[1] + (nxt[1] - prev[1]) * ratio
  return coords[-1][0], coords[-1][1]


def _along_line(coords, lengths, lng, lat):
  best = 0.0
  best_distance = None
  for index, item in enumerate(coords):
    distance = _km(lng, lat, item[0], item[1])
    if best_distance is None or distance < best_distance:
      best_distance = distance
      best = lengths[index]
  return best


def _known_along(slots, survived, point, start_point, end_point):
  if point == start_point:
    return 0.0
  if point == end_point:
    return 1.0
  for item in slots:
    if id(item) not in survived:
      continue
    if abs(item["lng"] - point[0]) < 1e-6 and abs(item["lat"] - point[1]) < 1e-6 and item.get("route_along") is not None:
      return item["route_along"]
  return 0.0


def _after_point(prev, target):
  # 没找到路名时，在上一个点朝下一站的方向放一个可拖动的途径点。
  dist = _km(prev[0], prev[1], target[0], target[1])
  if dist < 0.2:
    lat = prev[1]
    lng = prev[0] + 0.25 / max(20.0, 111.0 * math.cos(math.radians(lat)))
    return lng, lat
  step = min(0.8, max(0.25, dist * 0.35))
  if step > dist * 0.6:
    step = dist * 0.45
  ratio = step / dist
  return prev[0] + (target[0] - prev[0]) * ratio, prev[1] + (target[1] - prev[1]) * ratio


def _via_coordinate(item, origin, dest):
  lng = item["lng"]
  lat = item["lat"]
  bbox = item.get("bbox")
  if item.get("snapped") or not bbox or _is_road(item.get("query") or "") or item.get("kind") == "highway":
    return lng, lat
  south, north, west, east = bbox
  span = _km(west, south, east, north)
  if span < 0.45 or span > 12:
    return lng, lat
  return _closest_rect(origin, dest, west, south, east, north)


def _json_object(text: str) -> dict:
  from llm.io_preview import extract_json
  try:
    data = extract_json(text)
  except (ValueError, json.JSONDecodeError) as exc:
    raise ValueError("模型没有返回可用的查询结果") from exc
  if not isinstance(data, dict):
    raise ValueError("模型没有返回可用的查询结果")
  return data


def _clean_queries(value) -> list[str]:
  found = []
  for item in value or []:
    name = str(item or "").replace("\u3000", " ").strip()
    if len(name) < 2 or len(name) > 40 or name in found:
      continue
    found.append(name)
    if len(found) >= 12:
      break
  return found


def _route_off(lng, lat, route, origin, dest):
  path = route if route and len(route) >= 2 else [origin, dest]
  best = None
  for index in range(1, len(path)):
    distance, _ = _segment_distance(lng, lat, path[index - 1], path[index])
    if best is None or distance < best:
      best = distance
  return best if best is not None else 1e9


def _best_sample(samples):
  nearest = min(item["route_dist"] for item in samples)
  band = [item for item in samples if item["route_dist"] <= nearest + 0.15]
  band.sort(key=lambda item: item.get("route_along") or 0)
  return band[len(band) // 2]


def _bearing(start, end):
  scale = max(0.2, math.cos(math.radians((start[1] + end[1]) / 2.0)))
  return math.atan2((end[0] - start[0]) * scale, end[1] - start[1])


def _turn(left, right):
  diff = abs(left - right) % (2 * math.pi)
  if diff > math.pi:
    diff = (2 * math.pi) - diff
  return diff


def _shape_bearing(shape, lng, lat):
  if not shape or len(shape) < 2:
    return None
  best_index = 1
  best_distance = None
  for index in range(1, len(shape)):
    distance, _ = _segment_distance(lng, lat, shape[index - 1], shape[index])
    if best_distance is None or distance < best_distance:
      best_distance = distance
      best_index = index
  return _bearing(shape[best_index - 1], shape[best_index])


def _path_bearing(path, along):
  if not path or len(path) < 2:
    return None
  lengths = _polyline_lengths(path)
  total = lengths[-1] or 1.0
  target = min(1.0, max(0.0, along or 0.0)) * total
  for index in range(1, len(path)):
    if lengths[index] + 1e-9 >= target or index == len(path) - 1:
      return _bearing(path[index - 1], path[index])
  return None


def _sample_turn(sample, route, origin, dest):
  way = _shape_bearing(sample.get("road_shape") or [], sample["lng"], sample["lat"])
  if way is None:
    return 0.0
  path = route if route and len(route) >= 2 else [origin, dest]
  road = _path_bearing(path, sample.get("route_along") or 0.5)
  if road is None:
    return 0.0
  return _turn(way, road)


def _drop_opposite(groups, route, origin, dest):
  # 同名道路两侧都有时，只留和行程同向的一侧。只有一条线时两边都能走，不丢。
  if not groups:
    return groups
  turns = [_sample_turn(_best_sample(samples), route, origin, dest) for samples in groups]
  if not any(turn <= math.radians(100) for turn in turns):
    return groups
  return [samples for samples, turn in zip(groups, turns) if turn <= math.radians(100)]


def _forward_only(candidates, route, origin, dest):
  buckets = {}
  order = []
  for item in candidates:
    shape = tuple(item.get("road_shape") or ())
    key = shape if len(shape) >= 2 else ("point", id(item))
    if key not in buckets:
      buckets[key] = []
      order.append(key)
    buckets[key].append(item)
  kept = []
  for samples in _drop_opposite([buckets[key] for key in order], route, origin, dest):
    kept.extend(samples)
  return kept


def _project_xy(lng, lat, start, end):
  lat_scale = max(0.2, math.cos(math.radians((start[1] + end[1]) / 2)))
  ax = start[0] * 111.0 * lat_scale
  ay = start[1] * 111.0
  bx = end[0] * 111.0 * lat_scale
  by = end[1] * 111.0
  px = lng * 111.0 * lat_scale
  py = lat * 111.0
  dx = bx - ax
  dy = by - ay
  length_sq = dx * dx + dy * dy
  if length_sq <= 1e-12:
    return _km(lng, lat, start[0], start[1]), start
  ratio = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
  return _km(lng, lat, start[0] + (end[0] - start[0]) * ratio, start[1] + (end[1] - start[1]) * ratio), (
    start[0] + (end[0] - start[0]) * ratio,
    start[1] + (end[1] - start[1]) * ratio,
  )


def _closest_on_shape(shape, lng, lat):
  if not shape:
    return None
  if len(shape) == 1:
    return _km(lng, lat, shape[0][0], shape[0][1]), shape[0][0], shape[0][1], 1
  best = None
  for index in range(1, len(shape)):
    dist, point = _project_xy(lng, lat, shape[index - 1], shape[index])
    if best is None or dist < best[0]:
      best = (dist, point[0], point[1], index)
  return best


def _shapes_closest(prev_shape, shape):
  best = None
  for lng, lat in prev_shape:
    found = _closest_on_shape(shape, lng, lat)
    if found and (best is None or found[0] < best[0]):
      best = found
  for index, (lng, lat) in enumerate(shape):
    found = _closest_on_shape(prev_shape, lng, lat)
    if not found:
      continue
    item = (found[0], lng, lat, max(index, 1))
    if best is None or item[0] < best[0]:
      best = item
  return best


def _segment_progress_km(shape, seg, origin, dest):
  if len(shape) < 2:
    return 0.0
  index = min(max(seg, 1), len(shape) - 1)
  start = shape[index - 1]
  end = shape[index]
  direct = max(_km(origin[0], origin[1], dest[0], dest[1]), 1.0)
  return (_along(origin, dest, end[0], end[1]) - _along(origin, dest, start[0], start[1])) * direct


def _feature_shape(feature):
  return feature.get("shape") or feature.get("road_shape") or [(feature["lng"], feature["lat"])]


def _is_line(feature):
  if feature.get("kind") in ("收费站", "服务区", "停车区", "加油站"):
    return False
  return len(_feature_shape(feature)) >= 2 and (
    feature.get("kind") == "highway" or _is_road(feature.get("label") or "") or _is_road(feature.get("query") or "")
  )


def _meeting(prev, feature, origin, dest):
  shape = _feature_shape(feature)
  prev_shape = prev.get("road_shape") if prev.get("road_shape") and len(prev.get("road_shape")) >= 2 else None
  line = _is_line(feature)
  if line and prev_shape:
    found = _shapes_closest(prev_shape, shape)
    meet = "路与路"
    limit = 0.35
  elif line:
    found = _closest_on_shape(shape, prev["lng"], prev["lat"])
    meet = "点与路"
    limit = 4.0
  elif prev_shape:
    found = _closest_on_shape(prev_shape, feature["lng"], feature["lat"])
    meet = "路与点"
    limit = 0.45
  else:
    found = (_km(prev["lng"], prev["lat"], feature["lng"], feature["lat"]), feature["lng"], feature["lat"], 1)
    meet = "点与点"
    limit = 4.0
  if not found or found[0] > limit:
    if line and prev_shape:
      found = _closest_on_shape(shape, prev["lng"], prev["lat"])
      meet = "点与路"
      limit = 4.0
    if not found or found[0] > limit:
      return None
  _dist, lng, lat, seg = found
  along = _along(origin, dest, lng, lat)
  return {
    "dist": _dist,
    "lng": lng,
    "lat": lat,
    "seg": seg,
    "meet": meet,
    "route_along": along,
    "prog": _segment_progress_km(shape, seg, origin, dest) if line else 0.0,
    "line": line,
    "shape": shape,
    "feature": feature,
  }


def _chain_hit(prev, query, origin, dest):
  rows = _search_local(query, _route_bounds([(prev["lng"], prev["lat"]), dest], origin, dest))
  meetings = [item for item in (_meeting(prev, row, origin, dest) for row in rows) if item]
  if any(item["prog"] > 0.05 for item in meetings):
    meetings = [item for item in meetings if item["prog"] >= -0.05]
  if not meetings:
    return None
  meetings.sort(key=lambda item: (_km(prev["lng"], prev["lat"], item["lng"], item["lat"]), -item["prog"], item["dist"]))
  best = meetings[0]
  feature = best["feature"]
  label = feature.get("label") or query
  return {
    "query": query,
    "name": label,
    "lng": best["lng"],
    "lat": best["lat"],
    "road": best["line"] or _is_road(query) or _is_road(label) or feature.get("kind") == "highway",
    "route_along": best["route_along"],
    "route_dist": best["dist"],
    "road_shape": best["shape"] if best["line"] else None,
    "meet": best["meet"],
  }


def _geom_of(item):
  shape = item.get("road_shape") if isinstance(item, dict) else None
  if shape and len(shape) >= 2:
    return shape
  if isinstance(item, dict) and "lng" in item:
    return [(item["lng"], item["lat"])]
  return []


def _gap_on(shape, geom):
  if not shape or not geom:
    return None
  if len(shape) >= 2 and len(geom) >= 2:
    return _shapes_closest(geom, shape)
  if len(shape) >= 2:
    return _closest_on_shape(shape, geom[0][0], geom[0][1])
  if len(geom) >= 2:
    found = _closest_on_shape(geom, shape[0][0], shape[0][1])
    if not found:
      return None
    return found[0], shape[0][0], shape[0][1], 1
  return _km(shape[0][0], shape[0][1], geom[0][0], geom[0][1]), shape[0][0], shape[0][1], 1


def _load_named(query, origin, dest):
  bounds = _route_bounds([origin, dest], origin, dest)
  rows = list(_search_local(query, bounds))
  # 主路和辅道之间可以走，即使用户没有把辅道写进途径名称。
  base = (query or "").strip()
  if len(base) >= 2 and not any(mark in base for mark in ("辅道", "辅路", "辅线")):
    seen = {(round(item["lng"], 5), round(item["lat"], 5)) for item in rows}
    for suffix in ("辅道", "辅路", "辅线"):
      for extra in _search_local(base + suffix, bounds):
        key = (round(extra["lng"], 5), round(extra["lat"], 5))
        if key in seen:
          continue
        seen.add(key)
        extra = dict(extra)
        extra["frontage"] = True
        extra["query"] = base
        rows.append(extra)
  return rows


def _collect_hits(shape, geom):
  hits = []
  if not shape or not geom:
    return hits
  if len(shape) == 1:
    if len(geom) >= 2:
      found = _closest_on_shape(geom, shape[0][0], shape[0][1])
      if found:
        hits.append((found[0], shape[0][0], shape[0][1], 1))
    else:
      hits.append((_km(shape[0][0], shape[0][1], geom[0][0], geom[0][1]), shape[0][0], shape[0][1], 1))
    return hits
  for lng, lat in geom:
    found = _closest_on_shape(shape, lng, lat)
    if found:
      hits.append(found)
  for index, (lng, lat) in enumerate(shape):
    if len(geom) >= 2:
      found = _closest_on_shape(geom, lng, lat)
    else:
      found = (_km(lng, lat, geom[0][0], geom[0][1]), geom[0][0], geom[0][1], 1)
    if found:
      hits.append((found[0], lng, lat, max(index, 1)))
  return hits


def _biased_gap(shape, geom, bias):
  # 几何上同样近时，用起点或终点决定靠哪一头。
  hits = _collect_hits(shape, geom)
  if not hits:
    return None
  nearest = min(hit[0] for hit in hits)
  pool = [hit for hit in hits if hit[0] <= nearest + 0.4]
  pool.sort(key=lambda hit: (_km(hit[1], hit[2], bias[0], bias[1]), hit[0]))
  return pool[0]


def _seg_bearing(shape, seg):
  if len(shape) < 2:
    return None
  index = min(max(int(seg), 1), len(shape) - 1)
  return _bearing(shape[index - 1], shape[index])


def _aim_from(point, next_geom, origin, dest):
  if next_geom and len(next_geom) >= 2:
    end = max(next_geom, key=lambda item: (_along(origin, dest, item[0], item[1]), _km(point[0], point[1], item[0], item[1])))
    if _km(point[0], point[1], end[0], end[1]) > 0.03:
      return _bearing(point, end)
  if next_geom and _km(point[0], point[1], next_geom[0][0], next_geom[0][1]) > 0.03:
    return _bearing(point, next_geom[0])
  if _km(point[0], point[1], dest[0], dest[1]) > 0.03:
    return _bearing(point, dest)
  if _km(origin[0], origin[1], dest[0], dest[1]) > 0.03:
    return _bearing(origin, dest)
  return None


def _depart_aim(shape, entrance, next_geom, origin, dest):
  # 下一条线能定方向时用它；否则看这条线离开入口后朝终点延伸的那一头。
  if next_geom and len(next_geom) >= 2:
    return _aim_from(entrance, next_geom, origin, dest)
  if len(shape) >= 2:
    far = max(
      shape,
      key=lambda item: (
        _km(item[0], item[1], entrance[0], entrance[1]),
        _along(origin, dest, item[0], item[1]),
      ),
    )
    if _km(entrance[0], entrance[1], far[0], far[1]) > 0.03:
      return _bearing(entrance, far)
  return _aim_from(entrance, next_geom, origin, dest)


def _shift_on_shape(shape, lng, lat, seg, aim):
  way = _seg_bearing(shape, seg)
  if way is None or aim is None or len(shape) < 2:
    return lng, lat, seg
  if _turn(way, aim) <= math.radians(60):
    step = 0.1
  elif _turn((way + math.pi) % (2 * math.pi), aim) <= math.radians(60):
    step = -0.1
  else:
    return lng, lat, seg
  index = min(max(int(seg), 1), len(shape) - 1)
  if step > 0:
    cursor = (lng, lat)
    remain = step
    for vertex in shape[index:]:
      dist = _km(cursor[0], cursor[1], vertex[0], vertex[1])
      if dist + 1e-9 >= remain:
        ratio = 0.0 if dist <= 1e-9 else remain / dist
        return (
          cursor[0] + (vertex[0] - cursor[0]) * ratio,
          cursor[1] + (vertex[1] - cursor[1]) * ratio,
          index,
        )
      remain -= dist
      cursor = vertex
      index += 1
    return shape[-1][0], shape[-1][1], len(shape) - 1
  cursor = (lng, lat)
  remain = -step
  index -= 1
  while index >= 0 and remain > 0:
    vertex = shape[index]
    dist = _km(cursor[0], cursor[1], vertex[0], vertex[1])
    if dist + 1e-9 >= remain:
      ratio = 0.0 if dist <= 1e-9 else remain / dist
      return (
        cursor[0] + (vertex[0] - cursor[0]) * ratio,
        cursor[1] + (vertex[1] - cursor[1]) * ratio,
        max(index, 1),
      )
    remain -= dist
    cursor = vertex
    index -= 1
  return shape[0][0], shape[0][1], 1


def _is_poi(feature):
  return feature.get("kind") in ("收费站", "服务区", "停车区", "加油站")


def _onto_segment(start, end, point):
  # 点相对“上一段到下一段”这条方向的前后位置和偏离。ratio 小于 0 表示还在上一段背后。
  scale = max(0.2, math.cos(math.radians((start[1] + end[1]) / 2)))
  dx = (end[0] - start[0]) * 111.0 * scale
  dy = (end[1] - start[1]) * 111.0
  px = (point[0] - start[0]) * 111.0 * scale
  py = (point[1] - start[1]) * 111.0
  length = math.hypot(dx, dy)
  if length < 1e-6:
    return 0.0, math.hypot(px, py)
  ratio = (px * dx + py * dy) / (length * length)
  lateral = abs(dx * py - dy * px) / length
  return ratio, lateral


def _right_km(start, end, point):
  # 大于 0 表示点在 start→end 方向的右侧。
  scale = max(0.2, math.cos(math.radians((start[1] + end[1]) / 2)))
  dx = (end[0] - start[0]) * scale
  dy = end[1] - start[1]
  px = (point[0] - start[0]) * scale
  py = point[1] - start[1]
  length = math.hypot(dx, dy)
  if length < 1e-9:
    return 0.0
  return (px * dy - py * dx) / length * 111.0


def _travel_ray(prev_geom, next_geom, here):
  # 从当前所在位置开往和下一条路相接的地方。
  if not prev_geom or not next_geom:
    return None
  if len(prev_geom) < 2:
    return None
  hit = _gap_on(prev_geom, next_geom)
  if not hit:
    return None
  junction = (hit[1], hit[2])
  origin = here
  if origin is None or _km(origin[0], origin[1], junction[0], junction[1]) < 0.04:
    origin = min(prev_geom, key=lambda item: _km(item[0], item[1], junction[0], junction[1]) * -1)
  if origin is None or _km(origin[0], origin[1], junction[0], junction[1]) < 0.04:
    return None
  return origin, junction


def _geom_side(ray, geom):
  if not ray or not geom:
    return None
  band = [item for item in geom if 0.02 < _km(item[0], item[1], ray[1][0], ray[1][1]) <= 0.8]
  if not band:
    band = [item for item in geom if _km(item[0], item[1], ray[1][0], ray[1][1]) > 0.02]
  if not band:
    return None
  return sum(_right_km(ray[0], ray[1], item) for item in band) / len(band)


def _turn_on_right(prev_geom, next_geom, later_geom, here, ray=None):
  # 下一条路 C 决定这一步左转还是右转。C 左右不分时，再看再下一条路。
  ray = ray or _travel_ray(prev_geom, next_geom, here)
  if not ray and later_geom:
    ray = _travel_ray(prev_geom, later_geom, here)
  if not ray:
    return None
  side = _geom_side(ray, next_geom)
  if (side is None or abs(side) < 0.03) and later_geom:
    side = _geom_side(ray, later_geom)
  if side is None or abs(side) < 0.03:
    return None
  return side > 0


def _meet_ray(prev_geom, here, options, origin=None, dest=None):
  # 从当前所在位置开往前方的路口，不把已经落在起点后面的交会点当成行进方向。
  contacts = []
  for item in options:
    shape = item.get("shape")
    if not item.get("line") or not shape:
      continue
    hit = _gap_on(shape, prev_geom)
    if hit:
      contacts.append((hit[1], hit[2]))
  if not contacts or not prev_geom:
    return None
  pool = contacts
  if here is not None and origin is not None and dest is not None:
    anchor_prog = _progress_km(origin, dest, here)
    ahead = [
      point for point in contacts
      if _progress_km(origin, dest, point) >= anchor_prog - 0.4
    ]
    if ahead:
      pool = ahead
  if here is not None:
    junction = min(pool, key=lambda point: _km(point[0], point[1], here[0], here[1]))
  else:
    junction = pool[0]
  origin = here
  if origin is None or _km(origin[0], origin[1], junction[0], junction[1]) < 0.04:
    if len(prev_geom) < 2:
      return None
    origin = max(prev_geom, key=lambda point: _km(point[0], point[1], junction[0], junction[1]))
  if origin is None or _km(origin[0], origin[1], junction[0], junction[1]) < 0.04:
    return None
  return origin, junction


def _leave_bearing(item):
  shape = item.get("shape") or []
  if len(shape) < 2:
    return None
  if item.get("meet_lng") is not None:
    near = (item["meet_lng"], item["meet_lat"])
  elif item.get("near_lng") is not None:
    near = (item["near_lng"], item["near_lat"])
  else:
    return None
  far = max(shape, key=lambda point: _km(point[0], point[1], near[0], near[1]))
  if _km(near[0], near[1], far[0], far[1]) <= 0.03:
    return None
  return _bearing(near, far)


def _branch_side(item, ray):
  # 用离开路口的方向判断这一支在左还是在右，交会点本身分不出左右。
  leave = _leave_bearing(item)
  if leave is None or not ray:
    return item.get("right_km", 0.0)
  if item.get("meet_lng") is not None:
    junction = (item["meet_lng"], item["meet_lat"])
  else:
    junction = (item["lng"], item["lat"])
  lat = junction[1] + math.cos(leave) * 0.2 / 111.0
  lng = junction[0] + math.sin(leave) * 0.2 / max(20.0, 111.0 * math.cos(math.radians(junction[1])))
  return _right_km(ray[0], ray[1], (lng, lat))


def _progress_km(origin, dest, point):
  return _along(origin, dest, point[0], point[1]) * max(_km(origin[0], origin[1], dest[0], dest[1]), 0.001)


def _heading_km(item, ray):
  # 线自己的方向朝左还是朝右。往左的线小于 0。
  way = item.get("way")
  if way is None or not ray:
    return item.get("right_km", 0.0)
  if item.get("meet_lng") is not None:
    junction = (item["meet_lng"], item["meet_lat"])
  else:
    junction = (item["lng"], item["lat"])
  lat = junction[1] + math.cos(way) * 0.2 / 111.0
  lng = junction[0] + math.sin(way) * 0.2 / max(20.0, 111.0 * math.cos(math.radians(junction[1])))
  return _right_km(ray[0], ray[1], (lng, lat))


def _sit_at_crossing(item):
  # 点放在两条路交会处，再顺着这条线的方向挪出几十米。
  item["lng"] = item["meet_lng"]
  item["lat"] = item["meet_lat"]
  way = item.get("way")
  if way is not None:
    step = 0.04
    lat = item["lat"] + math.cos(way) * step / 111.0
    lng = item["lng"] + math.sin(way) * step / max(20.0, 111.0 * math.cos(math.radians(item["lat"])))
    item["lng"], item["lat"] = lng, lat
  item["near_lng"] = item["lng"]
  item["near_lat"] = item["lat"]
  if item.get("shape"):
    item["shape"] = _clip_shape(item["shape"], item["lng"], item["lat"], 0.25)


def _crossing_choice(branches, on_right, here, origin, dest, ray):
  # 先取靠近上一个点、并且不走到起点后面的那个路口，再按 C 决定左右。
  if not branches or on_right is None:
    return [], ""
  anchor = here if here is not None else (origin[0], origin[1])
  anchor_prog = _progress_km(origin, dest, anchor)

  def meet_key(item):
    point = (item["meet_lng"], item["meet_lat"])
    behind = 1 if _progress_km(origin, dest, point) < anchor_prog - 0.4 else 0
    return (
      behind,
      _km(point[0], point[1], anchor[0], anchor[1]),
      _km(point[0], point[1], dest[0], dest[1]),
    )

  best = min(branches, key=meet_key)
  junction = (best["meet_lng"], best["meet_lat"])
  local = [
    item for item in branches
    if _km(item["meet_lng"], item["meet_lat"], junction[0], junction[1]) <= 0.3
  ]
  for item in local:
    item["heading_km"] = _heading_km(item, ray)
  if on_right:
    side = [item for item in local if _heading_km(item, ray) >= -0.04]
    # 右转用旁边、方向往右的那条线。
    picked = [item for item in side if item.get("forward") and _heading_km(item, ray) > 0.02] or [item for item in side if item.get("forward")] or side
    turn = "right"
  else:
    side = [item for item in local if _heading_km(item, ray) <= 0.04]
    # 左转用方向往左的那条线，点仍在路口上。
    picked = [item for item in side if _heading_km(item, ray) < -0.02] or side
    turn = "left"
  for item in picked:
    _sit_at_crossing(item)
    item["cross_turn"] = turn
  return picked, turn


def _is_cross_branch(item, ray):
  # 离开上一条路的方向和行进方向差开，说明这是路口分出去的一支，不是对向车道。
  if not ray or not item.get("line"):
    return False
  leave = _leave_bearing(item)
  travel = _bearing(ray[0], ray[1])
  if leave is None or travel is None:
    return False
  angle = _turn(leave, travel)
  return math.radians(35) <= angle <= math.radians(150)


def _later_geom(next_geom, later_rows):
  best = None
  best_dist = None
  for row in later_rows or []:
    geom = _row_geom(row)
    if not geom:
      continue
    if next_geom:
      gap = _gap_on(geom, next_geom)
      dist = gap[0] if gap else 1e9
    else:
      dist = 0.0
    if best is None or dist < best_dist:
      best = geom
      best_dist = dist
  return best


def _link_ends(prev_geom, next_geom):
  # 上下两段各自离对方最近的点，方向就是从上一处开往下一处。
  if not prev_geom or not next_geom:
    return None
  best = None

  def consider(prev_pt, next_pt):
    nonlocal best
    dist = _km(prev_pt[0], prev_pt[1], next_pt[0], next_pt[1])
    if best is None or dist < best[0]:
      best = (dist, prev_pt, next_pt)

  if len(next_geom) >= 2:
    for lng, lat in prev_geom:
      found = _closest_on_shape(next_geom, lng, lat)
      if found:
        consider((lng, lat), (found[1], found[2]))
  else:
    for lng, lat in prev_geom:
      consider((lng, lat), next_geom[0])
  if len(prev_geom) >= 2:
    for lng, lat in next_geom:
      found = _closest_on_shape(prev_geom, lng, lat)
      if found:
        consider((found[1], found[2]), (lng, lat))
  elif len(prev_geom) == 1:
    for lng, lat in next_geom:
      consider(prev_geom[0], (lng, lat))
  if not best:
    return None
  return best[1], best[2]


def _faces_forward(shape, prev_geom):
  # 从和上一段的接点出发，线的方向要朝自己离开的那一头，不能是对向。
  if len(shape) < 2:
    return True, None
  hit = _gap_on(shape, prev_geom)
  if not hit:
    return False, None
  contact = (hit[1], hit[2])
  far = max(shape, key=lambda item: _km(item[0], item[1], contact[0], contact[1]))
  if _km(contact[0], contact[1], far[0], far[1]) <= 0.03:
    return True, hit
  way = _seg_bearing(shape, hit[3])
  want = _bearing(contact, far)
  return way is None or _turn(way, want) <= math.radians(100), hit


def _row_geom(row):
  shape = _feature_shape(row)
  if _is_line(row) or (_is_poi(row) and len(shape) >= 2 and _km(shape[0][0], shape[0][1], shape[-1][0], shape[-1][1]) >= 0.03):
    return shape
  return [(row["lng"], row["lat"])]


def _forward_next(prev_geom, rows, fallback):
  # 下一条线用顺着上一段开出去的那一侧，不用更近的对向。
  forward = []
  others = []
  for row in rows or []:
    geom = _row_geom(row)
    if len(geom) < 2:
      dist = _gap_on(prev_geom, geom)
      others.append((dist[0] if dist else 1e9, geom))
      continue
    ok, hit = _faces_forward(geom, prev_geom)
    if not hit:
      continue
    (forward if ok else others).append((hit[0], geom))
  pool = forward or others
  if not pool:
    return fallback
  pool.sort(key=lambda item: item[0])
  return pool[0][1]


def _clip_shape(shape, lng, lat, radius_km=0.3):
  # 分叉后只留下靠近已选点的一小段，避免下一次选点贴到远处的另一支。
  if not shape or len(shape) < 2:
    return shape
  nearest = min(range(len(shape)), key=lambda index: _km(shape[index][0], shape[index][1], lng, lat))
  start = nearest
  while start > 0 and _km(shape[start - 1][0], shape[start - 1][1], lng, lat) <= radius_km:
    start -= 1
  end = nearest
  while end + 1 < len(shape) and _km(shape[end + 1][0], shape[end + 1][1], lng, lat) <= radius_km:
    end += 1
  piece = shape[start:end + 1]
  if len(piece) >= 2:
    return piece
  index = min(max(nearest, 1), len(shape) - 1)
  return [shape[index - 1], shape[index]]


def _forked(options):
  anchors = [
    (item["near_lng"], item["near_lat"])
    for item in options
    if item.get("near_lng") is not None and item.get("line")
  ]
  if len(anchors) < 2:
    return False
  for index, left in enumerate(anchors):
    for right in anchors[index + 1:]:
      if _km(left[0], left[1], right[0], right[1]) <= 0.3:
        return True
  return False


def _place_between(feature, prev_geom, next_geom, origin, dest, reach=6.0, link=None, gate=""):
  shape = _feature_shape(feature)
  poi = _is_poi(feature)
  span = _km(shape[0][0], shape[0][1], shape[-1][0], shape[-1][1]) if len(shape) >= 2 else 0.0
  line = _is_line(feature) or (poi and len(shape) >= 2 and span >= 0.03)
  if not line:
    lng, lat = feature["lng"], feature["lat"]
    d0 = _gap_on(prev_geom, [(lng, lat)])
    d1 = _gap_on(next_geom, [(lng, lat)])
    if not d0 or not d1 or max(d0[0], d1[0]) > reach:
      return None
    prev_pt = (d0[1], d0[2])
    next_pt = (d1[1], d1[2])
    if _km(prev_pt[0], prev_pt[1], next_pt[0], next_pt[1]) > 0.04:
      aim = _bearing(prev_pt, next_pt)
    else:
      aim = _bearing((lng, lat), next_pt) if d1[0] > 0.02 else None
    arrive = _bearing(prev_pt, (lng, lat)) if d0[0] > 0.02 else aim
    turn = _turn(arrive, aim) if aim is not None and arrive is not None else 0.0
    lateral = min(d0[0], d1[0])
    forward = aim is None or turn <= math.radians(100)
    ratio = 0.0
    # 只留从上一段指向下一段这一侧的口。
    if link and _km(link[0][0], link[0][1], link[1][0], link[1][1]) > 0.04:
      ratio, lateral = _onto_segment(link[0], link[1], (lng, lat))
      aim = _bearing(link[0], link[1])
      arrive = _bearing(link[0], (lng, lat)) if _km(link[0][0], link[0][1], lng, lat) > 0.02 else aim
      turn = _turn(arrive, aim) if aim is not None and arrive is not None else 0.0
      forward = ratio >= -0.2 and turn <= math.radians(100)
      if gate == "exit":
        # 高速后：要在主线出去的那一侧，1.5 公里外是另一座站。
        forward = ratio >= -0.15 and turn <= math.radians(100) and lateral <= 0.45 and d0[0] <= 1.5
      elif gate == "enter":
        # 高速前：还没越过高速。已经到主线另一侧的是出口。
        forward = -0.2 <= ratio <= 1.08 and turn <= math.radians(100) and lateral <= 0.45
    return {
      "lng": lng,
      "lat": lat,
      "gap": d1[0],
      "forward": forward,
      "turn": turn,
      "line": False,
      "poi": poi,
      "shape": shape,
      "feature": feature,
      "dist": d0[0],
      "prev_dist": d0[0],
      "near_lng": lng,
      "near_lat": lat,
      "trip": d1[0],
      "lateral": lateral,
      "ratio": ratio,
    }
  left = _gap_on(shape, prev_geom)
  right = _gap_on(shape, next_geom)
  if not left or not right or max(left[0], right[0]) > reach:
    return None
  separated = _km(left[1], left[2], right[1], right[2]) > 0.05
  near = (left[1], left[2])
  near_seg = left[3]
  meet = (left[1], left[2])
  if separated:
    want = _bearing((left[1], left[2]), (right[1], right[2]))
  else:
    far = max(shape, key=lambda item: _km(item[0], item[1], near[0], near[1]))
    want = _bearing(near, far) if _km(near[0], near[1], far[0], far[1]) > 0.03 else None
  if want is not None:
    shifted = _shift_on_shape(shape, near[0], near[1], near_seg, want)
    near = (shifted[0], shifted[1])
    near_seg = shifted[2]
  # 普通路取刚接上一段的位置。出口落到高速出去的那一头，入口留在还没上高速的那一头。
  if gate == "exit" and separated:
    point = (right[1], right[2])
    seg = right[3]
  else:
    point = near
    seg = near_seg
  way = _seg_bearing(shape, seg)
  turn = _turn(way, want) if way is not None and want is not None else 0.0
  forward = want is None or turn <= math.radians(100)
  lateral = 0.0
  ratio = 0.0
  if link and _km(link[0][0], link[0][1], link[1][0], link[1][1]) > 0.04:
    ratio, lateral = _onto_segment(link[0], link[1], point)
    if gate == "exit":
      forward = ratio >= -0.15 and lateral <= 0.45 and left[0] <= 1.5
    elif gate == "enter":
      forward = -0.2 <= ratio <= 1.08 and lateral <= 0.45
    elif ratio < -0.2:
      forward = False
  return {
    "lng": point[0],
    "lat": point[1],
    "gap": left[0] + right[0],
    "forward": forward,
    "turn": turn,
    "way": way,
    "line": True,
    "poi": poi,
    "shape": shape,
    "feature": feature,
    "dist": min(left[0], right[0]),
    "prev_dist": left[0],
    "near_lng": near[0],
    "near_lat": near[1],
    "meet_lng": meet[0],
    "meet_lat": meet[1],
    "full_shape": list(shape),
    "trip": right[0],
    "lateral": lateral,
    "ratio": ratio,
  }


def _ranked_options(rows, prev_geom, next_rows, fallback, origin, dest, query, reach=6.0, gate="", here=None, later_rows=None):
  if gate == "enter":
    highway_rows = [row for row in (next_rows or []) if _is_expressway(row.get("label") or "") or _is_expressway(row.get("query") or "")]
    if highway_rows:
      next_rows = highway_rows
  next_geom = _forward_next(prev_geom, next_rows, fallback)
  link = _link_ends(prev_geom, next_geom)
  options = []
  for row in rows:
    placed = _place_between(row, prev_geom, next_geom, origin, dest, reach, link, gate)
    if placed:
      options.append(placed)
  ray = _meet_ray(prev_geom, here, options, origin, dest) or _travel_ray(prev_geom, next_geom, here)
  later_geom = _later_geom(next_geom, later_rows)
  for item in options:
    item["right_km"] = _right_km(ray[0], ray[1], (item["lng"], item["lat"])) if ray else 0.0
  on_right = _turn_on_right(prev_geom, next_geom, later_geom, here, ray)
  if gate in ("exit", "enter"):
    # 出入口靠右：先上右侧匝道，左侧是对向的口。
    right_tolls = [item for item in options if item.get("poi") and item.get("right_km", 0.0) >= -0.02]
    if right_tolls and len(right_tolls) < len([item for item in options if item.get("poi")]):
      options = [item for item in options if not item.get("poi") or item.get("right_km", 0.0) >= -0.02]
  else:
    branches = [item for item in options if _is_cross_branch(item, ray) and item.get("meet_lng") is not None]
    for item in branches:
      item["right_km"] = _branch_side(item, ray)
    sided, _turn = _crossing_choice(branches, on_right, here, origin, dest, ray)
    if sided:
      options = sided + [item for item in options if not item.get("line")]
    elif any(item.get("line") and item.get("forward") for item in options):
      # 当前侧能走就留在当前侧。跑到对向车道会先绕过去再绕回来。
      options = [item for item in options if not item.get("line") or item.get("forward")]
    elif on_right is False and any(item.get("line") and not item["forward"] for item in options):
      options = [item for item in options if not item.get("line") or not item["forward"]]
  if not options:
    return []
  anchor = here if here is not None else (origin[0], origin[1])
  anchor_prog = _progress_km(origin, dest, anchor)
  for item in options:
    item["here_dist"] = _km(item["lng"], item["lat"], anchor[0], anchor[1])
    item["start_dist"] = _km(item["lng"], item["lat"], origin[0], origin[1])
    item["end_dist"] = _km(item["lng"], item["lat"], dest[0], dest[1])
    item["behind"] = 1 if _progress_km(origin, dest, (item["lng"], item["lat"])) < anchor_prog - 0.4 else 0
  if gate == "exit":
    # 先上右侧匝道，再过出口。右侧更靠匝道外侧的口优先。
    options.sort(key=lambda item: (
      0 if item.get("right_km", 0.0) >= -0.02 else 1,
      -min(item.get("prev_dist", item["dist"]), 1.2),
      -item.get("right_km", 0.0),
    ))
  elif gate == "enter":
    # 入口也在右侧匝道上，还在高速前面。
    options.sort(key=lambda item: (
      0 if item.get("right_km", 0.0) >= -0.02 else 1,
      item.get("trip", 0.0),
      -item.get("right_km", 0.0),
    ))
  else:
    # 路口的点已经落在交会处。其余的点先留在当前侧，再尽量靠近上一个点。
    options.sort(key=lambda item: (
      0 if item.get("cross_turn") != "left" or item.get("heading_km", item.get("right_km", 0.0)) < 0 else 1,
      item.get("behind", 0),
      item.get("here_dist", item.get("prev_dist", item["dist"])),
      item.get("end_dist", 0.0),
      item.get("lateral", 0.0),
    ))
    nearest = options[0].get("here_dist", 0.0)
    # 同一侧只留靠近上一条路的点，不把点放到这条路的远处。
    options = [
      item for item in options
      if not item.get("line") or item.get("here_dist", 0.0) <= nearest + 0.4
    ]
  return options


def _slot_from(best, query, origin, dest, gate):
  feature = best["feature"]
  label = feature.get("label") or query
  frontage = bool(feature.get("frontage")) or any(mark in (label or "") for mark in ("辅道", "辅路", "辅线"))
  shape = best["shape"] if best["line"] else None
  if best.get("poi") and shape:
    # 只把收费口附近交给下一段，整条匝道会把后面的路带到远处。
    shape = _clip_shape(shape, best["lng"], best["lat"], 0.25)
  slot = {
    "query": query,
    "name": label,
    "lng": best["lng"],
    "lat": best["lat"],
    "road": (not frontage) and ((best["line"] and not best.get("poi")) or _is_road(query) or _is_road(label) or feature.get("kind") == "highway"),
    "route_along": _along(origin, dest, best["lng"], best["lat"]),
    "route_dist": best["dist"],
    "road_shape": shape,
    "meet": "之间",
    "gate": gate,
  }
  if best.get("full_shape"):
    slot["full_shape"] = best["full_shape"]
  if best.get("way") is not None:
    slot["way"] = best["way"]
  if best.get("cross_turn"):
    slot["cross_turn"] = best["cross_turn"]
  if best.get("meet_lng") is not None:
    slot["meet_lng"] = best["meet_lng"]
    slot["meet_lat"] = best["meet_lat"]
  return slot


def _finish_choice(options, query, origin, dest, gate):
  if not options:
    return None
  best = options[0]
  if (
    gate not in ("exit", "enter")
    and best.get("line")
    and not best.get("poi")
    and best.get("near_lng") is not None
    and (_forked(options) or _km(best["lng"], best["lat"], best["near_lng"], best["near_lat"]) > 0.25)
  ):
    best = dict(best)
    best["lng"] = best["near_lng"]
    best["lat"] = best["near_lat"]
    best["shape"] = _clip_shape(best["shape"], best["lng"], best["lat"])
  return _slot_from(best, query, origin, dest, gate)


def _choose_between(rows, prev_geom, next_rows, fallback, origin, dest, query, reach=6.0, gate="", here=None, later_rows=None):
  return _finish_choice(
    _ranked_options(rows, prev_geom, next_rows, fallback, origin, dest, query, reach, gate, here, later_rows),
    query, origin, dest, gate,
  )


def _along_of(path, point):
  found = _closest_on_shape(path, point[0], point[1])
  if not found:
    return None
  seg = max(int(found[3]), 1)
  walked = 0.0
  for index in range(1, seg):
    walked += _km(path[index - 1][0], path[index - 1][1], path[index][0], path[index][1])
  walked += _km(path[seg - 1][0], path[seg - 1][1], found[1], found[2])
  return walked, (found[1], found[2])


def _segment_gap(a, b, c, d):
  # 两条线段的最近距离（公里），以及落在第一条线段上的点。
  scale = max(0.2, math.cos(math.radians((a[1] + b[1]) / 2)))

  def xy(point):
    return ((point[0] - a[0]) * scale * 111.0, (point[1] - a[1]) * 111.0)

  bx, by = xy(b)
  cx, cy = xy(c)
  dx, dy = xy(d)
  rx, ry = dx - cx, dy - cy
  denom = bx * ry - by * rx
  if abs(denom) < 1e-9:
    candidates = []
    for ux in (0.0, 1.0):
      px, py = bx * ux, by * ux
      length = math.hypot(rx, ry)
      if length < 1e-9:
        vx = 0.0
      else:
        vx = min(1.0, max(0.0, ((px - cx) * rx + (py - cy) * ry) / (length * length)))
      qx, qy = cx + rx * vx, cy + ry * vx
      candidates.append((math.hypot(px - qx, py - qy), ux))
    dist, ux = min(candidates)
  else:
    ux = min(1.0, max(0.0, (cx * ry - cy * rx) / denom))
    vx = min(1.0, max(0.0, (cx * by - cy * bx) / denom))
    px, py = bx * ux, by * ux
    qx, qy = cx + rx * vx, cy + ry * vx
    dist = math.hypot(px - qx, py - qy)
  return dist, (a[0] + (b[0] - a[0]) * ux, a[1] + (b[1] - a[1]) * ux)


def _crossings_until(path, own_names, stop_names):
  # 沿这条路查出交会的路，直到下一条指定路名。先全部记下，是否接到下一条路另作返回。
  if len(path) < 2 or not stop_names:
    return [], False
  boxes = []
  for lng, lat in path:
    pad_lat = 0.35 / 111.0
    pad_lng = 0.35 / max(20.0, 111.0 * math.cos(math.radians(lat)))
    boxes.append((lng - pad_lng, lat - pad_lat, lng + pad_lng, lat + pad_lat))
  hits = []
  for road in _roads_in_box(boxes):
    name = (road.get("label") or "").strip()
    other = road.get("shape") or []
    if not name or name in own_names or len(other) < 2:
      continue
    best = None
    for index in range(len(path) - 1):
      for other_index in range(len(other) - 1):
        dist, point = _segment_gap(path[index], path[index + 1], other[other_index], other[other_index + 1])
        if best is None or dist < best[0]:
          best = (dist, point, index, other_index)
    if not best or best[0] > 0.08:
      continue
    placed = _along_of(path, best[1])
    if not placed:
      continue
    our_way = _bearing(path[best[2]], path[best[2] + 1])
    their_way = _bearing(other[best[3]], other[best[3] + 1])
    if our_way is not None and their_way is not None and _turn(our_way, their_way) < math.radians(25):
      continue
    hits.append((placed[0], placed[1], name))
  hits.sort(key=lambda item: item[0])
  chosen = []
  found = False
  for along, point, name in hits:
    if along < 0.12:
      continue
    if name in stop_names:
      found = True
      break
    if any(_km(point[0], point[1], prev[0], prev[1]) < 0.3 for prev in chosen):
      continue
    chosen.append(point)
  return chosen, found


def _shape_key(shape):
  start = (round(shape[0][0], 5), round(shape[0][1], 5))
  end = (round(shape[-1][0], 5), round(shape[-1][1], 5))
  return (start, end) if start <= end else (end, start)


def _directed_slice(shape, start, bearing, meet):
  # 从已选点出发，只留顺着已选走向的那一半。
  found = _closest_on_shape(shape, start[0], start[1])
  if not found:
    return []
  seg = max(int(found[3]), 1)
  point = (found[1], found[2])
  ahead = [point] + [item for item in shape[seg:] if _km(item[0], item[1], point[0], point[1]) > 0.01]
  behind = [point] + [item for item in reversed(shape[:seg]) if _km(item[0], item[1], point[0], point[1]) > 0.01]

  def score(part):
    if len(part) < 2:
      return (math.pi, 1)
    step = _bearing(part[0], part[min(len(part) - 1, 3)])
    angle = _turn(step, bearing) if step is not None and bearing is not None else 0.0
    back = 0
    if meet is not None and _km(part[-1][0], part[-1][1], meet[0], meet[1]) + 0.05 < _km(point[0], point[1], meet[0], meet[1]):
      back = 1
    return (angle, back)

  best = min((ahead, behind), key=score)
  if len(best) < 2:
    other = behind if best is ahead else ahead
    if len(other) >= 2 and (bearing is None or score(other)[0] <= math.radians(80)):
      best = other
  if len(best) >= 2:
    return best
  if bearing is None:
    return []
  lat = point[1] + math.cos(bearing) * 0.05 / 111.0
  lng = point[0] + math.sin(bearing) * 0.05 / max(20.0, 111.0 * math.cos(math.radians(point[1])))
  return [point, (lng, lat)]


def _next_piece(end, bearing, rows, name, used):
  # 同一路名、同一走向的下一段。路口处换到另一条路就停。
  best = None
  for row in rows or []:
    if (row.get("label") or "").strip() != name:
      continue
    shape = row.get("shape") or []
    if len(shape) < 2:
      continue
    key = _shape_key(shape)
    if key in used:
      continue
    if _km(shape[0][0], shape[0][1], end[0], end[1]) <= 0.12:
      part = list(shape)
    elif _km(shape[-1][0], shape[-1][1], end[0], end[1]) <= 0.12:
      part = list(reversed(shape))
    else:
      continue
    step = _bearing(part[0], part[min(len(part) - 1, 3)])
    angle = _turn(bearing, step) if bearing is not None and step is not None else 0.0
    if angle > math.radians(70):
      continue
    dist = _km(part[0][0], part[0][1], end[0], end[1])
    if best is None or angle < best[0] - 0.15 or (abs(angle - best[0]) <= 0.15 and dist < best[1]):
      best = (angle, dist, part, key)
  if not best:
    return None
  used.add(best[3])
  return best[2]


def _forward_path(hit, rows):
  # 走向和点位已经定了，就从这里顺着这条路继续往前接。
  shape = hit.get("full_shape") or []
  if len(shape) < 2 or hit.get("lng") is None:
    return []
  start = (hit["lng"], hit["lat"])
  meet = (hit["meet_lng"], hit["meet_lat"]) if hit.get("meet_lng") is not None else None
  path = _directed_slice(shape, start, hit.get("way"), meet)
  if len(path) < 2:
    return []
  name = (hit.get("name") or "").strip()
  used = {_shape_key(shape)}
  walked = 0.0
  for index in range(1, len(path)):
    walked += _km(path[index - 1][0], path[index - 1][1], path[index][0], path[index][1])
  for _ in range(40):
    if walked >= 45:
      break
    piece = _next_piece(path[-1], _bearing(path[-2], path[-1]), rows, name, used)
    if not piece:
      break
    for point in piece[1:]:
      walked += _km(path[-1][0], path[-1][1], point[0], point[1])
      path.append(point)
      if walked >= 45:
        break
  return path


def _next_is_toll(next_rows):
  for row in next_rows or []:
    for key in ("label", "query"):
      if _is_toll_name(row.get(key) or ""):
        return True
  return False


def _path_meets(path, rows, limit=0.45):
  # 线已经和下一条路交上或靠得很近，就说明这条选点是接上的。
  for row in rows or []:
    geom = _row_geom(row)
    if len(path) >= 2 and len(geom) >= 2:
      nearest = None
      for index in range(len(path) - 1):
        for other in range(len(geom) - 1):
          dist, _point = _segment_gap(path[index], path[index + 1], geom[other], geom[other + 1])
          if nearest is None or dist < nearest:
            nearest = dist
      if nearest is not None and nearest <= limit:
        return True
      continue
    if geom:
      gap = _gap_on(path, geom)
      if gap and gap[0] <= limit:
        return True
  return False


def _extra_along(hit, rows, next_rows, dest):
  # 沿路路口只用来确认能不能接到下一条路，不生成途径点。
  # 收费站和已经靠上下一条路的点按靠右、出入口规则保留。走到头仍没有，才返回 None。
  if not hit or hit.get("guess") or hit.get("gate") or not hit.get("road"):
    return []
  if _next_is_toll(next_rows):
    return []
  path = _forward_path(hit, rows)
  if len(path) < 2:
    return []
  own_names = {(hit.get("name") or "").strip(), (hit.get("query") or "").strip()}
  own_names.discard("")
  stop_names = set()
  for row in next_rows or []:
    for key in ("label", "query"):
      name = (row.get(key) or "").strip()
      if name:
        stop_names.add(name)
  if not stop_names:
    return []
  _crossings, found = _crossings_until(path, own_names, stop_names)
  if found or _path_meets(path, next_rows):
    return []
  return None


def _point_after(prev, dest, step_km=0.2):
  # 紧挨着上一个点，沿已有走向往前放一小段。
  start = (float(prev["lng"]), float(prev["lat"]))
  if dest is not None:
    room = _km(start[0], start[1], dest[0], dest[1])
    if room < step_km * 1.6:
      step_km = max(0.08, room * 0.45)
  bearing = prev.get("way")
  if bearing is None and dest is not None and _km(start[0], start[1], dest[0], dest[1]) > 0.05:
    bearing = _bearing(start, (dest[0], dest[1]))
  shape = prev.get("full_shape") or prev.get("road_shape") or []
  if len(shape) >= 2 and bearing is not None:
    path = _directed_slice(shape, start, bearing, None)
    walked = 0.0
    for index in range(1, len(path)):
      seg = _km(path[index - 1][0], path[index - 1][1], path[index][0], path[index][1])
      if seg <= 1e-9:
        continue
      if walked + seg >= step_km:
        ratio = (step_km - walked) / seg
        return (
          path[index - 1][0] + (path[index][0] - path[index - 1][0]) * ratio,
          path[index - 1][1] + (path[index][1] - path[index - 1][1]) * ratio,
        )
      walked += seg
  if bearing is None:
    bearing = 0.0
  lat = start[1] + math.cos(bearing) * step_km / 111.0
  lng = start[0] + math.sin(bearing) * step_km / max(20.0, 111.0 * math.cos(math.radians(start[1])))
  return lng, lat


def _stand_in(hit, prev, dest):
  # 这条路走到头仍接不到下一条路，先不用这个点，改放到上一个点后面。
  lng, lat = _point_after(prev, dest)
  return {
    "query": hit.get("query"),
    "name": hit.get("name"),
    "lng": lng,
    "lat": lat,
    "road": False,
    "route_along": _along((prev["lng"], prev["lat"]), dest, lng, lat),
    "route_dist": hit.get("route_dist"),
    "road_shape": None,
    "meet": "之间",
  }


def _attach_along(hit, rows, next_rows, prev, dest):
  extras = _extra_along(hit, rows, next_rows, dest)
  if extras is None:
    return [_stand_in(hit, prev, dest)]
  return [hit] + extras


def _distinct_options(options, limit):
  kept = []
  for item in options or []:
    if any(_km(item["lng"], item["lat"], prev["lng"], prev["lat"]) < 0.12 for prev in kept):
      continue
    kept.append(item)
    if len(kept) >= limit:
      break
  return kept


def _option_note(item, gate):
  label = (item.get("feature") or {}).get("label") or ""
  if gate == "enter":
    role = "入口"
  elif gate == "exit":
    role = "出口"
  elif item.get("feature", {}).get("frontage") or any(mark in label for mark in ("辅道", "辅路", "辅线")):
    role = "辅道"
  elif item.get("forward"):
    role = "当前侧"
  else:
    role = "对向"
  side = item.get("right_km", 0.0)
  if side >= 0.03:
    hand = "右"
  elif side <= -0.03:
    hand = "左"
  else:
    hand = "正"
  return (
    f"{role} {hand} 离上一个点{item.get('here_dist', item.get('prev_dist', item.get('dist', 0))):.1f}"
    f" 离起点{item.get('start_dist', 0):.1f} 离终点{item.get('end_dist', 0):.1f}"
  )


_PICK_SYSTEM = (
  "你是路线规划助手。只输出 JSON，不要解释。"
  "通盘看整条路线，起点坐标和终点坐标都要算进去，每个名称只能选一个编号。"
  "编号 a 是离上一个点最近的默认点。只有换成别的点整条更顺、而且仍然靠近上一个点时才改。"
  "第一个点要靠近起点，之后每个点尽量靠近上一个点，最后一个点要能接到终点。"
  "从一条路转到下一条路，左右都是下一条路时，看再下一条路决定转向。"
  "左转选下一条路里方向往左的那条线，点在两条路交会处。右转选旁边、方向往右的那条线。"
  "不要折返，不要把点放到远离路口的地方。直行不要改到对向车道。"
  "收费站后面是高速选入口，从高速下来选出口，出入口走右侧。"
  "顺序不能变，不能新增名称，不能自己编坐标。"
  "输出 {\"picks\":[\"1a\",\"2b\"]}，编号必须来自候选。"
)


def _ask_route(offers, origin, dest):
  # 每处只有一个点时，几何结果就是唯一选择。
  if not any(len(group.get("options") or []) > 1 for group in offers):
    return []
  lines = [
    f"起点坐标 {origin[0]:.5f},{origin[1]:.5f}",
    f"终点坐标 {dest[0]:.5f},{dest[1]:.5f}",
    "选点时把起点坐标和终点坐标一起考虑。第一个点靠近起点，之后尽量靠近上一个点，最后一个点接到终点。左右都是下一条路时，看再下一条路：左转用方向往左的那条线，右转用旁边往右的那条线，点都在路口上。",
    "整条顺序：" + " → ".join(group["name"] for group in offers),
    "默认接法：" + " → ".join(
      f"{group['name']} {group['options'][0]['lng']:.4f},{group['options'][0]['lat']:.4f}"
      for group in offers
      if group.get("options")
    ),
  ]
  for group in offers:
    lines.append(group["name"])
    for item in group["options"]:
      lines.append(f"{item['offer_id']} {item['lng']:.5f},{item['lat']:.5f} {_option_note(item, group.get('gate') or '')}")
  try:
    data = _json_object(chat(
      [
        {"role": "system", "content": _PICK_SYSTEM},
        {"role": "user", "content": "\n".join(lines)},
      ],
      temperature=0.1,
      json_mode=True,
      max_tokens=240,
    ))
  except (ValueError, RuntimeError):
    return []
  found = []
  for item in data.get("picks") or []:
    mark = str(item or "").strip().lower()
    if mark and mark not in found:
      found.append(mark)
  return found


def _apply_picks(slots, offers, picks, origin, dest):
  by_id = {}
  for group in offers:
    for item in group.get("options") or []:
      by_id[item["offer_id"]] = (group, item)
  chosen = {}
  for mark in picks or []:
    pair = by_id.get(mark)
    if pair and pair[0]["name"] not in chosen:
      chosen[pair[0]["name"]] = pair[1]
  if not chosen:
    return slots
  updated = list(slots)
  previous = (origin[0], origin[1])
  primaries = [(index, slot) for index, slot in enumerate(slots) if not slot.get("along")]
  for (index, slot), group in zip(primaries, offers):
    picked = chosen.get(group["name"])
    options = group.get("options") or []
    if not picked or not options or slot.get("guess") or picked is options[0]:
      if slot.get("lng") is not None:
        previous = (slot["lng"], slot["lat"])
      continue
    base = options[0]
    jumped = _km(picked["lng"], picked["lat"], previous[0], previous[1])
    base_jump = _km(base["lng"], base["lat"], previous[0], previous[1])
    forward_exists = any(item.get("line") and item.get("forward") for item in options)
    left_turn = base.get("cross_turn") == "left"
    if left_turn:
      wrong_side = picked.get("heading_km", picked.get("right_km", 0.0)) >= -0.02 and base.get("heading_km", -1) < -0.02
    else:
      wrong_side = forward_exists and picked.get("line") and not picked.get("forward")
    # 左转可以换成同路口的对向点。直行不能跑到对向，也不能比默认点离上一个点更远一截。
    if wrong_side or jumped > base_jump + 1.0 or jumped > max(8.0, base_jump * 3):
      if slot.get("lng") is not None:
        previous = (slot["lng"], slot["lat"])
      continue
    hit = _slot_from(picked, group["name"], origin, dest, group.get("gate") or "")
    updated[index] = hit
    previous = (hit["lng"], hit["lat"])
  return updated


def _refill_along(slots, loaded, dest, origin):
  # 选点确定后，再沿路核对下一条路。对不上就改到上一个点后面，沿路路口不生成途径点。
  groups = []
  index = 0
  while index < len(slots):
    slot = slots[index]
    index += 1
    if slot.get("along"):
      continue
    while index < len(slots) and slots[index].get("along"):
      index += 1
    groups.append(slot)
  rebuilt = []
  previous = {"lng": origin[0], "lat": origin[1]}
  for pos, slot in enumerate(groups):
    rows = loaded[pos] if pos < len(loaded) else []
    next_rows = loaded[pos + 1] if pos + 1 < len(loaded) else []
    group = _attach_along(slot, rows, next_rows, previous, dest)
    rebuilt.extend(group)
    previous = group[-1]
  return rebuilt


def _chain_names(names, origin, dest, route):
  loaded = [_load_named(name, origin, dest) for name in names]
  prev = {"lng": origin[0], "lat": origin[1], "route_along": 0.0, "road_shape": None}
  fallback = [(dest[0], dest[1])]
  slots = []
  missed = []
  offers = []
  limit = 3 if len(names) <= 6 else 2
  letters = "abc"
  for index, name in enumerate(names):
    next_name = names[index + 1] if index + 1 < len(names) else ""
    next_rows = loaded[index + 1] if index + 1 < len(names) else []
    later_rows = loaded[index + 2] if index + 2 < len(names) else []
    prev_name = f"{prev.get('name') or ''} {prev.get('query') or ''}"
    here = (prev["lng"], prev["lat"]) if "lng" in prev else None
    gate = _toll_gate(prev_name, next_name, name, next_rows)
    prev_geom = _geom_of(prev)
    ranked = _ranked_options(loaded[index], prev_geom, next_rows, fallback, origin, dest, name, 6.0, gate, here, later_rows)
    if not ranked and len(prev_geom) >= 2:
      ranked = _ranked_options(loaded[index], [(prev["lng"], prev["lat"])], next_rows, fallback, origin, dest, name, 6.0, gate, here, later_rows)
    if not ranked:
      ranked = _ranked_options(loaded[index], prev_geom, next_rows, fallback, origin, dest, name, 18.0, gate, here, later_rows)
    distinct = _distinct_options(ranked, 1 if gate in ("exit", "enter") else limit)
    for pos, item in enumerate(distinct):
      item["offer_id"] = f"{index + 1}{letters[pos]}"
    hit = _finish_choice(ranked, name, origin, dest, gate)
    if not hit:
      hit = _chain_hit(prev, name, origin, dest)
    offers.append({"name": name, "gate": gate, "options": distinct})
    if not hit:
      missed.append(name)
      slots.append(_guess_slot(name))
      continue
    slots.extend(_attach_along(hit, loaded[index], next_rows, prev, dest))
    prev = slots[-1]
  slots = _apply_picks(slots, offers, _ask_route(offers, origin, dest), origin, dest)
  slots = _refill_along(slots, loaded, dest, origin)
  return slots, missed


def _ordered_names(data):
  names = _clean_queries(data.get("searches") or data.get("queries"))
  if names:
    return names
  found = []
  for item in data.get("places") or []:
    if isinstance(item, str):
      name = item.strip()
    elif isinstance(item, dict):
      name = str(item.get("query") or item.get("name") or "").strip()
    else:
      name = ""
    if len(name) >= 2 and name not in found:
      found.append(name)
    if len(found) >= 12:
      break
  return found


def _guess_slot(name: str):
  return {"query": name, "name": name, "guess": True}


def _choice_slots(data, catalog):
  slots = []
  missed = []
  seen = set()

  def add_miss(name):
    name = (name or "").strip()
    if not name or name in missed:
      return
    missed.append(name)
    slots.append(_guess_slot(name))

  for item in data.get("places") or []:
    if isinstance(item, str):
      add_miss(item)
      continue
    if not isinstance(item, dict):
      continue
    mark = str(item.get("id") or "").strip()
    chosen = catalog.get(mark)
    query = str(item.get("query") or item.get("name") or "").strip()
    if chosen is None:
      add_miss(query or mark)
      continue
    key = (round(chosen["lng"], 4), round(chosen["lat"], 4))
    if key in seen:
      continue
    seen.add(key)
    label = chosen.get("label") or query or mark
    query_name = query or label
    if any(item.get("query") == query_name and not item.get("guess") for item in slots):
      continue
    slots.append({
      "query": query_name,
      "name": label,
      "lng": chosen["lng"],
      "lat": chosen["lat"],
      "road": _is_road(query_name) or chosen.get("kind") == "highway",
      "route_along": chosen.get("route_along"),
      "route_dist": chosen.get("route_dist"),
    })
  for item in list(data.get("missing") or []) + list(data.get("missed") or []):
    add_miss(str(item or ""))
  return slots, missed


def _ensure_catalog(slots, missed, catalog):
  # 查到的每条路都要有点，模型漏选时也补上。
  found = {item.get("query") for item in slots if not item.get("guess")}
  for chosen in catalog.values():
    query = (chosen.get("query") or chosen.get("label") or "").strip()
    if not query or query in found:
      continue
    slots = [item for item in slots if not (item.get("guess") and item.get("query") == query)]
    missed = [name for name in missed if name != query]
    label = chosen.get("label") or query
    slots.append({
      "query": query,
      "name": label,
      "lng": chosen["lng"],
      "lat": chosen["lat"],
      "road": _is_road(query) or _is_road(label) or chosen.get("kind") == "highway",
      "route_along": chosen.get("route_along"),
      "route_dist": chosen.get("route_dist"),
    })
    found.add(query)
  return slots, missed


_DECIDE_SYSTEM = (
  "你是路线规划助手。只输出 JSON，不要解释。"
  "从起点出发，按行进顺序拆开要经过的路和地点，输出 {\"searches\":[\"名称\"]}。"
  "一条一个，不要合并，用户写了几个就保留几个，不要丢掉后面的，最多 12 个。"
  "路名用用户写的完整名称，不要缩短，也不要改成另一条路。"
  "顺序就是从第一个点开始往下接的顺序。"
  "例如「先走广州大道再过猎德收费站」输出 {\"searches\":[\"广州大道\",\"猎德收费站\"]}。"
  "收费站、服务区、停车区、加油站可以直接用这些词。不要输出坐标。"
)


def _decide_places(description, origin, dest, route):
  direct = _km(origin[0], origin[1], dest[0], dest[1])
  try:
    data = _json_object(chat(
      [
        {"role": "system", "content": _DECIDE_SYSTEM},
        {"role": "user", "content": (
          f"起点：{origin[0]:.5f}, {origin[1]:.5f}\n"
          f"终点：{dest[0]:.5f}, {dest[1]:.5f}\n"
          f"直线距离约 {direct:.1f} 公里。\n"
          f"途径名称：{description}\n"
          "按从起点往终点的顺序给出名称。"
        )},
      ],
      temperature=0.1,
      json_mode=True,
      max_tokens=400,
    ))
  except ValueError:
    return None
  names = _ordered_names(data)
  if not names:
    return None
  return _chain_names(names, origin, dest, route)


def _fill_by_name(names, start_point, end_point, base_route):
  return _chain_names(names, start_point, end_point, base_route)


def _one_along(slots, origin, dest, route):
  # 同一个名称相距很近的只留一个。长路上隔开的点都保留。
  kept = []
  guesses = []
  for item in slots:
    name = (item.get("query") or item.get("name") or "").strip()
    if item.get("guess"):
      if name and not any((prev.get("query") or prev.get("name")) == name for prev in guesses):
        guesses.append(item)
      continue
    if "lng" not in item:
      continue
    if any(
      (prev.get("query") or prev.get("name") or "").strip() == name
      and _km(prev["lng"], prev["lat"], item["lng"], item["lat"]) < 0.1
      for prev in kept
    ):
      continue
    kept.append(item)
  return kept + guesses, []


def _extract_places(description: str, start, end) -> list[str]:
  system = (
    "你是路线规划助手。根据用户对途径路线的描述，抽出从起点走向终点时真正要经过的道路、收费站、服务区、加油站或地标。"
    "只输出 JSON，格式为 {\"places\":[\"地点1\",\"地点2\"]}。"
    "按行进顺序排列，同一条路只保留一次。路名保持用户写的完整名称，不要缩短。"
    "不要包含起点和终点，不要编造描述里没有的地点，不要输出坐标或解释。"
  )
  prompt = (
    f"起点坐标：{start[0]}, {start[1]}\n"
    f"终点坐标：{end[0]}, {end[1]}\n"
    f"途径描述：{description}"
  )
  text = chat(
    [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
    temperature=0.1,
    json_mode=True,
    max_tokens=400,
  )
  return _parse_places(text)


def _nudge_apart(item, blocked, end_point):
  # 和已有点挤在一起时，沿路或朝终点挪开一点，避免后面的途径点被当成重复点删掉。
  lng, lat = item["lng"], item["lat"]
  aim = _bearing((lng, lat), end_point) if _km(lng, lat, end_point[0], end_point[1]) > 0.05 else None
  shape = item.get("road_shape")
  if shape and len(shape) >= 2 and aim is not None:
    hit = _closest_on_shape(shape, lng, lat)
    if hit:
      moved = _shift_on_shape(shape, lng, lat, hit[3], aim)
      if all(_km(moved[0], moved[1], point[0], point[1]) >= 0.05 for point in blocked):
        return moved[0], moved[1]
  if aim is None:
    return lng + 0.0008, lat
  east = math.sin(aim) * 0.08 / max(20.0, 111.0 * math.cos(math.radians(lat)))
  north = math.cos(aim) * 0.08 / 111.0
  return lng + east, lat + north


def describe(profile: str, start, end, description: str):
  text = (description or "").strip()
  if not text:
    raise ValueError("请填写途径名称")
  if not isinstance(start, (list, tuple)) or not isinstance(end, (list, tuple)):
    raise ValueError("请在地图上设置起点和终点")
  if len(start) < 2 or len(end) < 2:
    raise ValueError("请在地图上设置起点和终点")
  start_point = (float(start[0]), float(start[1]))
  end_point = (float(end[0]), float(end[1]))
  if not current_pbf():
    raise ValueError("请先启动路线服务")
  base_route = []
  try:
    base = plan(profile, [list(start_point), list(end_point)])
    base_route = _thin_route(base.get("coordinates") or [])
  except ValueError as exc:
    if "请先启动" in str(exc):
      raise
    base_route = []
  decided = None
  try:
    decided = _decide_places(text, start_point, end_point, base_route)
  except RuntimeError as exc:
    raise ValueError(str(exc)) from exc
  if decided is None:
    try:
      wanted = _extract_places(text, start_point, end_point)
    except RuntimeError as exc:
      raise ValueError(str(exc)) from exc
    slots, missed = _fill_by_name(wanted, start_point, end_point, base_route)
  else:
    slots, missed = decided
  slots, dropped = _one_along(slots, start_point, end_point, base_route)
  for name in dropped:
    if name not in missed:
      missed.append(name)
  # 保持从起点逐段接上的顺序，不用直线投影重排。
  ordered = []
  found_items = [item for item in slots if not item.get("guess")]
  for item in found_items:
    blocked = [start_point, end_point] + [(prev["lng"], prev["lat"]) for prev in ordered]
    if any(_km(item["lng"], item["lat"], point[0], point[1]) < 0.05 for point in blocked):
      moved = _nudge_apart(item, blocked, end_point)
      if moved and all(_km(moved[0], moved[1], point[0], point[1]) >= 0.04 for point in blocked):
        item["lng"], item["lat"] = moved
      elif _km(item["lng"], item["lat"], start_point[0], start_point[1]) < 0.03:
        continue
      elif _km(item["lng"], item["lat"], end_point[0], end_point[1]) < 0.03:
        continue
      elif any(_km(item["lng"], item["lat"], prev["lng"], prev["lat"]) < 0.03 for prev in ordered):
        continue
    ordered.append(item)
  points = [list(start_point)]
  names = [""]
  hints = [""]
  for item in ordered:
    points.append([item["lng"], item["lat"]])
    names.append(item["name"])
    hint = ""
    if item.get("road"):
      hint = item.get("name") or item.get("query") or ""
    hints.append(hint)
  points.append(list(end_point))
  names.append("")
  hints.append("")
  result = plan(profile, points, names, hints)
  coords = result.get("coordinates") or [list(start_point), list(end_point)]
  lengths = _polyline_lengths(coords)
  survived = {id(item) for item in ordered}
  groups = []
  grouped = {}
  for index, item in enumerate(slots):
    if not item.get("guess"):
      continue
    prev = start_point
    for earlier in range(index - 1, -1, -1):
      if id(slots[earlier]) in survived:
        prev = (slots[earlier]["lng"], slots[earlier]["lat"])
        break
    nxt = end_point
    for later in range(index + 1, len(slots)):
      if id(slots[later]) in survived:
        nxt = (slots[later]["lng"], slots[later]["lat"])
        break
    key = (prev, nxt)
    if key not in grouped:
      grouped[key] = []
      groups.append(key)
    grouped[key].append(item)
  for prev, nxt in groups:
    items = grouped[(prev, nxt)]
    start_at = _along_line(coords, lengths, prev[0], prev[1])
    end_at = _along_line(coords, lengths, nxt[0], nxt[1])
    if end_at < start_at:
      end_at = lengths[-1]
    prev_along = _known_along(slots, survived, prev, start_point, end_point)
    next_along = _known_along(slots, survived, nxt, start_point, end_point)
    if next_along < prev_along:
      next_along = 1.0
    span = max(0.0, next_along - prev_along)
    if end_at - start_at < 0.3:
      cursor = prev
      for offset, item in enumerate(items, start=1):
        lng, lat = _after_point(cursor, nxt)
        item["lng"] = lng
        item["lat"] = lat
        item["route_along"] = prev_along + span * offset / (len(items) + 1)
        cursor = (lng, lat)
      continue
    for offset, item in enumerate(items, start=1):
      lng, lat = _point_at(coords, lengths, start_at + (end_at - start_at) * offset / (len(items) + 1))
      item["lng"] = lng
      item["lat"] = lat
      item["route_along"] = prev_along + span * offset / (len(items) + 1)
  places = []
  for item in slots:
    if item.get("guess") or id(item) in survived:
      places.append(item)
  for item in places:
    item.pop("guess", None)
    item.pop("road", None)
    item.pop("road_shape", None)
    item.pop("full_shape", None)
    item.pop("along", None)
    item.pop("meet", None)
    item.pop("gate", None)
    item.pop("way", None)
    item.pop("cross_turn", None)
    item.pop("meet_lng", None)
    item.pop("meet_lat", None)
  result["places"] = places
  result["missed"] = missed
  return result
