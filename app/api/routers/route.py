from fastapi import APIRouter
from pydantic import BaseModel

from route_engine.describe import describe
from route_engine.service import defaults, plan, start, status, stop
from utils.response import ResponseModel

router = APIRouter(prefix="/route", tags=["路线规划"])


class StartBody(BaseModel):
  pbf_path: str


class PlanBody(BaseModel):
  profile: str = "car"
  points: list[list[float]]


class DescribeBody(BaseModel):
  profile: str = "car"
  start: list[float]
  end: list[float]
  description: str


@router.get("/defaults")
def route_defaults():
  return ResponseModel(data=defaults())


@router.get("/status")
def route_status():
  return ResponseModel(data=status())


@router.post("/start")
def route_start(body: StartBody):
  try:
    data = start(body.pbf_path)
  except ValueError as exc:
    return ResponseModel(code=201, msg=str(exc))
  return ResponseModel(data=data)


@router.post("/stop")
def route_stop():
  return ResponseModel(data=stop())


@router.post("/plan")
def route_plan(body: PlanBody):
  try:
    data = plan(body.profile, body.points)
  except ValueError as exc:
    return ResponseModel(code=201, msg=str(exc))
  return ResponseModel(data=data)


@router.post("/describe")
def route_describe(body: DescribeBody):
  try:
    data = describe(body.profile, body.start, body.end, body.description)
  except ValueError as exc:
    return ResponseModel(code=201, msg=str(exc))
  return ResponseModel(data=data)
