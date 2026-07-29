from fastapi import APIRouter, Request
from utils.response import ResponseModel
from utils.osm_importer import PBFImporter
import postgis.server.datasetsServer as datasets_server_methods
import postgis.server.featuresServer as features_server_methods

router = APIRouter(prefix="/postgis", tags=["POSTGIS"])

# 查询数据源列表
@router.get("/datasets")
def read_root():
  datasets = datasets_server_methods.get_all_datasets()
  return ResponseModel(
    code=200,
    msg="查询列表成功",
    data=datasets if datasets else []
  )

# 新增/编辑 数据源
@router.post("/datasets/add")
def add_dataset(data: dict):
  id = datasets_server_methods.add_dataset(data) if not data.get('id') else datasets_server_methods.update_dataset(data.get('id'), data)
  return ResponseModel(
    code=200,
    msg="新增数据源成功",
    data=id
  )

@router.post("/datasets/delete")
def delete_dataset(data: dict):
  result = datasets_server_methods.delete_dataset(data.get('id'))
  return ResponseModel(
    code=200,
    msg="删除数据源成功",
    data=result
  )

# 导入数据
@router.post("/features/import")
def import_data(data: dict):
  data_type = data.get('data_type')
  file_path = data.get('file_path')
  datasets_id = data.get('datasets_id')

  try:
    if data_type == 'pbf':
      handler = PBFImporter(file_path=file_path, datasets_id=datasets_id) 
      handler.apply_file(
        handler.file_path,
        locations=True
      )
      handler.flush()      # 写入最后不足5000条的数据
    return ResponseModel(
      code=200,
      msg="导入数据成功",
      data=True
    )
  except Exception as e:
    return ResponseModel(
      code=500,
      msg=f"导入数据失败: {e}",
      data=False
    )

# 根据数据源id查询数据
@router.get("/features/list")
def list_features(request: Request):
  params = dict(request.query_params)
  is_geojson = params.get('is_geojson') or False
  datasets_id = params.get('datasets_id')
  page = params.get('page') or 1
  page_size = params.get('page_size') or 1000
  page = int(page)
  page_size = int(page_size)
  features = features_server_methods.get_features_by_dataset_id_geojson(datasets_id, page, page_size) if is_geojson else features_server_methods.get_features_by_dataset_id(datasets_id, page, page_size)
  data = {
    'data': features['data'] if features else [],
    'total': features['total'] if features else 0,
    'page': features['page'] if features else 1,
    'page_size': features['page_size'] if features else 1000
  }
  return ResponseModel(
    code=200,
    msg="查询数据成功",
    data=data
  )

# 根据数据源id删除所有数据
@router.post("/features/delete")
def delete_features(data: dict):
  result = features_server_methods.delete_feature_by_dataset_id(data.get('datasets_id'))
  return ResponseModel(
    code=200,
    msg="删除数据成功",
    data=result
  )

# 根据dataset_id查询数据中properties中的key
@router.get("/features/properties/keys")
def get_feature_properties_keys(request: Request):
  params = dict(request.query_params)
  datasets_id = params.get('datasets_id')
  keys = features_server_methods.get_feature_properties_keys(datasets_id)
  return ResponseModel(
    code=200,
    msg="查询数据成功",
    data=keys
  )

# 根据dataset_id和key查询数据中properties中的value
@router.get("/features/properties/values")
def get_feature_properties_values(request: Request):
  params = dict(request.query_params)
  datasets_id = params.get('datasets_id')
  key = params.get('key')
  values = features_server_methods.get_feature_properties_values(datasets_id, key)
  return ResponseModel(
    code=200,
    msg="查询数据成功",
    data=values
  )
