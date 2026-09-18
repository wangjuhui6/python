from postgis.database import get_session
from postgis.base.datasets import Dataset
from postgis.categories import normalize_category, parse_json_field

def _dataset_dict(dataset):
  data = dataset.to_dict()
  data['mapping'] = parse_json_field(data.get('mapping'), {}) or {}
  cats = parse_json_field(data.get('categories'), []) or []
  data['categories'] = [normalize_category(c) for c in cats if isinstance(c, dict)]
  return data

def _fill_dataset(dataset, data: dict):
  dataset.name = data['name']
  dataset.code = data['code']
  dataset.srid = data['srid']
  dataset.description = data.get('description') or ''
  if 'mapping' in data:
    mapping = parse_json_field(data.get('mapping'), {})
    dataset.mapping = mapping if isinstance(mapping, dict) else {}
  if 'categories' in data:
    cats = parse_json_field(data.get('categories'), [])
    if not isinstance(cats, list):
      cats = []
    dataset.categories = [normalize_category(c) for c in cats if isinstance(c, dict)]

def update_dataset_categories(dataset_id: int, categories):
  with get_session() as session:
    dataset = session.query(Dataset).filter(Dataset.id == int(dataset_id)).first()
    if not dataset:
      return None
    cats = parse_json_field(categories, [])
    if not isinstance(cats, list):
      cats = []
    dataset.categories = [normalize_category(c) for c in cats if isinstance(c, dict)]
    session.commit()
    return _dataset_dict(dataset)

# 添加数据
def add_dataset(data: dict):
  with get_session() as session:
    dataset = Dataset(
      name=data['name'],
      code=data['code'],
      srid=data['srid'],
      description=data.get('description') or '',
      mapping=parse_json_field(data.get('mapping'), {}) or {},
      categories=[normalize_category(c) for c in (parse_json_field(data.get('categories'), []) or []) if isinstance(c, dict)],
    )
    session.add(dataset)
    session.commit()
    return _dataset_dict(dataset)

# 查询数据
def get_dataset(id: int):
  with get_session() as session:
    dataset = session.query(Dataset).filter(Dataset.id == id).first()
    return _dataset_dict(dataset) if dataset else None

# 更新数据
def update_dataset(id: int, data: dict):
  with get_session() as session:
    dataset = session.query(Dataset).filter(Dataset.id == id).first()
    _fill_dataset(dataset, data)
    session.commit()
    return _dataset_dict(dataset)

# 删除数据
def delete_dataset(id: int):
  with get_session() as session:
    dataset = session.query(Dataset).filter(Dataset.id == id).first()
    session.delete(dataset)
    session.commit()
    return True

# 查询所有数据
def get_all_datasets():
  with get_session() as session:
    datasets = session.query(Dataset).all()
    return [_dataset_dict(dataset) for dataset in datasets]

# 查询数据
def get_dataset_by_code(code: str):
  with get_session() as session:
    dataset = session.query(Dataset).filter(Dataset.code == code).first()
    return _dataset_dict(dataset) if dataset else None

# 查询数据
def get_dataset_by_name(name: str):
  with get_session() as session:
    dataset = session.query(Dataset).filter(Dataset.name == name).first()
    return _dataset_dict(dataset) if dataset else None
