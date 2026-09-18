from __future__ import annotations

import re
from pathlib import Path

from llm.io_preview import peek
from llm.mapping import MAPPING_SUFFIXES

TABLE_FILE_SUFFIXES = {".xlsx", ".xls", ".csv"}

PATH_RE = re.compile(
  r"[\"']([^\"']+)[\"']"
  r"|([A-Za-z]:\\[^\s\"'<>|*?]+)"
  r"|(\\\\[^\s\"'<>|*?]+)"
)


def extract_path_strings(text: str) -> list[str]:
  found = []
  for match in PATH_RE.finditer(text or ""):
    raw = next((g for g in match.groups() if g), "")
    raw = raw.strip().rstrip("，。；,.;")
    if not raw:
      continue
    if raw not in found:
      found.append(raw)
  return found


def extract_paths(text: str) -> list[str]:
  found = []
  for raw in extract_path_strings(text):
    path = Path(raw)
    if path.exists():
      resolved = str(path.resolve())
      if resolved not in found:
        found.append(resolved)
  return found


def merge_paths(instruction: str, extra: list[str] | None = None) -> list[str]:
  paths = extract_paths(instruction)
  for item in extra or []:
    text = str(item or "").strip()
    if not text:
      continue
    path = Path(text)
    if path.exists():
      resolved = str(path.resolve())
      if resolved not in paths:
        paths.append(resolved)
  return paths


def inspect_paths(paths: list[str]) -> list[dict]:
  items = []
  for path in paths:
    try:
      data = peek(path)
      data["exists"] = True
      items.append(data)
    except Exception as exc:
      items.append({"path": path, "exists": False, "error": str(exc)})
  return items


def guess_roles(instruction: str, paths: list[str]) -> dict:
  from llm.codegen import looks_like_script

  folders = []
  mappings = []
  tables = []
  files = []
  for raw in paths:
    path = Path(raw)
    suffix = path.suffix.lower()
    if path.is_dir():
      folders.append(str(path.resolve()))
    elif suffix in {".md", ".markdown"}:
      mappings.append(str(path.resolve()))
    elif suffix in TABLE_FILE_SUFFIXES:
      tables.append(str(path.resolve()))
    elif suffix in MAPPING_SUFFIXES:
      mappings.append(str(path.resolve()))
    elif path.is_file():
      files.append(str(path.resolve()))
  script_task = looks_like_script(instruction)
  if script_task:
    source = tables[0] if tables else (files[0] if files else (folders[0] if folders else ""))
    mapping = mappings[0] if mappings else ""
  else:
    source = folders[0] if folders else (tables[0] if tables else (files[0] if files else ""))
    mapping = mappings[0] if mappings else ""
    if source and not mapping:
      from llm.mapping import find_mapping_file
      mapping = find_mapping_file(source)
  save = ""
  text = instruction or ""
  marker = re.search(r"(?:输出到|保存到|复制到|拷贝到|放到)\s*[\"']?([A-Za-z]:\\[^\s\"'<>|*?]+)", text)
  if marker:
    save = str(Path(marker.group(1)))
  if not save:
    extracted = extract_path_strings(text)
    for raw in extracted:
      path = Path(raw)
      resolved = str(path.resolve()) if path.exists() else str(path)
      if source and resolved != source and ("输出" in text or "保存" in text):
        save = resolved
        break
  if not save and source:
    src = Path(source)
    if script_task:
      save = str((src.parent / f"{src.stem}_fetch.js").resolve())
    elif "原地" in text or "直接改名" in text:
      save = str(src.resolve())
    else:
      parent = src.parent if src.is_file() else src
      name = src.stem if src.is_file() else src.name
      save = str((parent / f"{name}_out").resolve())
  return {
    "source_path": source,
    "mapping_path": mapping,
    "save_path": save,
  }
