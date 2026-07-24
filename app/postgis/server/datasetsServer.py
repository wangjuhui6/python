from postgis.database import get_session
from postgis.base.datasets import Dataset

# 添加数据
def add_dataset(data: dict):
  with get_session() as session:
    dataset = Dataset(
      name=data['name'],
      code=data['code'],
      srid=data['srid'],
      description=data['description']
    )
    session.add(dataset)
    session.commit()
    return dataset.to_dict()

# 查询数据
def get_dataset(id: int):
  with get_session() as session:
    dataset = session.query(Dataset).filter(Dataset.id == id).first()
    return dataset.to_dict()

# 更新数据
def update_dataset(id: int, data: dict):
  with get_session() as session:
    dataset = session.query(Dataset).filter(Dataset.id == id).first()
    dataset.name = data['name']
    dataset.code = data['code']
    dataset.srid = data['srid']
    dataset.description = data['description']
    session.commit()
    return dataset.to_dict()

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
    return [dataset.to_dict() for dataset in datasets]

# 查询数据
def get_dataset_by_code(code: str):
  with get_session() as session:
    dataset = session.query(Dataset).filter(Dataset.code == code).first()
    return dataset.to_dict()

# 查询数据
def get_dataset_by_name(name: str):
  with get_session() as session:
    dataset = session.query(Dataset).filter(Dataset.name == name).first()
    return dataset.to_dict()
