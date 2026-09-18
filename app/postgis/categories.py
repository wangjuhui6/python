from sqlalchemy import and_, case, cast, false, func, not_, or_
from sqlalchemy.dialects.postgresql import JSONB
from geoalchemy2.functions import ST_GeometryType
from postgis.base.features import Feature

GEOM_GROUPS = {
  'point': ['ST_Point', 'ST_MultiPoint'],
  'line': ['ST_LineString', 'ST_MultiLineString'],
  'polygon': ['ST_Polygon', 'ST_MultiPolygon'],
}

GEOM_LABELS = {
  'point': '点',
  'line': '线',
  'polygon': '面',
}

DEFAULT_ZOOM = {
  'point': (12, 22),
  'line': (8, 22),
  'polygon': (6, 22),
}


def _as_values(item: dict) -> list:
  if isinstance(item.get('values'), list):
    return [str(v).strip() for v in item['values'] if v is not None and str(v).strip() != '']
  value = str(item.get('value') or '').strip()
  return [value] if value else []


def _as_bool(value, default=False) -> bool:
  if isinstance(value, bool):
    return value
  if value in (None, ''):
    return default
  if isinstance(value, str):
    return value.lower() in ('1', 'true', 'yes', 'on')
  return bool(value)


def normalize_condition(item: dict) -> dict:
  key = str(item.get('key') or '').strip()
  values = _as_values(item)
  exclude = _as_bool(item.get('exclude', item.get('not', False)))
  return {'key': key, 'values': values, 'exclude': exclude}


def normalize_conditions(item: dict) -> list:
  raw = item.get('conditions')
  if isinstance(raw, list) and raw:
    return [normalize_condition(c) for c in raw if isinstance(c, dict) and str(c.get('key') or '').strip()]
  if item.get('key'):
    return [normalize_condition(item)]
  return []


def condition_label(cond: dict) -> str:
  key = cond.get('key') or ''
  values = cond.get('values') or []
  exclude = bool(cond.get('exclude'))
  if not key:
    return ''
  if not values:
    return f'无{key}' if exclude else key
  joined = values[0] if len(values) == 1 else ','.join(values)
  if exclude:
    return f'{key}≠{joined}' if len(values) == 1 else f'{key}∉{joined}'
  return f'{key}={joined}' if len(values) == 1 else f'{key}∈{joined}'


def normalize_category(item: dict) -> dict:
  geom_type = (item.get('geom_type') or '').strip()
  if geom_type not in GEOM_GROUPS:
    geom_type = ''
  conditions = normalize_conditions(item)
  zmin, zmax = DEFAULT_ZOOM.get(geom_type, (0, 22))
  min_zoom = item.get('minZoom', item.get('min_zoom', zmin))
  max_zoom = item.get('maxZoom', item.get('max_zoom', zmax))
  try:
    min_zoom = int(min_zoom)
  except (TypeError, ValueError):
    min_zoom = zmin
  try:
    max_zoom = int(max_zoom)
  except (TypeError, ValueError):
    max_zoom = zmax
  show = item.get('show', True)
  if isinstance(show, str):
    show = show.lower() not in ('false', '0', 'no')
  name = str(item.get('name') or '').strip()
  if not name:
    parts = []
    if geom_type:
      parts.append(GEOM_LABELS.get(geom_type, geom_type))
    parts.extend([condition_label(c) for c in conditions if condition_label(c)])
    name = ' 且 '.join(parts) or '未命名分类'
  cid = item.get('id') or f"custom-{abs(hash((geom_type, name, str(conditions))))}"
  return {
    'id': cid,
    'name': name,
    'geom_type': geom_type,
    'conditions': conditions,
    'minZoom': min_zoom,
    'maxZoom': max_zoom,
    'show': bool(show),
  }


def parse_json_field(value, default):
  import json
  if value is None or value == '':
    return default
  if isinstance(value, (dict, list)):
    return value
  if isinstance(value, str):
    try:
      return json.loads(value)
    except json.JSONDecodeError:
      return default
  return default


def feature_properties_jsonb():
  """兼容 properties 被存成 JSON 字符串的旧数据。"""
  parsed = cast(func.trim(Feature.properties.op('#>>')('{}')), JSONB)
  return case(
    (func.jsonb_typeof(Feature.properties) == 'string', parsed),
    else_=Feature.properties,
  )


def _condition_sql(cond: dict):
  key = cond.get('key')
  if not key:
    return None
  props = feature_properties_jsonb()
  values = cond.get('values') or []
  exclude = bool(cond.get('exclude'))
  has_key = props.op('?')(key)
  if values:
    in_values = props.op('->>')(key).in_([str(v) for v in values])
    if exclude:
      return and_(has_key, not_(in_values))
    return in_values
  if exclude:
    return not_(has_key)
  return has_key


def category_sql_clause(cat: dict):
  parts = []
  geom_type = cat.get('geom_type')
  if geom_type in GEOM_GROUPS:
    parts.append(ST_GeometryType(Feature.geom).in_(GEOM_GROUPS[geom_type]))
  for cond in cat.get('conditions') or []:
    clause = _condition_sql(cond)
    if clause is not None:
      parts.append(clause)
  if not parts:
    return None
  return and_(*parts) if len(parts) > 1 else parts[0]


def apply_category_filter(query, categories: list, selected_ids: list, zoom=None):
  """分类之间为 OR；同一分类内多个条件为 AND（同一 key 多个 value 为 OR）。"""
  if not selected_ids:
    return query
  selected = {str(i) for i in selected_ids if i}
  clauses = []
  for raw in categories or []:
    cat = normalize_category(raw)
    if cat['id'] not in selected:
      continue
    if zoom is not None and not (cat['minZoom'] <= float(zoom) <= cat['maxZoom']):
      continue
    clause = category_sql_clause(cat)
    if clause is not None:
      clauses.append(clause)
  if not clauses:
    return query.filter(false())
  return query.filter(or_(*clauses))


def apply_uncategorized_filter(query, categories: list):
  """排除已命中任一分类规则的要素。没有有效分类时返回全部。"""
  clauses = []
  for raw in categories or []:
    cat = normalize_category(raw)
    clause = category_sql_clause(cat)
    if clause is not None:
      clauses.append(clause)
  if not clauses:
    return query
  return query.filter(not_(or_(*clauses)))
