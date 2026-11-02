import json
import math
import urllib.parse
import urllib.request

from llm.engine import chat
from route_engine.service import plan

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
  return places[:6]


def _area_hint(lng: float, lat: float) -> str:
  query = urllib.parse.urlencode({
    "format": "jsonv2",
    "lat": lat,
    "lon": lng,
    "zoom": 10,
    "accept-language": "zh",
  })
  try:
    data = _http_json(f"https://nominatim.openstreetmap.org/reverse?{query}")
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
  direct = _km(origin[0], origin[1], dest[0], dest[1])
  return max(1.5, min(6.0, direct * 0.22))


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


def _pick(candidates, query: str, origin, dest, limit: float):
  key = _name_key(query)
  road = _is_road(query)
  best = None
  best_score = None
  for item in candidates:
    cross, along = _cross_km(origin, dest, item["lng"], item["lat"])
    if along < 0:
      beyond = _km(item["lng"], item["lat"], origin[0], origin[1])
    elif along > 1:
      beyond = _km(item["lng"], item["lat"], dest[0], dest[1])
    else:
      beyond = 0.0
    if cross > limit or beyond > limit:
      continue
    bbox = item.get("bbox")
    span = _km(bbox[2], bbox[0], bbox[3], bbox[1]) if bbox else 0.0
    named = bool(key and key in (item.get("label") or ""))
    on_road = road and item.get("kind") == "highway"
    broad = span > 4
    score = (1 if broad else 0, 0 if named else 1, 0 if on_road else 1, cross + beyond)
    if best_score is None or score < best_score:
      best = item
      best_score = score
  return best


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
  rows = _http_json("https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(params))
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


def _geocode(query: str, origin, dest):
  viewbox = _viewbox(origin, dest)
  limit = _limit_km(origin, dest)
  queries = [query]
  key = _name_key(query)
  if key and key not in queries:
    queries.append(key)
  candidates = []
  seen = set()
  for bounded in (True, False):
    for item_query in queries:
      try:
        rows = _search_nominatim(item_query, viewbox, bounded)
      except Exception:
        continue
      for row in rows:
        mark = (round(row["lng"], 4), round(row["lat"], 4))
        if mark in seen:
          continue
        seen.add(mark)
        candidates.append(row)
    if _pick(candidates, query, origin, dest, limit):
      break
  return _pick(candidates, query, origin, dest, limit) or _pick(candidates, query, origin, dest, max(limit * 2, 4.0))


def _via_coordinate(item, origin, dest):
  lng = item["lng"]
  lat = item["lat"]
  bbox = item.get("bbox")
  if not bbox or _is_road(item.get("query") or "") or item.get("kind") == "highway":
    return lng, lat
  south, north, west, east = bbox
  span = _km(west, south, east, north)
  if span < 0.45 or span > 12:
    return lng, lat
  return _closest_rect(origin, dest, west, south, east, north)


def _extract_places(description: str, start, end) -> list[str]:
  system = (
    "你是路线规划助手。根据用户对途径路线的描述，抽出从起点走向终点时真正要经过的道路或地标。"
    "只输出 JSON，格式为 {\"places\":[\"地点1\",\"地点2\"]}。"
    "按行进顺序排列，同一条路只保留一次。不要输出区、市、镇这类大范围地名。"
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


def describe(profile: str, start, end, description: str):
  text = (description or "").strip()
  if not text:
    raise ValueError("请填写途径路线的描述")
  if not isinstance(start, (list, tuple)) or not isinstance(end, (list, tuple)):
    raise ValueError("请在地图上设置起点和终点")
  if len(start) < 2 or len(end) < 2:
    raise ValueError("请在地图上设置起点和终点")
  start_point = (float(start[0]), float(start[1]))
  end_point = (float(end[0]), float(end[1]))
  try:
    wanted = _extract_places(text, start_point, end_point)
  except RuntimeError as exc:
    raise ValueError(str(exc)) from exc
  hint = _area_hint(start_point[0], start_point[1])
  found = []
  missed = []
  for name in wanted:
    query = name if not hint or hint in name else f"{name} {hint}"
    hit = _geocode(query, start_point, end_point)
    if not hit and query != name:
      hit = _geocode(name, start_point, end_point)
    if not hit:
      missed.append(name)
      continue
    chosen = dict(hit)
    chosen["query"] = name
    lng, lat = _via_coordinate(chosen, start_point, end_point)
    _cross, along = _cross_km(start_point, end_point, lng, lat)
    found.append({
      "query": name,
      "name": chosen["label"],
      "lng": lng,
      "lat": lat,
      "along": along,
    })
  if wanted and not found:
    raise ValueError("这些地点没有找到：" + "、".join(missed))
  found.sort(key=lambda item: item["along"])
  ordered = []
  for item in found:
    if any(_km(item["lng"], item["lat"], prev["lng"], prev["lat"]) < 0.3 for prev in ordered):
      continue
    ordered.append(item)
  found = ordered
  points = [list(start_point)]
  names = [""]
  hints = [""]
  for item in found:
    points.append([item["lng"], item["lat"]])
    names.append(item["name"])
    hints.append(item["query"] if _is_road(item["query"]) else "")
    item.pop("along", None)
  points.append(list(end_point))
  names.append("")
  hints.append("")
  result = plan(profile, points, names, hints)
  result["places"] = found
  result["missed"] = missed
  return result
