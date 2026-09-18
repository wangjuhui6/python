from __future__ import annotations

import json
import re
from pathlib import Path

MAPPING_SUFFIXES = {".md", ".markdown", ".csv", ".xlsx", ".xls", ".json", ".tsv"}


def find_mapping_file(folder: str | Path) -> str:
  root = Path(folder)
  if not root.is_dir():
    return ""
  preferred = []
  others = []
  for path in sorted(root.rglob("*")):
    if not path.is_file() or path.suffix.lower() not in MAPPING_SUFFIXES:
      continue
    name = path.name.lower()
    if any(token in name for token in ("iso", "map", "dict", "对照", "编码", "code", "name")):
      preferred.append(path)
    else:
      others.append(path)
  chosen = (preferred or others)
  return str(chosen[0].resolve()) if chosen else ""


def parse_mapping(path: str | Path) -> dict:
  p = Path(path)
  if not p.is_file():
    raise FileNotFoundError(f"对照文件不存在: {path}")
  suffix = p.suffix.lower()
  if suffix in {".md", ".markdown"}:
    columns, records = _parse_markdown(p.read_text(encoding="utf-8", errors="replace"))
  elif suffix == ".csv":
    columns, records = _parse_csv(p)
  elif suffix == ".tsv":
    columns, records = _parse_csv(p, sep="\t")
  elif suffix in {".xlsx", ".xls"}:
    columns, records = _parse_excel(p)
  elif suffix == ".json":
    columns, records = _parse_json(p)
  else:
    raise ValueError(f"不支持的对照文件: {suffix}")
  return {
    "path": str(p.resolve()),
    "name": p.name,
    "columns": columns,
    "records": records,
    "row_count": len(records),
    "sample": records[:12],
  }


def _parse_csv(path: Path, sep: str = ","):
  import pandas as pd
  df = pd.read_csv(path, sep=sep, dtype=str).fillna("")
  columns = [str(c).strip() for c in df.columns.tolist()]
  records = df.to_dict(orient="records")
  return columns, [{str(k): str(v).strip() for k, v in row.items()} for row in records]


def _parse_excel(path: Path):
  import pandas as pd
  df = pd.read_excel(path, dtype=str).fillna("")
  columns = [str(c).strip() for c in df.columns.tolist()]
  records = df.to_dict(orient="records")
  return columns, [{str(k): str(v).strip() for k, v in row.items()} for row in records]


def _parse_json(path: Path):
  data = json.loads(path.read_text(encoding="utf-8"))
  if isinstance(data, dict):
    if all(not isinstance(v, (dict, list)) for v in data.values()):
      records = [{"key": str(k), "value": str(v)} for k, v in data.items()]
      return ["key", "value"], records
    for key in ("items", "data", "records", "rows"):
      if isinstance(data.get(key), list):
        data = data[key]
        break
    else:
      data = [data]
  if not isinstance(data, list) or not data:
    return [], []
  if all(not isinstance(x, dict) for x in data):
    return ["value"], [{"value": str(x)} for x in data]
  columns = []
  records = []
  for row in data:
    if not isinstance(row, dict):
      continue
    item = {str(k): "" if v is None else str(v).strip() for k, v in row.items()}
    for key in item:
      if key not in columns:
        columns.append(key)
    records.append(item)
  return columns, records


def _split_md_row(line: str) -> list[str]:
  text = line.strip().strip("|")
  return [part.strip() for part in text.split("|")]


def _parse_markdown(text: str):
  columns = []
  records = []
  lines = text.splitlines()
  i = 0
  while i < len(lines):
    line = lines[i]
    nxt = lines[i + 1] if i + 1 < len(lines) else ""
    if "|" in line and re.match(r"^\s*\|?\s*:?-{2,}", nxt):
      header = [h for h in _split_md_row(line) if h]
      i += 2
      while i < len(lines) and "|" in lines[i] and not re.match(r"^\s*\|?\s*:?-{2,}", lines[i]):
        cells = _split_md_row(lines[i])
        if len(cells) < 2:
          i += 1
          continue
        row = {}
        for idx, key in enumerate(header):
          row[key] = cells[idx].strip() if idx < len(cells) else ""
        records.append(row)
        i += 1
      if header and not columns:
        columns = header
      elif header:
        for key in header:
          if key not in columns:
            columns.append(key)
      continue
    i += 1

  if records:
    return columns or sorted({k for row in records for k in row}), records

  # 无表格时解析「编码 中文 英文」类列表
  for raw in lines:
    line = raw.strip()
    if not line or line.startswith("#") or line.startswith("```"):
      continue
    line = re.sub(r"^[-*+]\s+", "", line)
    line = re.sub(r"^\d+[.\)]\s+", "", line)
    if "|" in line:
      parts = [p.strip() for p in line.strip("|").split("|") if p.strip()]
    elif "：" in line or ":" in line:
      parts = [p.strip() for p in re.split(r"[:：]", line, maxsplit=1) if p.strip()]
      if len(parts) == 2 and ("/" in parts[1] or "、" in parts[1] or "," in parts[1]):
        rest = re.split(r"[\/、,，]\s*", parts[1])
        parts = [parts[0], *[x for x in rest if x]]
    else:
      parts = [p.strip() for p in re.split(r"[\t,，/、]{1}|\s{2,}", line) if p.strip()]
      if len(parts) < 2:
        parts = line.split()
    if len(parts) < 2:
      continue
    if not columns:
      if len(parts) >= 3:
        columns = ["code", "name1", "name2"]
      else:
        columns = ["code", "name"]
    row = {}
    for idx, key in enumerate(columns):
      row[key] = parts[idx] if idx < len(parts) else ""
    if len(parts) > len(columns):
      row[columns[-1]] = " ".join(parts[len(columns) - 1:])
    records.append(row)
  return columns, records


def mapping_preview(parsed: dict) -> dict:
  return {
    "path": parsed.get("path"),
    "name": parsed.get("name"),
    "columns": parsed.get("columns") or [],
    "row_count": parsed.get("row_count") or 0,
    "sample": parsed.get("sample") or [],
    "sample_rows": parsed.get("sample") or [],
  }
