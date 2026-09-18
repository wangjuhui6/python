from __future__ import annotations

import threading
from pathlib import Path

from .config import CONFIG_PATH, load_config, save_config

_lock = threading.Lock()
_llm = None
_loaded_path = ""
_loaded_mmproj = ""
_last_error = ""


def _file_size_mb(path: Path) -> float:
  try:
    return round(path.stat().st_size / (1024 * 1024), 1)
  except OSError:
    return 0.0


def _is_mmproj(path: str | Path) -> bool:
  name = Path(path).name.lower()
  return "mmproj" in name or name.startswith("mmproj")


def _looks_like_vision_model(path: str | Path) -> bool:
  name = Path(path).name.lower()
  return any(token in name for token in ("vl", "llava", "vision", "minicpm-v"))


def find_mmproj(model_path: str, explicit: str | None = None) -> str:
  if explicit:
    p = Path(explicit)
    if p.is_file():
      return str(p.resolve())
  folder = Path(model_path).parent
  if not folder.is_dir():
    return ""
  matches = [p for p in sorted(folder.glob("*.gguf")) if p.is_file() and _is_mmproj(p)]
  return str(matches[0].resolve()) if matches else ""


def list_models(model_dir: str | None = None) -> list[dict]:
  cfg = load_config()
  directory = Path(model_dir or cfg.get("model_dir") or "")
  if not directory.is_dir():
    return []
  items = []
  for path in sorted(directory.rglob("*.gguf")):
    if path.is_file():
      projector = _is_mmproj(path)
      items.append({
        "name": path.name,
        "path": str(path.resolve()),
        "size_mb": _file_size_mb(path),
        "kind": "mmproj" if projector else "language",
        "vision": _looks_like_vision_model(path) and not projector,
      })
  return items


def runtime_status() -> dict:
  cfg = load_config()
  path = cfg.get("model_path") or ""
  mmproj = cfg.get("mmproj_path") or ""
  p = Path(path) if path else None
  m = Path(mmproj) if mmproj else None
  return {
    **cfg,
    "config_path": str(CONFIG_PATH),
    "loaded": _llm is not None,
    "loaded_path": _loaded_path,
    "loaded_mmproj": _loaded_mmproj,
    "vision_enabled": bool(_llm is not None and _loaded_mmproj),
    "model_exists": bool(p and p.is_file()),
    "mmproj_exists": bool(m and m.is_file()),
    "last_error": _last_error,
    "runtime_available": _llama_available()[0],
    "runtime_message": _llama_available()[1],
  }


def _llama_available() -> tuple[bool, str]:
  try:
    import llama_cpp  # noqa: F401
    return True, "llama-cpp-python 已安装"
  except ImportError:
    return False, "未安装 llama-cpp-python，请执行 pip install llama-cpp-python"


def unload() -> None:
  global _llm, _loaded_path, _loaded_mmproj
  with _lock:
    _llm = None
    _loaded_path = ""
    _loaded_mmproj = ""


def load(model_path: str | None = None, mmproj_path: str | None = None, persist: bool = True) -> dict:
  global _llm, _loaded_path, _loaded_mmproj, _last_error
  ok, msg = _llama_available()
  if not ok:
    _last_error = msg
    raise RuntimeError(msg)

  from llama_cpp import Llama

  cfg = load_config()
  path = model_path or cfg.get("model_path") or ""
  p = Path(path)
  if not p.is_file():
    _last_error = f"模型文件不存在: {path}"
    raise FileNotFoundError(_last_error)
  if p.suffix.lower() != ".gguf":
    _last_error = "仅支持 .gguf 模型文件"
    raise ValueError(_last_error)
  if _is_mmproj(p):
    _last_error = "当前选的是 mmproj 投影文件，请把它填到「视觉投影」，语言模型请选 Qwen2.5-VL 的主 GGUF"
    raise ValueError(_last_error)

  explicit = mmproj_path if mmproj_path is not None else (cfg.get("mmproj_path") or "")
  if explicit or _looks_like_vision_model(p):
    chosen_mmproj = find_mmproj(str(p), explicit)
  else:
    chosen_mmproj = ""
  if chosen_mmproj and not Path(chosen_mmproj).is_file():
    _last_error = f"视觉投影文件不存在: {chosen_mmproj}"
    raise FileNotFoundError(_last_error)
  if chosen_mmproj and not _looks_like_vision_model(p):
    chosen_mmproj = ""
  if _looks_like_vision_model(p) and not chosen_mmproj:
    _last_error = "这是视觉模型，需要同时指定同目录下的 mmproj-model-f16.gguf"
    raise ValueError(_last_error)

  chat_handler = None
  if chosen_mmproj:
    from llama_cpp.llama_chat_format import Qwen25VLChatHandler
    chat_handler = Qwen25VLChatHandler(clip_model_path=chosen_mmproj, verbose=False)

  kwargs = {
    "model_path": str(p.resolve()),
    "n_ctx": int(cfg.get("n_ctx") or 2048),
    "n_threads": int(cfg.get("n_threads") or 4),
    "n_gpu_layers": int(cfg.get("n_gpu_layers") or 0),
    "n_batch": int(cfg.get("n_batch") or 256),
    "verbose": False,
  }
  if chat_handler is not None:
    kwargs["chat_handler"] = chat_handler

  with _lock:
    _llm = Llama(**kwargs)
    _loaded_path = str(p.resolve())
    _loaded_mmproj = chosen_mmproj
    _last_error = ""

  if persist:
    save_config({
      "model_path": _loaded_path,
      "mmproj_path": _loaded_mmproj,
      "model_dir": str(p.parent),
    })
  return runtime_status()


def chat(messages: list[dict], temperature: float = 0.2, json_mode: bool = False, max_tokens: int | None = None) -> str:
  global _last_error
  if _llm is None:
    load()
  cfg = load_config()
  kwargs = {
    "messages": messages,
    "temperature": temperature,
    "max_tokens": int(max_tokens or cfg.get("max_tokens") or 512),
  }
  if json_mode:
    kwargs["response_format"] = {"type": "json_object"}
  with _lock:
    if _llm is None:
      raise RuntimeError("模型未加载")
    try:
      resp = _llm.create_chat_completion(**kwargs)
    except Exception:
      if json_mode:
        kwargs.pop("response_format", None)
        resp = _llm.create_chat_completion(**kwargs)
      else:
        raise
  try:
    return resp["choices"][0]["message"]["content"]
  except (KeyError, IndexError, TypeError) as exc:
    _last_error = str(exc)
    raise RuntimeError("模型返回格式异常") from exc
