from postgis.database import get_session
from postgis.base.features import Feature
from geoalchemy2.shape import WKTElement
import json

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

# 根据dataset_id删除所有数据
def delete_feature_by_dataset_id(dataset_id: int):
  with get_session() as session:
    count = ((session.query(Feature).filter(Feature.dataset_id == dataset_id).delete(synchronize_session=False)))
    session.commit()
    print(f"删除 {count} 条数据")
    return True
# to_geojson

# 根据dataset_id查询数据中properties中的key
def get_feature_properties_keys(dataset_id: int):
  with get_session() as session:
    features = session.query(Feature).filter(Feature.dataset_id == dataset_id).all()
    keys = []
    for feature in features:
      _properties = json.loads(feature.properties)
      for key in _properties.keys():
        if key not in keys:
          keys.append(key)
    return keys

# 根据dataset_id和key查询数据中properties中的value
def get_feature_properties_values(dataset_id: int, key: str):
  with get_session() as session:
    features = session.query(Feature).filter(Feature.dataset_id == dataset_id).filter(Feature.properties[key].isnot(None)).all()
    values = []
    for feature in features:
      _properties = json.loads(feature.properties)
      if key in _properties:
        values.append(_properties[key])
    return values

# 查询数据
def get_feature_by_geom(geom: str):
  with get_session() as session:
    features = session.query(Feature).filter(Feature.geom == geom).all()
    return [feature.to_dict() for feature in features]