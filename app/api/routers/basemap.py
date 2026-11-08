import mimetypes

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

from utils.basemap_server import asset_path, start, status, stop, style_document, tile
from utils.response import ResponseModel

router = APIRouter(prefix="/basemap", tags=["底图"])
public_router = APIRouter(prefix="/basemap", tags=["底图"])


class BasemapParams(BaseModel):
  mbtiles: str
  style: str


@router.get("/status")
def basemap_status():
  return ResponseModel(code=200, msg="ok", data=status())


@router.post("/start")
def basemap_start(params: BasemapParams):
  data = start(params.mbtiles, params.style)
  return ResponseModel(code=200, msg=data.get("message") or "ok", data=data)


@router.post("/stop")
def basemap_stop():
  data = stop()
  return ResponseModel(code=200, msg=data.get("message") or "ok", data=data)


@public_router.get("/style.json")
def basemap_style():
  doc = style_document()
  if doc is None:
    return JSONResponse({"message": "底图服务未启动"}, status_code=404)
  return JSONResponse(doc)


@public_router.get("/tiles/{z}/{x}/{y}.pbf")
def basemap_tile(z: int, x: int, y: int):
  data = tile(z, x, y)
  if data is None:
    return Response(status_code=404)
  if data == b"":
    return Response(status_code=204)
  headers = {
    "Content-Type": "application/vnd.mapbox-vector-tile",
    "Cache-Control": "public, max-age=86400",
  }
  if data[:2] == b"\x1f\x8b":
    headers["Content-Encoding"] = "gzip"
  return Response(content=data, headers=headers)


@public_router.get("/{path:path}")
def basemap_asset(path: str):
  file_path = asset_path(path)
  if not file_path:
    return Response(status_code=404)
  media = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
  return FileResponse(file_path, media_type=media)
