# 把文件夹里的图片按四个角的经纬度切成栅格 MBTiles。
# 角点顺序：左上、右上、右下、左下。图片可以是旋转的。
# size 是像素宽高，原图会先缩放到这个尺寸，再按角点贴到地图上。
import io
import json
import math
import sqlite3
from pathlib import Path

import numpy as np
from PIL import Image

TILE_SIZE = 256
MAX_LAT = 85.05112878
EARTH_RADIUS = 6378137.0
ORIGIN_SHIFT = math.pi * EARTH_RADIUS


class ImageMbtilesError(Exception):
  pass


def find_manifest(folder):
  files = sorted(path for path in folder.glob("*.json") if path.is_file())
  if not files:
    raise ImageMbtilesError(f"{folder} 里没有 json 文件")
  if len(files) == 1:
    return files[0]
  matched = []
  for path in files:
    try:
      data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
      continue
    items = data if isinstance(data, list) else [data]
    if items and isinstance(items[0], dict) and (
      "boundingVolume" in items[0] or "corners" in items[0] or "coordinates" in items[0]
    ):
      matched.append(path)
  if len(matched) == 1:
    return matched[0]
  names = "、".join(path.name for path in files)
  raise ImageMbtilesError(f"文件夹里有多个 json，无法确定用哪一个：{names}")


def as_point(value, label):
  if isinstance(value, dict):
    lon = value.get("lon", value.get("lng", value.get("x")))
    lat = value.get("lat", value.get("y"))
    if lon is None or lat is None:
      raise ImageMbtilesError(f"{label} 的角点需要 lon、lat")
    return float(lon), float(lat)
  if not isinstance(value, (list, tuple)) or len(value) < 2:
    raise ImageMbtilesError(f"{label} 的角点需要 [经度, 纬度]")
  return float(value[0]), float(value[1])


def parse_corners(value, label):
  if not isinstance(value, (list, tuple)) or len(value) != 4:
    raise ImageMbtilesError(f"{label} 需要 4 个角点，顺序是左上、右上、右下、左下")
  if len(value) == 4 and all(isinstance(item, (int, float)) for item in value):
    raise ImageMbtilesError(
      f"{label} 的坐标要写成 4 个点："
      "[[左上经度, 左上纬度], [右上经度, 右上纬度], [右下经度, 右下纬度], [左下经度, 左下纬度]]"
    )
  corners = [as_point(item, label) for item in value]
  for lon, lat in corners:
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
      raise ImageMbtilesError(f"{label} 的经纬度超出 -180~180、-90~90")
  return corners


def parse_size(value, label):
  if isinstance(value, dict):
    width = value.get("width", value.get("w"))
    height = value.get("height", value.get("h"))
    if width is None or height is None:
      raise ImageMbtilesError(f"{label} 的 size 需要 width 和 height")
    value = [width, height]
  if not isinstance(value, (list, tuple)) or len(value) < 2:
    raise ImageMbtilesError(f"{label} 的 size 需要 [宽, 高]，单位是像素")
  width, height = int(value[0]), int(value[1])
  if width <= 0 or height <= 0:
    raise ImageMbtilesError(f"{label} 的 size 必须是正数")
  return width, height


def load_images(manifest):
  data = json.loads(manifest.read_text(encoding="utf-8"))
  if isinstance(data, dict):
    for key in ("images", "items", "data", "tiles"):
      if isinstance(data.get(key), list):
        data = data[key]
        break
    else:
      data = [data]
  if not isinstance(data, list) or not data:
    raise ImageMbtilesError("json 里没有图片记录")
  images = []
  for index, item in enumerate(data, start=1):
    if not isinstance(item, dict):
      raise ImageMbtilesError(f"第 {index} 条不是对象")
    raw_url = item.get("url") or item.get("path") or item.get("image") or item.get("file")
    if not raw_url:
      raise ImageMbtilesError(f"第 {index} 条没有图片地址")
    path = Path(raw_url)
    if not path.is_absolute():
      path = (manifest.parent / path).resolve()
    label = f"第 {index} 条 {raw_url}"
    corners_value = item.get("boundingVolume", item.get("corners", item.get("coordinates")))
    if corners_value is None:
      raise ImageMbtilesError(f"{label} 没有四个角的坐标")
    if "size" not in item:
      raise ImageMbtilesError(f"{label} 没有 size，需要填写图片像素尺寸，例如 [175, 109]")
    if not path.is_file():
      raise ImageMbtilesError(f"{label} 找不到图片：{path}")
    width, height = parse_size(item["size"], label)
    image = Image.open(path).convert("RGBA")
    if image.size != (width, height):
      image = image.resize((width, height), Image.Resampling.LANCZOS)
    corners = parse_corners(corners_value, label)
    mercator = np.array([lonlat_to_mercator(lon, lat) for lon, lat in corners], dtype=np.float64)
    images.append({
      "path": path,
      "corners": corners,
      "mercator": mercator,
      "homography": image_homography(mercator, width, height),
      "bounds": corner_bounds(corners),
      "pixels": np.asarray(image),
    })
  return images


def lonlat_to_mercator(lon, lat):
  lat = min(max(lat, -MAX_LAT), MAX_LAT)
  x = lon * ORIGIN_SHIFT / 180
  y = math.log(math.tan((90 + lat) * math.pi / 360)) * EARTH_RADIUS
  return x, y


def mercator_y(lat):
  lat = min(max(lat, -MAX_LAT), MAX_LAT)
  rad = math.radians(lat)
  return (1 - math.log(math.tan(rad) + 1 / math.cos(rad)) / math.pi) / 2


def lat_from_mercator(y):
  return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y))))


def tile_bounds(z, x, y):
  n = 2 ** z
  west = x / n * 360 - 180
  east = (x + 1) / n * 360 - 180
  north = lat_from_mercator(y / n)
  south = lat_from_mercator((y + 1) / n)
  return west, south, east, north


def corner_bounds(corners):
  lons = [lon for lon, _lat in corners]
  lats = [lat for _lon, lat in corners]
  return min(lons), min(lats), max(lons), max(lats)


def image_homography(mercator, width, height):
  # 地图上的点经这组系数变回图片像素。先平移到左上角附近，避免墨卡托大数把系数算歪。
  origin = mercator[0].copy()
  local = mercator - origin

  def cross(a, b):
    return a[0] * b[1] - a[1] * b[0]

  area = abs(cross(local[1] - local[0], local[3] - local[0]))
  area += abs(cross(local[1] - local[2], local[3] - local[2]))
  if area < 0.01:
    raise ImageMbtilesError("四个角没有围出面积，无法按坐标贴图")
  target = np.array([
    [0, 0],
    [width, 0],
    [width, height],
    [0, height],
  ], dtype=np.float64)
  matrix = []
  for index in range(4):
    x, y = local[index]
    u, v = target[index]
    matrix.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
    matrix.append([0, 0, 0, x, y, 1, -v * x, -v * y])
  coefficients, _, _, _ = np.linalg.lstsq(np.array(matrix, dtype=np.float64), target.reshape(-1), rcond=None)
  homography = np.array([
    [coefficients[0], coefficients[1], coefficients[2]],
    [coefficients[3], coefficients[4], coefficients[5]],
    [coefficients[6], coefficients[7], 1],
  ], dtype=np.float64)
  return homography, origin


def apply_homography(mapping, xs, ys):
  homography, origin = mapping
  xs = xs - origin[0]
  ys = ys - origin[1]
  denominator = homography[2, 0] * xs + homography[2, 1] * ys + homography[2, 2]
  px = (homography[0, 0] * xs + homography[0, 1] * ys + homography[0, 2]) / denominator
  py = (homography[1, 0] * xs + homography[1, 1] * ys + homography[1, 2]) / denominator
  return px, py


def zoom_for_image(mercator, width, height):
  edges = (
    np.linalg.norm(mercator[1] - mercator[0]),
    np.linalg.norm(mercator[2] - mercator[1]),
    np.linalg.norm(mercator[3] - mercator[2]),
    np.linalg.norm(mercator[0] - mercator[3]),
  )
  ground_per_pixel = max(edges[0], edges[2]) / width
  ground_per_pixel = max(ground_per_pixel, max(edges[1], edges[3]) / height)
  if ground_per_pixel <= 0:
    raise ImageMbtilesError("四个角叠在一起，无法确定图片方向和范围")
  resolution_z0 = 2 * ORIGIN_SHIFT / TILE_SIZE
  return max(0, min(22, int(round(math.log2(resolution_z0 / ground_per_pixel)))))


def overview_zoom(bounds):
  west, south, east, north = bounds
  lon_fraction = (east - west) / 360
  lat_fraction = abs(mercator_y(south) - mercator_y(north))
  fraction = max(lon_fraction, lat_fraction, 1e-12)
  return max(0, int(math.floor(math.log2(1 / fraction))) - 1)


def iter_tiles(bounds, zoom):
  west, south, east, north = bounds
  n = 2 ** zoom
  x0 = int(math.floor((west + 180) / 360 * n))
  x1 = int(math.floor((east + 180) / 360 * n - 1e-12))
  y0 = int(math.floor(mercator_y(north) * n))
  y1 = int(math.floor(mercator_y(south) * n - 1e-12))
  x0 = max(0, min(n - 1, x0))
  x1 = max(0, min(n - 1, x1))
  y0 = max(0, min(n - 1, y0))
  y1 = max(0, min(n - 1, y1))
  for x in range(x0, x1 + 1):
    for y in range(y0, y1 + 1):
      yield x, y


def sample_tile(pixels, homography, zoom, x, y):
  height, width = pixels.shape[:2]
  n = 2 ** zoom
  columns = (x + (np.arange(TILE_SIZE) + 0.5) / TILE_SIZE) / n * 2 * ORIGIN_SHIFT - ORIGIN_SHIFT
  rows = ORIGIN_SHIFT - (y + (np.arange(TILE_SIZE) + 0.5) / TILE_SIZE) / n * 2 * ORIGIN_SHIFT
  grid_x, grid_y = np.meshgrid(columns, rows)
  px, py = apply_homography(homography, grid_x, grid_y)
  mask = (px >= -1e-3) & (px <= width + 1e-3) & (py >= -1e-3) & (py <= height + 1e-3)
  if not mask.any():
    return None
  x0 = np.floor(px).astype(np.int32)
  y0 = np.floor(py).astype(np.int32)
  x1 = x0 + 1
  y1 = y0 + 1
  wx = (px - x0)[..., None]
  wy = (py - y0)[..., None]
  x0 = np.clip(x0, 0, width - 1)
  x1 = np.clip(x1, 0, width - 1)
  y0 = np.clip(y0, 0, height - 1)
  y1 = np.clip(y1, 0, height - 1)
  upper = pixels[y0, x0].astype(np.float32) * (1 - wx) + pixels[y0, x1].astype(np.float32) * wx
  lower = pixels[y1, x0].astype(np.float32) * (1 - wx) + pixels[y1, x1].astype(np.float32) * wx
  sampled = upper * (1 - wy) + lower * wy
  sampled *= mask[..., None]
  if sampled[..., 3].max() <= 0:
    return None
  return sampled


def composite(base, incoming):
  if base is None:
    return incoming
  src_alpha = incoming[..., 3:4] / 255
  dst_alpha = base[..., 3:4] / 255
  out_alpha = src_alpha + dst_alpha * (1 - src_alpha)
  out_rgb = incoming[..., :3] * src_alpha + base[..., :3] * dst_alpha * (1 - src_alpha)
  out_rgb = np.divide(out_rgb, out_alpha, out=np.zeros_like(out_rgb), where=out_alpha > 0)
  return np.concatenate([out_rgb, out_alpha * 255], axis=-1)


def encode_png(pixels):
  image = Image.fromarray(np.clip(np.rint(pixels), 0, 255).astype(np.uint8), "RGBA")
  buffer = io.BytesIO()
  image.save(buffer, format="PNG", optimize=True)
  return buffer.getvalue()


def union_bounds(images):
  west = min(item["bounds"][0] for item in images)
  south = min(item["bounds"][1] for item in images)
  east = max(item["bounds"][2] for item in images)
  north = max(item["bounds"][3] for item in images)
  return west, south, east, north


def build(folder, output, minzoom=None, maxzoom=None):
  folder = Path(folder).resolve()
  manifest = find_manifest(folder)
  images = load_images(manifest)
  native_zooms = [
    zoom_for_image(item["mercator"], item["pixels"].shape[1], item["pixels"].shape[0])
    for item in images
  ]
  auto_max = max(native_zooms)
  auto_min = min(overview_zoom(item["bounds"]) for item in images)
  zoom_max = auto_max if maxzoom is None else maxzoom
  zoom_min = min(auto_min, zoom_max) if minzoom is None else minzoom
  if not (0 <= zoom_min <= zoom_max <= 24):
    raise ImageMbtilesError(f"缩放级别不正确：{zoom_min} 到 {zoom_max}")

  tiles = {}
  for zoom in range(zoom_min, zoom_max + 1):
    for item in images:
      for x, y in iter_tiles(item["bounds"], zoom):
        sampled = sample_tile(item["pixels"], item["homography"], zoom, x, y)
        if sampled is None:
          continue
        key = (zoom, x, y)
        tiles[key] = composite(tiles.get(key), sampled)
  if not tiles:
    raise ImageMbtilesError("没有切出任何瓦片")

  output = Path(output) if output else folder / f"{manifest.stem}.mbtiles"
  output = output.resolve()
  if output.exists():
    output.unlink()
  bounds = union_bounds(images)
  west, south, east, north = bounds
  center_zoom = min(zoom_max, max(zoom_min, (zoom_min + zoom_max) // 2))
  connection = sqlite3.connect(output)
  try:
    connection.execute("CREATE TABLE metadata (name TEXT, value TEXT)")
    connection.execute(
      "CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB)"
    )
    connection.execute("CREATE UNIQUE INDEX tile_index ON tiles (zoom_level, tile_column, tile_row)")
    metadata = {
      "name": manifest.stem,
      "type": "overlay",
      "version": "1.3",
      "description": manifest.name,
      "format": "png",
      "bounds": f"{west},{south},{east},{north}",
      "center": f"{(west + east) / 2},{(south + north) / 2},{center_zoom}",
      "minzoom": str(zoom_min),
      "maxzoom": str(zoom_max),
    }
    connection.executemany("INSERT INTO metadata (name, value) VALUES (?, ?)", metadata.items())
    rows = []
    for (zoom, x, y), pixels in tiles.items():
      tile_row = (2 ** zoom - 1) - y
      rows.append((zoom, x, tile_row, encode_png(pixels)))
    connection.executemany(
      "INSERT INTO tiles (zoom_level, tile_column, tile_row, tile_data) VALUES (?, ?, ?, ?)",
      rows,
    )
    connection.commit()
  finally:
    connection.close()
  return {
    "output": str(output),
    "manifest": str(manifest),
    "images": len(images),
    "tiles": len(tiles),
    "minzoom": zoom_min,
    "maxzoom": zoom_max,
    "bounds": bounds,
  }

