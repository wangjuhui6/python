from __future__ import annotations

import re
import shutil
from pathlib import Path

from llm.io_preview import IMAGE_SUFFIXES, TABLE_SUFFIXES, file_kind, _read_table, write_table

KIND_SUFFIX = {
  "image": IMAGE_SUFFIXES,
  "table": TABLE_SUFFIXES,
  "gis": {".shp", ".geojson", ".gpkg", ".mbtiles", ".kml", ".kmz", ".gml", ".tif", ".tiff"},
  "doc": {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt", ".md"},
}

INVALID_NAME = re.compile(r'[\\/:*?"<>|]')


def safe_filename(name: str) -> str:
  text = INVALID_NAME.sub("_", (name or "").strip())
  text = re.sub(r"\s+", " ", text).strip(" .")
  return text or "未命名"


def lookup_value(stem: str, plan: dict) -> str:
  lookup = plan.get("lookup") or {}
  if lookup.get("enabled") is False:
    return ""
  records = plan.get("lookup_records") or []
  if not records:
    mapping_path = plan.get("mapping_path") or lookup.get("mapping_path")
    if mapping_path:
      from llm.mapping import parse_mapping
      records = parse_mapping(mapping_path).get("records") or []
      plan["lookup_records"] = records
  if not records:
    return ""
  key_fields = [str(x) for x in (lookup.get("key_fields") or []) if str(x).strip()]
  value_fields = [str(x) for x in (lookup.get("value_fields") or []) if str(x).strip()]
  if not key_fields:
    key_fields = list((records[0] or {}).keys())[:1]
  if not value_fields:
    keys = list((records[0] or {}).keys())
    value_fields = keys[1:2] or keys[:1]
  table = []
  for row in records:
    keys = []
    for field in key_fields:
      raw = str(row.get(field) or "").strip()
      if raw:
        keys.append(raw)
    value = ""
    for field in value_fields:
      raw = str(row.get(field) or "").strip()
      if raw:
        value = raw
        break
    if keys and value:
      table.append((keys, value))
  return _match_lookup(stem, table, lookup)


def _match_lookup(stem: str, table: list, lookup: dict) -> str:
  if not stem:
    return ""
  mode = str(lookup.get("match") or "contains").lower()
  insensitive = lookup.get("case_insensitive", True)
  source = stem.lower() if insensitive else stem

  def norm(text: str) -> str:
    return text.lower() if insensitive else text

  # 更长的键优先，避免 CN 盖掉 CN-HK
  ranked = sorted(table, key=lambda item: max(len(k) for k in item[0]), reverse=True)

  tokens = re.split(r"[_\-\.\s]+", stem)
  tokens_n = [norm(t) for t in tokens if t]

  for keys, value in ranked:
    for key in keys:
      nk = norm(key)
      if not nk:
        continue
      if mode in {"stem", "exact"} and source == nk:
        return value
      if mode == "prefix" and (source.startswith(nk) or nk.startswith(source)):
        return value
      if mode == "token" and nk in tokens_n:
        return value
      if mode in {"contains", "auto", ""} and (nk in source or source in nk):
        return value
  if mode == "auto":
    return ""
  # auto/contains 失败时再试 token
  for keys, value in ranked:
    for key in keys:
      if norm(key) in tokens_n:
        return value
  return ""


SIDECARS = {
  ".shp": [".dbf", ".shx", ".prj", ".cpg", ".qpj", ".sbn", ".sbx", ".shp.xml"],
  ".tif": [".tfw", ".tif.aux.xml", ".xml"],
  ".tiff": [".tfw", ".aux.xml"],
  ".jpg": [".jgw", ".jpgw", ".wld", ".aux.xml"],
  ".jpeg": [".jgw", ".wld", ".aux.xml"],
  ".png": [".pgw", ".wld", ".aux.xml"],
}

MAX_APPLY_FILES = 500


def list_source_files(src: Path, recursive: bool) -> list[Path]:
  if src.is_file():
    return [src]
  if not src.is_dir():
    return []
  iterator = src.rglob("*") if recursive else src.iterdir()
  files = []
  for item in iterator:
    if item.is_file():
      files.append(item)
      if len(files) >= MAX_APPLY_FILES:
        break
  return sorted(files)


def _sidecar_names(files: list[Path]) -> set[Path]:
  skip = set()
  file_set = {p.resolve() for p in files}
  for path in files:
    for extra in _sidecar_paths(path):
      if extra.resolve() in file_set:
        skip.add(extra.resolve())
  return skip


def plan_targets(src: Path, dest: Path, plan: dict) -> list[dict]:
  recursive = plan.get("recursive", True)
  files = list_source_files(src, recursive)
  include = _norm_exts(plan.get("include_suffixes"))
  exclude = _norm_exts(plan.get("exclude_suffixes"))
  kinds = {str(x).lower() for x in (plan.get("include_kinds") or []) if str(x).strip()}
  if kinds:
    for kind in kinds:
      include |= set(KIND_SUFFIX.get(kind) or set())
    if "image" in kinds:
      include |= IMAGE_SUFFIXES
  file_map = _file_map_index(plan.get("file_map") or [])
  skip = _sidecar_names(files)
  rows = []
  for item in files:
    if item.resolve() in skip:
      continue
    rel = item.relative_to(src) if src.is_dir() else Path(item.name)
    if include and rel.suffix.lower() not in include:
      continue
    if exclude and rel.suffix.lower() in exclude:
      continue
    lookup = plan.get("lookup") or {}
    mapped_name = file_map.get(rel.as_posix()) or file_map.get(rel.name)
    if (lookup.get("enabled") or plan.get("mapping_path") or plan.get("lookup_records")) and lookup.get("unmatched") == "skip" and not mapped_name:
      if not lookup_value(rel.stem, plan):
        continue
    rel_out = _map_relative(rel, file_map, plan)
    target = _safe_join(dest if dest.is_dir() or src.is_dir() else dest.parent, rel_out, dest, src)
    rows.append({
      "from": str(item.resolve()),
      "from_rel": rel.as_posix(),
      "to": str(target),
      "to_rel": rel_out.as_posix(),
      "is_table": item.suffix.lower() in TABLE_SUFFIXES,
    })
  return rows


def apply_files(src: Path, dest_path: str, plan: dict, dry_run: bool = False) -> dict:
  dest = Path(dest_path)
  src = src.resolve()
  if src.is_dir():
    dest.mkdir(parents=True, exist_ok=True)
    dest = dest.resolve()
  else:
    # 单文件：输出可以是新文件路径，也可以是目录
    if dest.suffix:
      dest.parent.mkdir(parents=True, exist_ok=True)
    else:
      dest.mkdir(parents=True, exist_ok=True)
      dest = dest.resolve()

  action = (plan.get("action") or "copy").lower()
  if action not in {"copy", "move", "rename"}:
    action = "copy"
  overwrite = bool(plan.get("overwrite"))
  rows = plan_targets(src, dest if dest.is_dir() else dest, plan)

  # 单文件输出到明确文件名
  if src.is_file() and dest.suffix and len(rows) == 1:
    rows[0]["to"] = str(dest.resolve())
    rows[0]["to_rel"] = dest.name

  if dest.is_dir() and src.is_dir() and dest == src and action == "copy":
    action = "rename"

  results = []
  if dry_run:
    return {
      "output": str(dest),
      "action": action,
      "dry_run": True,
      "count": len(rows),
      "files": rows,
    }

  for row in rows:
    source = Path(row["from"])
    target = Path(row["to"])
    if target.resolve() == source.resolve():
      results.append({**row, "status": "skip_same"})
      continue
    if target.exists() and not overwrite:
      results.append({**row, "status": "skip_exists"})
      continue
    target.parent.mkdir(parents=True, exist_ok=True)
    if row["is_table"] and (plan.get("column_map") or []) and (plan.get("output_format") not in {None, "", "copy"}):
      df, _extra = _read_table(source)
      df = _apply_column_map(df, plan)
      fmt = plan.get("output_format")
      if fmt:
        target = target.with_suffix("." + str(fmt).lstrip("."))
        row["to"] = str(target)
      write_table(df, str(target), fmt)
      if action in {"move", "rename"} and target.resolve() != source.resolve():
        _delete_with_sidecars(source)
      status = "converted"
    else:
      _transfer(source, target, action)
      _transfer_sidecars(source, target, action)
      status = action
    results.append({**row, "status": status})

  return {
    "output": str(dest),
    "action": action,
    "dry_run": False,
    "count": len(results),
    "files": results,
  }


def _apply_column_map(df, plan: dict):
  column_map = plan.get("column_map") or []
  rename = {}
  for item in column_map:
    src = str(item.get("from") or "").strip()
    dst = str(item.get("to") or "").strip()
    if src and dst and src in df.columns:
      rename[src] = dst
  if rename:
    df = df.rename(columns=rename)
  if plan.get("keep_unmapped") is False:
    keep = list(rename.values()) or list(df.columns)
    df = df[[c for c in keep if c in df.columns]]
  return df


def _norm_exts(values) -> set[str]:
  result = set()
  for item in values or []:
    text = str(item).strip().lower()
    if not text:
      continue
    if not text.startswith("."):
      text = "." + text
    result.add(text)
  return result


def _file_map_index(items: list) -> dict[str, str]:
  index = {}
  for item in items:
    src = str(item.get("from") or "").replace("\\", "/").strip()
    dst = str(item.get("to") or "").replace("\\", "/").strip()
    if src and dst:
      index[src] = dst
      index[Path(src).name] = dst
  return index


def _map_relative(rel: Path, file_map: dict[str, str], plan: dict) -> Path:
  key = rel.as_posix()
  mapped = file_map.get(key) or file_map.get(rel.name)
  if mapped:
    mapped_path = Path(mapped)
    if mapped_path.is_absolute():
      mapped_path = Path(mapped_path.name)
    return mapped_path

  rules = plan.get("name_rules") or {}
  stem = rel.stem
  looked = lookup_value(stem, plan)
  if looked:
    stem = looked
  for item in rules.get("replace") or []:
    stem = stem.replace(str(item.get("from") or ""), str(item.get("to") or ""))
  stem = f"{rules.get('prefix') or ''}{stem}{rules.get('suffix') or ''}"
  if rules.get("to_lower"):
    stem = stem.lower()
  if rules.get("to_upper"):
    stem = stem.upper()
  stem = safe_filename(stem)
  ext = str(rules.get("change_ext") or rel.suffix or "")
  if ext and not ext.startswith("."):
    ext = "." + ext
  name = f"{stem}{ext}"
  parent = rel.parent if plan.get("keep_structure", True) else Path(".")
  out = parent / name
  if rules.get("by_ext_subdir"):
    folder = (ext or rel.suffix or ".other").lstrip(".") or "other"
    out = Path(folder) / out.name
  if rules.get("by_kind_subdir"):
    out = Path(file_kind(rel.suffix.lower())) / out.name
  return out


def _safe_join(base: Path, rel_out: Path, dest: Path, src: Path) -> Path:
  if dest.suffix and src.is_file():
    return dest
  target = (base / rel_out).resolve()
  root = base.resolve()
  if root not in target.parents and target != root:
    raise ValueError(f"非法输出路径: {rel_out}")
  return target


def _transfer(source: Path, target: Path, action: str):
  if action in {"move", "rename"}:
    if target.exists():
      target.unlink()
    shutil.move(str(source), str(target))
    return
  shutil.copy2(source, target)


def _sidecar_paths(path: Path) -> list[Path]:
  extras = SIDECARS.get(path.suffix.lower()) or []
  found = []
  for extra in extras:
    if not extra.startswith("."):
      extra = "." + extra
    candidate = path.parent / f"{path.stem}{extra}"
    if candidate.exists() and candidate.is_file() and candidate.resolve() != path.resolve():
      found.append(candidate)
  return found


def _transfer_sidecars(source: Path, target: Path, action: str):
  src_stem = source.stem
  dst_stem = target.stem
  for extra in _sidecar_paths(source):
    suffix_part = extra.name[len(src_stem):]
    dest_extra = target.parent / f"{dst_stem}{suffix_part}"
    dest_extra.parent.mkdir(parents=True, exist_ok=True)
    if dest_extra.resolve() == extra.resolve():
      continue
    if action in {"move", "rename"}:
      if dest_extra.exists():
        dest_extra.unlink()
      shutil.move(str(extra), str(dest_extra))
    else:
      shutil.copy2(extra, dest_extra)


def _delete_with_sidecars(source: Path):
  for extra in _sidecar_paths(source):
    extra.unlink(missing_ok=True)
  source.unlink(missing_ok=True)
