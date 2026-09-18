from __future__ import annotations

import base64
import math
from pathlib import Path

from llm.engine import chat, runtime_status
from llm.georef import fit_transform
from llm.io_preview import extract_json

LEGEND_SYSTEM = """你是地图图例识别助手。只输出一个 JSON 对象，不要 Markdown，不要解释。
根据图上的图例列表识别每一项。点状图例名称旁边通常是一个图标，面状图例是色块/填充范围示意，线状图例是一段线。
不要编造经纬度，不要枚举地图上的要素。

必须输出：
{
  "legend": [
    {
      "name": "名称",
      "description": "含义",
      "shape": "point 或 line 或 polygon",
      "icon_box": {"x": 0, "y": 0, "w": 0, "h": 0},
      "color": "#RRGGBB"
    }
  ],
  "legend_box": {"x": 0, "y": 0, "w": 0, "h": 0},
  "notes": "一句话"
}

规则：
1. icon_box 是该图例项「符号」在你看到的这张图上的像素框：点=图标，面=示例色块，线=示例线段。不要把文字框进去。
2. legend_box 是整块图例区域。
3. 所有 x/y/w/h 必须对应你看到的这张图的像素，原点左上。
4. color 只作为辅助，点状图例不要只靠颜色。
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


def recognize_map(image_path: str, gcps: list[dict], instruction: str = "") -> dict:
  image = Path(image_path)
  if not image.is_file():
    raise FileNotFoundError("图片不存在")
  from PIL import Image

  with Image.open(image) as im:
    width, height = im.size
  georef = fit_transform(gcps)
  status = runtime_status()
  legend = []
  notes = ""
  used_vision = False
  raw = ""
  if status.get("vision_enabled"):
    used_vision = True
    preview, preview_scale, pw, ph = _vision_preview(image)
    box_scale = (1.0 / preview_scale) if preview_scale else 1.0
    prompt = "请识别这张地图图片中的图例。"
    extra = (instruction or "").strip()
    if extra:
      prompt += f"\n用户补充：{extra}"
    prompt += f"\n你看到的这张图像素宽高是 {pw}x{ph}，所有 box 必须用这个坐标系。"
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
      temperature=0.1,
      json_mode=True,
      max_tokens=1280,
    )
    try:
      parsed = extract_json(raw)
    except Exception as exc:
      parsed = {}
      notes = f"图例 JSON 解析失败：{exc}"
    else:
      notes = str((parsed or {}).get("notes") or "")
    legend = _normalize_legend(parsed.get("legend") if isinstance(parsed, dict) else [], box_scale)
    legend_box = _scale_box_dict(parsed.get("legend_box") if isinstance(parsed, dict) else None, box_scale)
  else:
    notes = "未加载视觉模型（需要 Qwen2.5-VL 主文件 + mmproj）。已完成控制点配准，图例和要素需加载视觉模型后重试。"
    legend_box = None

  features = detect_features(image, legend, georef["matrix"], width, height, legend_box)
  geojson = features_to_geojson(features, georef)
  if legend and not features:
    extra = "图例已识别，但地图上未匹配到对应图标/范围。可补充说明图例位置。"
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
    if not name:
      continue
    shape = str(row.get("shape") or "point").strip().lower() or "point"
    if shape in {"area", "fill", "region", "面", "polygon", "rect", "rectangle", "box", "swatch"}:
      shape = "polygon"
    elif shape in {"icon", "marker", "点", "symbol", "poi"}:
      shape = "point"
    elif shape in {"polyline", "线", "linestring"}:
      shape = "line"
    else:
      shape = "point"
    if any(key in name for key in ("景区", "城区", "范围", "区域", "面状")) and shape == "point":
      shape = "polygon"
    items.append({
      "name": name,
      "description": str(row.get("description") or row.get("desc") or "").strip(),
      "color": _normalize_color(row.get("color") or row.get("hex") or ""),
      "shape": shape,
      "icon_box": _scale_box_dict(row.get("icon_box") or row.get("symbol_box") or row.get("sample_box"), box_scale),
    })
  return items


def _normalize_color(value) -> str:
  text = str(value or "").strip()
  if text.startswith("#") and len(text) in {4, 7}:
    if len(text) == 4:
      return "#" + "".join(ch * 2 for ch in text[1:])
    return text.upper()
  return ""


def _hex_to_rgb(color: str) -> tuple[int, int, int] | None:
  text = (color or "").lstrip("#")
  if len(text) != 6:
    return None
  try:
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
  except ValueError:
    return None


def detect_features(image_path: Path, legend: list[dict], matrix: list[list[float]], width: int, height: int, legend_box=None) -> list[dict]:
  if not legend:
    return []
  from PIL import Image
  import numpy as np

  with Image.open(image_path) as im:
    rgb = im.convert("RGB")
    arr = np.asarray(rgb, dtype=np.uint8)

  work_scale = min(1.0, 900 / max(width, height))
  if work_scale < 1:
    work = rgb.resize((max(1, int(width * work_scale)), max(1, int(height * work_scale))))
    work_arr = np.asarray(work, dtype=np.uint8)
  else:
    work_arr = arr
    work_scale = 1.0
  gray = _to_gray(work_arr)
  legend_rect = _clip_box(legend_box, width, height) or _guess_legend_rect(arr)
  _fill_icon_boxes(arr, legend, legend_rect)

  features = []
  for item in legend:
    shape = item.get("shape") or "point"
    icon = _crop_box(arr, item.get("icon_box"), pad=2)
    if shape == "polygon":
      found = _extract_areas(work_arr, icon, item, work_scale, legend_rect, width, height)
    elif shape == "line":
      found = _extract_lines(work_arr, icon, item, work_scale, legend_rect, width, height)
    else:
      found = _extract_icons(gray, icon, item, work_scale, legend_rect, width, height)
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
      })
  return features[:600]


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
  return (x0, y0, x1, y1)


def _blob_chroma(arr, box) -> float:
  import numpy as np
  x0, y0, x1, y1 = box
  patch = arr[y0:y1, x0:x1]
  if patch.size == 0:
    return 0.0
  rgb = patch.reshape(-1, 3).astype(np.float32)
  return float((rgb.max(axis=1) - rgb.min(axis=1)).mean())


def _legend_symbols(arr, legend_rect) -> list[dict]:
  x0, y0, x1, y1 = legend_rect
  crop = arr[y0:y1, x0:x1]
  if crop.size == 0:
    return []
  ink = crop.min(axis=2) < 242
  blobs = []
  for pixels in _connected_components(ink, min_cells=8, limit=120):
    xs = [p[0] for p in pixels]
    ys = [p[1] for p in pixels]
    bx0, bx1, by0, by1 = min(xs), max(xs), min(ys), max(ys)
    if bx1 - bx0 < 6 or by1 - by0 < 6:
      continue
    if (bx1 - bx0) * (by1 - by0) < 80:
      continue
    if (bx1 - bx0) < 10 or (by1 - by0) < 10:
      continue
    blobs.append((x0 + bx0, y0 + by0, x0 + bx1, y0 + by1))
  if not blobs:
    return []
  blobs.sort(key=lambda b: (b[1] + b[3]) / 2)
  heights = sorted(b[3] - b[1] for b in blobs)
  gap = max(16, heights[len(heights) // 2] * 1.1)
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
    colored = max(row["blobs"], key=lambda b: _blob_chroma(arr, b) * math.sqrt(max(1, (b[2] - b[0]) * (b[3] - b[1]))))
    if _blob_chroma(arr, colored) < 18:
      continue
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
  if len(symbols) >= len(legend):
    symbols = symbols[-len(legend):]
  panel_area = max(1, (legend_rect[2] - legend_rect[0]) * (legend_rect[3] - legend_rect[1]))
  for item, box in zip(legend, symbols):
    current = item.get("icon_box")
    too_big = False
    if current:
      too_big = (current.get("w") or 0) * (current.get("h") or 0) > panel_area * 0.12
    if (not current) or too_big:
      box = dict(box)
      if box["w"] > box["h"] * 2.1:
        box["x"] = box["x"] + box["w"] - int(box["h"] * 1.3)
        box["w"] = int(box["h"] * 1.3)
      item["icon_box"] = box


def _extract_icons(gray, icon, item: dict, work_scale: float, legend_rect, width: int, height: int) -> list[dict]:
  import numpy as np
  if icon is None:
    return []
  templ = _to_gray(icon)
  if templ.shape[0] < 4 or templ.shape[1] < 4 or float(templ.mean()) > 248:
    return []
  found = []
  from PIL import Image
  for scale in (0.75, 1.0, 1.3):
    tw = max(6, int(round(templ.shape[1] * work_scale * scale)))
    th = max(6, int(round(templ.shape[0] * work_scale * scale)))
    if tw >= gray.shape[1] or th >= gray.shape[0]:
      continue
    templ_small = np.asarray(Image.fromarray(templ.astype("uint8")).resize((tw, th)), dtype=np.float32)
    stride = max(1, min(tw, th) // 5)
    peaks = _match_template(gray, templ_small, threshold=0.63, stride=stride)
    for x, y, score in peaks:
      ox = x / work_scale
      oy = y / work_scale
      if _in_legend(ox, oy, legend_rect, 1.0):
        continue
      if ox < 0 or oy < 0 or ox >= width or oy >= height:
        continue
      found.append((ox, oy, score, tw * th))
  merged = _nms([(x, y, s) for x, y, s, _ in found], 22)
  merged = sorted(merged, key=lambda item: item[2], reverse=True)
  if merged:
    cutoff = merged[0][2] * 0.9
    merged = [item for item in merged if item[2] >= cutoff][:20]
  pixels = {(round(x, 1), round(y, 1), s): p for x, y, s, p in found}
  return [{
    "type": "Point",
    "coordinates": [x, y],
    "x": x,
    "y": y,
    "score": score,
    "pixels": int(pixels.get((round(x, 1), round(y, 1), score), 16)),
  } for x, y, score in merged]


def _match_template(image, templ, threshold: float = 0.48, stride: int = 2):
  import numpy as np
  h, w = templ.shape
  H, W = image.shape
  if H < h or W < w:
    return []
  t = templ - templ.mean()
  t_norm = math.sqrt(float((t * t).sum())) + 1e-6
  wins = np.lib.stride_tricks.sliding_window_view(image, (h, w))[::stride, ::stride]
  mean = wins.mean(axis=(2, 3), keepdims=True)
  p = wins - mean
  denom = np.sqrt((p * p).sum(axis=(2, 3))) * t_norm + 1e-6
  score = (p * t).sum(axis=(2, 3)) / denom
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


def _extract_areas(work_arr, icon, item: dict, work_scale: float, legend_rect, width: int, height: int) -> list[dict]:
  fill = _fill_color(icon, item.get("color"))
  if fill is None:
    return []
  mask = _color_mask(work_arr, fill, rgb_tol=62, hue_tol=20)
  mask = _blank_legend(mask, legend_rect, work_scale)
  geoms = []
  min_area = 220 if icon is None else max(180, int(icon.shape[0] * icon.shape[1] * work_scale * work_scale * 4))
  scale = 1.0 / work_scale
  for pixels in _connected_components(mask):
    if len(pixels) < min_area:
      continue
    xs = [p[0] for p in pixels]
    ys = [p[1] for p in pixels]
    cx = (sum(xs) / len(xs)) * scale
    cy = (sum(ys) / len(ys)) * scale
    if _in_legend(cx, cy, legend_rect, 1.0):
      continue
    if cx < 0 or cy < 0 or cx >= width or cy >= height:
      continue
    ring = _region_ring(pixels, scale)
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
  if geoms:
    cutoff = geoms[0]["pixels"] * 0.22
    geoms = [g for g in geoms if g["pixels"] >= cutoff][:4]
  return geoms


def _extract_lines(work_arr, icon, item: dict, work_scale: float, legend_rect, width: int, height: int) -> list[dict]:
  fill = _fill_color(icon, item.get("color"))
  if fill is None:
    return []
  mask = _color_mask(work_arr, fill, rgb_tol=58, hue_tol=18)
  mask = _blank_legend(mask, legend_rect, work_scale)
  scale = 1.0 / work_scale
  geoms = []
  for pixels in _connected_components(mask):
    if len(pixels) < 18:
      continue
    xs = [p[0] for p in pixels]
    ys = [p[1] for p in pixels]
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    if span < 12:
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
  return geoms


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


def _fill_color(icon, fallback_hex: str):
  import numpy as np
  if icon is not None and icon.size:
    pixels = icon.reshape(-1, 3).astype(np.int16)
    # ignore near-white legend background
    keep = pixels.sum(axis=1) < 720
    sample = pixels[keep] if int(keep.sum()) > 8 else pixels
    mean = sample.mean(axis=0)
    return int(mean[0]), int(mean[1]), int(mean[2])
  return _hex_to_rgb(fallback_hex or "")


def _region_ring(pixels: list[tuple[int, int]], scale: float) -> list[list[float]]:
  from shapely.geometry import MultiPoint

  if len(pixels) > 3500:
    step = max(1, len(pixels) // 2500)
    pixels = pixels[::step]
  hull = MultiPoint([(x * scale, y * scale) for x, y in pixels]).convex_hull
  if hull.geom_type != "Polygon" or hull.is_empty:
    return []
  return [[float(x), float(y)] for x, y in hull.exterior.coords]


def features_to_geojson(features: list[dict], georef: dict | None = None) -> dict:
  items = []
  for feat in features or []:
    geometry = _geojson_geometry(feat.get("type") or "Point", feat.get("coordinates"))
    if not geometry:
      continue
    items.append({
      "type": "Feature",
      "properties": {
        "name": feat.get("name") or "",
        "description": feat.get("description") or "",
        "color": feat.get("color") or "",
        "shape": feat.get("shape") or "",
        "x": feat.get("x"),
        "y": feat.get("y"),
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
