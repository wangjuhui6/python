import json
import os
from pathlib import Path

from base import get_writable_dir

CONFIG_DIR = Path(get_writable_dir()) / "config"
CONFIG_PATH = CONFIG_DIR / "llm.json"

DEFAULT_CONFIG = {
  "model_dir": "",
  "model_path": "",
  "n_ctx": 2048,
  "n_threads": max(1, os.cpu_count() or 4),
  "n_gpu_layers": 0,
  "autoload": False,
  "skip_llm_for_script": False,
  "max_tokens": 512,
}


def load_config() -> dict:
  data = dict(DEFAULT_CONFIG)
  if CONFIG_PATH.exists():
    try:
      saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
      if isinstance(saved, dict):
        data.update({k: saved[k] for k in DEFAULT_CONFIG if k in saved})
    except (OSError, json.JSONDecodeError):
      pass
  return data


def save_config(updates: dict) -> dict:
  data = load_config()
  for key in DEFAULT_CONFIG:
    if key in updates and updates[key] is not None:
      data[key] = updates[key]
  CONFIG_DIR.mkdir(parents=True, exist_ok=True)
  CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
  return data
