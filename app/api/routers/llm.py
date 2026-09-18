from fastapi import APIRouter
from pydantic import BaseModel

from llm.config import CONFIG_PATH, load_config, save_config
from llm.engine import chat, list_models, load, runtime_status, unload
from llm.io_preview import peek
from llm.transform import apply_plan, make_plan, run_instruction
from utils.response import ResponseModel

router = APIRouter(prefix="/llm", tags=["LLM"])


class ConfigBody(BaseModel):
  model_dir: str | None = None
  model_path: str | None = None
  n_ctx: int | None = None
  n_threads: int | None = None
  n_gpu_layers: int | None = None
  autoload: bool | None = None
  skip_llm_for_script: bool | None = None
  max_tokens: int | None = None


class LoadBody(BaseModel):
  model_path: str | None = None


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
    data = load(params.model_path)
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
