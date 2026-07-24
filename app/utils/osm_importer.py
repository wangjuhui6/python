# pbf 流式读取，使用 osmium 库
import osmium
from sqlalchemy import text
import json
from postgis.database import engine
from osmium.geom import WKTFactory
from postgis.server.featuresServer import add_features

POLYGON_KEYS = {
  "building",
  "landuse",
  "natural",
  "leisure",
  "amenity",
  "aeroway",
  "boundary",
  "place",
  "water",
}

class PBFImporter(osmium.SimpleHandler):
  def __init__(self, file_path, datasets_id, batch_size=5000):
    super().__init__()
    self.wkt = WKTFactory()
    self.file_path = file_path # 文件路径
    self.datasets_id = datasets_id # 数据源id
    self.batch_size = batch_size # 批量大小
    self.cache = [] # 缓存
  
  def append(self, feature):
    self.cache.append(feature)

    if len(self.cache) >= self.batch_size:
        self.flush()

  def flush(self):

    if not self.cache:
      return

    batch = self.cache.copy()

    # 批量添加数据
    result = add_features(batch)
    if not result:
      raise Exception("添加数据失败")

    self.cache = []

  def node(self, n):
    if len(n.tags) == 0:
      return

    feature = {
      'dataset_id': self.datasets_id,
      'geom': f"POINT({n.location.lon} {n.location.lat})",
      'properties': json.dumps(dict(n.tags), ensure_ascii=False)
    }
    
    self.append(feature)

  # 判断是否是面
  def is_polygon(self, w):
    tags = dict(w.tags)

    # 明确指定是面
    if tags.get("area") == "yes":
      return True

    # 明确指定不是面
    if tags.get("area") == "no":
      return False

    # 必须闭合
    if not w.is_closed():
      return False

    # 根据 Tag 判断
    for key in POLYGON_KEYS:
      if key in tags:
        return True
      return False
  
  # 获取几何体类型
  def way_geometry_type(self, way):
    if self.is_polygon(way):
      return "Polygon"
    return "LineString"

  # 获取关系几何体类型
  def relation_geometry_type(self, relation):
    tags = dict(relation.tags)
    relation_type = tags.get("type")
    if relation_type == "multipolygon":
      return "MultiPolygon"
    if relation_type == "boundary":
      return "MultiPolygon"
    return None


  def way(self, w):
    try:
      geometry_type = self.way_geometry_type(w)
      
      if geometry_type == "Polygon":
        geom = self.wkt.create_polygon(w)
      else:
        geom = self.wkt.create_linestring(w)

      feature = {
        "dataset_id": self.datasets_id,
        "geom": geom,
        "properties": json.dumps(dict(w.tags), ensure_ascii=False)
      }

      self.append(feature)

    except Exception:
      return

  def relation(self, r):
    try:
      geometry_type = self.relation_geometry_type(r)
      if geometry_type is None:
        return
      # Relation 转 WKT（根据你的实现）
      geom = self.wkt.create_multipolygon(r)
      feature = {
        "dataset_id": self.datasets_id,
        "geom": geom,
        "properties": json.dumps(dict(r.tags), ensure_ascii=False)
      }
      self.append(feature)
    except Exception:
      return
    
  def finish(self):
    """导入完成后，将最后不足 batch_size 的数据写入数据库"""
    self.flush()