from fastapi import APIRouter
from server.record import get_all_record, delete_record
from utils.response import ResponseModel

router = APIRouter(prefix="/record", tags=["RECORD"])

# 查询列表
@router.get("/list")
def read_root(page: int, page_size: int):
  print(page, page_size, '我是请求参数')

  data = get_all_record()
  return ResponseModel(
    code=200,
    msg="查询成功",
    data=data
  )

# 删除记录
@router.post("/delete")
def read_root(params: dict):
  id = params.get("id")
  data = delete_record(id)
  return ResponseModel(
    code=200,
    msg="删除成功",
    data=data
  )

