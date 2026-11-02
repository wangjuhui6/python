import asyncio

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from llm.config import CONFIG_PATH, load_config, save_config
from llm.engine import chat, list_models, load, runtime_status, unload
from llm.io_preview import peek
from llm.map_legend import recognize_map
from llm.train_legend import (
  add_run,
  add_sample,
  dataset_info,
  delete_sample,
  export_dataset,
  get_sample,
  list_samples,
  load_synth_config,
  prelabel_sample,
  sample_image_path,
  save_sample,
  save_synth_config,
)
from llm.transform import apply_plan, make_plan, run_instruction
from utils.response import ResponseModel

router = APIRouter(prefix="/llm", tags=["LLM"])


class ConfigBody(BaseModel):
  model_dir: str | None = None
  model_path: str | None = None
  mmproj_path: str | None = None
  n_ctx: int | None = None
  n_threads: int | None = None
  n_gpu_layers: int | None = None
  autoload: bool | None = None
  skip_llm_for_script: bool | None = None
  max_tokens: int | None = None


class LoadBody(BaseModel):
  model_path: str | None = None
  mmproj_path: str | None = None


class ChatBody(BaseModel):
  prompt: str
  system: str | None = "你是本地离线助手，回答简洁。"
  temperature: float = 0.2


class PathBody(BaseModel):
  path: str


class PlanBody(BaseModel):
  instruction: str
  paths: list[str] | None = None
  path: str | None = None
  mapping_path: str | None = None
  save_path: str | None = None


class ApplyBody(BaseModel):
  instruction: str | None = None
  paths: list[str] | None = None
  path: str | None = None
  save_path: str | None = None
  plan: dict | None = None
  dry_run: bool = False
  mapping_path: str | None = None


class RunBody(BaseModel):
  instruction: str
  paths: list[str] | None = None
  dry_run: bool = True
  plan: dict | None = None


class TrainSampleBody(BaseModel):
  legend: list | None = None
  legend_box: dict | None = None
  features: list | None = None
  instruction: str | None = None
  notes: str | None = None
  status: str | None = None
  source: str | None = None


class TrainExportBody(BaseModel):
  statuses: list[str] | None = None


class TrainRunBody(BaseModel):
  export_path: str | None = None
  base_model: str | None = None
  output_path: str | None = None
  sample_count: int | None = None
  notes: str | None = None


class TrainPrelabelBody(BaseModel):
  instruction: str | None = None


class TrainSynthConfigBody(BaseModel):
  basemapText: str | None = None
  nwLng: str | None = None
  nwLat: str | None = None
  seLng: str | None = None
  seLat: str | None = None
  imageCount: int | None = None
  mapWidth: int | None = None
  mapHeight: int | None = None
  minZoom: int | None = None
  maxZoom: int | None = None
  minFeatures: int | None = None
  maxFeatures: int | None = None
  minLegend: int | None = None
  catalog: list[dict] | None = None


@router.get("/config")
def get_config():
  data = runtime_status()
  data["config_path"] = str(CONFIG_PATH)
  return ResponseModel(data=data)


@router.post("/config")
def update_config(params: ConfigBody):
  save_config(params.model_dump(exclude_none=True))
  data = runtime_status()
  data["config_path"] = str(CONFIG_PATH)
  return ResponseModel(msg="配置已保存", data=data)


@router.get("/models")
def models(model_dir: str | None = None):
  directory = model_dir or load_config().get("model_dir") or ""
  if not directory:
    return ResponseModel(msg="尚未设置模型目录", data=[])
  return ResponseModel(data=list_models(directory))


@router.post("/load")
def load_model(params: LoadBody):
  try:
    data = load(params.model_path, mmproj_path=params.mmproj_path)
    data["config_path"] = str(CONFIG_PATH)
    return ResponseModel(msg="模型已加载", data=data)
  except Exception as exc:
    return ResponseModel(code=201, msg=str(exc), data=runtime_status())


@router.post("/unload")
def unload_model():
  unload()
  data = runtime_status()
  data["config_path"] = str(CONFIG_PATH)
  return ResponseModel(msg="模型已卸载", data=data)


@router.post("/chat")
def chat_model(params: ChatBody):
  if not (params.prompt or "").strip():
    return ResponseModel(code=201, msg="请输入测试内容", data=None)
  try:
    text = chat(
      [
        {"role": "system", "content": params.system or ""},
        {"role": "user", "content": params.prompt},
      ],
      temperature=params.temperature,
    )
    return ResponseModel(data={"text": text})
  except Exception as exc:
    return ResponseModel(code=201, msg=str(exc), data=None)


@router.post("/preview")
def preview_source(params: PathBody):
  if not (params.path or "").strip():
    return ResponseModel(code=201, msg="请选择文件或文件夹", data=None)
  try:
    return ResponseModel(data=peek(params.path))
  except Exception as exc:
    return ResponseModel(code=201, msg=str(exc), data=None)


@router.post("/plan")
def plan_transform(params: PlanBody):
  if not (params.instruction or "").strip():
    return ResponseModel(code=201, msg="请填写描述", data=None)
  try:
    return ResponseModel(data=make_plan(
      params.instruction,
      paths=params.paths,
      path=params.path,
      mapping_path=params.mapping_path,
      save_path=params.save_path,
    ))
  except Exception as exc:
    return ResponseModel(code=201, msg=str(exc), data=None)


@router.post("/apply")
def apply_transform(params: ApplyBody):
  try:
    return ResponseModel(
      msg="转换完成",
      data=apply_plan(
        params.path,
        params.save_path,
        params.plan or {},
        dry_run=params.dry_run,
        mapping_path=params.mapping_path,
      ),
    )
  except Exception as exc:
    return ResponseModel(code=201, msg=str(exc), data=None)


@router.post("/run")
def run_transform(params: RunBody):
  if not (params.instruction or "").strip():
    return ResponseModel(code=201, msg="请填写描述", data=None)
  try:
    return ResponseModel(data=run_instruction(
      params.instruction,
      paths=params.paths,
      dry_run=params.dry_run,
      plan=params.plan,
    ))
  except Exception as exc:
    return ResponseModel(code=201, msg=str(exc), data=None)


@router.post("/map-legend")
async def map_legend_recognize(
  file: UploadFile = File(...),
  gcps: str = Form("[]"),
  instruction: str = Form(""),
  legend_box: str = Form(""),
):
  import json
  import uuid
  from pathlib import Path

  from base import get_writable_dir

  raw_gcps = gcps or "[]"
  try:
    parsed = json.loads(raw_gcps)
  except json.JSONDecodeError:
    return ResponseModel(code=201, msg="控制点格式不正确", data=None)
  if not isinstance(parsed, list) or len(parsed) < 2:
    return ResponseModel(code=201, msg="请至少在图上标注 2 个控制点并填写经纬度", data=None)
  user_legend = None
  if (legend_box or "").strip():
    try:
      user_legend = json.loads(legend_box)
    except json.JSONDecodeError:
      return ResponseModel(code=201, msg="图例范围格式不正确", data=None)
  suffix = Path(file.filename or "map.jpg").suffix.lower()
  if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}:
    suffix = ".jpg"
  dest_dir = Path(get_writable_dir()) / "data" / "map-legend"
  dest_dir.mkdir(parents=True, exist_ok=True)
  dest = dest_dir / f"{uuid.uuid4().hex}{suffix}"
  dest.write_bytes(await file.read())
  try:
    data = await asyncio.to_thread(
      recognize_map, str(dest), parsed, instruction, user_legend
    )
  except Exception as exc:
    return ResponseModel(code=201, msg=str(exc), data=None)
  data["image_path"] = str(dest)
  geo_path = dest.with_suffix(".geojson")
  geo_path.write_text(json.dumps(data.get("geojson") or {}, ensure_ascii=False, indent=2), encoding="utf-8")
  data["geojson_path"] = str(geo_path)
  return ResponseModel(data=data)


@router.post("/georef-auto")
async def georef_auto(
  file: UploadFile = File(...),
  canvas: UploadFile = File(...),
  west: float = Form(...),
  south: float = Form(...),
  east: float = Form(...),
  north: float = Form(...),
  use_ai: str = Form("0"),
):
  import uuid
  from pathlib import Path

  from base import get_writable_dir
  from llm.georef_match import register_photo_to_canvas

  dest_dir = Path(get_writable_dir()) / "data" / "georef"
  dest_dir.mkdir(parents=True, exist_ok=True)
  photo_suffix = Path(file.filename or "map.jpg").suffix.lower() or ".jpg"
  canvas_suffix = Path(canvas.filename or "canvas.png").suffix.lower() or ".png"
  if photo_suffix not in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}:
    photo_suffix = ".jpg"
  if canvas_suffix not in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
    canvas_suffix = ".png"
  photo_path = dest_dir / f"{uuid.uuid4().hex}{photo_suffix}"
  canvas_path = dest_dir / f"{uuid.uuid4().hex}{canvas_suffix}"
  photo_path.write_bytes(await file.read())
  canvas_path.write_bytes(await canvas.read())
  try:
    data = await asyncio.to_thread(
      register_photo_to_canvas,
      photo_path,
      canvas_path,
      west,
      south,
      east,
      north,
      str(use_ai).strip() in {"1", "true", "True", "yes"},
    )
  except Exception as exc:
    return ResponseModel(code=201, msg=str(exc), data=None)
  return ResponseModel(data=data)


@router.get("/train-legend/dataset")
def train_legend_dataset():
  return ResponseModel(data=dataset_info())


@router.get("/train-legend/samples")
def train_legend_list(status: str | None = None):
  return ResponseModel(data=list_samples(status))


@router.post("/train-legend/samples")
async def train_legend_import(
  files: list[UploadFile] | None = File(None),
  file: UploadFile | None = File(None),
  legend: str = Form("[]"),
  legend_box: str = Form(""),
  features: str = Form("[]"),
  instruction: str = Form(""),
  status: str = Form("draft"),
  source: str = Form("human"),
  notes: str = Form(""),
):
  import json

  uploads = list(files or [])
  if file is not None:
    uploads.append(file)
  if not uploads:
    return ResponseModel(code=201, msg="请选择图片", data=None)
  parsed_legend = []
  parsed_box = None
  parsed_features = []
  if (legend or "").strip():
    try:
      loaded = json.loads(legend)
      parsed_legend = loaded if isinstance(loaded, list) else []
    except json.JSONDecodeError:
      return ResponseModel(code=201, msg="图例格式不正确", data=None)
  if (legend_box or "").strip():
    try:
      parsed_box = json.loads(legend_box)
    except json.JSONDecodeError:
      return ResponseModel(code=201, msg="图例范围格式不正确", data=None)
  if (features or "").strip():
    try:
      loaded_feats = json.loads(features)
      parsed_features = loaded_feats if isinstance(loaded_feats, list) else []
    except json.JSONDecodeError:
      return ResponseModel(code=201, msg="图上标注格式不正确", data=None)
  created = []
  try:
    for upload in uploads:
      created.append(add_sample(
        await upload.read(),
        filename=upload.filename or "map.jpg",
        legend=parsed_legend if len(uploads) == 1 else None,
        legend_box=parsed_box if len(uploads) == 1 else None,
        features=parsed_features if len(uploads) == 1 else None,
        instruction=instruction,
        status=status,
        source=source,
        notes=notes,
      ))
  except Exception as exc:
    return ResponseModel(code=201, msg=str(exc), data=None)
  return ResponseModel(msg=f"已导入 {len(created)} 张", data=created)


@router.get("/train-legend/samples/{sample_id}")
def train_legend_get(sample_id: str):
  try:
    return ResponseModel(data=get_sample(sample_id))
  except FileNotFoundError as exc:
    return ResponseModel(code=201, msg=str(exc), data=None)


@router.get("/train-legend/samples/{sample_id}/image")
def train_legend_image(sample_id: str):
  try:
    path = sample_image_path(sample_id)
  except FileNotFoundError:
    raise HTTPException(status_code=404, detail="样本图片不存在")
  return FileResponse(path)


@router.post("/train-legend/samples/{sample_id}")
def train_legend_save(sample_id: str, params: TrainSampleBody):
  try:
    return ResponseModel(msg="已保存", data=save_sample(sample_id, params.model_dump(exclude_none=True)))
  except Exception as exc:
    return ResponseModel(code=201, msg=str(exc), data=None)


@router.post("/train-legend/samples/{sample_id}/prelabel")
async def train_legend_prelabel(sample_id: str, params: TrainPrelabelBody | None = None):
  instruction = params.instruction if params else None
  try:
    data = await asyncio.to_thread(prelabel_sample, sample_id, instruction)
    return ResponseModel(msg="预标注完成", data=data)
  except Exception as exc:
    return ResponseModel(code=201, msg=str(exc), data=None)


@router.delete("/train-legend/samples/{sample_id}")
def train_legend_delete(sample_id: str):
  delete_sample(sample_id)
  return ResponseModel(msg="已删除", data=None)


@router.post("/train-legend/export")
def train_legend_export(params: TrainExportBody | None = None):
  try:
    data = export_dataset(params.statuses if params else None)
    return ResponseModel(msg=f"已导出 {data['count']} 条", data=data)
  except Exception as exc:
    return ResponseModel(code=201, msg=str(exc), data=None)


@router.post("/train-legend/runs")
def train_legend_add_run(params: TrainRunBody):
  return ResponseModel(msg="训练记录已保存", data=add_run(params.model_dump()))


@router.get("/train-legend/synth-config")
def train_legend_get_synth_config():
  return ResponseModel(data=load_synth_config())


@router.post("/train-legend/synth-config")
def train_legend_save_synth_config(params: TrainSynthConfigBody):
  return ResponseModel(msg="配置已保存", data=save_synth_config(params.model_dump()))


@router.get("/proxy")
def proxy_url(url: str = Query(..., min_length=8)):
  from urllib.error import HTTPError, URLError
  from urllib.parse import urlparse
  from urllib.request import Request, urlopen

  parsed = urlparse(url)
  if parsed.scheme not in {"http", "https"}:
    raise HTTPException(status_code=400, detail="只允许 http/https")
  headers = {
    "User-Agent": "Mozilla/5.0 MapToolLegendSynth/1.0",
    "Accept": "*/*",
    "Referer": f"{parsed.scheme}://{parsed.netloc}/",
  }
  req = Request(url, headers=headers)
  try:
    with urlopen(req, timeout=25) as resp:
      data = resp.read()
      content_type = resp.headers.get("Content-Type") or "application/octet-stream"
  except HTTPError as exc:
    raise HTTPException(status_code=502, detail=f"底图资源 HTTP {exc.code}：{url}") from exc
  except URLError as exc:
    raise HTTPException(status_code=502, detail=f"底图资源读取失败：{exc.reason}") from exc
  except Exception as exc:
    raise HTTPException(status_code=502, detail=f"底图资源读取失败：{exc}") from exc
  return Response(
    content=data,
    media_type=content_type.split(";")[0].strip() or "application/octet-stream",
    headers={"Cache-Control": "public, max-age=3600"},
  )

