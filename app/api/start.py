from fastapi import FastAPI
from fastapi import APIRouter
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from .routers import base, data, gdal
import os

api = FastAPI()

# 接口服务
api_router = APIRouter(prefix="/api")
api_router.include_router(base.router)
api_router.include_router(data.router)
api_router.include_router(gdal.router)

api.include_router(api_router)

# 静态服务
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(BASE_DIR, "html")

api.mount(
    "/",
    StaticFiles(
        directory=WEB_DIR,
        html=True
    ),
    name="html"
)
