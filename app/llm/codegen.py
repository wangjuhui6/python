from __future__ import annotations

import json
import math
import re
from pathlib import Path

EXCEL_COL = re.compile(r"^[A-Za-z]{1,3}$")


def excel_index(label: str) -> int:
  text = (label or "").strip().upper()
  value = 0
  for ch in text:
    if not ("A" <= ch <= "Z"):
      return 0
    value = value * 26 + (ord(ch) - 64)
  return max(value - 1, 0)


def excel_label(index: int) -> str:
  n = int(index) + 1
  letters = ""
  while n > 0:
    n, rem = divmod(n - 1, 26)
    letters = chr(65 + rem) + letters
  return letters or "A"


FIELD_STOP = {
  "一个", "数组", "对象", "取成", "做成", "作为", "映射为", "改成",
  "数据", "每行", "文件", "按照", "组成", "变成", "json",
}


def _cell(value):
  try:
    import pandas as pd
    if value is None or (isinstance(value, float) and math.isnan(value)) or pd.isna(value):
      return ""
  except Exception:
    if value is None:
      return ""
  if hasattr(value, "item") and not isinstance(value, (bytes, str)):
    try:
      value = value.item()
    except Exception:
      pass
  if isinstance(value, bool):
    return value
  if isinstance(value, int):
    return value
  if isinstance(value, float):
    if value.is_integer():
      return int(value)
    return value
  text = str(value).strip()
  if text.lower() in {"nan", "none", "nat"}:
    return ""
  return text


def _read_raw_table(path: Path, nrows: int | None = None):
  import pandas as pd

  suffix = path.suffix.lower()
  if suffix in {".xlsx", ".xls"}:
    xl = pd.ExcelFile(path)
    if nrows:
      for sheet in xl.sheet_names:
        df = pd.read_excel(path, sheet_name=sheet, header=None, dtype=object, nrows=nrows)
        df = df.dropna(how="all").dropna(axis=1, how="all")
        if not df.empty:
          return df
      return pd.DataFrame()
    best = None
    for sheet in xl.sheet_names:
      df = pd.read_excel(path, sheet_name=sheet, header=None, dtype=object)
      df = df.dropna(how="all")
      df = df.dropna(axis=1, how="all")
      if best is None or len(df.index) > len(best.index):
        best = df
    return best if best is not None else pd.DataFrame()
  if suffix in {".csv", ".tsv"}:
    sep = "\t" if suffix == ".tsv" else ","
    last_error = None
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
      try:
        df = pd.read_csv(path, header=None, dtype=object, encoding=enc, sep=sep, nrows=nrows)
        return df.dropna(how="all").dropna(axis=1, how="all")
      except Exception as exc:
        last_error = exc
    raise ValueError(f"无法读取表格: {last_error}")
  if suffix == ".json":
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "features" in data:
      data = [f.get("properties") or {} for f in data.get("features") or []]
    if isinstance(data, list) and data and isinstance(data[0], dict):
      return pd.DataFrame(data)
    return pd.json_normalize(data)
  raise ValueError(f"不支持的表格格式: {suffix}")


def _extract_letter_columns(text: str) -> list[str]:
  chunk = re.search(
    r"((?:[A-Za-z]\s*列\s*[、,，和与\s]*){1,}[A-Za-z]\s*列)",
    text or "",
  )
  if chunk:
    letters = [part.upper() for part in re.findall(r"[A-Za-z]", chunk.group(1))]
    return letters if len(letters) >= 2 else []
  isolated = re.findall(r"(?<![A-Za-z0-9_])([A-Za-z])(?![A-Za-z0-9_])", text or "")
  return [part.upper() for part in isolated] if len(isolated) >= 2 else []


def _split_tokens(text: str) -> list[str]:
  parts = re.split(r"[、,，/]+|\s+", text or "")
  return [p.strip() for p in parts if p.strip() and p.strip().lower() not in FIELD_STOP]


def _extract_field_group(text: str, pattern: str) -> list[str]:
  match = re.search(pattern, text or "", re.I)
  if not match:
    return []
  return _split_tokens(match.group(1))


def _zip_columns(sources: list[str], targets: list[str]) -> list[dict]:
  if not sources and not targets:
    return []
  if sources and targets:
    size = min(len(sources), len(targets))
    return [{"from": sources[idx], "to": targets[idx]} for idx in range(size)]
  names = targets or sources
  return [{"from": name, "to": name} for name in names]


def _extract_source_and_target_fields(text: str) -> tuple[list[str], list[str]]:
  sources = _extract_field_group(
    text,
    r"按照\s+([A-Za-z0-9_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff、,，/\s]*?)\s*(?:取成|做成|组成|变成|作为)",
  )
  targets = _extract_field_group(
    text,
    r"(?:将|把)?\s*(?:key|键名|键|字段名|列名|表头)\s*(?:转换|改|映射|换|变)\s*(?:成|为)\s+([A-Za-z0-9_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff、,，/\s]*)",
  )
  if not targets:
    targets = _extract_field_group(
      text,
      r"(?:key|键名|键)\s*(?:转换|改成|改成|映射为|换成|变成)\s+([A-Za-z0-9_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff、,，/\s]*)",
    )
  if not sources:
    sources = _extract_field_group(
      text,
      r"(?:取成|作为|映射为|做成|改成)\s+([A-Za-z0-9_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff、,，/\s]*?)(?:\s*(?:取成|做成|组成|变成|作为)\s*(?:一个)?\s*(?:数组|对象|json)|$)",
    )
  if sources and targets and [s.lower() for s in sources] == [t.lower() for t in targets]:
    targets = []
  return sources, targets


def _spec_names(columns: list[dict], key: str) -> list[str]:
  names = []
  for spec in columns or []:
    value = str(spec.get(key) or spec.get("field") or spec.get("excel") or "").strip()
    if value:
      names.append(value)
  return names


def _headers_match_columns(values: list, columns: list[dict]) -> bool:
  from_names = _spec_names(columns, "from")
  to_names = _spec_names(columns, "to")
  need = min(2, max(len(from_names), len(to_names), 1))
  return _header_match_count(values, from_names) >= need or _header_match_count(values, to_names) >= need


def _named_columns(df) -> list[str]:
  names = []
  for col in list(df.columns):
    if isinstance(col, int) or (isinstance(col, float) and col == int(col)):
      return []
    text = str(col).strip()
    if re.fullmatch(r"\d+", text):
      return []
    names.append(text)
  return names


def _positional_columns(fields: list[str]) -> list[dict]:
  return [{"from": excel_label(idx), "to": name} for idx, name in enumerate(fields)]


def _header_match_count(values: list, fields: list[str]) -> int:
  lowered = {str(_cell(v)).strip().lower() for v in values if str(_cell(v)).strip()}
  return sum(1 for name in fields if name.lower() in lowered)


def _looks_like_header_row(values: list, field_names: list[str] | None = None) -> bool:
  cells = [str(_cell(v)).strip() for v in values]
  nonempty = [c for c in cells if c]
  if len(nonempty) < 2:
    return False
  expect = {str(name).strip().lower() for name in (field_names or []) if name}
  lowered = [c.lower() for c in nonempty]
  if expect:
    return sum(1 for c in lowered if c in expect) >= min(2, len(expect))
  return all(re.match(r"^[A-Za-z][A-Za-z0-9_]*$", c) for c in nonempty)


def _rows_from_named(df, columns: list[dict], headers: list[str]) -> list[dict]:
  remap = {}
  selected = []
  for spec in columns or []:
    src = str(spec.get("from") or spec.get("excel") or "").strip()
    dst = str(spec.get("to") or spec.get("field") or src).strip() or src
    if src:
      remap[src.lower()] = dst
      selected.append(src.lower())
  index_by_name = {str(name).strip().lower(): idx for idx, name in enumerate(headers)}
  rows = []
  for pos in range(len(df.index)):
    item = {}
    if selected:
      for spec in columns:
        src = str(spec.get("from") or spec.get("excel") or "").strip()
        dst = str(spec.get("to") or spec.get("field") or src).strip() or src
        idx = index_by_name.get(src.lower())
        item[dst] = _cell(df.iat[pos, idx]) if idx is not None and idx < len(df.columns) else ""
    else:
      for idx, header in enumerate(headers):
        key = remap.get(header.lower(), header)
        if idx < len(df.columns):
          item[key] = _cell(df.iat[pos, idx])
    if any(str(v) != "" for v in item.values()):
      rows.append(item)
  return rows


def _rows_from_headers(df, columns: list[dict]) -> list[dict]:
  if df is None or df.empty:
    return []
  named = _named_columns(df)
  if named and _headers_match_columns(named, columns):
    return _rows_from_named(df, columns, named)
  headers = []
  for idx, value in enumerate(list(df.iloc[0].values)):
    name = str(_cell(value) or "").strip() or f"col{idx + 1}"
    headers.append(name)
  from_names = _spec_names(columns, "from")
  to_names = _spec_names(columns, "to")
  if not _headers_match_columns(headers, columns) and (from_names or to_names):
    output = to_names or from_names
    if all(EXCEL_COL.match(name) for name in from_names) if from_names else False:
      return _rows_from_letters(df, columns)
    return _rows_from_letters(df, _positional_columns(output))
  data = df.iloc[1:].reset_index(drop=True)
  return _rows_from_named(data, columns, headers)


def _rows_from_letters(df, columns: list[dict]) -> list[dict]:
  if df is None or df.empty:
    return []
  fields = [str(spec.get("to") or spec.get("field") or "") for spec in columns]
  sources = [str(spec.get("from") or spec.get("excel") or "") for spec in columns]
  row0 = list(df.iloc[0].values)
  if _looks_like_header_row(row0, sources) or _looks_like_header_row(row0, fields):
    df = df.iloc[1:].reset_index(drop=True)
  width = len(df.columns)
  rows = []
  for pos in range(len(df.index)):
    item = {}
    for spec in columns:
      src = str(spec.get("from") or spec.get("excel") or "").strip()
      dst = str(spec.get("to") or spec.get("field") or src).strip() or src
      value = ""
      if EXCEL_COL.match(src):
        idx = excel_index(src)
        if idx < width:
          value = df.iat[pos, idx]
      elif src:
        for idx in range(width):
          if str(df.columns[idx]) == src:
            value = df.iat[pos, idx]
            break
      item[dst] = _cell(value)
    if any(str(v) != "" for v in item.values()):
      rows.append(item)
  return rows


def _rows_from_table(path: Path, columns: list[dict], column_mode: str = "", nrows: int | None = None) -> list[dict]:
  df = _read_raw_table(path, nrows=nrows)
  mapping = list(columns or [])
  mode = (column_mode or "").lower()
  from_names = _spec_names(mapping, "from")
  to_names = _spec_names(mapping, "to")
  named = _named_columns(df) if df is not None and not df.empty else []
  row0 = list(df.iloc[0].values) if df is not None and not df.empty else []
  if mode in {"", "auto"}:
    if named and _headers_match_columns(named, mapping):
      mode = "headers"
    elif _headers_match_columns(row0, mapping):
      mode = "headers"
    elif mapping and all(EXCEL_COL.match(str(spec.get("from") or "")) for spec in mapping):
      mode = "letters"
    elif to_names or from_names:
      mode = "letters"
      mapping = _positional_columns(to_names or from_names)
    else:
      mode = "headers"
  if mode == "headers":
    return _rows_from_headers(df, mapping)
  if not mapping and (to_names or from_names):
    mapping = _positional_columns(to_names or from_names)
  return _rows_from_letters(df, mapping or [
    {"from": "A", "to": "col1"},
    {"from": "B", "to": "col2"},
    {"from": "C", "to": "col3"},
  ])


def _find_table_file(source: Path) -> Path:
  if source.is_file():
    return source
  if source.is_dir():
    for pattern in ("*.xlsx", "*.xls", "*.csv", "*.tsv", "*.json"):
      matches = sorted(source.glob(pattern))
      if matches:
        return matches[0]
  raise ValueError("生成脚本需要一个表格文件（xlsx/csv/json）")


def build_fetch_script(rows: list[dict], script: dict, instruction: str = "", preview_limit: int | None = None) -> str:
  url = str(script.get("url") or _extract_url(instruction) or "http://localhost:21006/api/gdal/lineDeduplication")
  method = str(script.get("method") or "POST").upper()
  interval_ms = int(script.get("interval_ms") or 1000)
  headers = script.get("headers") or {"Content-Type": "application/json"}
  template = script.get("body_template")
  if not isinstance(template, dict):
    template = {}
  shown = rows[:preview_limit] if preview_limit else rows
  payload = json.dumps(shown, ensure_ascii=False, indent=2)
  note = ""
  if preview_limit:
    note = f"// 预览仅展示样例 {len(shown)} 条，确认执行后会写入全部数据\n"
  header_json = json.dumps(headers, ensure_ascii=False)
  template_json = json.dumps(template, ensure_ascii=False)
  return f"""{note}const rows = {payload};

const url = {json.dumps(url, ensure_ascii=False)};
const method = {json.dumps(method)};
const headers = {header_json};
const bodyTemplate = {template_json};
const intervalMs = {interval_ms};

function sleep(ms) {{
  return new Promise((resolve) => setTimeout(resolve, ms));
}}

async function run() {{
  for (let i = 0; i < rows.length; i += 1) {{
    const row = rows[i];
    const body = Object.keys(bodyTemplate).length ? {{ ...bodyTemplate, ...row }} : row;
    const res = await fetch(url, {{
      method,
      headers,
      body: method === "GET" ? undefined : JSON.stringify(body),
    }});
    console.log(i + 1, "/", rows.length, res.status, row);
    if (i < rows.length - 1) {{
      await sleep(intervalMs);
    }}
  }}
  console.log("全部完成", rows.length);
}}

run();
"""


def _extract_url(text: str) -> str:
  match = re.search(r"https?://[^\s\"']+", text or "")
  return match.group(0) if match else ""


def generate_script(source: str, save_path: str, plan: dict, dry_run: bool = False) -> dict:
  src = _find_table_file(Path(source))
  script = plan.get("script") if isinstance(plan.get("script"), dict) else {}
  instruction = plan.get("instruction") or ""
  url_in_text = _extract_url(instruction)
  if url_in_text:
    script["url"] = url_in_text
  rows = _rows_from_table(
    src,
    script.get("columns") or plan.get("column_map") or [],
    str(script.get("column_mode") or ""),
    nrows=32 if dry_run else None,
  )
  if not rows:
    raise ValueError(f"没有从表格读到数据，请确认文件有内容: {src}")
  code = build_fetch_script(
    rows,
    script,
    instruction,
    preview_limit=8 if dry_run else None,
  )
  dest = Path(save_path) if save_path else src.with_name(src.stem + "_fetch.js")
  if dest.suffix.lower() not in {".js", ".html", ".txt"}:
    dest = dest / f"{src.stem}_fetch.js" if dest.suffix == "" or dest.is_dir() or not dest.suffix else dest.with_suffix(".js")
  files = [{
    "from": str(src.resolve()),
    "from_rel": src.name,
    "to": str(dest),
    "to_rel": dest.name,
    "status": "preview" if dry_run else "generated",
  }]
  sample = rows[:8]
  if dry_run:
    return {
      "output": str(dest),
      "action": "generate_script",
      "dry_run": True,
      "count": len(rows),
      "files": files,
      "code": code,
      "sample": sample,
    }
  dest.parent.mkdir(parents=True, exist_ok=True)
  dest.write_text(code, encoding="utf-8")
  return {
    "output": str(dest.resolve()),
    "action": "generate_script",
    "dry_run": False,
    "count": len(rows),
    "files": files,
    "code": code,
    "sample": sample,
  }


def looks_like_script(instruction: str) -> bool:
  text = instruction or ""
  low = text.lower()
  if "fetch(" in low or "json.stringify" in low:
    return True
  if "浏览器" in text and any(token in text for token in ("执行", "调用", "接口", "代码")):
    return True
  if re.search(r"每\s*\d+", text) and any(token in text for token in ("调用", "请求", "fetch", "接口")):
    return True
  if any(token in text for token in ("数组", "每行")) and any(token in text for token in ("按照", "取成", "做成", "字段", "转换", "key")):
    return True
  return False


def infer_script_plan(instruction: str) -> dict:
  """从自然语言里猜脚本方案，只做兜底，不限定 name/age/time。"""
  text = instruction or ""
  columns = []
  column_mode = "headers" if re.search(r"表头|列名|字段名|按字段", text) else ""

  for match in re.finditer(
    r"([A-Za-z])\s*列\s*(?:作为|改成|映射为|取成|按照)\s*([A-Za-z0-9_\u4e00-\u9fff]+)",
    text,
  ):
    columns.append({"from": match.group(1).upper(), "to": match.group(2)})

  if not columns:
    for match in re.finditer(
      r"把?([A-Za-z0-9_\u4e00-\u9fff]{1,20})\s*(?:列|字段|表头)?\s*(?:作为|映射为|改成)\s*([A-Za-z0-9_\u4e00-\u9fff]+)",
      text,
    ):
      src, dst = match.group(1), match.group(2)
      if src.lower() in {"把", "将", "其中"}:
        continue
      columns.append({"from": src.upper() if EXCEL_COL.match(src) else src, "to": dst})

  letters = _extract_letter_columns(text)
  sources, targets = _extract_source_and_target_fields(text)
  fields = targets or sources

  if not columns and letters:
    column_mode = "letters"
    if fields and len(fields) >= len(letters):
      columns = [{"from": letter, "to": fields[idx]} for idx, letter in enumerate(letters)]
    elif fields:
      columns = [{"from": letter, "to": fields[idx] if idx < len(fields) else letter.lower()} for idx, letter in enumerate(letters)]
    else:
      columns = [{"from": letter, "to": letter.lower()} for letter in letters]
  elif not columns and (sources or targets):
    column_mode = column_mode or "auto"
    columns = _zip_columns(sources, targets)
  elif columns and all(EXCEL_COL.match(str(item.get("from") or "")) for item in columns):
    column_mode = "letters"
  else:
    column_mode = column_mode or "auto"

  interval = 1000
  sec = re.search(r"每\s*(\d+(?:\.\d+)?)\s*秒", text) or re.search(r"每\s*(\d+)\s*s", text, re.I)
  if sec:
    interval = int(float(sec.group(1)) * 1000)
  url = _extract_url(text) or "http://localhost:21006/api/gdal/lineDeduplication"
  method = "POST"
  if re.search(r"\bGET\b", text, re.I):
    method = "GET"
  return {
    "action": "generate_script",
    "script": {
      "kind": "browser_fetch",
      "url": url,
      "method": method,
      "interval_ms": interval,
      "headers": {"Content-Type": "application/json"},
      "body_template": {},
      "column_mode": column_mode,
      "columns": columns,
    },
  }
