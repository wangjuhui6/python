from fastapi import FastAPI
from fastapi import APIRouter
from fastapi.responses import FileResponse
from .routers import base, data
import os

api = FastAPI()

# 静态服务
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(BASE_DIR, "html")

@api.get("/")
def read_index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))

# 接口服务
api_router = APIRouter(prefix="/api")
api_router.include_router(base.router)
api_router.include_router(data.router)

api.include_router(api_router)
