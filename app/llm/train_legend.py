from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from base import get_writable_dir
from llm.map_legend import LEGEND_SYSTEM, legend_user_prompt, read_legend

STATUSES = ("draft", "review", "accepted", "rejected")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def _now() -> str:
  return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def dataset_root() -> Path:
  root = Path(get_writable_dir()) / "data" / "train-legend"
  for name in ("images", "labels", "exports", "runs"):
    (root / name).mkdir(parents=True, exist_ok=True)
  meta = root / "dataset.json"
  if not meta.exists():
    _write_json(meta, {
      "name": "图例训练样本",
      "task": "map-legend",
      "created_at": _now(),
      "updated_at": _now(),
    })
  return root


def _write_json(path: Path, data) -> None:
  path.parent.mkdir(parents=True, exist_ok=True)
  tmp = path.with_suffix(path.suffix + ".tmp")
  tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
  tmp.replace(path)


def _read_json(path: Path):
  return json.loads(path.read_text(encoding="utf-8"))


def _touch_dataset() -> None:
  root = dataset_root()
  meta_path = root / "dataset.json"
  meta = _read_json(meta_path) if meta_path.exists() else {"name": "图例训练样本", "task": "map-legend"}
  meta["updated_at"] = _now()
  _write_json(meta_path, meta)


def _find_image(sample_id: str) -> Path | None:
  images = dataset_root() / "images"
  matches = sorted(images.glob(f"{sample_id}.*"))
  return matches[0] if matches else None


def _label_path(sample_id: str) -> Path:
  return dataset_root() / "labels" / f"{sample_id}.json"


def _clean_legend(raw) -> list[dict]:
  items = []
  if not isinstance(raw, list):
    return items
  for row in raw:
    if not isinstance(row, dict):
      continue
    name = str(row.get("name") or "").strip()
    if not name:
      continue
    from llm.map_legend import _normalize_color, _shape_of
    shape = _shape_of(row.get("shape"), name)
    color = _normalize_color(row.get("color") or "")
    items.append({
      "name": name,
      "description": str(row.get("description") or "").strip(),
      "color": color,
      "shape": shape,
    })
  return items


def _clean_features(raw) -> list[dict]:
  items = []
  if not isinstance(raw, list):
    return items
  for row in raw:
    if not isinstance(row, dict):
      continue
    try:
      x = float(row.get("x"))
      y = float(row.get("y"))
    except (TypeError, ValueError):
      continue
    name = str(row.get("name") or "").strip()
    if not name:
      continue
    shape = str(row.get("shape") or "point").strip().lower() or "point"
    if shape not in {"point", "polygon", "line"}:
      shape = "point"
    item = {
      "name": name,
      "shape": shape,
      "color": str(row.get("color") or "").strip(),
      "x": round(x, 2),
      "y": round(y, 2),
    }
    for key in ("w", "h"):
      try:
        value = float(row.get(key))
      except (TypeError, ValueError):
        continue
      if value > 0:
        item[key] = round(value, 2)
    items.append(item)
  return items


def _pack_sample(sample_id: str, label: dict, image: Path | None) -> dict:
  return {
    "id": sample_id,
    "filename": label.get("filename") or (image.name if image else ""),
    "status": label.get("status") or "draft",
    "source": label.get("source") or "human",
    "instruction": label.get("instruction") or "",
    "legend": label.get("legend") or [],
    "legend_box": label.get("legend_box"),
    "features": label.get("features") or [],
    "width": label.get("width"),
    "height": label.get("height"),
    "notes": label.get("notes") or "",
    "created_at": label.get("created_at"),
    "updated_at": label.get("updated_at"),
    "has_image": bool(image and image.is_file()),
  }


def _counts() -> dict[str, int]:
  counts = {key: 0 for key in STATUSES}
  counts["total"] = 0
  labels = dataset_root() / "labels"
  for path in labels.glob("*.json"):
    try:
      status = str((_read_json(path) or {}).get("status") or "draft")
    except Exception:
      status = "draft"
    if status not in counts:
      status = "draft"
    counts[status] += 1
    counts["total"] += 1
  return counts


def dataset_info() -> dict:
  root = dataset_root()
  meta = _read_json(root / "dataset.json")
  runs = []
  for path in sorted((root / "runs").glob("*.json"), reverse=True):
    try:
      item = _read_json(path)
    except Exception:
      continue
    item["id"] = path.stem
    runs.append(item)
  exports = []
  for path in sorted((root / "exports").glob("*"), reverse=True):
    if path.suffix.lower() in {".jsonl", ".json"} and path.is_file():
      exports.append({"name": path.name, "path": str(path), "size": path.stat().st_size})
  return {
    **meta,
    "root": str(root),
    "counts": _counts(),
    "runs": runs,
    "exports": exports,
  }


def list_samples(status: str | None = None) -> list[dict]:
  root = dataset_root()
  wanted = (status or "").strip()
  items = []
  for path in sorted((root / "labels").glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
    sample_id = path.stem
    try:
      label = _read_json(path)
    except Exception:
      continue
    if wanted and wanted != "all" and str(label.get("status") or "draft") != wanted:
      continue
    items.append(_pack_sample(sample_id, label, _find_image(sample_id)))
  return items


def get_sample(sample_id: str) -> dict:
  path = _label_path(sample_id)
  if not path.is_file():
    raise FileNotFoundError("样本不存在")
  label = _read_json(path)
  packed = _pack_sample(sample_id, label, _find_image(sample_id))
  packed["image_url"] = f"/api/llm/train-legend/samples/{sample_id}/image"
  return packed


def sample_image_path(sample_id: str) -> Path:
  image = _find_image(sample_id)
  if not image or not image.is_file():
    raise FileNotFoundError("样本图片不存在")
  return image


def _suffix_of(name: str) -> str:
  suffix = Path(name or "map.jpg").suffix.lower()
  if suffix not in IMAGE_SUFFIXES:
    return ".jpg"
  return suffix


def add_sample(
  raw: bytes,
  filename: str = "map.jpg",
  legend=None,
  legend_box=None,
  instruction: str = "",
  status: str = "draft",
  source: str = "human",
  notes: str = "",
  width=None,
  height=None,
  features=None,
) -> dict:
  if not raw:
    raise ValueError("图片为空")
  root = dataset_root()
  sample_id = uuid.uuid4().hex
  dest = root / "images" / f"{sample_id}{_suffix_of(filename)}"
  dest.write_bytes(raw)
  if width is None or height is None:
    from PIL import Image
    with Image.open(dest) as im:
      width, height = im.size
  now = _now()
  state = status if status in STATUSES else "draft"
  if legend:
    if state == "draft":
      state = "review"
  label = {
    "filename": Path(filename or dest.name).name,
    "status": state,
    "source": source or "human",
    "instruction": instruction or "",
    "legend": _clean_legend(legend),
    "legend_box": legend_box if isinstance(legend_box, dict) else None,
    "features": _clean_features(features),
    "width": width,
    "height": height,
    "notes": notes or "",
    "created_at": now,
    "updated_at": now,
  }
  _write_json(_label_path(sample_id), label)
  _touch_dataset()
  return get_sample(sample_id)


def save_sample(sample_id: str, payload: dict) -> dict:
  path = _label_path(sample_id)
  if not path.is_file():
    raise FileNotFoundError("样本不存在")
  label = _read_json(path)
  if "legend" in payload:
    label["legend"] = _clean_legend(payload.get("legend"))
  if "legend_box" in payload:
    box = payload.get("legend_box")
    label["legend_box"] = box if isinstance(box, dict) else None
  if "features" in payload:
    label["features"] = _clean_features(payload.get("features"))
  if "instruction" in payload:
    label["instruction"] = str(payload.get("instruction") or "")
  if "notes" in payload:
    label["notes"] = str(payload.get("notes") or "")
  if "source" in payload and payload.get("source"):
    label["source"] = str(payload.get("source"))
  status = str(payload.get("status") or "").strip()
  if status:
    if status not in STATUSES:
      raise ValueError("状态只能是 draft / review / accepted / rejected")
    label["status"] = status
  label["updated_at"] = _now()
  _write_json(path, label)
  _touch_dataset()
  return get_sample(sample_id)


def delete_sample(sample_id: str) -> None:
  path = _label_path(sample_id)
  if path.is_file():
    path.unlink()
  image = _find_image(sample_id)
  if image and image.is_file():
    image.unlink()
  _touch_dataset()


def prelabel_sample(sample_id: str, instruction: str | None = None) -> dict:
  image = sample_image_path(sample_id)
  path = _label_path(sample_id)
  label = _read_json(path)
  hint = instruction if instruction is not None else (label.get("instruction") or "")
  result = read_legend(str(image), hint, label.get("legend_box"))
  label["legend"] = _clean_legend(result.get("legend"))
  if result.get("legend_box"):
    label["legend_box"] = result.get("legend_box")
  label["width"] = result.get("width") or label.get("width")
  label["height"] = result.get("height") or label.get("height")
  label["notes"] = result.get("notes") or ""
  label["source"] = "model"
  label["instruction"] = hint
  if label.get("status") == "draft":
    label["status"] = "review"
  label["updated_at"] = _now()
  _write_json(path, label)
  _touch_dataset()
  data = get_sample(sample_id)
  data["used_vision"] = result.get("used_vision")
  return data


def export_dataset(statuses: list[str] | None = None) -> dict:
  root = dataset_root()
  allow = [item for item in (statuses or ["accepted"]) if item in STATUSES] or ["accepted"]
  stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
  export_dir = root / "exports" / stamp
  export_dir.mkdir(parents=True, exist_ok=True)
  images_dir = export_dir / "images"
  images_dir.mkdir(parents=True, exist_ok=True)
  jsonl_path = export_dir / "train.jsonl"
  rows = []
  for item in list_samples():
    if item.get("status") not in allow:
      continue
    image = _find_image(item["id"])
    if not image:
      continue
    rel = f"images/{item['id']}{image.suffix.lower()}"
    shutil.copy2(image, export_dir / rel)
    output = {
      "legend": item.get("legend") or [],
      "legend_box": item.get("legend_box"),
      "features": item.get("features") or [],
      "notes": "",
    }
    width = int(item.get("width") or 0)
    height = int(item.get("height") or 0)
    row = {
      "id": item["id"],
      "image": rel,
      "system": LEGEND_SYSTEM.strip(),
      "prompt": legend_user_prompt(width, height, item.get("instruction") or "", item.get("legend_box")),
      "output": output,
      "output_text": json.dumps(output, ensure_ascii=False),
    }
    rows.append(row)
  with jsonl_path.open("w", encoding="utf-8") as handle:
    for row in rows:
      handle.write(json.dumps(row, ensure_ascii=False) + "\n")
  manifest = {
    "created_at": _now(),
    "count": len(rows),
    "statuses": allow,
    "jsonl": str(jsonl_path),
  }
  _write_json(export_dir / "manifest.json", manifest)
  _touch_dataset()
  return {
    "path": str(export_dir),
    "jsonl": str(jsonl_path),
    "count": len(rows),
    "statuses": allow,
  }


def add_run(payload: dict) -> dict:
  root = dataset_root()
  run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
  record = {
    "export_path": str(payload.get("export_path") or ""),
    "base_model": str(payload.get("base_model") or ""),
    "output_path": str(payload.get("output_path") or ""),
    "sample_count": payload.get("sample_count"),
    "notes": str(payload.get("notes") or ""),
    "created_at": _now(),
  }
  _write_json(root / "runs" / f"{run_id}.json", record)
  _touch_dataset()
  record["id"] = run_id
  return record


def _synth_config_path() -> Path:
  return dataset_root() / "synth-config.json"


def load_synth_config() -> dict:
  path = _synth_config_path()
  if not path.is_file():
    return {}
  try:
    data = _read_json(path)
  except Exception:
    return {}
  return data if isinstance(data, dict) else {}


def save_synth_config(payload: dict) -> dict:
  catalog = []
  for row in payload.get("catalog") or []:
    if not isinstance(row, dict):
      continue
    catalog.append({
      "name": str(row.get("name") or ""),
      "shape": str(row.get("shape") or "point"),
      "color": str(row.get("color") or ""),
      "description": str(row.get("description") or ""),
    })
  data = {
    "basemapText": str(payload.get("basemapText") or ""),
    "nwLng": str(payload.get("nwLng") or ""),
    "nwLat": str(payload.get("nwLat") or ""),
    "seLng": str(payload.get("seLng") or ""),
    "seLat": str(payload.get("seLat") or ""),
    "imageCount": payload.get("imageCount"),
    "mapWidth": payload.get("mapWidth"),
    "mapHeight": payload.get("mapHeight"),
    "minZoom": payload.get("minZoom"),
    "maxZoom": payload.get("maxZoom"),
    "minFeatures": payload.get("minFeatures"),
    "maxFeatures": payload.get("maxFeatures"),
    "minLegend": payload.get("minLegend"),
    "catalog": catalog,
    "updated_at": _now(),
  }
  _write_json(_synth_config_path(), data)
  return data
