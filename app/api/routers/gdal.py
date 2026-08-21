import subprocess
from fastapi import APIRouter
from pydantic import BaseModel
import os
from utils.response import ResponseModel
from server.record import add_record, update_record
import geopandas as gpd
from utils.shpToGlb import ShpToGlb
from utils.clip3dTiles import Clip3dTiles
from utils.clip3dTilesNew import Clip3dTilesNew

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

# geojson转shp
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

  def run_command():
    process = subprocess.Popen(
      cmd,
      env=env,
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
      text=True
    )
    record = add_record(inputFile, outputPath, 0)

    for line in process.stdout:
      print(line.strip())

    return_code = process.wait()

    if return_code == 0:
      update_record(record.id, 1)
    else:
      update_record(record.id, 2)
  
  run_command()

  return ResponseModel(
    code=200,
    msg="任务添加成功",
    data=True
  )

# shp转geojson
@router.post("/shpToGeojson")
def shpToGeojson(params: GeojsonToShpParams):
  inputFile = params.inputFile
  outputPath = params.outputPath
  layerName = os.path.basename(outputPath).split(".")[0]

  cmd = [
    OGR2OGR,
    "-f",
    "GeoJSON",
    outputPath,
    inputFile,
    "-nln",
    layerName,
    "-lco",
    "ENCODING=UTF-8"
  ]

  def run_command():
    process = subprocess.Popen(
      cmd,
      env=env,
      stdout=subprocess.PIPE,
      stderr=subprocess.PIPE,
      text=True
    )
    record = add_record(inputFile, outputPath, 0)

    for line in process.stdout:
      print(line.strip())

    return_code = process.wait()

    if return_code == 0:
      update_record(record.id, 1)
    else:
      update_record(record.id, 2)
  
  run_command()

  return ResponseModel(
    code=200,
    msg="任务添加成功",
    data=True
  )

# osm pbf转mbtiles
@router.post("/osmPbfToMbtiles")
def osmPbfToMbtiles(params: GeojsonToShpParams):
  inputFile = params.inputFile
  outputPath = params.outputPath
  pathName = os.path.basename(outputPath).split(".")[0]
  print(pathName, '我是pathName', outputPath, '我是inputFile')
  # outputPath = params.outputPath

  # cmd = [
  #   OGR2OGR,
  #   "-f",
  #   "MBTiles",
  #   outputPath,
  #   inputFile,
  #   "-nln",
  #   layerName,
  #   "-lco",
  #   "ENCODING=UTF-8"
  # ]

  # def run_command():
  #   process = subprocess.Popen(
  #     cmd,
  #     env=env,
  #     stdout=subprocess.PIPE,
  #     stderr=subprocess.PIPE,
  #     text=True
  #   )
  #   record = add_record(inputFile, outputPath, 0)

  #   for line in process.stdout:
  #     print(line.strip())

  #   return_code = process.wait()
  #   if return_code == 0:
  #     update_record(record.id, 1)
  #   else:
  #     update_record(record.id, 2)
  
  # run_command()

  # return ResponseModel(
  #   code=200,
  #   msg="任务添加成功",
  #   data=True
  # )

# shp 获取字段
@router.post("/getShpFields")
def getShpFields(data: dict):
  file = data.get('file')
  gdf = gpd.read_file(file)
  fields = gdf.columns.tolist()
  return ResponseModel(
    code=200,
    msg="获取字段成功",
    data=fields
  )

# shp 生成白膜
@router.post("/generateGlb")
def generateGlb(data: dict):
  shpToGlb = ShpToGlb(data)
  print(shpToGlb)

  return ResponseModel(
    code=200,
    msg="生成白膜成功",
    data=True
  )

# 3dtiles裁剪
@router.post("/clip3dTiles")
def clip3dTiles(data: dict):
  inputPath = data.get('inputPath')
  outputPath = data.get('outputPath')
  clipPolygon = data.get('clipPolygon')
  mode = data.get('mode')
  isNew = data.get('isNew')
  debugger = data.get('debugger', False)
  if isNew:
    clip3dTiles = Clip3dTilesNew({
      'inputPath': inputPath,
      'outputPath': outputPath,
      'clipPolygon': clipPolygon,
      'mode': mode,
      'debugger': debugger,
    })
  else:
    clip3dTiles = Clip3dTiles({
      'inputPath': inputPath,
      'outputPath': outputPath,
      'clipPolygon': clipPolygon,
      'mode': mode,
      'debugger': debugger,
    })

  return ResponseModel(
    code=200 if clip3dTiles else 500,
    msg="裁剪3dtiles成功" if clip3dTiles else "裁剪3dtiles失败",
    data=True if clip3dTiles else False
  )