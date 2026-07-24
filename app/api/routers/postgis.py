from fastapi import APIRouter, Request
from utils.response import ResponseModel
from utils.osm_importer import PBFImporter
from postgis.server.datasetsServer import add_dataset as add_dataset_server, update_dataset as update_dataset_server, delete_dataset as delete_dataset_server, get_all_datasets as get_all_datasets_server, get_dataset_by_code as get_dataset_by_code_server, get_dataset_by_name as get_dataset_by_name_server
from postgis.server.featuresServer import add_feature as add_feature_server, update_feature as update_feature_server, delete_feature as delete_feature_server, get_all_features as get_all_features_server, get_feature_by_dataset_id as get_feature_by_dataset_id_server, get_feature_by_geom as get_feature_by_geom_server

router = APIRouter(prefix="/postgis", tags=["POSTGIS"])

# 查询数据源列表
@router.get("/datasets")
def read_root():
  print("查询数据源列表")
  datasets = get_all_datasets_server()
  return ResponseModel(
    code=200,
    msg="查询列表成功",
    data=datasets if datasets else []
  )

# 新增/编辑 数据源
@router.post("/datasets/add")
def add_dataset(data: dict):
  id = add_dataset_server(data) if not data.get('id') else update_dataset_server(data.get('id'), data)
  return ResponseModel(
    code=200,
    msg="新增数据源成功",
    data=id
  )

@router.post("/datasets/delete")
def delete_dataset(data: dict):
  result = delete_dataset_server(data.get('id'))
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
  datasets_id = params.get('datasets_id')
  features = get_feature_by_dataset_id_server(datasets_id)
  return ResponseModel(
    code=200,
    msg="查询数据成功",
    data=features if features else []
  )
