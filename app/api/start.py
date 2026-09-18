from fastapi import FastAPI
from fastapi import APIRouter
from fastapi.staticfiles import StaticFiles
from .routers import base, data, gdal, tkinter, record, postgis, style, llm
from base import get_request_path

api = FastAPI()

# 接口服务
api_router = APIRouter(prefix="/api")
api_router.include_router(base.router)
api_router.include_router(data.router)
api_router.include_router(gdal.router)
api_router.include_router(tkinter.router)
api_router.include_router(record.router)
# postgis 接口相关
api_router.include_router(postgis.router)
api_router.include_router(style.router)
api_router.include_router(llm.router)

api.include_router(api_router)

# 静态服务（打包后从解压目录读取 html）
WEB_DIR = get_request_path("html")

api.mount(
    "/",
    StaticFiles(
        directory=WEB_DIR,
        html=True
    ),
    name="html"
)
