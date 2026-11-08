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
