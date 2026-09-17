import base64
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel
from utils.response import ResponseModel

router = APIRouter(prefix="/style", tags=["STYLE"])


class PathBody(BaseModel):
  file_path: str


class WriteBody(BaseModel):
  file_path: str
  content: str


class WriteBinaryBody(BaseModel):
  file_path: str
  content_b64: str


@router.post("/read")
def read_style(params: PathBody):
  p = Path(params.file_path)
  if not p.exists() or not p.is_file():
    return ResponseModel(code=201, msg="文件不存在", data=None)
  try:
    return ResponseModel(data=p.read_text(encoding="utf-8"))
  except UnicodeDecodeError:
    return ResponseModel(data=p.read_text(encoding="utf-8", errors="replace"))


@router.post("/write")
def write_style(params: WriteBody):
  p = Path(params.file_path)
  p.parent.mkdir(parents=True, exist_ok=True)
  p.write_text(params.content, encoding="utf-8")
  return ResponseModel(msg="保存成功")


@router.post("/read_binary")
def read_binary(params: PathBody):
  p = Path(params.file_path)
  if not p.exists() or not p.is_file():
    return ResponseModel(code=201, msg="文件不存在", data=None)
  return ResponseModel(data=base64.b64encode(p.read_bytes()).decode("ascii"))


@router.post("/write_binary")
def write_binary(params: WriteBinaryBody):
  p = Path(params.file_path)
  p.parent.mkdir(parents=True, exist_ok=True)
  p.write_bytes(base64.b64decode(params.content_b64))
  return ResponseModel(msg="保存成功")
