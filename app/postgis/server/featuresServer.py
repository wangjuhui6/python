from postgis.database import get_session
from postgis.base.features import Feature
from postgis.base.datasets import Dataset
from postgis.categories import apply_category_filter, apply_uncategorized_filter, parse_json_field
from geoalchemy2.shape import WKTElement
from geoalchemy2.functions import (
  ST_AsGeoJSON,
  ST_Buffer,
  ST_GeometryType,
  ST_Intersects,
  ST_MakeEnvelope,
  ST_MakePoint,
  ST_SetSRID,
  ST_SimplifyPreserveTopology,
)
from sqlalchemy import case, func, text
import json

MAP_FEATURE_LIMIT = 4000
MAP_FEATURE_LIMIT_MAX = 8000
POINT_MIN_ZOOM = 12
LINE_MIN_ZOOM = 8

def parse_properties(value):
  if value is None:
    return {}
  if isinstance(value, dict):
    return value
  if isinstance(value, str):
    try:
      parsed = json.loads(value)
      return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
      return {}
  return {}

# 添加数据
def add_feature(data: dict):
  with get_session() as session:
    feature = Feature(
      dataset_id=data['dataset_id'],
      geom=WKTElement(data['geom'], srid=4326),
      properties=data['properties']
    )
    session.add(feature)
    session.commit()
    return feature.to_dict()

# 批量添加数据
def add_features(data: list):
  with get_session() as session:
    for feature in data:
      feature = Feature(
        dataset_id=feature['dataset_id'],
        geom=WKTElement(feature['geom'], srid=4326),
        properties=feature['properties']
      )
      session.add(feature)
    session.commit()
    return True

# 查询数据
def get_feature(id: int):
  with get_session() as session:
    feature = session.query(Feature).filter(Feature.id == id).first()
    return feature.to_dict()

# 更新数据
def update_feature(id: int, data: dict):
  with get_session() as session:
    feature = session.query(Feature).filter(Feature.id == id).first()
    feature.dataset_id = data['dataset_id']
    feature.geom = data['geom']
    feature.properties = data['properties']
    session.commit()
    return feature.to_dict()

# 删除数据
def delete_feature(id: int):
  with get_session() as session:
    feature = session.query(Feature).filter(Feature.id == id).first()
    session.delete(feature)
    session.commit()
    return True

# 查询所有数据
def get_all_features():
  with get_session() as session:
    features = session.query(Feature).all()
    return [feature.to_dict() for feature in features]

# 查询数据
# def get_feature_by_dataset_id(dataset_id: int):
#   with get_session() as session:
#     features = session.query(Feature).filter(Feature.dataset_id == dataset_id).all()
#     return [feature.to_geojson() for feature in features]

# 分页查询数据并返回总数
def get_features_by_dataset_id(dataset_id: int, page: int = 1, page_size: int = 1000):
  with get_session() as session:
    features = session.query(Feature).filter(Feature.dataset_id == dataset_id).offset((page - 1) * page_size).limit(page_size).all()
    return {
      'data': [feature.to_dict() for feature in features],
      'page': page,
      'page_size': page_size,
      'total': session.query(Feature).filter(Feature.dataset_id == dataset_id).count()
    }

# 分页查询数据并返回总数geojson
def get_features_by_dataset_id_geojson(dataset_id: int, page: int = 1, page_size: int = 1000):
  dataset_id = int(dataset_id)
  page = int(page)
  page_size = int(page_size)
  with get_session() as session:
    features = session.query(Feature).filter(Feature.dataset_id == dataset_id).offset((page - 1) * page_size).limit(page_size).all()
    data = []
    for feature in features:
      feature.properties = parse_properties(feature.properties)
      data.append(feature.to_geojson())
    return {
      'data': data,
      'page': page,
      'page_size': page_size,
      'total': session.query(Feature).filter(Feature.dataset_id == dataset_id).count()
    }

def _simplify_tolerance(zoom: float) -> float:
  if zoom >= 15:
    return 0
  # 约 1 像素对应的经纬度，zoom 越低抽稀越狠
  return 360.0 / (256.0 * (2 ** zoom))

def get_features_in_bbox(
  dataset_id: int,
  west: float,
  south: float,
  east: float,
  north: float,
  zoom: float = 10,
  limit: int = MAP_FEATURE_LIMIT,
  category_ids: list | None = None,
  uncategorized: bool = False,
):
  dataset_id = int(dataset_id)
  zoom = float(zoom)
  limit = min(max(int(limit), 1), MAP_FEATURE_LIMIT_MAX)
  envelope = ST_MakeEnvelope(west, south, east, north, 4326)
  geom_type = ST_GeometryType(Feature.geom)
  tolerance = _simplify_tolerance(zoom)
  geom_expr = ST_SimplifyPreserveTopology(Feature.geom, tolerance) if tolerance > 0 else Feature.geom
  type_priority = case(
    (geom_type.in_(['ST_Polygon', 'ST_MultiPolygon']), 0),
    (geom_type.in_(['ST_LineString', 'ST_MultiLineString']), 1),
    else_=2,
  )

  with get_session() as session:
    query = session.query(
      Feature.id,
      Feature.properties,
      ST_AsGeoJSON(geom_expr).label('geojson'),
    ).filter(
      Feature.dataset_id == dataset_id,
      ST_Intersects(Feature.geom, envelope),
    )

    dataset = session.query(Dataset).filter(Dataset.id == dataset_id).first()
    categories = parse_json_field(dataset.categories, []) if dataset else []
    selected_ids = category_ids or []
    skipped = []
    if uncategorized:
      query = apply_uncategorized_filter(query, categories)
    else:
      query = apply_category_filter(query, categories, selected_ids, zoom=zoom)
      if not selected_ids:
        if zoom < LINE_MIN_ZOOM:
          query = query.filter(geom_type.in_(['ST_Polygon', 'ST_MultiPolygon']))
          skipped = ['点', '线']
        elif zoom < POINT_MIN_ZOOM:
          query = query.filter(geom_type.notin_(['ST_Point', 'ST_MultiPoint']))
          skipped = ['点']

    rows = query.order_by(type_priority, Feature.id).limit(limit + 1).all()
    truncated = len(rows) > limit
    rows = rows[:limit]
    data = []
    for row in rows:
      if not row.geojson:
        continue
      data.append({
        'type': 'Feature',
        'id': row.id,
        'geometry': json.loads(row.geojson),
        'properties': parse_properties(row.properties),
      })

    hint = None
    if truncated:
      hint = f'视野内超过 {limit} 条，已按面优先截断，请放大后再看细节'
    elif uncategorized:
      hint = '当前为未命中任何分类的数据'
    elif selected_ids:
      hint = f'已按 {len(selected_ids)} 个分类筛选'
    elif skipped:
      hint = f'当前缩放级别已隐藏{" / ".join(skipped)}，放大后加载'

    return {
      'data': data,
      'total': len(data),
      'limit': limit,
      'truncated': truncated,
      'zoom': zoom,
      'hint': hint,
      'uncategorized': uncategorized,
    }

def get_uncategorized_features(dataset_id: int, page: int = 1, page_size: int = 10):
  dataset_id = int(dataset_id)
  page = max(int(page), 1)
  page_size = min(max(int(page_size), 1), 100)
  with get_session() as session:
    dataset = session.query(Dataset).filter(Dataset.id == dataset_id).first()
    categories = parse_json_field(dataset.categories, []) if dataset else []
    query = session.query(Feature).filter(Feature.dataset_id == dataset_id)
    query = apply_uncategorized_filter(query, categories)
    total = query.count()
    features = query.order_by(Feature.id).offset((page - 1) * page_size).limit(page_size).all()
    data = []
    for feature in features:
      feature.properties = parse_properties(feature.properties)
      data.append(feature.to_geojson())
    return {
      'data': data,
      'total': total,
      'page': page,
      'page_size': page_size,
      'uncategorized': True,
      'hint': f'未分类共 {total} 条',
    }

def get_features_at_point(dataset_id: int, lng: float, lat: float, zoom: float = 14, limit: int = 80):
  dataset_id = int(dataset_id)
  lng = float(lng)
  lat = float(lat)
  zoom = float(zoom)
  limit = min(max(int(limit), 1), 200)
  buffer_deg = max(0.00002, 360.0 / (256.0 * (2 ** zoom)) * 12)
  point = ST_SetSRID(ST_MakePoint(lng, lat), 4326)
  click_area = ST_Buffer(point, buffer_deg)

  with get_session() as session:
    rows = session.query(
      Feature.id,
      Feature.properties,
      ST_AsGeoJSON(Feature.geom).label('geojson'),
      ST_GeometryType(Feature.geom).label('geom_type'),
    ).filter(
      Feature.dataset_id == dataset_id,
      ST_Intersects(Feature.geom, click_area),
    ).order_by(func.ST_Distance(Feature.geom, point), Feature.id).limit(limit).all()

    data = []
    for row in rows:
      if not row.geojson:
        continue
      geom_type = (row.geom_type or '').replace('ST_', '')
      data.append({
        'type': 'Feature',
        'id': row.id,
        'geometry': json.loads(row.geojson),
        'properties': parse_properties(row.properties),
        'geom_type': geom_type,
      })
    return {
      'data': data,
      'lng': lng,
      'lat': lat,
      'total': len(data),
    }

# 根据dataset_id删除所有数据
def delete_feature_by_dataset_id(dataset_id: int):
  with get_session() as session:
    count = ((session.query(Feature).filter(Feature.dataset_id == dataset_id).delete(synchronize_session=False)))
    session.commit()
    print(f"删除 {count} 条数据")
    return True
# to_geojson

PROPS_JSON = """
CASE
  WHEN f.properties IS NULL THEN '{}'::jsonb
  WHEN jsonb_typeof(f.properties) = 'object' THEN f.properties
  WHEN jsonb_typeof(f.properties) = 'string' THEN
    CASE
      WHEN left(trim(f.properties #>> '{}'), 1) = '{' THEN (trim(f.properties #>> '{}'))::jsonb
      ELSE '{}'::jsonb
    END
  ELSE '{}'::jsonb
END
"""

def get_feature_properties_keys(dataset_id: int):
  dataset_id = int(dataset_id)
  sql = text(f"""
    SELECT DISTINCT k.key
    FROM features f
    CROSS JOIN LATERAL (
      SELECT jsonb_object_keys({PROPS_JSON}) AS key
    ) k
    WHERE f.dataset_id = :dataset_id
    ORDER BY k.key
  """)
  with get_session() as session:
    rows = session.execute(sql, {'dataset_id': dataset_id}).fetchall()
    return [row[0] for row in rows if row[0]]

def get_feature_properties_values(dataset_id: int, key: str):
  dataset_id = int(dataset_id)
  sql = text(f"""
    SELECT DISTINCT kv.value
    FROM features f
    CROSS JOIN LATERAL jsonb_each_text({PROPS_JSON}) AS kv
    WHERE f.dataset_id = :dataset_id AND kv.key = :key
    ORDER BY kv.value
    LIMIT 5000
  """)
  with get_session() as session:
    rows = session.execute(sql, {'dataset_id': dataset_id, 'key': key}).fetchall()
    return [row[0] for row in rows if row[0] is not None]

# 查询数据
def get_feature_by_geom(geom: str):
  with get_session() as session:
    features = session.query(Feature).filter(Feature.geom == geom).all()
    return [feature.to_dict() for feature in features]