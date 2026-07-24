from postgis.database import get_session
from postgis.base.features import Feature

# 添加数据
def add_feature(data: dict):
  with get_session() as session:
    feature = Feature(
      dataset_id=data['dataset_id'],
      geom=data['geom'],
      properties=data['properties']
    )
    session.add(feature)
    session.commit()
    return feature.to_dict()

# 批量添加数据
def add_features(data: list):
  with get_session() as session:
    for feature in data:
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
def get_feature_by_dataset_id(dataset_id: int):
  with get_session() as session:
    features = session.query(Feature).filter(Feature.dataset_id == dataset_id).all()
    return [feature.to_dict() for feature in features]

# 查询数据
def get_feature_by_geom(geom: str):
  with get_session() as session:
    features = session.query(Feature).filter(Feature.geom == geom).all()
    return [feature.to_dict() for feature in features]