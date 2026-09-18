from __future__ import annotations

import math


def _valid_gcps(gcps: list[dict]) -> list[dict]:
  rows = []
  for item in gcps or []:
    try:
      x = float(item.get("x"))
      y = float(item.get("y"))
      lng = float(item.get("lng"))
      lat = float(item.get("lat"))
    except (TypeError, ValueError):
      continue
    if not all(math.isfinite(v) for v in (x, y, lng, lat)):
      continue
    rows.append({"x": x, "y": y, "lng": lng, "lat": lat, "note": str(item.get("note") or "")})
  return rows


def fit_transform(gcps: list[dict]) -> dict:
  points = _valid_gcps(gcps)
  if len(points) < 2:
    raise ValueError("至少需要 2 个控制点（图上坐标 + 经纬度）")
  import numpy as np

  xs = np.array([p["x"] for p in points], dtype=float)
  ys = np.array([p["y"] for p in points], dtype=float)
  lngs = np.array([p["lng"] for p in points], dtype=float)
  lats = np.array([p["lat"] for p in points], dtype=float)

  if len(points) == 2:
    # similarity: [lng, lat] = s * R * [x, y] + t
    dx = xs[1] - xs[0]
    dy = ys[1] - ys[0]
    dlng = lngs[1] - lngs[0]
    dlat = lats[1] - lats[0]
    denom = dx * dx + dy * dy
    if denom < 1e-9:
      raise ValueError("两个控制点在图上太近，请选更散开的位置")
    a = (dx * dlng + dy * dlat) / denom
    b = (dx * dlat - dy * dlng) / denom
    tx = lngs[0] - a * xs[0] + b * ys[0]
    ty = lats[0] - b * xs[0] - a * ys[0]
    matrix = [[a, -b, tx], [b, a, ty]]
    kind = "similarity"
  else:
    a_mat = np.column_stack([xs, ys, np.ones(len(points))])
    coef_lng, *_ = np.linalg.lstsq(a_mat, lngs, rcond=None)
    coef_lat, *_ = np.linalg.lstsq(a_mat, lats, rcond=None)
    matrix = [coef_lng.tolist(), coef_lat.tolist()]
    kind = "affine"

  residuals = []
  err_sum = 0.0
  for point in points:
    lng, lat = apply_matrix(matrix, point["x"], point["y"])
    dist = _haversine_m(point["lng"], point["lat"], lng, lat)
    err_sum += dist
    residuals.append({
      "note": point["note"],
      "x": point["x"],
      "y": point["y"],
      "input_lng": point["lng"],
      "input_lat": point["lat"],
      "fitted_lng": round(lng, 8),
      "fitted_lat": round(lat, 8),
      "error_m": round(dist, 2),
    })
  return {
    "kind": kind,
    "count": len(points),
    "matrix": matrix,
    "mean_error_m": round(err_sum / len(points), 2),
    "residuals": residuals,
  }


def apply_matrix(matrix: list[list[float]], x: float, y: float) -> tuple[float, float]:
  lng = matrix[0][0] * x + matrix[0][1] * y + matrix[0][2]
  lat = matrix[1][0] * x + matrix[1][1] * y + matrix[1][2]
  return lng, lat


def _haversine_m(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
  r = 6371000.0
  p1, p2 = math.radians(lat1), math.radians(lat2)
  dphi = math.radians(lat2 - lat1)
  dlmb = math.radians(lng2 - lng1)
  a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
  return 2 * r * math.asin(min(1.0, math.sqrt(a)))
