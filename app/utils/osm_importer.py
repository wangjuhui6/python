# pbf 流式读取：点走 node，线走 way，面走 osmium Area 组装
import osmium
from osmium.geom import WKTFactory
from postgis.server.featuresServer import add_features

# 闭合 way 何时成面：与 osmtogeojson / iD polygon-features 对齐
# True = 任意取值都是面；set = 仅这些取值是面
POLYGON_KEYS = {
  "building": True,
  "landuse": True,
  "amenity": True,
  "leisure": True,
  "harbour": True,
  "historic": True,
  "military": True,
  "place": True,
  "public_transport": True,
  "office": True,
  "shop": True,
  "craft": True,
  "tourism": True,
  "golf": True,
  "boundary": True,
  "aerialway": True,
  "healthcare": True,
  "cemetery": True,
}

POLYGON_WHITELIST = {
  "highway": {"services", "rest_area", "escape", "platform"},
  "railway": {"station", "turntable", "roundhouse", "platform"},
  "waterway": {"riverbank", "dock", "boatyard", "dam"},
  "power": {"plant", "substation", "generator", "transformer"},
}

# 这些 key 默认是面，下列取值除外（仍是线）
POLYGON_EXCEPT = {
  "natural": {"coastline", "cliff", "ridge", "arete", "tree_row"},
  "man_made": {"cutline", "embankment", "pipeline"},
  "aeroway": {"taxiway", "runway"},
}


def tags_dict(obj):
  return dict(obj.tags)


def closed_way_is_polygon(tags: dict) -> bool:
  if not tags:
    return False
  area = tags.get("area")
  if area == "no":
    return False
  if area == "yes":
    return True
  for key in POLYGON_KEYS:
    if key in tags:
      return True
  for key, values in POLYGON_WHITELIST.items():
    if tags.get(key) in values:
      return True
  for key, excluded in POLYGON_EXCEPT.items():
    value = tags.get(key)
    if value is not None and value not in excluded:
      return True
  return False


class PBFImporter(osmium.SimpleHandler):
  def __init__(self, file_path, datasets_id, batch_size=5000):
    super().__init__()
    self.wkt = WKTFactory()
    self.file_path = file_path
    self.datasets_id = datasets_id
    self.batch_size = batch_size
    self.cache = []

  def append(self, feature):
    self.cache.append(feature)
    if len(self.cache) >= self.batch_size:
      self.flush()

  def flush(self):
    if not self.cache:
      return
    batch = self.cache
    self.cache = []
    result = add_features(batch)
    if not result:
      raise Exception("添加数据失败")

  def _feature(self, geom, tags):
    return {
      "dataset_id": self.datasets_id,
      "geom": geom,
      "properties": tags,
    }

  def node(self, n):
    if len(n.tags) == 0:
      return
    try:
      geom = self.wkt.create_point(n)
    except Exception:
      return
    self.append(self._feature(geom, tags_dict(n)))

  def way(self, w):
    tags = tags_dict(w)
    if not tags:
      return
    # 闭合且按 tag 是面：交给 area()，避免和外环重复
    if w.is_closed() and closed_way_is_polygon(tags):
      return
    try:
      geom = self.wkt.create_linestring(w)
    except Exception:
      return
    self.append(self._feature(geom, tags))

  def area(self, a):
    tags = tags_dict(a)
    if not tags:
      return
    # osmium 会对几乎所有闭合 way 调 area()，环岛等线性闭合要素在这里丢掉
    if a.from_way() and not closed_way_is_polygon(tags):
      return
    try:
      geom = self.wkt.create_multipolygon(a)
    except Exception:
      return
    self.append(self._feature(geom, tags))
