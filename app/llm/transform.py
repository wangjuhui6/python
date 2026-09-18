from __future__ import annotations

import json
from pathlib import Path

from llm.codegen import _extract_url, generate_script, infer_script_plan, looks_like_script
from llm.config import load_config
from llm.context import guess_roles, inspect_paths, merge_paths
from llm.engine import chat
from llm.file_ops import apply_files, _apply_column_map
from llm.io_preview import TABLE_SUFFIXES, extract_json, write_table, _read_table
from llm.mapping import mapping_preview, parse_mapping

SYSTEM = """你是任务理解器，不是代码生成器。只输出一个 JSON，不要解释，不要 Markdown，不要写 fetch/JavaScript。
先理解用户在说什么，再决定怎么做。关键字怎么写都可以，不要死记「按照」「转换成」这种词。

输出：
{
  "action": "copy 或 move 或 rename 或 generate_script",
  "need_more_ai": false,
  "execute": "python 或 llm",
  "source_path": "必须来自可用路径",
  "mapping_path": "",
  "save_path": "",
  "recursive": true,
  "keep_structure": true,
  "include_suffixes": [],
  "include_kinds": [],
  "exclude_suffixes": [],
  "overwrite": false,
  "lookup": { "enabled": false, "key_fields": [], "value_fields": [], "match": "auto", "case_insensitive": true, "unmatched": "keep" },
  "name_rules": { "replace": [], "prefix": "", "suffix": "", "change_ext": "", "by_ext_subdir": false, "by_kind_subdir": false },
  "file_map": [],
  "column_map": [],
  "script": {
    "kind": "browser_fetch",
    "url": "",
    "method": "POST",
    "interval_ms": 1000,
    "headers": {"Content-Type": "application/json"},
    "body_template": {},
    "column_mode": "headers",
    "columns": [{"from": "真实表头或A/B/C", "to": "输出key"}]
  },
  "output_format": "",
  "notes": "用中文一句话说明你的理解"
}

如何决定是否还要用 AI：
- generate_script（把表格每行做成数组/对象、改 key、生成浏览器调用）：execute 必须是 python，need_more_ai 必须是 false。你只负责填 columns，程序去读表和写代码。
- 复制/移动/按对照表改名且规则已经清楚：execute 用 python，need_more_ai false。
- 只有无法从描述和表头确定规则、必须逐条判断时，才 need_more_ai true、execute 用 llm。

columns 规则：
- from 必须来自「真实表头」或用户说的 A/B/C 列，禁止编造。
- to 是用户要的输出字段名。用户说把 国家/年龄/时间/性别 的 key 改成 name/age/time/ag，就输出
  [{"from":"国家","to":"name"},{"from":"年龄","to":"age"},{"from":"时间","to":"time"},{"from":"性别","to":"ag"}]
- 用户只给了目标字段、没说对应哪一列：若表头同名就用同名；否则按从左到右顺序对应。
- 默认 copy，不要删除源文件。
"""


def build_prompt(instruction: str, guessed: dict, contexts: list[dict], mapping: dict | None) -> str:
  slim_ctx = []
  headers = []
  for item in contexts:
    table = item.get("first_table") if item.get("kind") == "folder" else item
    columns = (table or {}).get("columns") or item.get("columns") or []
    sample = (table or {}).get("sample_rows") or item.get("sample_rows") or []
    if columns and not headers:
      headers = [str(c) for c in columns]
    row = {
      "path": item.get("path"),
      "kind": item.get("kind"),
      "name": item.get("name"),
      "file_count": item.get("file_count"),
      "columns": columns,
      "sample_rows": sample[:3],
    }
    files = item.get("files") or []
    if files and item.get("kind") != "table":
      row["files"] = [
        {
          "name": f.get("name"),
          "rel": f.get("rel") or f.get("name"),
          "suffix": f.get("suffix"),
          "kind": f.get("kind"),
        }
        for f in files[:30]
      ]
    slim_ctx.append(row)
  mapping_text = json.dumps(mapping, ensure_ascii=False, indent=2) if mapping else "无对照表"
  return (
    f"用户描述：\n{instruction.strip()}\n\n"
    f"真实表头：{json.dumps(headers, ensure_ascii=False)}\n\n"
    f"路径角色猜测（可改）：\n{json.dumps(guessed, ensure_ascii=False, indent=2)}\n\n"
    f"可用路径预览（含样例行）：\n{json.dumps(slim_ctx, ensure_ascii=False, indent=2)}\n\n"
    f"对照表列名和样例：\n{mapping_text}\n\n"
    "先理解描述，再决定 action / execute / need_more_ai，并填好 script.columns。"
  )


def _infer_lookup(columns: list[str], instruction: str) -> dict:
  text = instruction or ""
  def pick(tokens: list[str]) -> list[str]:
    found = []
    for col in columns:
      raw = str(col)
      key = raw.lower()
      if any(token.lower() in key or token in raw for token in tokens):
        found.append(raw)
    return found
  keys = pick(["iso", "code", "编码", "alpha", "id", "英文", "english", "en"])
  if "中文" in text or "汉语" in text:
    values = pick(["中文", "zh", "cn", "名称", "name_zh", "chinese", "汉语"])
  elif "英文" in text or "english" in text.lower():
    values = pick(["英文", "en", "english", "name_en"])
  else:
    values = pick(["中文", "zh", "名称", "name", "title", "英文", "english"])
  if not keys and columns:
    keys = [columns[0]]
  if not values and len(columns) > 1:
    values = [columns[1]]
  elif not values and columns:
    values = [columns[0]]
  if keys and values and keys[0] == values[0] and len(columns) > 1:
    values = [c for c in columns if c != keys[0]][:1]
  return {
    "enabled": True,
    "key_fields": keys[:3],
    "value_fields": values[:2],
    "match": "auto",
    "case_insensitive": True,
    "unmatched": "keep",
  }


def _coerce_columns(raw) -> list[dict]:
  columns = []
  if not isinstance(raw, list):
    return columns
  for item in raw:
    if not isinstance(item, dict):
      continue
    src = item.get("from") or item.get("source") or item.get("header") or item.get("column") or item.get("列") or ""
    dst = item.get("to") or item.get("target") or item.get("key") or item.get("field") or item.get("字段") or src
    src = str(src).strip()
    dst = str(dst).strip() or src
    if src:
      columns.append({"from": src, "to": dst})
  return columns


def _columns_renames(columns: list[dict]) -> bool:
  return any(str(item.get("from") or "").strip().lower() != str(item.get("to") or "").strip().lower() for item in columns)


def _normalize_plan(plan: dict, guessed: dict, instruction: str, parsed_mapping) -> dict:
  plan.setdefault("action", "copy")
  plan.setdefault("recursive", True)
  plan.setdefault("keep_structure", True)
  plan.setdefault("include_suffixes", [])
  plan.setdefault("include_kinds", [])
  plan.setdefault("exclude_suffixes", [])
  plan.setdefault("overwrite", False)
  plan.setdefault("name_rules", {})
  plan.setdefault("file_map", [])
  plan.setdefault("column_map", [])
  plan["source_path"] = plan.get("source_path") or guessed.get("source_path") or ""
  plan["save_path"] = plan.get("save_path") or guessed.get("save_path") or ""
  plan["mapping_path"] = plan.get("mapping_path") or guessed.get("mapping_path") or ""
  plan["instruction"] = instruction
  execute = str(plan.get("execute") or "").strip().lower()
  script_task = plan.get("action") == "generate_script" or looks_like_script(instruction)
  if script_task:
    inferred_script = infer_script_plan(instruction)
    plan["action"] = "generate_script"
    llm_script = plan.get("script") if isinstance(plan.get("script"), dict) else {}
    merged = dict(inferred_script.get("script") or {})
    llm_columns = _coerce_columns(llm_script.get("columns") or plan.get("column_map"))
    rule_columns = _coerce_columns(merged.get("columns"))
    for key, value in llm_script.items():
      if key == "columns":
        continue
      if value not in (None, "", [], {}):
        merged[key] = value
    if llm_columns:
      merged["columns"] = llm_columns
    elif rule_columns:
      merged["columns"] = rule_columns
    if llm_columns and _columns_renames(llm_columns):
      merged["column_mode"] = llm_script.get("column_mode") or "headers"
    elif not llm_script.get("column_mode"):
      merged["column_mode"] = inferred_script["script"].get("column_mode") or "auto"
    url_in_text = _extract_url(instruction)
    if url_in_text:
      merged["url"] = url_in_text
    plan["script"] = merged
    plan["execute"] = execute or "python"
    plan["need_more_ai"] = False
    src = Path(plan["source_path"]) if plan.get("source_path") else None
    if src and src.is_file():
      dest = Path(plan["save_path"]) if plan.get("save_path") else src.parent
      if dest.exists() and dest.is_dir():
        plan["save_path"] = str(dest / f"{src.stem}_fetch.js")
      elif dest.suffix.lower() not in {".js", ".html", ".txt"}:
        plan["save_path"] = str(src.with_name(src.stem + "_fetch.js"))
  else:
    plan["execute"] = execute or "python"
    plan.setdefault("need_more_ai", False)
  if parsed_mapping and not script_task:
    plan["mapping_path"] = parsed_mapping["path"]
    inferred = _infer_lookup(parsed_mapping.get("columns") or [], instruction)
    lookup = plan.get("lookup") if isinstance(plan.get("lookup"), dict) else {}
    lookup.setdefault("enabled", True)
    for key, value in inferred.items():
      if key in {"key_fields", "value_fields"}:
        if not lookup.get(key):
          lookup[key] = value
      else:
        lookup.setdefault(key, value)
    plan["lookup"] = lookup
  return plan


def make_plan(instruction: str, paths: list[str] | None = None, path: str | None = None, mapping_path: str | None = None, save_path: str | None = None) -> dict:
  extra = list(paths or [])
  if path:
    extra.append(path)
  if mapping_path:
    extra.append(mapping_path)
  if save_path:
    extra.append(save_path)
  available = merge_paths(instruction, extra)
  if not available:
    raise ValueError("请在描述中写出文件/文件夹路径，或点「添加路径」")
  guessed = guess_roles(instruction, available)
  if mapping_path:
    guessed["mapping_path"] = mapping_path
  if path:
    guessed["source_path"] = str(Path(path).resolve())
  if save_path:
    guessed["save_path"] = save_path
  cfg = load_config()
  skip_llm = bool(cfg.get("skip_llm_for_script", False)) and looks_like_script(instruction)
  contexts = inspect_paths(available)
  parsed = None
  mapping_view = None
  mapping_file = guessed.get("mapping_path") or ""
  if mapping_file:
    parsed = parse_mapping(mapping_file)
    mapping_view = mapping_preview(parsed)
  if skip_llm:
    plan = _normalize_plan(
      {
        "action": "generate_script",
        "source_path": guessed.get("source_path") or "",
        "save_path": guessed.get("save_path") or "",
        "execute": "python",
        "need_more_ai": False,
        "notes": "已跳过模型理解，仅用规则解析描述。",
      },
      guessed,
      instruction,
      None,
    )
    return {
      "preview": next((c for c in contexts if c.get("path") == plan.get("source_path")), contexts[0] if contexts else None),
      "contexts": contexts,
      "mapping": mapping_view,
      "guessed": guessed,
      "plan": plan,
      "raw": "",
      "used_llm": False,
    }
  text = chat(
    [
      {"role": "system", "content": SYSTEM},
      {"role": "user", "content": build_prompt(instruction, guessed, contexts, mapping_view)},
    ],
    temperature=0.1,
    json_mode=True,
  )
  plan = _normalize_plan(extract_json(text), guessed, instruction, parsed)
  return {
    "preview": next((c for c in contexts if c.get("path") == plan.get("source_path")), contexts[0] if contexts else None),
    "contexts": contexts,
    "mapping": mapping_view,
    "guessed": guessed,
    "plan": plan,
    "raw": text,
    "used_llm": True,
  }


def prepare_plan(plan: dict, mapping_path: str | None = None) -> dict:
  plan = dict(plan or {})
  if mapping_path:
    plan["mapping_path"] = mapping_path
  if plan.get("mapping_path") and not plan.get("lookup_records"):
    try:
      parsed = parse_mapping(plan["mapping_path"])
      plan["lookup_records"] = parsed.get("records") or []
      lookup = plan.get("lookup") if isinstance(plan.get("lookup"), dict) else {}
      lookup.setdefault("enabled", True)
      if not lookup.get("key_fields") or not lookup.get("value_fields"):
        inferred = _infer_lookup(parsed.get("columns") or [], "")
        lookup.setdefault("key_fields", inferred["key_fields"])
        lookup.setdefault("value_fields", inferred["value_fields"])
        lookup.setdefault("match", "auto")
      plan["lookup"] = lookup
    except Exception:
      pass
  return plan


def apply_plan(path: str | None, save_path: str | None, plan: dict, dry_run: bool = False, mapping_path: str | None = None) -> dict:
  plan = prepare_plan(plan, mapping_path)
  src = path or plan.get("source_path") or ""
  dest = save_path or plan.get("save_path") or ""
  if not src:
    raise ValueError("方案中没有来源路径")
  p = Path(src)
  action = plan.get("action") or "copy"
  if action == "generate_script":
    dest = dest or str(p.with_name(p.stem + "_fetch.js"))
    return generate_script(src, dest, plan, dry_run=dry_run)
  if not dest:
    raise ValueError("方案中没有输出路径")
  dest_path = Path(dest)
  if (
    p.is_file()
    and p.suffix.lower() in TABLE_SUFFIXES
    and plan.get("column_map")
    and dest_path.suffix
    and dest_path.suffix.lower() not in {".js", ".html"}
  ):
    if dry_run:
      return {
        "output": dest,
        "action": "convert",
        "dry_run": True,
        "count": 1,
        "files": [{
          "from": str(p.resolve()),
          "from_rel": p.name,
          "to": dest,
          "to_rel": dest_path.name,
          "is_table": True,
        }],
      }
    df, _extra = _read_table(p)
    df = _apply_column_map(df, plan)
    output = write_table(df, dest, plan.get("output_format"))
    return {
      "output": output,
      "action": "convert",
      "dry_run": False,
      "count": 1,
      "files": [{"from": str(p.resolve()), "to": output, "status": "converted"}],
    }
  return apply_files(p, dest, plan, dry_run=dry_run)


def run_instruction(instruction: str, paths: list[str] | None = None, dry_run: bool = True, plan: dict | None = None) -> dict:
  built = None
  if plan:
    result_plan = plan
    extra = {"contexts": [], "mapping": None, "guessed": None, "preview": None}
  else:
    built = make_plan(instruction, paths)
    result_plan = built["plan"]
    extra = built
  applied = apply_plan(result_plan.get("source_path"), result_plan.get("save_path"), result_plan, dry_run=dry_run)
  return {
    "preview": extra.get("preview"),
    "contexts": extra.get("contexts") or [],
    "mapping": extra.get("mapping"),
    "guessed": extra.get("guessed"),
    "plan": result_plan,
    "result": applied,
    "used_llm": bool(extra.get("used_llm")),
  }
