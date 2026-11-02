from __future__ import annotations

import base64
import math
from pathlib import Path

from llm.engine import chat, runtime_status
from llm.georef import fit_transform
from llm.io_preview import extract_json

_LEGEND_CACHE: dict[str, dict] = {}

LEGEND_SYSTEM = """你是地图图例读取助手。只看图例，不要标地图上的点位，不要经纬度。只输出 JSON。
按图例条目从上到下列出，名称用图上原文。

{"legend":[{"name":"医院","shape":"point","color":"#c0392b"},{"name":"控制区","shape":"polygon","color":"#27ae60"},{"name":"往路线","shape":"line","color":"#2980b9"}],"legend_box":{"x":0,"y":0,"w":0,"h":0},"notes":""}

shape 只能是 point（小图标）、polygon（色块/填色范围，如城区、景区、控制区）或 line（路线）。
color 必须是图例符号的真实六位十六进制，禁止写 #RRGGBB。
"""


def _vision_preview(path: Path, max_side: int = 1024) -> tuple[Path, float, int, int]:
  from PIL import Image

  with Image.open(path) as im:
    rgb = im.convert("RGB")
    w, h = rgb.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1:
      rgb = rgb.resize((max(1, int(w * scale)), max(1, int(h * scale))))
    dest = path.with_name(path.stem + "_vl.jpg")
    rgb.save(dest, format="JPEG", quality=85)
    pw, ph = rgb.size
    return dest, (pw / w if w else 1.0), pw, ph


def image_to_data_url(path: str | Path) -> str:
  raw = Path(path).read_bytes()
  suffix = Path(path).suffix.lower().lstrip(".")
  mime = "image/png" if suffix == "png" else "image/webp" if suffix == "webp" else "image/jpeg"
  if suffix == "gif":
    mime = "image/gif"
  b64 = base64.b64encode(raw).decode("ascii")
  return f"data:{mime};base64,{b64}"


def _legend_cache_key(image: Path, instruction: str, user_box) -> str:
  import hashlib
  import json
  digest = hashlib.md5()
  digest.update(image.read_bytes())
  digest.update((instruction or "").encode("utf-8"))
  digest.update(json.dumps(user_box if isinstance(user_box, dict) else {}, sort_keys=True, ensure_ascii=False).encode("utf-8"))
  return digest.hexdigest()


def legend_user_prompt(width: int, height: int, instruction: str = "", legend_box_user=None) -> str:
  prompt = "按图例从上到下列出全部条目（名称、shape、真实颜色）。shape 用 point / polygon / line。颜色用六位十六进制，不要写 #RRGGBB。不要标地图上的图标坐标。"
  extra = (instruction or "").strip()
  if extra:
    prompt += f"\n用户补充：{extra}"
  user_hint = _parse_box(legend_box_user)
  if user_hint:
    prompt += (
      f"\n用户已框出图例区域（原图像素）：x={user_hint['x']:.0f}, y={user_hint['y']:.0f}, "
      f"w={user_hint['w']:.0f}, h={user_hint['h']:.0f}。"
    )
  prompt += f"\n图像素宽高是 {width}x{height}，legend_box 用这个坐标系。"
  return prompt


def read_legend(image_path: str, instruction: str = "", legend_box_user=None) -> dict:
  image = Path(image_path)
  if not image.is_file():
    raise FileNotFoundError("图片不存在")
  from PIL import Image

  with Image.open(image) as im:
    width, height = im.size
  status = runtime_status()
  legend = []
  notes = ""
  used_vision = False
  raw = ""
  legend_box = None
  if status.get("vision_enabled"):
    used_vision = True
    user_hint = _parse_box(legend_box_user)
    cache_key = _legend_cache_key(image, instruction, user_hint)
    cached = _LEGEND_CACHE.get(cache_key)
    if cached:
      legend = [dict(item) for item in cached.get("legend") or []]
      legend_box = cached.get("legend_box")
      notes = cached.get("notes") or ""
      raw = cached.get("raw") or ""
    else:
      preview, preview_scale, pw, ph = _vision_preview(image)
      box_scale = (1.0 / preview_scale) if preview_scale else 1.0
      prompt = legend_user_prompt(pw, ph, instruction, user_hint)
      raw = chat(
        [
          {"role": "system", "content": LEGEND_SYSTEM},
          {
            "role": "user",
            "content": [
              {"type": "image_url", "image_url": {"url": image_to_data_url(preview)}},
              {"type": "text", "text": prompt},
            ],
          },
        ],
        temperature=0,
        json_mode=False,
        max_tokens=700,
      )
      try:
        parsed = extract_json(raw)
      except Exception as exc:
        parsed = {}
        notes = f"图例 JSON 解析失败：{exc}"
      else:
        notes = str((parsed or {}).get("notes") or "")
      legend = _normalize_legend(parsed.get("legend") if isinstance(parsed, dict) else [], box_scale)
      legend_box = _usable_legend_box(
        _scale_box_dict(parsed.get("legend_box") if isinstance(parsed, dict) else None, box_scale),
        width, height,
      )
      if len(_LEGEND_CACHE) >= 8:
        _LEGEND_CACHE.pop(next(iter(_LEGEND_CACHE)))
      _LEGEND_CACHE[cache_key] = {
        "legend": [dict(item) for item in legend],
        "legend_box": legend_box,
        "notes": notes,
        "raw": raw,
      }
  else:
    notes = "未加载视觉模型（需要 Qwen2.5-VL 主文件 + mmproj）。"

  user_box = _usable_legend_box(_parse_box(legend_box_user), width, height)
  if user_box:
    legend_box = user_box
  return {
    "width": width,
    "height": height,
    "legend": legend,
    "legend_box": legend_box,
    "notes": notes,
    "used_vision": used_vision,
    "raw": raw,
  }


def recognize_map(image_path: str, gcps: list[dict], instruction: str = "", legend_box_user=None) -> dict:
  image = Path(image_path)
  labeled = read_legend(str(image), instruction, legend_box_user)
  width = labeled["width"]
  height = labeled["height"]
  legend = labeled["legend"]
  legend_box = labeled["legend_box"]
  notes = labeled["notes"]
  used_vision = labeled["used_vision"]
  raw = labeled["raw"]
  georef = fit_transform(gcps)
  if not used_vision:
    extra = "已有四角经纬度，图上要素需加载视觉模型后识别。"
    notes = f"{notes} {extra}".strip() if notes else extra
  try:
    cv_feats = detect_features(image, legend, georef["matrix"], width, height, legend_box) if legend else []
  except Exception as exc:
    notes = (notes + "；" if notes else "") + f"图上定位失败：{exc}"
    cv_feats = []
  features = _merge_all_features([], cv_feats)
  features = _dedupe_map_points(features)
  for index, feat in enumerate(features, start=1):
    feat["id"] = index
  geojson = features_to_geojson(features, georef)
  if legend and not features:
    extra = "图例已识别，但图片上没有标出对应点/面。可框选图例后重试。"
    notes = f"{notes} {extra}".strip() if notes else extra
  return {
    "width": width,
    "height": height,
    "georef": georef,
    "legend": legend,
    "legend_box": legend_box,
    "features": features,
    "geojson": geojson,
    "notes": notes,
    "used_vision": used_vision,
    "raw": raw,
  }


def _parse_box(raw) -> dict | None:
  if not isinstance(raw, dict):
    return None
  try:
    x = float(raw.get("x", raw.get("left", 0)) or 0)
    y = float(raw.get("y", raw.get("top", 0)) or 0)
    if raw.get("w") is not None or raw.get("width") is not None:
      w = float(raw.get("w") or raw.get("width") or 0)
      h = float(raw.get("h") or raw.get("height") or 0)
    else:
      w = float(raw.get("right") or 0) - x
      h = float(raw.get("bottom") or 0) - y
  except (TypeError, ValueError):
    return None
  if w <= 1 or h <= 1:
    return None
  return {"x": x, "y": y, "w": w, "h": h}


def _scale_box_dict(raw, scale: float) -> dict | None:
  box = _parse_box(raw)
  if not box:
    return None
  return {
    "x": box["x"] * scale,
    "y": box["y"] * scale,
    "w": box["w"] * scale,
    "h": box["h"] * scale,
  }


def _normalize_legend(raw, box_scale: float = 1.0) -> list[dict]:
  items = []
  if not isinstance(raw, list):
    return items
  for row in raw:
    if not isinstance(row, dict):
      continue
    name = str(row.get("name") or row.get("label") or "").strip()
    if not name or _is_placeholder_name(name):
      continue
    shape = _shape_of(row.get("shape"), name)
    items.append({
      "name": name,
      "description": str(row.get("description") or row.get("desc") or "").strip(),
      "color": _normalize_color(row.get("color") or row.get("hex") or ""),
      "shape": shape,
      "icon_box": _scale_box_dict(row.get("icon_box") or row.get("symbol_box") or row.get("sample_box"), box_scale),
    })
  return items


def _is_placeholder_name(name: str) -> bool:
  text = (name or "").strip()
  if text in {"名称", "与图例相同的名称", "示例", "样例", "label", "name", "图例"}:
    return True
  if "与图例相同" in text:
    return True
  return False


def _merge_all_features(vision: list[dict], opencv: list[dict]) -> list[dict]:
  return [
    feat for feat in (opencv or [])
    if not _is_placeholder_name(feat.get("name") or "")
  ]


def _shape_from_name(name: str) -> str | None:
  text = name or ""
  if any(key in text for key in ("路线", "道路", "航线", "管线")):
    return "line"
  if any(key in text for key in (
    "城区", "建成区", "景区", "控制区", "核心区", "警戒区",
    "范围", "用地", "绿地", "水面", "湖泊", "园区",
  )):
    return "polygon"
  return None


def _shape_of(value, name: str = "") -> str:
  shape = str(value or "").strip().lower()
  if shape in {"area", "fill", "region", "面", "polygon", "rect", "rectangle", "box", "swatch"}:
    return "polygon"
  if shape in {"polyline", "线", "linestring", "line"}:
    return "line"
  inferred = _shape_from_name(name)
  if inferred:
    return inferred
  if shape in {"icon", "marker", "点", "symbol", "poi", "point"}:
    return "point"
  return "point"


def _usable_legend_box(box, width: int, height: int):
  parsed = _parse_box(box) if not (isinstance(box, dict) and "w" in box and "h" in box and "x" in box) else box
  if not parsed:
    return None
  if parsed["w"] * parsed["h"] > width * height * 0.28:
    return None
  return parsed


def _xy_of(row: dict) -> tuple[float, float] | None:
  for a, b in (("x", "y"), ("px", "py"), ("left", "top")):
    if row.get(a) is not None and row.get(b) is not None:
      try:
        return float(row[a]), float(row[b])
      except (TypeError, ValueError):
        return None
  loc = row.get("position") or row.get("point") or row.get("xy")
  if isinstance(loc, (list, tuple)) and len(loc) >= 2:
    try:
      return float(loc[0]), float(loc[1])
    except (TypeError, ValueError):
      return None
  return None


def _clamp_xy(x: float, y: float, width: int, height: int) -> tuple[float, float] | tuple[None, None]:
  if -width * 0.15 <= x <= width * 1.15 and -height * 0.15 <= y <= height * 1.15:
    return min(width - 1, max(0.0, x)), min(height - 1, max(0.0, y))
  return None, None


def _normalize_vision_features(raw, box_scale: float, width: int, height: int, legend_box, preview_w: int = 0, preview_h: int = 0, poly_names=None) -> list[dict]:
  items = []
  if not isinstance(raw, list):
    return items
  poly_names = poly_names or set()
  scale = _guess_xy_scale(raw, box_scale, width, height, preview_w, preview_h)
  for row in raw:
    if not isinstance(row, dict):
      continue
    name = str(row.get("name") or row.get("label") or "").strip()
    if not name or _is_placeholder_name(name):
      continue
    color = _normalize_color(row.get("color") or row.get("hex") or "")
    declared = str(row.get("shape") or "point").strip().lower()
    want_poly = declared in {"polygon", "area", "fill"} or name in poly_names
    geom = None
    try:
      ring = row.get("ring")
      pts = []
      if isinstance(ring, list):
        for pt in ring:
          if isinstance(pt, (list, tuple)) and len(pt) >= 2:
            pts.append([float(pt[0]) * scale, float(pt[1]) * scale])
      if want_poly and len(pts) >= 3:
        if pts[0] != pts[-1]:
          pts.append(pts[0])
        x = sum(p[0] for p in pts[:-1]) / max(1, len(pts) - 1)
        y = sum(p[1] for p in pts[:-1]) / max(1, len(pts) - 1)
        geom = {"type": "Polygon", "coordinates": [pts], "x": x, "y": y, "shape": "polygon"}
      elif want_poly:
        continue
      else:
        xy = _xy_of(row)
        if xy is None:
          continue
        x, y = xy[0] * scale, xy[1] * scale
        geom = {"type": "Point", "coordinates": [x, y], "x": x, "y": y, "shape": "point"}
    except (TypeError, ValueError):
      continue
    if geom is None:
      continue
    xy2 = _clamp_xy(geom["x"], geom["y"], width, height)
    if xy2[0] is None:
      continue
    geom["x"], geom["y"] = xy2
    if geom["type"] == "Point":
      geom["coordinates"] = [geom["x"], geom["y"]]
    geom.update({"name": name, "description": str(row.get("description") or ""), "color": color})
    items.append(geom)
  return items


def _guess_xy_scale(raw, box_scale: float, width: int, height: int, preview_w: int, preview_h: int) -> float:
  xs, ys = [], []
  for row in raw or []:
    if not isinstance(row, dict):
      continue
    try:
      if row.get("x") is not None and row.get("y") is not None:
        xs.append(float(row["x"]))
        ys.append(float(row["y"]))
    except (TypeError, ValueError):
      continue
  if not xs:
    return box_scale or 1.0
  mx, my = max(xs), max(ys)
  # 模型看的是预览图：坐标落在预览宽高内则换算回原图
  if preview_w and mx <= preview_w * 1.12 and my <= (preview_h or preview_w) * 1.12:
    return box_scale or 1.0
  return 1.0


def _project_vision_features(rows: list[dict], matrix) -> list[dict]:
  features = []
  for row in rows:
    coords = _project_coords(row["coordinates"], row["type"], matrix)
    if not coords:
      continue
    lng, lat = _first_lnglat(row["type"], coords)
    features.append({
      "name": row["name"],
      "description": row.get("description") or "",
      "color": row.get("color") or "",
      "shape": row.get("shape") or "point",
      "type": row["type"],
      "x": row["x"],
      "y": row["y"],
      "lng": lng,
      "lat": lat,
      "coordinates": coords,
      "score": 1.0,
      "pixels": 1,
    })
  return features


def _normalize_color(value) -> str:
  text = str(value or "").strip()
  if text.upper() in {"#RRGGBB", "#RGB", "RRGGBB"}:
    return ""
  if text.startswith("#") and len(text) in {4, 7}:
    body = text[1:]
    if not all(ch in "0123456789abcdefABCDEF" for ch in body):
      return ""
    if len(text) == 4:
      return "#" + "".join(ch * 2 for ch in body)
    return ("#" + body).upper()
  return ""


def _hex_to_rgb(color: str) -> tuple[int, int, int] | None:
  text = (color or "").lstrip("#")
  if len(text) != 6:
    return None
  try:
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
  except ValueError:
    return None


def _rgb_dist(a, b) -> float:
  if not a or not b:
    return 999.0
  return float(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5)


def _item_fill(icon, item: dict):
  hex_rgb = _hex_to_rgb((item or {}).get("color") or "")
  if hex_rgb:
    return hex_rgb
  sampled = _swatch_color(icon, "")
  if sampled and (max(sampled) - min(sampled) >= 18) and sum(sampled) < 680:
    return sampled
  return _fill_color(icon, (item or {}).get("color") or "")


def _collect_poly_fills(arr, legend: list[dict]) -> list[tuple[int, int, int]]:
  fills = []
  for item in legend or []:
    if (item.get("shape") or "") != "polygon":
      continue
    icon = _trim_symbol(_crop_box(arr, item.get("icon_box"), pad=2))
    rgb = _item_fill(icon, item)
    if rgb:
      fills.append(rgb)
  return fills


def detect_features(image_path: Path, legend: list[dict], matrix: list[list[float]], width: int, height: int, legend_box=None) -> list[dict]:
  if not legend:
    return []
  from PIL import Image
  import numpy as np

  with Image.open(image_path) as im:
    rgb = im.convert("RGB")
    arr = np.array(rgb, dtype=np.uint8, copy=True)

  work_scale = min(1.0, 900 / max(width, height))
  if work_scale < 1:
    work = Image.fromarray(arr).resize((max(1, int(width * work_scale)), max(1, int(height * work_scale))))
    work_arr = np.array(work, dtype=np.uint8, copy=True)
  else:
    work_arr = arr
    work_scale = 1.0
  legend_inner = _clip_box(legend_box, width, height) or _guess_legend_rect(arr)
  for item in legend or []:
    item["shape"] = _shape_of(item.get("shape"), item.get("name") or "")
    item["color"] = _normalize_color(item.get("color") or "")
  _fill_icon_boxes(arr, legend, legend_inner)
  legend_rect = _expand_rect(legend_inner, width, height, pad=12)
  poly_fills = _collect_poly_fills(arr, legend)

  features = []
  for item in legend:
    shape = item.get("shape") or "point"
    icon = _trim_symbol(_crop_box(arr, item.get("icon_box"), pad=2))
    if shape == "polygon":
      own = _item_fill(icon, item)
      rivals = [rgb for rgb in poly_fills if _rgb_dist(own, rgb) > 14]
      found = _extract_areas(work_arr, icon, item, work_scale, legend_rect, width, height, rivals)
    elif shape == "line":
      found = _extract_lines(work_arr, icon, item, work_scale, legend_rect, width, height, poly_fills)
    else:
      found = _extract_icons(
        work_arr, icon, item, work_scale, legend_rect, width, height, poly_fills, legend,
      )
    for geom in found:
      coords = _project_coords(geom["coordinates"], geom["type"], matrix)
      if not coords:
        continue
      lng, lat = _first_lnglat(geom["type"], coords)
      features.append({
        "name": item["name"],
        "description": item["description"],
        "color": item.get("color") or "",
        "shape": shape,
        "type": geom["type"],
        "x": geom["x"],
        "y": geom["y"],
        "lng": lng,
        "lat": lat,
        "coordinates": coords,
        "score": geom.get("score", 0),
        "pixels": geom.get("pixels", 0),
        "color_dist": geom.get("color_dist", 0),
      })
  features = [feat for feat in features if not _in_legend(feat["x"], feat["y"], legend_rect)]
  features = _dedupe_map_points(features)
  features = _assign_shared_color_lines(features, legend)
  features = _subtract_scenic_from_urban(features)
  return features[:400]


def _to_gray(arr):
  import numpy as np
  return (0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]).astype(np.float32)


def _clip_box(box, width: int, height: int):
  parsed = _parse_box(box)
  if not parsed:
    return None
  x0 = int(max(0, parsed["x"]))
  y0 = int(max(0, parsed["y"]))
  x1 = int(min(width, parsed["x"] + parsed["w"]))
  y1 = int(min(height, parsed["y"] + parsed["h"]))
  if x1 - x0 < 4 or y1 - y0 < 4:
    return None
  return x0, y0, x1, y1


def _crop_box(arr, box, pad: int = 0):
  parsed = _parse_box(box)
  if parsed is None:
    return None
  h, w = arr.shape[:2]
  x0 = int(max(0, parsed["x"] - pad))
  y0 = int(max(0, parsed["y"] - pad))
  x1 = int(min(w, parsed["x"] + parsed["w"] + pad))
  y1 = int(min(h, parsed["y"] + parsed["h"] + pad))
  if x1 - x0 < 4 or y1 - y0 < 4:
    return None
  return arr[y0:y1, x0:x1].copy()


def _in_legend(x: float, y: float, legend_rect, _scale: float = 1.0) -> bool:
  if not legend_rect:
    return False
  return legend_rect[0] <= x <= legend_rect[2] and legend_rect[1] <= y <= legend_rect[3]


def _expand_rect(rect, width: int, height: int, pad: int = 16):
  if not rect:
    return None
  x0, y0, x1, y1 = rect
  return (
    max(0, int(x0 - pad)),
    max(0, int(y0 - pad)),
    min(width, int(x1 + pad)),
    min(height, int(y1 + pad)),
  )


def _union_icon_boxes(rect, legend: list[dict], width: int, height: int):
  boxes = []
  if rect:
    boxes.append(rect)
  for item in legend or []:
    clipped = _clip_box(item.get("icon_box"), width, height)
    if clipped:
      boxes.append(clipped)
  if not boxes:
    return rect
  x0 = min(b[0] for b in boxes)
  y0 = min(b[1] for b in boxes)
  x1 = max(b[2] for b in boxes)
  y1 = max(b[3] for b in boxes)
  # icon_boxes 都在图例里时，只扩大已有图例框，避免把整张图并进去
  if rect:
    rx0, ry0, rx1, ry1 = rect
    if x0 >= rx0 - 40 and y0 >= ry0 - 40 and x1 <= rx1 + 40 and y1 <= ry1 + 40:
      return (min(rx0, x0), min(ry0, y0), max(rx1, x1), max(ry1, y1))
    return rect
  return (x0, y0, x1, y1)


def _guess_legend_rect(arr):
  import numpy as np
  h, w = arr.shape[:2]
  white = (arr.min(axis=2) > 248).astype(np.float32)
  k = 21
  if h <= k or w <= k:
    return None
  interior = np.lib.stride_tricks.sliding_window_view(white, (k, k)).mean(axis=(2, 3)) > 0.92
  interior[: max(1, int(h * 0.2)), :] = False
  interior[:, : max(1, int(w * 0.45))] = False
  ys, xs = np.where(interior)
  if len(xs) < 200:
    return None
  x0, y0 = int(xs.min()), int(ys.min())
  x1, y1 = int(xs.max() + k), int(ys.max() + k)
  if (x1 - x0) < w * 0.1 or (y1 - y0) < h * 0.1:
    return None
  if (x1 - x0) * (y1 - y0) > w * h * 0.28:
    return None
  return (x0, y0, x1, y1)


def _blob_chroma(arr, box) -> float:
  import numpy as np
  x0, y0, x1, y1 = box
  patch = arr[y0:y1, x0:x1]
  if patch.size == 0:
    return 0.0
  rgb = patch.reshape(-1, 3).astype(np.float32)
  return float((rgb.max(axis=1) - rgb.min(axis=1)).mean())


def _legend_ink(crop):
  import numpy as np
  pix = crop.astype(np.float32)
  bg = np.median(pix.reshape(-1, 3), axis=0)
  dist = np.sqrt(((pix - bg) ** 2).sum(axis=2))
  chroma = pix.max(axis=2) - pix.min(axis=2)
  lum = pix.mean(axis=2)
  bg_lum = float(bg.mean())
  colorful = chroma > 22
  dark = (lum < bg_lum - 40) & (dist > 28) & (chroma > 8)
  return colorful | dark


def _legend_symbols(arr, legend_rect) -> list[dict]:
  x0, y0, x1, y1 = legend_rect
  crop = arr[y0:y1, x0:x1]
  if crop.size == 0:
    return []
  ink = _legend_ink(crop)
  blobs = []
  ch, cw = crop.shape[:2]
  for pixels in _connected_components(ink, min_cells=6, limit=160):
    xs = [p[0] for p in pixels]
    ys = [p[1] for p in pixels]
    bx0, bx1, by0, by1 = min(xs), max(xs), min(ys), max(ys)
    bw, bh = bx1 - bx0 + 1, by1 - by0 + 1
    if bw < 3 or bh < 3 or bw * bh < 18:
      continue
    if max(bw, bh) < 6:
      continue
    if bw >= cw * 0.9 and bh >= ch * 0.45:
      continue
    blobs.append((x0 + bx0, y0 + by0, x0 + bx1, y0 + by1))
  if not blobs:
    return []
  blobs.sort(key=lambda b: (b[1] + b[3]) / 2)
  heights = sorted(max(4, b[3] - b[1]) for b in blobs)
  gap = max(12, heights[len(heights) // 2] * 1.15)
  rows: list[dict] = []
  for b in blobs:
    cy = (b[1] + b[3]) / 2
    if rows and abs(cy - rows[-1]["cy"]) <= gap:
      rows[-1]["blobs"].append(b)
      n = len(rows[-1]["blobs"])
      rows[-1]["cy"] = (rows[-1]["cy"] * (n - 1) + cy) / n
    else:
      rows.append({"cy": cy, "blobs": [b]})
  symbols = []
  for row in rows:
    colorful = [b for b in row["blobs"] if _blob_chroma(arr, b) >= 12]
    if not colorful:
      continue
    colored = min(colorful, key=lambda b: b[0])
    symbols.append({
      "x": colored[0],
      "y": colored[1],
      "w": max(4, colored[2] - colored[0]),
      "h": max(4, colored[3] - colored[1]),
    })
  return symbols


def _fill_icon_boxes(arr, legend: list[dict], legend_rect) -> None:
  if not legend_rect or not legend:
    return
  symbols = _legend_symbols(arr, legend_rect)
  if not symbols:
    return
  symbols = sorted(symbols, key=lambda box: box["y"])
  colors = []
  for box in symbols:
    crop = _trim_symbol(_crop_box(arr, box, pad=2))
    fg = _icon_fg_mask(crop) if crop is not None else None
    colors.append(_dominant_icon_rgb(crop, fg, "") if crop is not None else None)
  if len(symbols) == len(legend):
    for item, box in zip(legend, symbols):
      item["icon_box"] = dict(box)
      if not _hex_to_rgb(item.get("color") or ""):
        crop = _trim_symbol(_crop_box(arr, box, pad=2))
        fg = _icon_fg_mask(crop) if crop is not None else None
        rgb = _dominant_icon_rgb(crop, fg, "") if crop is not None else None
        if rgb:
          item["color"] = "#{:02X}{:02X}{:02X}".format(*rgb)
    return
  used = set()
  for index, item in enumerate(legend):
    target = _hex_to_rgb(item.get("color") or "")
    shape = item.get("shape") or "point"
    best_i = None
    best_cost = 1e9
    for i, box in enumerate(symbols):
      if i in used:
        continue
      rgb = colors[i]
      color_d = _rgb_dist(rgb, target) if rgb and target else 40.0
      order_d = abs(i - index) * 26.0
      thin = box["h"] <= 6 and box["w"] >= max(8, box["h"] * 2)
      if shape == "line":
        kind_d = 0.0 if thin else 22.0
      elif thin:
        kind_d = 45.0
      elif shape == "polygon":
        kind_d = 0.0 if box["w"] >= 10 and box["h"] >= 10 else 18.0
      else:
        kind_d = 12.0 if box["w"] >= 14 and box["h"] >= 12 and box["h"] <= 18 else 0.0
      cost = color_d + order_d + kind_d + _name_color_bias(item.get("name") or "", rgb)
      if cost < best_cost:
        best_cost = cost
        best_i = i
    if best_i is None:
      continue
    used.add(best_i)
    box = dict(symbols[best_i])
    if shape == "point" and box["h"] > 8 and box["w"] > box["h"] * 1.6:
      box["w"] = max(4, int(box["h"] * 1.25))
    item["icon_box"] = box
    if not _hex_to_rgb(item.get("color") or ""):
      crop = _trim_symbol(_crop_box(arr, box, pad=2))
      fg = _icon_fg_mask(crop) if crop is not None else None
      rgb = _dominant_icon_rgb(crop, fg, "") if crop is not None else None
      if rgb:
        item["color"] = "#{:02X}{:02X}{:02X}".format(*rgb)


def _trim_symbol(arr):
  import numpy as np
  if arr is None or arr.size == 0:
    return arr
  pix = arr.astype(np.float32)
  chroma = pix.max(axis=2) - pix.min(axis=2)
  lum = pix.mean(axis=2)
  bg_lum = float(np.median(lum))
  ink = (chroma > 18) | (lum < bg_lum - 18)
  if not ink.any():
    return arr
  ys, xs = np.where(ink)
  y0, y1 = int(ys.min()), int(ys.max()) + 1
  x0, x1 = int(xs.min()), int(xs.max()) + 1
  pad = 1
  y0 = max(0, y0 - pad)
  x0 = max(0, x0 - pad)
  y1 = min(arr.shape[0], y1 + pad)
  x1 = min(arr.shape[1], x1 + pad)
  if x1 - x0 < 4 or y1 - y0 < 4:
    return arr
  return arr[y0:y1, x0:x1].copy()


def _icon_bg_rgb(icon):
  import numpy as np
  h, w = icon.shape[:2]
  border = np.concatenate([
    icon[0, :].reshape(-1, 3),
    icon[-1, :].reshape(-1, 3),
    icon[1:-1, 0].reshape(-1, 3) if h > 2 else icon[:, 0].reshape(-1, 3),
    icon[1:-1, -1].reshape(-1, 3) if h > 2 else icon[:, -1].reshape(-1, 3),
  ], axis=0).astype(np.float32)
  return np.median(border, axis=0)


def _icon_fg_mask(icon):
  """图例底色视为透明：与边框底色接近的像素不参与匹配。"""
  import numpy as np
  if icon is None or icon.size == 0:
    return None
  bg = _icon_bg_rgb(icon)
  pix = icon.astype(np.float32)
  dist = np.sqrt(((pix - bg) ** 2).sum(axis=2))
  chroma = pix.max(axis=2) - pix.min(axis=2)
  lum = pix.mean(axis=2)
  bg_lum = float(bg.mean())
  fg = (dist > 26.0) | (chroma > 20.0)
  if bg_lum > 220:
    fg = fg | (lum < bg_lum - 18)
  if int(fg.sum()) < 8:
    fg = chroma > 12
  return fg


def _resize_mask(mask, tw: int, th: int):
  from PIL import Image
  import numpy as np
  img = Image.fromarray((mask.astype(np.uint8) * 255))
  return np.asarray(img.resize((tw, th), Image.Resampling.NEAREST)) > 127


def _is_urban_name(name: str) -> bool:
  text = name or ""
  return any(key in text for key in ("城区", "建成区", "城镇", "市区", "居住用地", "建设用地"))


def _is_scenic_name(name: str) -> bool:
  text = name or ""
  return any(key in text for key in ("景区", "景点", "风景", "绿地", "公园"))


def _name_color_bias(name: str, rgb) -> float:
  if not rgb:
    return 0.0
  r, g, b = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
  if any(key in (name or "") for key in ("景区", "绿地", "公园", "风景")):
    return 0.0 if g > r + 4 and g > b else 28.0
  if _is_urban_name(name or ""):
    if g > r + 14 and g > b + 8:
      return 42.0
    return 0.0
  if any(key in (name or "") for key in ("饭店", "餐饮", "酒店", "餐馆")):
    return 0.0 if r > g + 8 and r > b + 4 else 18.0
  return 0.0


def _peer_point_colors(item: dict, peers: list[dict], icon, fg):
  own = _dominant_icon_rgb(icon, fg, item.get("color") or "")
  others = []
  for peer in peers or []:
    if peer is item:
      continue
    if (peer.get("shape") or "point") != "point":
      continue
    rgb = _hex_to_rgb(peer.get("color") or "")
    if rgb:
      others.append(rgb)
  return own, others


def _color_unique_among(own, others) -> bool:
  if not own:
    return False
  for rgb in others or []:
    if _rgb_dist(own, rgb) < 48:
      return False
  return True


def _is_simple_color_mark(icon, fg) -> bool:
  import numpy as np
  if icon is None or icon.size == 0:
    return False
  h, w = icon.shape[:2]
  if h < 4 or w < 4 or h > 36 or w > 36:
    return False
  if max(h, w) / max(1, min(h, w)) > 1.7:
    return False
  mask = fg if fg is not None else np.ones((h, w), dtype=bool)
  n = int(np.asarray(mask).sum())
  if n < 8:
    return False
  fill = n / float(h * w)
  if fill < 0.28 or fill > 0.92:
    return False
  pix = icon[np.asarray(mask)].astype(np.float32)
  chroma = float((pix.max(axis=1) - pix.min(axis=1)).mean())
  return chroma >= 28


def _extract_icons(work_arr, icon, item: dict, work_scale: float, legend_rect, width: int, height: int, poly_fills=None, peers=None) -> list[dict]:
  import numpy as np
  if icon is None or icon.size == 0 or icon.shape[0] < 4 or icon.shape[1] < 4:
    rgb = _hex_to_rgb(item.get("color") or "")
    if not rgb:
      return []
    icon = np.full((12, 12, 3), rgb, dtype=np.uint8)
    fg = _icon_fg_mask(icon)
    found = _extract_color_spots(work_arr, icon, item, work_scale, legend_rect, width, height, poly_fills or [])
  else:
    fg = _icon_fg_mask(icon)
    templates = _extract_icon_templates(work_arr, icon, item, fg, work_scale, legend_rect, width, height)
    spots = _extract_color_spots(work_arr, icon, item, work_scale, legend_rect, width, height, poly_fills or [])
    found = list(spots) + [row for row in templates if row[4] <= 14]
  if not found:
    return []
  icon_r = max(18.0, max(icon.shape[0], icon.shape[1]) * 1.3)
  merged = _nms([(x, y, s) for x, y, s, _, _ in found], icon_r)
  merged = sorted(merged, key=lambda row: row[2], reverse=True)
  best = merged[0][2]
  merged = [row for row in merged if row[2] >= max(0.50, best * 0.88)][:4]
  extra = {(round(x, 1), round(y, 1)): (p, d) for x, y, s, p, d in found}
  out = []
  for x, y, score in merged:
    pix, dist = extra.get((round(x, 1), round(y, 1)), (16, 99))
    out.append({
      "type": "Point",
      "coordinates": [x, y],
      "x": x,
      "y": y,
      "score": score,
      "pixels": int(pix),
      "color_dist": float(dist),
    })
  return out


def _extract_icon_templates(work_arr, icon, item, fg, work_scale, legend_rect, width, height) -> list[tuple]:
  from PIL import Image
  import numpy as np

  gray = _to_gray(work_arr)
  icon_match = icon.copy()
  if fg is not None and fg.shape[:2] == icon.shape[:2]:
    icon_match = icon.copy()
    icon_match[~np.asarray(fg)] = np.array(_map_base_rgb(work_arr), dtype=np.uint8)
  templ_gray = _to_gray(icon_match)
  found = []
  for scale in (0.7, 0.85, 1.0, 1.2):
    tw = max(7, int(round(icon.shape[1] * work_scale * scale)))
    th = max(7, int(round(icon.shape[0] * work_scale * scale)))
    if tw >= gray.shape[1] or th >= gray.shape[0]:
      continue
    mask_small = _resize_mask(fg, tw, th) if fg is not None else None
    stride = max(1, min(tw, th) // 4)
    templ_small = np.asarray(Image.fromarray(templ_gray.astype("uint8")).resize((tw, th)), dtype=np.float32)
    peaks = _match_template(gray, templ_small, threshold=0.50, stride=stride, mask=mask_small)
    for x, y, score in peaks:
      ox = x / work_scale
      oy = y / work_scale
      if _in_legend(ox, oy, legend_rect, 1.0):
        continue
      if ox < 0 or oy < 0 or ox >= width or oy >= height:
        continue
      color_d = _icon_color_dist(work_arr, icon, item, x, y, tw, th, mask_small, fg)
      if color_d is None or color_d > 48:
        continue
      found.append((ox, oy, score, tw * th, color_d))
  return found


def _extract_color_spots(work_arr, icon, item, work_scale, legend_rect, width, height, poly_fills) -> list[tuple]:
  import numpy as np
  fg = _icon_fg_mask(icon)
  target = _hex_to_rgb(item.get("color") or "") or _dominant_icon_rgb(icon, fg, item.get("color") or "")
  if target is None:
    return []
  hits = _hue_mask(work_arr, target, hue_tol=20, min_sat=36)
  for fill in poly_fills or []:
    if _rgb_dist(target, fill) > 22:
      hits = hits & ~_area_color_mask(work_arr, fill)
  hits = _blank_legend(hits, legend_rect, work_scale)
  icon_area = max(16, int(icon.shape[0] * icon.shape[1] * work_scale * work_scale))
  scale = 1.0 / work_scale
  out = []
  for pixels in _connected_components(hits, min_cells=max(6, icon_area // 5), limit=50):
    if len(pixels) < icon_area * 0.2 or len(pixels) > icon_area * 4.5:
      continue
    xs = [p[0] for p in pixels]
    ys = [p[1] for p in pixels]
    bw = max(xs) - min(xs) + 1
    bh = max(ys) - min(ys) + 1
    if bw < 4 or bh < 4:
      continue
    if max(bw, bh) / max(1, min(bw, bh)) > 2.2:
      continue
    fill_ratio = len(pixels) / float(bw * bh)
    if fill_ratio < 0.22 or fill_ratio > 0.96:
      continue
    ox = (sum(xs) / len(xs)) * scale
    oy = (sum(ys) / len(ys)) * scale
    if _in_legend(ox, oy, legend_rect, 1.0):
      continue
    if ox < 0 or oy < 0 or ox >= width or oy >= height:
      continue
    patch = np.array([work_arr[p[1], p[0]] for p in pixels], dtype=np.float32)
    chroma = patch.max(axis=1) - patch.min(axis=1)
    vivid = patch[chroma >= 24] if int((chroma >= 24).sum()) >= 4 else patch
    target_v = np.array(target, dtype=np.float32)
    d = np.sqrt(((vivid - target_v) ** 2).sum(axis=1))
    k = max(3, len(d) // 3)
    dist = float(np.median(np.sort(d)[:k]))
    if dist > 14:
      continue
    ncc = _ncc_at(work_arr, icon, fg, ox, oy, work_scale)
    out.append((ox, oy, max(0.52, ncc), len(pixels), dist))
  return out


def _ncc_at(work_arr, icon, fg, ox: float, oy: float, work_scale: float) -> float:
  import numpy as np
  if icon is None or icon.size == 0:
    return 0.4
  gray = _to_gray(work_arr)
  tw = max(7, int(round(icon.shape[1] * work_scale)))
  th = max(7, int(round(icon.shape[0] * work_scale)))
  cx = int(ox * work_scale)
  cy = int(oy * work_scale)
  x0 = max(0, cx - tw // 2)
  y0 = max(0, cy - th // 2)
  x1 = min(gray.shape[1], x0 + tw)
  y1 = min(gray.shape[0], y0 + th)
  if x1 - x0 < 5 or y1 - y0 < 5:
    return 0.4
  from PIL import Image
  templ = np.asarray(Image.fromarray(_to_gray(icon).astype("uint8")).resize((x1 - x0, y1 - y0)), dtype=np.float32)
  patch = gray[y0:y1, x0:x1].astype(np.float32)
  mask = None
  if fg is not None:
    mask = _resize_mask(fg, x1 - x0, y1 - y0).astype(np.float32)
    if float(mask.sum()) < 8:
      mask = np.ones_like(templ)
  else:
    mask = np.ones_like(templ)
  t = (templ - (templ * mask).sum() / (mask.sum() + 1e-6)) * mask
  p = (patch - (patch * mask).sum() / (mask.sum() + 1e-6)) * mask
  denom = float(np.sqrt((t * t).sum() * (p * p).sum())) + 1e-6
  return float((t * p).sum() / denom)


def _hue_mask(arr, rgb, hue_tol: int = 30, min_sat: int = 32):
  from PIL import Image
  import numpy as np
  hsv = np.asarray(Image.fromarray(arr.astype(np.uint8)).convert("HSV"))
  th, ts, _ = _hsv_of(rgb)
  dh = np.abs(hsv[:, :, 0].astype(np.int16) - int(th))
  dh = np.minimum(dh, 255 - dh)
  return (dh <= hue_tol) & (hsv[:, :, 1] >= min(min_sat, max(18, int(ts) * 0.35)))


def _dedupe_map_points(features: list[dict]) -> list[dict]:
  points = [f for f in features if f.get("type") == "Point"]
  rest = [f for f in features if f.get("type") != "Point"]

  def key(feat):
    score = float(feat.get("score") or 0)
    dist = float(feat.get("color_dist") or 99)
    return (-(score - min(dist, 90) / 140.0), dist)

  points.sort(key=key)
  kept = []
  for feat in points:
    x, y = float(feat.get("x") or 0), float(feat.get("y") or 0)
    hit = None
    hit_i = -1
    for i, other in enumerate(kept):
      dx = x - float(other.get("x") or 0)
      dy = y - float(other.get("y") or 0)
      if dx * dx + dy * dy < 30 * 30:
        hit = other
        hit_i = i
        break
    if hit is None:
      kept.append(feat)
      continue
    if (hit.get("name") or "") == (feat.get("name") or ""):
      continue
    hit_dist = float(hit.get("color_dist") or 99)
    feat_dist = float(feat.get("color_dist") or 99)
    hit_score = float(hit.get("score") or 0)
    feat_score = float(feat.get("score") or 0)
    if feat_score > hit_score + 0.04 or (feat_dist + 8 < hit_dist and feat_score >= hit_score - 0.08):
      kept[hit_i] = feat
  return rest + kept


def _assign_shared_color_lines(features: list[dict], legend: list[dict]) -> list[dict]:
  line_names = [item.get("name") for item in legend or [] if (item.get("shape") or "") == "line"]
  if not line_names:
    return features
  colors = {}
  for item in legend or []:
    if (item.get("shape") or "") == "line":
      colors[item.get("name")] = _hex_to_rgb(item.get("color") or "")
  rest = [feat for feat in features if feat.get("type") != "LineString"]
  by_name: dict[str, list[dict]] = {}
  for feat in features:
    if feat.get("type") == "LineString":
      by_name.setdefault(feat.get("name") or "", []).append(feat)
  grouped: list[list[str]] = []
  taken = set()
  for i, name in enumerate(line_names):
    if name in taken:
      continue
    group = [name]
    taken.add(name)
    for other in line_names[i + 1:]:
      if other in taken:
        continue
      if colors.get(name) and colors.get(other) and _rgb_dist(colors[name], colors[other]) < 52:
        group.append(other)
        taken.add(other)
    grouped.append(group)
  out = []
  for group in grouped:
    geoms = []
    for name in group:
      geoms.extend(by_name.get(name) or [])
    geoms.sort(key=lambda row: int(row.get("pixels") or 0), reverse=True)
    uniq = []
    for geom in geoms:
      if any((geom["x"] - other["x"]) ** 2 + (geom["y"] - other["y"]) ** 2 < 48 * 48 for other in uniq):
        continue
      uniq.append(geom)
    for name, geom in zip(group, uniq):
      row = dict(geom)
      row["name"] = name
      out.append(row)
  return rest + out


def _hsv_of(rgb) -> tuple[float, float, float]:
  from PIL import Image
  import numpy as np
  pix = np.uint8([[list(rgb)]])
  h, s, v = np.asarray(Image.fromarray(pix).convert("HSV"))[0, 0]
  return float(h), float(s), float(v)


def _hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
  from PIL import Image
  import numpy as np
  pix = np.uint8([[[int(max(0, min(255, h))), int(max(0, min(255, s))), int(max(0, min(255, v)))]]])
  r, g, b = np.asarray(Image.fromarray(pix, "HSV").convert("RGB"))[0, 0]
  return int(r), int(g), int(b)


def _vivid_rgb(rgb) -> tuple[int, int, int]:
  h, s, v = _hsv_of(rgb)
  return _hsv_to_rgb(h, max(s, 200), min(200, max(90, v)))


def _dominant_icon_rgb(icon, icon_fg=None, fallback_hex: str = ""):
  import numpy as np
  if icon is None or not getattr(icon, "size", 0):
    return _hex_to_rgb(fallback_hex or "")
  if icon_fg is not None and icon_fg.shape[:2] == icon.shape[:2] and int(np.asarray(icon_fg).sum()) >= 6:
    pix = icon[np.asarray(icon_fg)].astype(np.float32)
  else:
    pix = icon.reshape(-1, 3).astype(np.float32)
  chroma = pix.max(axis=1) - pix.min(axis=1)
  colorful = pix[chroma >= 16]
  sample = colorful if len(colorful) >= 6 else pix
  mid = np.median(sample, axis=0)
  return int(mid[0]), int(mid[1]), int(mid[2])


def _icon_color_dist(work_arr, icon, item: dict, cx: float, cy: float, tw: int, th: int, fg_mask=None, icon_fg=None) -> float | None:
  """只比图标前景像素，避免城区填色把饭店/景点滤掉。"""
  import numpy as np
  h, w = work_arr.shape[:2]
  x0 = max(0, int(cx - tw / 2))
  y0 = max(0, int(cy - th / 2))
  x1 = min(w, x0 + tw)
  y1 = min(h, y0 + th)
  patch = work_arr[y0:y1, x0:x1]
  if patch.size < 12:
    return None
  target = np.array(_dominant_icon_rgb(icon, icon_fg, item.get("color") or ""), dtype=np.float32)
  hex_rgb = _hex_to_rgb(item.get("color") or "")
  if hex_rgb:
    target = 0.45 * target + 0.55 * np.array(hex_rgb, dtype=np.float32)
  mask = None
  if fg_mask is not None:
    mh, mw = min(fg_mask.shape[0], patch.shape[0]), min(fg_mask.shape[1], patch.shape[1])
    if mh >= 3 and mw >= 3 and int(np.asarray(fg_mask[:mh, :mw]).sum()) >= 6:
      mask = np.asarray(fg_mask[:mh, :mw]) > 0
      pix = patch[:mh, :mw][mask].astype(np.float32)
    else:
      pix = patch.reshape(-1, 3).astype(np.float32)
  else:
    pix = patch.reshape(-1, 3).astype(np.float32)
  if len(pix) < 4:
    return None
  chroma = pix.max(axis=1) - pix.min(axis=1)
  sample = pix[chroma >= 12] if int((chroma >= 12).sum()) >= 4 else pix
  mid = np.median(sample, axis=0)
  dist = float(np.linalg.norm(mid - target))
  t_chroma = float(target.max() - target.min())
  limit = 86.0 if t_chroma >= 18 else 58.0
  if dist > limit:
    return None
  dh = abs(_hsv_of(tuple(int(x) for x in mid))[0] - _hsv_of(tuple(int(x) for x in target))[0])
  dh = min(dh, 255 - dh)
  if t_chroma >= 18 and dh > 36:
    return None
  return dist


def _icon_color_ok(work_arr, icon, item: dict, cx: float, cy: float, tw: int, th: int, fg_mask=None, icon_fg=None) -> bool:
  return _icon_color_dist(work_arr, icon, item, cx, cy, tw, th, fg_mask, icon_fg) is not None


def _match_template(image, templ, threshold: float = 0.48, stride: int = 2, mask=None):
  import numpy as np
  image = np.ascontiguousarray(image, dtype=np.float32)
  templ = np.ascontiguousarray(templ, dtype=np.float32)
  if image.ndim != 2 or templ.ndim != 2:
    return []
  h, w = templ.shape
  H, W = image.shape
  if h < 3 or w < 3 or H < h or W < w:
    return []
  if mask is None:
    weight = np.ones((h, w), dtype=np.float32)
  else:
    weight = np.ascontiguousarray(mask, dtype=np.float32)
    if weight.shape != (h, w):
      return []
    weight = (weight > 0.5).astype(np.float32)
  msum = float(weight.sum())
  if msum < 8:
    return []
  t = (templ - (templ * weight).sum() / msum) * weight
  t_norm = math.sqrt(float((t * t).sum())) + 1e-6
  stride = max(1, int(stride))
  wins = np.lib.stride_tricks.sliding_window_view(image, (h, w))[::stride, ::stride]
  win_mean = (wins * weight).sum(axis=(2, 3), keepdims=True) / msum
  p = (wins - win_mean) * weight
  denom = np.sqrt((p * p).sum(axis=(2, 3))) * t_norm + 1e-6
  score = (p * t).sum(axis=(2, 3)) / denom
  ys, xs = np.where(score >= threshold)
  hits = [
    (float(x * stride + w / 2.0), float(y * stride + h / 2.0), float(score[y, x]))
    for y, x in zip(ys.tolist(), xs.tolist())
  ]
  return _nms(hits, max(w, h) * 0.75)


def _match_template_color(image, templ, threshold: float = 0.62, stride: int = 2, mask=None):
  import numpy as np
  image = np.ascontiguousarray(image, dtype=np.float32)
  templ = np.ascontiguousarray(templ, dtype=np.float32)
  if image.ndim != 3 or templ.ndim != 3:
    return []
  h, w = templ.shape[:2]
  H, W = image.shape[:2]
  if h < 3 or w < 3 or H < h or W < w:
    return []
  if mask is None:
    weight = np.ones((h, w), dtype=np.float32)
  else:
    weight = (np.ascontiguousarray(mask) > 0.5).astype(np.float32)
    if weight.shape != (h, w):
      return []
  msum = float(weight.sum())
  if msum < 8:
    return []
  w3 = weight[:, :, None]
  t_mean = (templ * w3).sum(axis=(0, 1), keepdims=True) / msum
  t = (templ - t_mean) * w3
  t_norm = math.sqrt(float((t * t).sum())) + 1e-6
  stride = max(1, int(stride))
  wins = np.lib.stride_tricks.sliding_window_view(image, (h, w, 3))[::stride, ::stride, 0]
  win_mean = (wins * w3).sum(axis=(2, 3), keepdims=True) / msum
  p = (wins - win_mean) * w3
  denom = np.sqrt((p * p).sum(axis=(2, 3, 4))) * t_norm + 1e-6
  score = (p * t).sum(axis=(2, 3, 4)) / denom
  ys, xs = np.where(score >= threshold)
  hits = [
    (float(x * stride + w / 2.0), float(y * stride + h / 2.0), float(score[y, x]))
    for y, x in zip(ys.tolist(), xs.tolist())
  ]
  return _nms(hits, max(w, h) * 0.75)


def _nms(hits: list[tuple[float, float, float]], radius: float) -> list[tuple[float, float, float]]:
  ordered = sorted(hits, key=lambda item: item[2], reverse=True)
  kept = []
  for x, y, score in ordered:
    if any((x - kx) ** 2 + (y - ky) ** 2 < radius * radius for kx, ky, _ in kept):
      continue
    kept.append((x, y, score))
    if len(kept) >= 250:
      break
  return kept


def _extract_areas(work_arr, icon, item: dict, work_scale: float, legend_rect, width: int, height: int, rivals=None) -> list[dict]:
  import numpy as np
  fill = _item_fill(icon, item)
  if fill is None:
    return []
  rivals = [rgb for rgb in (rivals or []) if _rgb_dist(fill, rgb) > 14]
  overlay = _area_overlay_mask(work_arr, fill, rivals)
  strict = _area_color_mask(work_arr, fill)
  if rivals:
    for other in rivals:
      strict = strict & ~_area_color_mask(work_arr, other)
  mask = overlay | strict
  img_area = width * height
  min_area = max(36 if rivals else 80, int(img_area * 0.00015))
  mask = _blank_legend(mask, legend_rect, work_scale)
  mask = _morph_close(mask, 9)
  scale = 1.0 / work_scale
  img_area = width * height
  blobs = []
  for pixels in _connected_components(mask, min_cells=min_area, limit=60):
    if len(pixels) < min_area:
      continue
    if len(pixels) * (scale * scale) > img_area * 0.72:
      continue
    xs = [p[0] for p in pixels]
    ys = [p[1] for p in pixels]
    bw = max(xs) - min(xs) + 1
    bh = max(ys) - min(ys) + 1
    if max(bw, bh) * scale < 36:
      continue
    if max(bw, bh) / max(1, min(bw, bh)) > 3.2:
      continue
    blobs.append(pixels)
  blobs = _merge_close_blobs(blobs, gap=14)
  geoms = []
  for pixels in blobs:
    xs = [p[0] for p in pixels]
    ys = [p[1] for p in pixels]
    cx = (sum(xs) / len(xs)) * scale
    cy = (sum(ys) / len(ys)) * scale
    if _in_legend(cx, cy, legend_rect, 1.0):
      continue
    if cx < 0 or cy < 0 or cx >= width or cy >= height:
      continue
    ring = _region_contour(pixels, scale)
    if len(ring) < 4:
      continue
    geoms.append({
      "type": "Polygon",
      "coordinates": [ring],
      "x": cx,
      "y": cy,
      "pixels": len(pixels),
      "score": 1.0,
    })
  geoms.sort(key=lambda g: g["pixels"], reverse=True)
  if not geoms:
    return []
  cover = geoms[0]["pixels"] * (scale * scale) / max(1, img_area)
  urban = _is_urban_name(str(item.get("name") or ""))
  if cover > 0.08 and not urban:
    return geoms[:1]
  cutoff = geoms[0]["pixels"] * (0.28 if urban else 0.55)
  return [g for g in geoms if g["pixels"] >= cutoff][: (3 if urban else 1)]


def _extract_lines(work_arr, icon, item: dict, work_scale: float, legend_rect, width: int, height: int, poly_fills=None) -> list[dict]:
  fill = _hex_to_rgb(item.get("color") or "") or _fill_color(icon, item.get("color") or "")
  if fill is None:
    return []
  bg = _map_base_rgb(work_arr)
  if _hue_close(fill, bg, 16):
    return []
  mask = _area_overlay_mask(work_arr, fill, poly_fills)
  mask = _blank_legend(mask, legend_rect, work_scale)
  mask = _morph_close(mask, 7)
  scale = 1.0 / work_scale
  img_area = width * height
  geoms = []
  for pixels in _connected_components(mask, min_cells=16, limit=40):
    if len(pixels) < 16:
      continue
    if len(pixels) * (scale * scale) > img_area * 0.01:
      continue
    xs = [p[0] for p in pixels]
    ys = [p[1] for p in pixels]
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    bw = max(xs) - min(xs) + 1
    bh = max(ys) - min(ys) + 1
    if span < 14:
      continue
    if max(bw, bh) / max(1, min(bw, bh)) < 1.55:
      continue
    cx = (sum(xs) / len(xs)) * scale
    cy = (sum(ys) / len(ys)) * scale
    if _in_legend(cx, cy, legend_rect, 1.0):
      continue
    if cx < 0 or cy < 0 or cx >= width or cy >= height:
      continue
    path = _polyline_from_pixels(pixels, scale)
    if len(path) < 2:
      continue
    geoms.append({
      "type": "LineString",
      "coordinates": path,
      "x": cx,
      "y": cy,
      "pixels": len(pixels),
      "score": 1.0,
    })
  geoms.sort(key=lambda g: g["pixels"], reverse=True)
  if not geoms:
    return []
  cutoff = geoms[0]["pixels"] * 0.22
  return [g for g in geoms if g["pixels"] >= cutoff][:3]


def _blank_legend(mask, legend_rect, work_scale: float):
  if not legend_rect:
    return mask
  x0 = int(legend_rect[0] * work_scale)
  y0 = int(legend_rect[1] * work_scale)
  x1 = int(legend_rect[2] * work_scale)
  y1 = int(legend_rect[3] * work_scale)
  mask[y0:y1, x0:x1] = False
  return mask


def _color_mask(arr, rgb, rgb_tol: float = 55, hue_tol: int = 20):
  import numpy as np
  from PIL import Image
  target = np.array(rgb, dtype=np.float32)
  diff = arr.astype(np.float32) - target
  rgb_d = np.sqrt((diff * diff).sum(axis=2))
  hsv = np.asarray(Image.fromarray(arr).convert("HSV"))
  th, ts, _tv = np.asarray(Image.fromarray(np.uint8([[rgb]])).convert("HSV"))[0, 0]
  dh = np.abs(hsv[:, :, 0].astype(np.int16) - int(th))
  dh = np.minimum(dh, 255 - dh)
  min_sat = min(40, max(18, int(ts) * 0.35))
  hue_ok = (dh <= hue_tol) & (hsv[:, :, 1] >= min_sat)
  return (rgb_d <= rgb_tol) | hue_ok


def _map_base_rgb(arr):
  import numpy as np
  lum = arr.astype(np.float32).mean(axis=2)
  dark = lum < 90
  if float(dark.mean()) > 0.35:
    return tuple(int(v) for v in np.median(arr[dark], axis=0))
  paper = lum > 210
  if float(paper.mean()) > 0.18:
    return tuple(int(v) for v in np.median(arr[paper], axis=0))
  return tuple(int(v) for v in np.median(arr.reshape(-1, 3), axis=0))


def _hue_close(a, b, tol: int = 18) -> bool:
  ha, sa, _ = _hsv_of(a)
  hb, sb, _ = _hsv_of(b)
  dh = abs(ha - hb)
  dh = min(dh, 255 - dh)
  return dh <= tol and min(sa, sb) >= 12


def _blend_t_dist(arr, rgb, bg):
  import numpy as np
  fill = np.array(_vivid_rgb(rgb), dtype=np.float32)
  pix = arr.astype(np.float32)
  direction = fill - bg
  n2 = float(np.dot(direction, direction)) + 1e-6
  t = ((pix - bg) * direction).sum(axis=2) / n2
  dist = np.sqrt(((pix - (bg + t[..., None] * direction)) ** 2).sum(axis=2))
  return t, dist


def _area_overlay_mask(arr, rgb, rivals=None):
  """半透明填色：像素落在底图色与图例色的连线上，并分给更近的图例色。"""
  import numpy as np
  bg = np.array(_map_base_rgb(arr), dtype=np.float32)
  if _hue_close(_vivid_rgb(rgb), bg, 16):
    return np.zeros(arr.shape[:2], dtype=bool)
  t, dist = _blend_t_dist(arr, rgb, bg)
  ok = (t >= 0.25) & (t <= 1.08) & (dist <= 20)
  for other in rivals or []:
    if _rgb_dist(rgb, other) < 14:
      continue
    _t2, dist2 = _blend_t_dist(arr, other, bg)
    ok = ok & ~((dist2 + 4 < dist) & (_t2 >= 0.22) & (_t2 <= 1.1))
  return ok


def _area_color_mask(arr, rgb):
  """面状填色：跟图例色块比 RGB/亮度，避免松散色相把整张底图吞掉。"""
  import numpy as np
  target = np.array(rgb, dtype=np.float32)
  pix = arr.astype(np.float32)
  rgb_d = np.sqrt(((pix - target) ** 2).sum(axis=2))
  lum = pix.mean(axis=2)
  t_lum = float(target.mean())
  chroma = pix.max(axis=2) - pix.min(axis=2)
  t_chroma = float(target.max() - target.min())
  paper = lum > 242
  if t_chroma < 28:
    tol = max(28.0, float(np.linalg.norm(target)) * 0.14)
    lum_ok = np.abs(lum - t_lum) <= max(22.0, t_lum * 0.16)
    chroma_ok = np.abs(chroma - t_chroma) <= max(26.0, t_chroma * 0.75)
    return (rgb_d <= tol) & lum_ok & chroma_ok & ~paper
  tol = max(22.0, float(np.linalg.norm(target)) * 0.12)
  lum_ok = np.abs(lum - t_lum) <= max(16.0, t_lum * 0.12)
  chroma_ok = np.abs(chroma - t_chroma) <= max(18.0, t_chroma * 0.45)
  return (rgb_d <= tol) & lum_ok & chroma_ok & ~paper


def _merge_close_blobs(groups: list[list[tuple[int, int]]], gap: float) -> list[list[tuple[int, int]]]:
  if len(groups) <= 1:
    return groups
  boxes = []
  for pixels in groups:
    xs = [p[0] for p in pixels]
    ys = [p[1] for p in pixels]
    boxes.append((min(xs), min(ys), max(xs), max(ys)))
  parent = list(range(len(groups)))

  def find(i):
    while parent[i] != i:
      parent[i] = parent[parent[i]]
      i = parent[i]
    return i

  def bbox_gap(a, b):
    dx = max(0, a[0] - b[2], b[0] - a[2])
    dy = max(0, a[1] - b[3], b[1] - a[3])
    return math.hypot(dx, dy)

  for i in range(len(groups)):
    for j in range(i + 1, len(groups)):
      if bbox_gap(boxes[i], boxes[j]) <= gap:
        pi, pj = find(i), find(j)
        if pi != pj:
          parent[pj] = pi
  buckets: dict[int, list[tuple[int, int]]] = {}
  for i, pixels in enumerate(groups):
    buckets.setdefault(find(i), []).extend(pixels)
  return list(buckets.values())


def _morph_close(mask, k: int = 5):
  import numpy as np
  if k < 3 or mask is None or getattr(mask, "size", 0) == 0:
    return mask
  if min(mask.shape[:2]) < 2:
    return mask
  pad = k // 2
  m = np.pad(mask.astype(bool), pad, mode="constant", constant_values=False)
  win = np.lib.stride_tricks.sliding_window_view(m, (k, k))
  dilated = win.any(axis=(2, 3))
  m2 = np.pad(dilated, pad, mode="constant", constant_values=True)
  win2 = np.lib.stride_tricks.sliding_window_view(m2, (k, k))
  return win2.all(axis=(2, 3))


def _swatch_color(icon, fallback_hex: str):
  import numpy as np
  if icon is None or not getattr(icon, "size", 0):
    return _hex_to_rgb(fallback_hex or "")
  pix = icon.reshape(-1, 3).astype(np.float32)
  keep = pix.min(axis=1) < 240
  sample = pix[keep] if int(keep.sum()) > 8 else pix
  mid = np.median(sample, axis=0)
  return int(mid[0]), int(mid[1]), int(mid[2])


def _fill_color(icon, fallback_hex: str, fg_mask=None):
  import numpy as np
  if icon is not None and icon.size:
    pixels = icon.reshape(-1, 3).astype(np.float32)
    if fg_mask is not None and fg_mask.shape[:2] == icon.shape[:2] and int(np.asarray(fg_mask).sum()) >= 8:
      pixels = icon[np.asarray(fg_mask)].astype(np.float32)
    chroma = pixels.max(axis=1) - pixels.min(axis=1)
    lum = pixels.sum(axis=1)
    keep = (lum < 720) & (lum > 80)
    sample = pixels[keep] if int(keep.sum()) > 8 else pixels
    ch = chroma[keep] if int(keep.sum()) > 8 else chroma
    colorful = sample[ch >= max(8.0, float(np.percentile(ch, 55)))]
    if len(colorful) < 6:
      colorful = sample
    mid = np.median(colorful, axis=0)
    if float(ch.mean()) < 8:
      hex_rgb = _hex_to_rgb(fallback_hex or "")
      if hex_rgb:
        return hex_rgb
    return int(mid[0]), int(mid[1]), int(mid[2])
  return _hex_to_rgb(fallback_hex or "")


def _region_contour(pixels: list[tuple[int, int]], scale: float) -> list[list[float]]:
  import numpy as np
  xs = [p[0] for p in pixels]
  ys = [p[1] for p in pixels]
  x0, x1 = min(xs), max(xs)
  y0, y1 = min(ys), max(ys)
  local = np.zeros((y1 - y0 + 3, x1 - x0 + 3), dtype=np.uint8)
  for x, y in pixels:
    local[y - y0 + 1, x - x0 + 1] = 255
  closed = _morph_close(local > 0, 7)
  if closed is not None and getattr(closed, "shape", None) == local.shape:
    local = closed.astype(np.uint8) * 255
  ring = _cv_contour(local, x0 - 1, y0 - 1, scale)
  if len(ring) >= 4:
    return ring
  return _region_ring(pixels, scale)


def _cv_contour(local, ox: int, oy: int, scale: float) -> list[list[float]]:
  try:
    import cv2
  except ImportError:
    return []
  if local is None or getattr(local, "size", 0) == 0:
    return []
  try:
    contours, _ = cv2.findContours(local, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
  except Exception:
    return []
  if not contours:
    return []
  cnt = max(contours, key=cv2.contourArea)
  if cv2.contourArea(cnt) < 16:
    return []
  peri = cv2.arcLength(cnt, True)
  approx = cv2.approxPolyDP(cnt, max(1.5, 0.006 * peri), True)
  pts = approx.reshape(-1, 2)
  if len(pts) < 3:
    pts = cnt.reshape(-1, 2)
  ring = [[float((x + ox) * scale), float((y + oy) * scale)] for x, y in pts.tolist()]
  if ring and ring[0] != ring[-1]:
    ring.append(ring[0])
  return ring


def _region_ring(pixels: list[tuple[int, int]], scale: float) -> list[list[float]]:
  from shapely.geometry import MultiPoint

  if len(pixels) > 3500:
    step = max(1, len(pixels) // 2500)
    pixels = pixels[::step]
  geom = MultiPoint([(x * scale, y * scale) for x, y in pixels])
  hull = None
  try:
    hull = geom.concave_hull(ratio=0.18)
  except Exception:
    hull = None
  if hull is None or hull.geom_type != "Polygon" or hull.is_empty:
    hull = geom.convex_hull
  if hull.geom_type != "Polygon" or hull.is_empty:
    return []
  return [[float(x), float(y)] for x, y in hull.exterior.coords]


def _feature_polygon(feat: dict):
  from shapely.geometry import Polygon

  coords = feat.get("coordinates")
  if not isinstance(coords, list) or not coords:
    return None
  ring = coords[0] if isinstance(coords[0], list) else coords
  if not isinstance(ring, list) or len(ring) < 4:
    return None
  try:
    geom = Polygon([(float(p[0]), float(p[1])) for p in ring if isinstance(p, (list, tuple)) and len(p) >= 2])
  except Exception:
    return None
  if geom.is_empty or not geom.is_valid:
    try:
      geom = geom.buffer(0)
    except Exception:
      return None
  if geom.is_empty:
    return None
  return geom


def _subtract_scenic_from_urban(features: list[dict]) -> list[dict]:
  urban = [f for f in features if f.get("type") == "Polygon" and _is_urban_name(str(f.get("name") or ""))]
  scenic = [
    f for f in features
    if f.get("type") == "Polygon" and any(key in str(f.get("name") or "") for key in ("景区", "绿地", "公园", "风景"))
  ]
  if not urban or not scenic:
    return features
  try:
    from shapely.ops import unary_union
  except Exception:
    return features
  holes = []
  for feat in scenic:
    geom = _feature_polygon(feat)
    if geom is not None:
      holes.append(geom)
  if not holes:
    return features
  try:
    hole = unary_union(holes)
  except Exception:
    return features
  out = []
  urban_ids = {id(f) for f in urban}
  for feat in features:
    if id(feat) not in urban_ids:
      out.append(feat)
      continue
    geom = _feature_polygon(feat)
    if geom is None:
      out.append(feat)
      continue
    try:
      diff = geom.difference(hole)
    except Exception:
      out.append(feat)
      continue
    if diff.is_empty:
      continue
    parts = list(diff.geoms) if diff.geom_type == "MultiPolygon" else [diff]
    parts = [p for p in parts if getattr(p, "geom_type", "") == "Polygon" and p.area >= geom.area * 0.08]
    if not parts:
      continue
    for index, part in enumerate(parts):
      item = dict(feat)
      ring = [[float(x), float(y)] for x, y in part.exterior.coords]
      item["coordinates"] = [ring]
      item["lng"] = round(float(part.centroid.x), 8)
      item["lat"] = round(float(part.centroid.y), 8)
      if index:
        item["id"] = None
      out.append(item)
  return out


def features_to_geojson(features: list[dict], georef: dict | None = None) -> dict:
  items = []
  for feat in features or []:
    geometry = _geojson_geometry(feat.get("type") or "Point", feat.get("coordinates"))
    if not geometry:
      continue
    items.append({
      "type": "Feature",
      "id": feat.get("id"),
      "properties": {
        "id": feat.get("id"),
        "name": feat.get("name") or "",
        "description": feat.get("description") or "",
        "color": feat.get("color") or "",
        "shape": feat.get("shape") or "",
        "x": feat.get("x"),
        "y": feat.get("y"),
        "lng": feat.get("lng"),
        "lat": feat.get("lat"),
      },
      "geometry": geometry,
    })
  return {
    "type": "FeatureCollection",
    "crs": {"type": "name", "properties": {"name": "EPSG:4326"}},
    "properties": {
      "georef_kind": (georef or {}).get("kind"),
      "mean_error_m": (georef or {}).get("mean_error_m"),
    },
    "features": items,
  }


def _connected_components(mask, min_cells: int = 5, limit: int = 80) -> list[list[tuple[int, int]]]:
  import numpy as np

  h, w = mask.shape
  seen = np.zeros((h, w), dtype=bool)
  groups = []
  for y in range(h):
    for x in range(w):
      if not mask[y, x] or seen[y, x]:
        continue
      stack = [(x, y)]
      seen[y, x] = True
      cells = []
      while stack:
        cx, cy = stack.pop()
        cells.append((cx, cy))
        for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
          if nx < 0 or ny < 0 or nx >= w or ny >= h:
            continue
          if seen[ny, nx] or not mask[ny, nx]:
            continue
          seen[ny, nx] = True
          stack.append((nx, ny))
      if len(cells) >= min_cells:
        groups.append(cells)
  groups.sort(key=len, reverse=True)
  return groups[:limit]


def _polyline_from_pixels(pixels: list[tuple[int, int]], scale: float) -> list[list[float]]:
  import numpy as np

  pts = np.array(pixels, dtype=float)
  mean = pts.mean(axis=0)
  centered = pts - mean
  if len(pts) < 2:
    return [[float(pts[0, 0] * scale), float(pts[0, 1] * scale)]]
  _, _, vh = np.linalg.svd(centered, full_matrices=False)
  axis = vh[0]
  order = np.argsort(centered @ axis)
  ordered = pts[order]
  step = max(1, len(ordered) // 80)
  sampled = ordered[::step]
  if not np.array_equal(sampled[-1], ordered[-1]):
    sampled = np.vstack([sampled, ordered[-1]])
  return [[float(x * scale), float(y * scale)] for x, y in sampled.tolist()]


def _project_coords(coordinates, geom_type: str, matrix: list[list[float]]):
  from llm.georef import apply_matrix

  if geom_type == "Point":
    x, y = coordinates
    lng, lat = apply_matrix(matrix, x, y)
    return [round(lng, 8), round(lat, 8)]
  if geom_type == "LineString":
    line = []
    for x, y in coordinates:
      lng, lat = apply_matrix(matrix, x, y)
      line.append([round(lng, 8), round(lat, 8)])
    return line
  if geom_type == "Polygon":
    rings = []
    for ring in coordinates:
      projected = []
      for x, y in ring:
        lng, lat = apply_matrix(matrix, x, y)
        projected.append([round(lng, 8), round(lat, 8)])
      if projected and projected[0] != projected[-1]:
        projected.append(projected[0])
      rings.append(projected)
    return rings
  return None


def _first_lnglat(geom_type: str, coords) -> tuple[float, float]:
  if geom_type == "Point":
    return coords[0], coords[1]
  if geom_type == "LineString":
    return coords[0][0], coords[0][1]
  return coords[0][0][0], coords[0][0][1]


def _geojson_geometry(geom_type: str, coordinates) -> dict | None:
  if not coordinates or geom_type not in {"Point", "LineString", "Polygon"}:
    return None
  return {"type": geom_type, "coordinates": coordinates}
