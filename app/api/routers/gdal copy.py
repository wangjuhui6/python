import subprocess
from fastapi import APIRouter
from pydantic import BaseModel
import os
from utils.response import ResponseModel

# todo geojson转shp成功了
# 后续看看还有哪些功能 将这些都集成一下
# 结合前端页面的上传功能
# python 引入数据库概念 做任务管理记录使用

# gdal 能做的东西
# 矢量数据处理
  # 坐标转换
  # 裁剪
  # sql查询
  # 字段处理
# 栅格处理
  #  格式转换
  #  投重投影
  # 裁剪影像
  # 影像压缩
# 瓦片生成
  # xyz瓦片
  # MBTiles
# DEM处理
  # 坡度
  # 坡向
  # 阴影分析
# Cesium相关
  # GeoJSON转3D Tiles
  # 坐标统一

# 项目根目录
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# GDAL根目录
GDAL_ROOT = os.path.join(BASE_DIR, "tools", "gdal")

# OGR2OGR 路径
OGR2OGR = os.path.join(
    GDAL_ROOT,
    "bin",
    "gdal",
    "apps",
    "ogr2ogr.exe"
)

# 环境变量
env = os.environ.copy()

# 添加 GDAL 路径到环境变量
env["PATH"] = (
    os.path.join(GDAL_ROOT, "bin")
    + ";"
    + env["PATH"]
)

# 添加 GDAL_DATA 路径到环境变量
env["GDAL_DATA"] = os.path.join(
    GDAL_ROOT,
    "share",
    "gdal"
)

# 添加 PROJ_LIB 路径到环境变量
env["PROJ_LIB"] = os.path.join(
    GDAL_ROOT,
    "bin",
    "proj9",
    "share",
    "proj"
)

# 执行 OGR2OGR 命令
result = subprocess.run(
    [OGR2OGR, "--version"],
    env=env,
    capture_output=True,
    text=True
)

router = APIRouter(prefix="/gdal", tags=["GDAL"])

class GeojsonToShpParams(BaseModel):
  inputFile: str
  outputPath: str

@router.post("/geojsonToShp")
def geojsonToShp(params: GeojsonToShpParams):
  inputFile = params.inputFile
  outputPath = params.outputPath
  layerName = os.path.basename(outputPath).split(".")[0]

  cmd = [
    OGR2OGR,
    "-f",
    "ESRI Shapefile",
    outputPath,
    inputFile,
    "-nln",
    layerName,
    "-lco",
    "ENCODING=UTF-8"
  ]

  result = subprocess.run(
    cmd,
    env=env,
    capture_output=True,
    text=True
  )

  if result.returncode != 0:
    return ResponseModel(
      code=500,
      msg="geoJSON转Shapefile失败",
      data=result.stderr
    )

  return ResponseModel(
    code=200,
    msg="geoJSON转Shapefile成功",
    data=result.stdout
  )
