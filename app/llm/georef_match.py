from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def register_photo_to_canvas(
  photo_path: str | Path,
  canvas_path: str | Path,
  west: float,
  south: float,
  east: float,
  north: float,
  use_ai: bool = False,
) -> dict:
  photo = Image.open(photo_path).convert("RGB")
  canvas = Image.open(canvas_path).convert("RGB")
  pw, ph = photo.size
  cw, ch = canvas.size
  if min(pw, ph, cw, ch) < 32:
    raise ValueError("图片或底图截图太小，无法对照")

  best = _match_outlines(photo, canvas)
  geom = None
  if best and best["score"] >= 0.28:
    ax, bx, ay, by = _to_canvas_affine(best, pw, ph, cw, ch)
    geom = _pack_result(
      _corner_pairs(pw, ph, ax, bx, ay, by),
      pw, ph, cw, ch, west, south, east, north,
      score=best["score"],
      method=f"{best['direction']}:{best['mode']}",
      notes="按主路/水体走向对照，忽略线宽和样式。",
    )

  if use_ai and (not geom or float(geom.get("score") or 0) < 0.42):
    ai = _match_with_vision(photo_path, canvas_path, pw, ph, cw, ch, west, south, east, north)
    if ai and (not geom or float(ai.get("score") or 0) >= float(geom.get("score") or 0)):
      return ai

  if geom:
    return geom

  return {
    "matched": False,
    "score": round(float(best["score"]) if best else 0.0, 4),
    "method": f"{best['direction']}:{best['mode']}" if best else "",
    "notes": "当前视野主路/水体走向未对上。请把底图再对齐一点（可略大于图片）。",
  }


def _corner_pairs(pw, ph, ax, bx, ay, by):
  pairs = []
  for x, y, note in (
    (0.0, 0.0, "左上"),
    (float(pw), 0.0, "右上"),
    (float(pw), float(ph), "右下"),
    (0.0, float(ph), "左下"),
  ):
    pairs.append({
      "x": x,
      "y": y,
      "canvas_x": ax * x + bx,
      "canvas_y": ay * y + by,
      "note": note,
    })
  return pairs


def canvas_to_lnglat(x: float, y: float, width: float, height: float, west: float, south: float, east: float, north: float):
  import math

  if width <= 1 or height <= 1:
    raise ValueError("底图尺寸无效")
  lng = west + (x / width) * (east - west)
  clamp = lambda v: min(89.5, max(-89.5, v))
  north_m = math.log(math.tan(math.pi / 4 + math.radians(clamp(north)) / 2))
  south_m = math.log(math.tan(math.pi / 4 + math.radians(clamp(south)) / 2))
  merc = north_m + (y / height) * (south_m - north_m)
  lat = math.degrees(2 * math.atan(math.exp(merc)) - math.pi / 2)
  return round(float(lng), 8), round(float(lat), 8)


def _pack_result(pairs, pw, ph, cw, ch, west, south, east, north, score, method, notes):
  from llm.georef import apply_matrix, fit_transform

  gcps = []
  for item in pairs:
    lng, lat = canvas_to_lnglat(item["canvas_x"], item["canvas_y"], cw, ch, west, south, east, north)
    gcps.append({
      "x": item["x"],
      "y": item["y"],
      "lng": lng,
      "lat": lat,
      "note": item.get("note") or "",
      "canvas_x": item["canvas_x"],
      "canvas_y": item["canvas_y"],
    })
  georef = fit_transform(gcps)
  corners = {}
  for key, x, y in (
    ("topLeft", 0, 0),
    ("topRight", pw, 0),
    ("bottomRight", pw, ph),
    ("bottomLeft", 0, ph),
  ):
    lng, lat = apply_matrix(georef["matrix"], x, y)
    corners[key] = [round(lng, 8), round(lat, 8)]
  lngs = [v[0] for v in corners.values()]
  lats = [v[1] for v in corners.values()]
  return {
    "score": round(float(score), 4),
    "method": method,
    "pairs": pairs,
    "gcps": gcps,
    "georef": georef,
    "width": pw,
    "height": ph,
    "corners": corners,
    "bbox": [min(lngs), min(lats), max(lngs), max(lats)],
    "west": min(lngs),
    "south": min(lats),
    "east": max(lngs),
    "north": max(lats),
    "notes": notes,
    "matched": True,
  }


def _match_with_vision(photo_path, canvas_path, pw, ph, cw, ch, west, south, east, north):
  from llm.engine import chat, runtime_status
  from llm.io_preview import extract_json
  from llm.map_legend import _vision_preview, image_to_data_url

  if not runtime_status().get("vision_enabled"):
    return None
  photo_ol = _major_outline_image(Image.open(photo_path).convert("RGB"))
  canvas_ol = _major_outline_image(Image.open(canvas_path).convert("RGB"))
  photo_tmp = Path(photo_path).with_name(Path(photo_path).stem + "_ol.jpg")
  canvas_tmp = Path(canvas_path).with_name(Path(canvas_path).stem + "_ol.jpg")
  photo_ol.convert("RGB").save(photo_tmp, quality=80)
  canvas_ol.convert("RGB").save(canvas_tmp, quality=80)
  photo_prev, pscale, ppw, pph = _vision_preview(photo_tmp, 512)
  canvas_prev, cscale, cpw, cph = _vision_preview(canvas_tmp, 512)
  prompt = (
    f"两张都是抽出来的主路（黑线）和水体岸线（蓝线），像素分别 {ppw}x{pph}、{cpw}x{cph}。"
    "忽略线宽、颜色深浅、是否填色，只看走向：选 3～6 条最长的路或最大的水面轮廓。"
    "第一张里每条线/面，在第二张找走向相同的那条，点出两端或明显拐弯。"
    "大致重合即可，底图可以略大。不要选图例。"
    "只输出 JSON："
    '{"pairs":[{"x":0,"y":0,"canvas_x":0,"canvas_y":0,"note":"主路"}],"notes":""}'
    "x/y 第一张，canvas_x/y 第二张，原点左上。"
  )
  raw = chat(
    [
      {"role": "system", "content": "你是地图配准助手，只输出 JSON。"},
      {
        "role": "user",
        "content": [
          {"type": "image_url", "image_url": {"url": image_to_data_url(photo_prev)}},
          {"type": "image_url", "image_url": {"url": image_to_data_url(canvas_prev)}},
          {"type": "text", "text": prompt},
        ],
      },
    ],
    temperature=0.1,
    json_mode=False,
    max_tokens=480,
  )
  try:
    parsed = extract_json(raw)
  except Exception:
    return None
  rows = parsed.get("pairs") if isinstance(parsed, dict) else None
  pairs = []
  for row in rows or []:
    if not isinstance(row, dict):
      continue
    try:
      x = float(row.get("x")) / (pscale or 1)
      y = float(row.get("y")) / (pscale or 1)
      cx = float(row.get("canvas_x")) / (cscale or 1)
      cy = float(row.get("canvas_y")) / (cscale or 1)
    except (TypeError, ValueError):
      continue
    if min(x, y, cx, cy) < -20:
      continue
    pairs.append({
      "x": x,
      "y": y,
      "canvas_x": cx,
      "canvas_y": cy,
      "note": str(row.get("note") or "道路特征"),
    })
  if len(pairs) < 2:
    return None
  return _pack_result(
    pairs, pw, ph, cw, ch, west, south, east, north,
    score=0.5,
    method="vision-roads",
    notes="视觉模型按主路/水体走向配准，忽略线宽。",
  )


def _pick_match(candidates: list[dict], pw: int, ph: int, cw: int, ch: int) -> dict | None:
  ranked = [item for item in candidates if item and item.get("score", -1) > 0]
  if not ranked:
    return None
  photo_bigger = pw * ph >= cw * ch
  ranked.sort(key=lambda item: item["score"], reverse=True)
  top = ranked[0]
  if photo_bigger:
    same = [item for item in ranked if item["direction"] == "map_in_image"]
    if same and same[0]["score"] >= top["score"] * 0.9:
      return same[0]
  else:
    same = [item for item in ranked if item["direction"] == "image_in_map"]
    if same and same[0]["score"] >= top["score"] * 0.9:
      return same[0]
  return top


def _match_outlines(photo: Image.Image, canvas: Image.Image) -> dict | None:
  photo_mask, _, _ = _major_outline_mask(photo, 200)
  canvas_mask, _, _ = _major_outline_mask(canvas, 200)
  if int(photo_mask.sum()) < 40 or int(canvas_mask.sum()) < 40:
    return None
  band = _dilate(canvas_mask, 3)
  best = None
  ph0, pw0 = photo_mask.shape
  ch, cw = canvas_mask.shape
  for scale in (0.9, 0.95, 1.0):
    tw = int(round(pw0 * scale))
    th = int(round(ph0 * scale))
    if tw < 40 or th < 40 or tw > cw or th > ch:
      continue
    templ = _resize(photo_mask.astype(np.float32), tw, th) > 0.35
    n = float(templ.sum())
    if n < 30:
      continue
    corr = _fft_correlate(band.astype(np.float32), templ.astype(np.float32))
    score_map = corr / n
    idx = int(np.argmax(score_map))
    y, x = divmod(idx, score_map.shape[1])
    score = float(score_map[y, x])
    if best is None or score > best["score"]:
      best = {
        "score": score,
        "x": x,
        "y": y,
        "tw": tw,
        "th": th,
        "image_w": cw,
        "image_h": ch,
        "templ_w": pw0,
        "templ_h": ph0,
        "direction": "image_in_map",
        "mode": "outline",
      }
  return best


def _major_outline_mask(im: Image.Image, max_side: int = 200) -> tuple[np.ndarray, int, int]:
  rgb = im.convert("RGB")
  w, h = rgb.size
  scale = min(1.0, max_side / max(w, h))
  if scale < 1:
    rgb = rgb.resize((max(8, int(w * scale)), max(8, int(h * scale))), Image.Resampling.BILINEAR)
  arr = np.asarray(rgb, dtype=np.float32)
  r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
  # 线划图里的蓝=水，黑=路；原图里偏蓝=水，强边缘=路
  ink = (r + g + b) < 420
  water = ((b > r + 10) & (b > g + 2) & (b > 80)) | ((b > 140) & (b > r) & (b > g) & ink)
  gray = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
  mag = _edges(gray)
  road = mag >= max(0.42, float(np.percentile(mag, 78)))
  road = _keep_longest(road, 8, 28)
  shore = _keep_longest(_ring(water), 4, 40)
  outline = road | shore
  return outline, rgb.size[0], rgb.size[1]


def _major_outline_image(im: Image.Image) -> Image.Image:
  mask, _, _ = _major_outline_mask(im, 360)
  rgb = im.convert("RGB")
  w, h = rgb.size
  vis = np.full((mask.shape[0], mask.shape[1], 3), 255, dtype=np.uint8)
  arr = np.asarray(rgb.resize((mask.shape[1], mask.shape[0])), dtype=np.float32)
  r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]
  water = ((b > r + 10) & (b > g + 2) & (b > 80))
  vis[mask] = (20, 20, 20)
  vis[water & mask] = (50, 120, 200)
  out = Image.fromarray(vis, mode="RGB")
  if out.size != (w, h):
    out = out.resize((w, h), Image.Resampling.NEAREST)
  return out


def _keep_longest(mask: np.ndarray, limit: int, min_cells: int) -> np.ndarray:
  h, w = mask.shape
  seen = np.zeros((h, w), dtype=bool)
  groups = []
  ys, xs = np.where(mask)
  for y, x in zip(ys.tolist(), xs.tolist()):
    if seen[y, x]:
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
  out = np.zeros_like(mask, dtype=bool)
  for cells in groups[:limit]:
    for x, y in cells:
      out[y, x] = True
  return out


def _ring(mask: np.ndarray) -> np.ndarray:
  er = np.zeros_like(mask, dtype=bool)
  er[1:-1, 1:-1] = (
    mask[1:-1, 1:-1]
    & mask[:-2, 1:-1] & mask[2:, 1:-1]
    & mask[1:-1, :-2] & mask[1:-1, 2:]
  )
  return mask & ~er


def _dilate(mask: np.ndarray, radius: int = 3) -> np.ndarray:
  k = radius * 2 + 1
  pad = np.pad(mask, radius, mode="constant", constant_values=False)
  win = np.lib.stride_tricks.sliding_window_view(pad, (k, k))
  return win.any(axis=(2, 3))


def _prepare(im: Image.Image, max_side: int = 360) -> np.ndarray:
  w, h = im.size
  scale = min(1.0, max_side / max(w, h))
  if scale < 1:
    im = im.resize((max(8, int(w * scale)), max(8, int(h * scale))), Image.Resampling.BILINEAR)
  arr = np.asarray(im.convert("L"), dtype=np.float32)
  lo, hi = np.percentile(arr, (2, 98))
  return np.clip((arr - lo) / (hi - lo + 1e-6), 0, 1)


def _edges(gray: np.ndarray) -> np.ndarray:
  gx = _conv(gray, np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float32))
  gy = _conv(gray, np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]], dtype=np.float32))
  mag = np.sqrt(gx * gx + gy * gy)
  lo, hi = np.percentile(mag, (50, 99.5))
  return np.clip((mag - lo) / (hi - lo + 1e-6), 0, 1)


def _conv(gray: np.ndarray, kernel: np.ndarray) -> np.ndarray:
  kh, kw = kernel.shape
  ph, pw = kh // 2, kw // 2
  padded = np.pad(gray, ((ph, ph), (pw, pw)), mode="edge")
  out = np.zeros_like(gray, dtype=np.float32)
  for i in range(kh):
    for j in range(kw):
      out += kernel[i, j] * padded[i:i + gray.shape[0], j:j + gray.shape[1]]
  return out


def _search_template(image: np.ndarray, templ_src: np.ndarray, direction: str) -> dict | None:
  best = None
  ih, iw = image.shape
  th0, tw0 = templ_src.shape
  for scale in (0.86, 0.93, 1.0):
    tw = int(round(tw0 * scale))
    th = int(round(th0 * scale))
    if tw < 36 or th < 36 or tw >= iw or th >= ih:
      continue
    if tw * th > 0.9 * iw * ih or tw * th < 0.12 * iw * ih:
      continue
    templ = _resize(templ_src, tw, th)
    score, x, y = _ncc_peak(image, templ)
    if best is None or score > best["score"]:
      best = {
        "score": score,
        "x": x,
        "y": y,
        "tw": tw,
        "th": th,
        "image_w": iw,
        "image_h": ih,
        "templ_w": tw0,
        "templ_h": th0,
        "direction": direction,
      }
  return best


def _resize(arr: np.ndarray, w: int, h: int) -> np.ndarray:
  im = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), mode="L")
  return np.asarray(im.resize((w, h), Image.Resampling.BILINEAR), dtype=np.float32) / 255.0


def _ncc_peak(image: np.ndarray, templ: np.ndarray) -> tuple[float, int, int]:
  th, tw = templ.shape
  ih, iw = image.shape
  t = templ - templ.mean()
  t_var = float((t * t).sum())
  if t_var < 1e-8:
    return -1.0, 0, 0
  corr = _fft_correlate(image, t)
  integ = _integral(image)
  integ2 = _integral(image * image)
  n = float(th * tw)
  y1 = np.arange(ih - th + 1)[:, None]
  x1 = np.arange(iw - tw + 1)[None, :]
  y2 = y1 + th
  x2 = x1 + tw
  win_sum = integ[y2, x2] - integ[y1, x2] - integ[y2, x1] + integ[y1, x1]
  win_sum2 = integ2[y2, x2] - integ2[y1, x2] - integ2[y2, x1] + integ2[y1, x1]
  win_var = np.maximum(win_sum2 - (win_sum * win_sum) / n, 1e-6)
  ncc = corr / np.sqrt(t_var * win_var)
  idx = int(np.argmax(ncc))
  y, x = divmod(idx, ncc.shape[1])
  return float(ncc[y, x]), int(x), int(y)


def _fft_correlate(image: np.ndarray, kernel: np.ndarray) -> np.ndarray:
  kh, kw = kernel.shape
  ih, iw = image.shape
  fimage = np.fft.rfft2(image, s=(ih, iw))
  kpad = np.zeros((ih, iw), dtype=np.float32)
  kpad[:kh, :kw] = kernel[::-1, ::-1]
  fkernel = np.fft.rfft2(kpad, s=(ih, iw))
  full = np.fft.irfft2(fimage * fkernel, s=(ih, iw)).real
  return full[kh - 1:ih, kw - 1:iw]


def _integral(arr: np.ndarray) -> np.ndarray:
  out = np.pad(arr, ((1, 0), (1, 0)))
  return out.cumsum(0).cumsum(1)


def _to_canvas_affine(match: dict, photo_w: int, photo_h: int, canvas_w: int, canvas_h: int) -> tuple[float, float, float, float]:
  """canvas_x = ax * photo_x + bx, canvas_y = ay * photo_y + by, in original pixels."""
  if match["direction"] == "map_in_image":
    sx = photo_w / match["image_w"]
    sy = photo_h / match["image_h"]
    scale_x = (match["tw"] / canvas_w) * sx
    scale_y = (match["th"] / canvas_h) * sy
    ox = match["x"] * sx
    oy = match["y"] * sy
    if abs(scale_x) < 1e-9 or abs(scale_y) < 1e-9:
      raise ValueError("对照尺度无效")
    return 1.0 / scale_x, -ox / scale_x, 1.0 / scale_y, -oy / scale_y

  canvas_sx = canvas_w / match["image_w"]
  canvas_sy = canvas_h / match["image_h"]
  ax = (match["tw"] / photo_w) * canvas_sx
  ay = (match["th"] / photo_h) * canvas_sy
  bx = match["x"] * canvas_sx
  by = match["y"] * canvas_sy
  return float(ax), float(bx), float(ay), float(by)
