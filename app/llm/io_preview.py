from __future__ import annotations

import json
import re
from pathlib import Path

TABLE_SUFFIXES = {".csv", ".xlsx", ".xls", ".json"}
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".ico"}
GIS_SUFFIXES = {".shp", ".geojson", ".gpkg", ".mbtiles", ".kml", ".kmz", ".gml", ".tif", ".tiff"}
DOC_SUFFIXES = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt", ".md"}
MAX_SAMPLE_ROWS = 8
MAX_FILES = 200


def file_kind(suffix: str) -> str:
  ext = (suffix or "").lower()
  if ext in TABLE_SUFFIXES:
    return "table"
  if ext in GIS_SUFFIXES:
    return "gis"
  if ext in IMAGE_SUFFIXES:
    return "image"
  if ext in DOC_SUFFIXES:
    return "doc"
  return "other"


def _file_item(path: Path, rel: str | None = None) -> dict:
  suffix = path.suffix.lower()
  return {
    "name": path.name,
    "rel": rel or path.name,
    "path": str(path.resolve()),
    "suffix": suffix,
    "kind": file_kind(suffix),
    "size_mb": round(path.stat().st_size / (1024 * 1024), 2),
    "is_table": suffix in TABLE_SUFFIXES,
  }


def peek(path: str) -> dict:
  p = Path(path)
  if not p.exists():
    raise FileNotFoundError(f"路径不存在: {path}")
  if p.is_dir():
    return _peek_folder(p)
  if p.suffix.lower() in TABLE_SUFFIXES:
    return _peek_table(p)
  if p.suffix.lower() in {".md", ".markdown"}:
    from llm.mapping import parse_mapping
    parsed = parse_mapping(p)
    return {
      "kind": "mapping",
      "path": parsed["path"],
      "name": parsed["name"],
      "columns": parsed["columns"],
      "row_count": parsed["row_count"],
      "sample_rows": parsed["sample"],
      "files": [_file_item(p)],
      "file_count": 1,
    }
  return {
    "kind": "file",
    "path": str(p.resolve()),
    "name": p.name,
    "suffix": p.suffix.lower(),
    "size_mb": round(p.stat().st_size / (1024 * 1024), 2),
    "is_table": False,
    "kind": file_kind(p.suffix.lower()),
    "files": [_file_item(p)],
    "file_count": 1,
  }


def _peek_table(path: Path) -> dict:
  import pandas as pd

  df, extra = _read_table(path)
  columns = [str(c) for c in df.columns.tolist()]
  sample = json.loads(df.head(MAX_SAMPLE_ROWS).fillna("").astype(str).to_json(orient="records", force_ascii=False))
  return {
    "kind": "table",
    "path": str(path.resolve()),
    "name": path.name,
    "row_count": int(len(df)),
    "columns": columns,
    "sample_rows": sample,
    "files": [_file_item(path)],
    "file_count": 1,
    **extra,
  }


def _peek_folder(path: Path) -> dict:
  files = []
  truncated = False
  for item in sorted(path.rglob("*")):
    if not item.is_file():
      continue
    rel = item.relative_to(path)
    files.append(_file_item(item, rel.as_posix()))
    if len(files) >= MAX_FILES:
      truncated = True
      break
  table_files = [f for f in files if f["is_table"]]
  preview = None
  if table_files:
    try:
      preview = _peek_table(Path(table_files[0]["path"]))
    except Exception:
      preview = None
  suffixes = sorted({f["suffix"] or "(无扩展名)" for f in files})
  kind_count = {}
  for f in files:
    kind_count[f["kind"]] = kind_count.get(f["kind"], 0) + 1
  return {
    "kind": "folder",
    "path": str(path.resolve()),
    "name": path.name,
    "file_count": len(files),
    "truncated": truncated,
    "suffixes": suffixes,
    "kind_count": kind_count,
    "files": files,
    "table_file_count": len(table_files),
    "first_table": preview,
  }


def _read_table(path: Path):
  import pandas as pd

  suffix = path.suffix.lower()
  extra = {"sheet": None, "sheets": []}
  if suffix == ".csv":
    df = pd.read_csv(path)
  elif suffix in {".xlsx", ".xls"}:
    xl = pd.ExcelFile(path)
    extra["sheets"] = xl.sheet_names
    extra["sheet"] = xl.sheet_names[0] if xl.sheet_names else None
    df = pd.read_excel(path, sheet_name=extra["sheet"])
  elif suffix == ".json":
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "features" in data:
      rows = [f.get("properties") or {} for f in data.get("features") or []]
      df = pd.DataFrame(rows)
      extra["geojson"] = True
    elif isinstance(data, list):
      df = pd.DataFrame(data)
    else:
      df = pd.json_normalize(data)
  else:
    raise ValueError(f"不支持的表格格式: {suffix}")
  return df, extra


def write_table(df, save_path: str, output_format: str | None = None):
  import pandas as pd

  dest = Path(save_path)
  dest.parent.mkdir(parents=True, exist_ok=True)
  fmt = (output_format or dest.suffix.lstrip(".") or "xlsx").lower()
  if fmt in {"xlsx", "xls"}:
    if dest.suffix.lower() not in {".xlsx", ".xls"}:
      dest = dest.with_suffix(".xlsx")
    df.to_excel(dest, index=False)
  elif fmt == "csv":
    if dest.suffix.lower() != ".csv":
      dest = dest.with_suffix(".csv")
    df.to_csv(dest, index=False, encoding="utf-8-sig")
  elif fmt == "json":
    if dest.suffix.lower() != ".json":
      dest = dest.with_suffix(".json")
    dest.write_text(df.fillna("").to_json(orient="records", force_ascii=False, indent=2), encoding="utf-8")
  else:
    raise ValueError(f"不支持的输出格式: {fmt}")
  return str(dest.resolve())


def extract_json(text: str) -> dict:
  raw = (text or "").strip()
  raw = re.sub(r"^```(?:json)?\s*", "", raw)
  raw = re.sub(r"\s*```$", "", raw)
  start = raw.find("{")
  end = raw.rfind("}")
  if start < 0 or end <= start:
    raise ValueError("模型没有返回 JSON 方案")
  return json.loads(raw[start:end + 1])
