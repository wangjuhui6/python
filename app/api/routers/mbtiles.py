from fastapi import APIRouter
from pydantic import BaseModel

from utils.mbtiles_convert import environment, start, status, stop
from utils.response import ResponseModel

router = APIRouter(prefix="/gdal", tags=["MBTiles"])


class OsmPbfToMbtilesParams(BaseModel):
  inputFile: str
  outputPath: str
  maxzoom: int = 14
  memoryGb: int = 6


class ImageToMbtilesParams(BaseModel):
  folder: str
  minzoom: int = 12
  maxzoom: int = 16


@router.get("/osmPbfToMbtiles/env")
def osm_pbf_to_mbtiles_env():
  return ResponseModel(code=200, msg="ok", data=environment())


@router.get("/osmPbfToMbtiles/status")
def osm_pbf_to_mbtiles_status():
  return ResponseModel(code=200, msg="ok", data=status())


@router.post("/osmPbfToMbtiles")
def osm_pbf_to_mbtiles(params: OsmPbfToMbtilesParams):
  data = start(params.inputFile, params.outputPath, params.maxzoom, params.memoryGb)
  return ResponseModel(code=200, msg=data.get("message") or "ok", data=data)


@router.post("/osmPbfToMbtiles/stop")
def osm_pbf_to_mbtiles_stop():
  data = stop()
  return ResponseModel(code=200, msg=data.get("message") or "ok", data=data)


@router.post("/imageToMbtiles")
def image_to_mbtiles(params: ImageToMbtilesParams):
  from utils.image_mbtiles import ImageMbtilesError, build

  folder = (params.folder or "").strip().strip('"')
  if not folder:
    return ResponseModel(code=400, msg="请选择文件夹", data=None)
  if params.minzoom > params.maxzoom:
    return ResponseModel(code=400, msg="最小级别不能大于最大级别", data=None)
  try:
    data = build(folder, None, params.minzoom, params.maxzoom)
  except ImageMbtilesError as exc:
    return ResponseModel(code=400, msg=str(exc), data=None)
  return ResponseModel(code=200, msg="已生成", data=data)
