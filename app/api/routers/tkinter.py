from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
from utils.tkinter import select_file, select_folder, select_save_path, select_save_path_and_file_name
from utils.response import ResponseModel

router = APIRouter(prefix="/tkinter", tags=["TKINTER"])

class FileTypes(BaseModel):
  filetypes: List[List[str]] | None = None

# 选择文件
@router.post("/file")
def read_root(params: FileTypes):
  data = select_file(params.filetypes)
  return ResponseModel(
    code=200 if data else 201,
    msg="选择文件成功" if data else "选择文件失败",
    data=data
  )

# 选择文件夹
@router.post("/folder")
def read_root():
  data = select_folder()
  return ResponseModel(
    code=200 if data else 201,
    msg="选择文件夹成功" if data else "选择文件夹失败",
    data=data
  )

# 选择要保存的文件路径
@router.post("/save_path")
def read_root(params: FileTypes):
  data = select_save_path(params.filetypes)
  return ResponseModel(
    code=200 if data else 201,
    msg="选择要保存的文件路径成功" if data else "选择要保存的文件路径失败",
    data=data
  )

# 保存文件路径 保存文件名
@router.post("/save_path_and_file_name")
def read_root(params: FileTypes):
  data = select_save_path_and_file_name(params.filetypes)
  return ResponseModel(
    code=200 if data else 201,
    msg="选择要保存的文件路径和文件名成功" if data else "选择要保存的文件路径和文件名失败",
    data=data
  )