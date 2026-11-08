# -*- coding: utf-8 -*-
"""从 shp 或 osm pbf 里筛出建筑面，另存为 shp，供后续白膜使用。"""

from __future__ import annotations

import os
import re
from pathlib import Path

import geopandas as gpd
from shapely.geometry import MultiPolygon
from shapely import wkb as shapely_wkb

POLYGON_TYPES = ("Polygon", "MultiPolygon")
VALUE_LIMIT = 300
SIDECARS = (
    ".shp",
    ".shx",
    ".dbf",
    ".prj",
    ".cpg",
    ".qpj",
    ".sbn",
    ".sbx",
    ".shp.xml",
)

EMPTY_TOKENS = {"", "none", "null", "nan", "no", "false", "0", "n", "<na>"}

# 字段名越像分类字段，分越高。landuse 这类面范围不拿来当建筑轮廓。
FIELD_SCORE = {
    "building": 100,
    "fclass": 50,
    "fwlx": 60,
    "fwyt": 40,
    "jzwlx": 60,
    "gb": 55,
    "cc": 40,
    "clasid": 55,
    "classid": 55,
    "ysdm": 45,
    "type": 30,
    "class": 25,
    "subtype": 25,
    "code": 20,
}
SKIP_FIELDS = {"landuse", "natural", "highway", "waterway", "railway", "name", "osm_id"}

ENGLISH_KEYWORDS = (
    "building",
    "house",
    "residential",
    "apartment",
    "apartments",
    "commercial",
    "industrial",
    "retail",
    "warehouse",
    "hotel",
    "school",
    "hospital",
    "church",
    "garage",
    "roof",
    "detached",
    "terrace",
    "bungalow",
    "dormitory",
    "university",
    "civic",
    "shed",
    "hut",
    "barn",
    "cabin",
    "semidetached",
)
CHINESE_KEYWORDS = (
    "建筑物",
    "建筑",
    "房屋",
    "居民地",
    "楼房",
    "楼宇",
    "建成房屋",
    "一般房屋",
    "普通房屋",
    "棚房",
    "白膜",
)
# GB/T 13923 房屋类代码，常见为 310301 建成房屋。
CODE_RE = re.compile(r"^310[3-9]\d{0,6}$")
NAME_HINTS = ("building", "buildings", "建筑", "房屋", "白膜", "resa", "居民地")

# pbf 里只统计这些标签。写出 shp 时换成 10 字符以内的列名。
PBF_FIELDS = (
    "building",
    "height",
    "building:levels",
    "min_height",
    "building:min_level",
    "building:use",
    "amenity",
)
PBF_COLUMNS = (
    ("building", "building"),
    ("name", "name"),
    ("height", "height"),
    ("building:levels", "levels"),
    ("min_height", "min_height"),
    ("building:min_level", "min_level"),
    ("building:use", "use"),
    ("amenity", "amenity"),
)
PBF_WRITE_BATCH = 4000
PBF_VALUE_CAP = 5000
_PBF_STATS: dict[tuple, dict] = {}


def norm_value(value) -> str:
    if value is None:
        return ""
    try:
        if value != value:
            return ""
    except Exception:
        pass
    if isinstance(value, bytes):
        text = None
        for enc in ("utf-8", "gbk", "gb18030"):
            try:
                text = value.decode(enc)
                break
            except Exception:
                continue
        value = text if text is not None else value.decode("utf-8", "ignore")
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null", "<na>"}:
        return ""
    if text.endswith(".0") and text[:-2].lstrip("-").isdigit():
        return text[:-2]
    return text


def _field_key(name: str) -> str:
    return str(name).strip().lower()


def _is_building_code(text: str) -> bool:
    digits = re.sub(r"\D", "", text)
    return bool(digits and CODE_RE.match(digits))


def is_building_value(field: str, text: str) -> bool:
    if not text:
        return False
    key = _field_key(field)
    low = text.lower()
    if key == "building":
        return low not in EMPTY_TOKENS
    if key in ("dlbm", "dlmc"):
        return any(word in text for word in ("房屋", "建筑"))
    if _is_building_code(text):
        return True
    if len(text) > 24:
        return False
    if any(word in text for word in CHINESE_KEYWORDS):
        return True
    if low in ENGLISH_KEYWORDS:
        return True
    return any(word in low and len(word) >= 5 for word in ENGLISH_KEYWORDS)


def _name_score(field: str) -> int:
    key = _field_key(field)
    score = FIELD_SCORE.get(key, 0)
    if any(word in str(field) for word in ("房屋", "建筑", "类型", "分类", "地类", "要素")):
        score = max(score, 35)
    return score


def _strong_field(field: str) -> bool:
    return _name_score(field) > 0


def _count_total(counts) -> int:
    if counts is None or len(counts) == 0:
        return 0
    total = getattr(counts, "sum", None)
    if callable(total):
        return int(total())
    return sum(int(value) for value in counts.values())


def _name_looks_like_buildings(path: str) -> bool:
    stem = Path(path).stem.lower()
    return any(hint in stem for hint in NAME_HINTS)


def _is_pbf(path: str) -> bool:
    name = os.path.basename(path or "").lower()
    return name.endswith(".pbf") or name.endswith(".osm")


def _require_file(path: str) -> None:
    if not path or not os.path.isfile(path):
        raise ValueError("找不到文件")


def read_vector(path: str) -> gpd.GeoDataFrame:
    _require_file(path)
    cpg = os.path.splitext(path)[0] + ".cpg"
    if os.path.isfile(cpg):
        return gpd.read_file(path)
    last = None
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            return gpd.read_file(path, encoding=enc)
        except Exception as exc:
            last = exc
    try:
        return gpd.read_file(path)
    except Exception as exc:
        raise ValueError(f"读取失败：{exc or last}") from exc


def _polygons(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    valid = gdf.geometry.notna()
    data = gdf[valid]
    if data.empty:
        return data
    data = data[data.geometry.geom_type.isin(POLYGON_TYPES)]
    if data.empty:
        return data
    return data[~data.geometry.is_empty]


def _attribute_fields(gdf: gpd.GeoDataFrame) -> list[str]:
    geom_name = gdf.geometry.name
    return [str(column) for column in gdf.columns if column != geom_name]


def _value_counts(gdf: gpd.GeoDataFrame, field: str):
    if field not in gdf.columns:
        raise ValueError(f"没有字段 {field}")
    return gdf[field].map(norm_value).value_counts(dropna=False)


def _score_field(field: str, counts) -> tuple[int, list[str], int]:
    if _field_key(field) in SKIP_FIELDS:
        return 0, [], 0
    name_score = _name_score(field)
    matched: list[tuple[int, str]] = []
    total = _count_total(counts)
    for raw, count in counts.items():
        text = norm_value(raw)
        if is_building_value(field, text):
            matched.append((int(count), text))
    if not matched:
        return 0, [], 0
    match_count = sum(count for count, _ in matched)
    if name_score == 0:
        has_strong = any(
            _is_building_code(text) or any(word in text for word in CHINESE_KEYWORDS)
            for _, text in matched
        )
        ratio = match_count / total if total else 0
        if not has_strong and ratio < 0.3:
            return 0, [], 0
    matched.sort(key=lambda item: (-item[0], item[1]))
    values = [text for _, text in matched]
    score = name_score + min(match_count, 100000) / 100 + len(values)
    return score, values, match_count


def _field_value_payload(field: str, counts) -> dict:
    items = []
    for raw, count in counts.items():
        text = norm_value(raw)
        items.append({
            "value": text,
            "count": int(count),
            "building": is_building_value(field, text),
        })
    items.sort(key=lambda item: (not item["building"], -item["count"], item["value"]))
    unique = len(items)
    truncated = unique > VALUE_LIMIT
    return {
        "field": field,
        "values": items[:VALUE_LIMIT],
        "unique": unique,
        "truncated": truncated,
    }


def _suggest_counts(path: str, counts_by_field: dict, polygon_count: int) -> tuple[dict, dict | None]:
    best_field = ""
    best_score = 0
    best_values: list[str] = []
    best_count = 0
    best_payload = None
    for field, counts in counts_by_field.items():
        if len(counts) > 5000 and not _strong_field(field):
            continue
        score, values, match_count = _score_field(field, counts)
        if score > best_score:
            best_field = field
            best_score = score
            best_values = values
            best_count = match_count
            best_payload = _field_value_payload(field, counts)
    if best_field:
        suggestion = {
            "field": best_field,
            "values": best_values[:VALUE_LIMIT],
            "count": best_count,
            "reason": f"字段「{best_field}」里有 {len(best_values)} 种建筑取值，约 {best_count} 条面。",
        }
        return suggestion, best_payload
    if polygon_count and _name_looks_like_buildings(path):
        reason = "文件名像建筑数据，将导出全部面。"
    elif polygon_count:
        reason = "没有识别到建筑字段。可以自己选字段和取值，或直接导出全部面。"
    else:
        reason = "里面没有面要素。白膜需要建筑轮廓面。"
    return {"field": "", "values": [], "count": int(polygon_count), "reason": reason}, None


def _suggest(path: str, polygons: gpd.GeoDataFrame) -> tuple[dict, dict | None]:
    counts = {}
    if not polygons.empty:
        for field in _attribute_fields(polygons):
            counts[field] = _value_counts(polygons, field)
    return _suggest_counts(path, counts, len(polygons))


def inspect_buildings(path: str) -> dict:
    if _is_pbf(path):
        return _inspect_pbf(path)
    gdf = read_vector(path)
    polygons = _polygons(gdf)
    fields = _attribute_fields(gdf)
    suggestion, payload = _suggest(path, polygons)
    values = payload["values"] if payload else []
    return {
        "format": "shp",
        "total": int(len(gdf)),
        "polygon": int(len(polygons)),
        "fields": fields,
        "suggestion": suggestion,
        "values": values,
        "truncated": bool(payload and payload["truncated"]),
        "unique": int(payload["unique"]) if payload else 0,
        "line": f"共 {len(gdf)} 条，其中面 {len(polygons)} 条",
    }


def field_values(path: str, field: str) -> dict:
    if not field:
        raise ValueError("请选择字段")
    if _is_pbf(path):
        return _pbf_field_values(path, field)
    gdf = read_vector(path)
    polygons = _polygons(gdf)
    if polygons.empty:
        raise ValueError("里面没有面要素")
    if field not in polygons.columns:
        raise ValueError(f"没有字段 {field}")
    payload = _field_value_payload(field, _value_counts(polygons, field))
    payload["polygon"] = int(len(polygons))
    return payload


def _remove_shapefile(path: Path) -> None:
    for suffix in SIDECARS:
        target = path.with_suffix(suffix)
        if target.exists() and target.is_file():
            target.unlink()


def _file_key(path: str) -> tuple:
    stat = os.stat(path)
    return (os.path.normcase(os.path.abspath(path)), stat.st_size, stat.st_mtime_ns)


def _load_osmium():
    try:
        import osmium
    except ImportError as exc:
        raise ValueError("没有安装 osmium，无法读取 pbf") from exc
    return osmium


def _with_pbf_areas(path: str, reset, on_area) -> None:
    osmium = _load_osmium()
    last = None
    for storage in ("flex_mem", "sparse_file_array"):
        reset()
        try:
            processor = osmium.FileProcessor(path).with_locations(storage=storage).with_areas()
            for obj in processor:
                if obj.is_area():
                    on_area(obj)
            return
        except MemoryError as exc:
            last = exc
    raise ValueError(f"PBF 太大，内存不够：{last}")


def _bump(state: dict, name: str, value: str) -> None:
    bucket = state["counts"][name]
    if value in bucket:
        bucket[value] += 1
        return
    if len(bucket) >= PBF_VALUE_CAP:
        state["truncated"].add(name)
        return
    bucket[value] = 1


def _empty_pbf_state() -> dict:
    return {
        "areas": 0,
        "positive": 0,
        "counts": {name: {} for name in PBF_FIELDS},
        "truncated": set(),
    }


def _collect_pbf_stats(path: str) -> dict:
    _require_file(path)
    key = _file_key(path)
    cached = _PBF_STATS.get(key)
    if cached:
        return cached
    state = _empty_pbf_state()

    def reset():
        fresh = _empty_pbf_state()
        state.clear()
        state.update(fresh)

    def on_area(area):
        tags = dict(area.tags)
        state["areas"] += 1
        if "building" not in tags:
            return
        building = norm_value(tags.get("building"))
        if is_building_value("building", building):
            state["positive"] += 1
        for name in PBF_FIELDS:
            if name != "building" and name not in tags:
                continue
            _bump(state, name, norm_value(tags.get(name)))

    try:
        _with_pbf_areas(path, reset, on_area)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"读取 PBF 失败：{exc}") from exc
    _PBF_STATS.clear()
    _PBF_STATS[key] = state
    return state


def _inspect_pbf(path: str) -> dict:
    stats = _collect_pbf_stats(path)
    counts = {name: bucket for name, bucket in stats["counts"].items() if bucket}
    suggestion, payload = _suggest_counts(path, counts, stats["positive"])
    if stats["positive"] == 0:
        suggestion = {
            "field": "",
            "values": [],
            "count": 0,
            "reason": "没有找到可用的建筑。PBF 需要带 building 标签，且取值不能是 no。",
        }
        payload = None
    values = payload["values"] if payload else []
    field = suggestion.get("field") or ""
    return {
        "format": "pbf",
        "total": stats["areas"],
        "polygon": stats["positive"],
        "fields": list(counts.keys()),
        "suggestion": suggestion,
        "values": values,
        "truncated": bool(payload and payload["truncated"]) or field in stats["truncated"],
        "unique": int(payload["unique"]) if payload else 0,
        "line": (
            f"OSM 面 {stats['areas']} 个，建筑 {stats['positive']} 个。"
            "导出列含 building、name、height、levels。"
        ),
    }


def _pbf_field_values(path: str, field: str) -> dict:
    stats = _collect_pbf_stats(path)
    bucket = stats["counts"].get(field) or {}
    if not bucket:
        raise ValueError(f"没有字段 {field}")
    payload = _field_value_payload(field, bucket)
    payload["polygon"] = stats["positive"]
    if field in stats["truncated"]:
        payload["truncated"] = True
    return payload


def _area_geometry(area, factory):
    try:
        raw = factory.create_multipolygon(area)
    except Exception:
        return None
    try:
        if isinstance(raw, str):
            geom = shapely_wkb.loads(raw, hex=True)
        else:
            geom = shapely_wkb.loads(bytes(raw))
    except Exception:
        return None
    if geom is None or geom.is_empty:
        return None
    if geom.geom_type == "Polygon":
        geom = MultiPolygon([geom])
    elif geom.geom_type != "MultiPolygon":
        return None
    return geom


def _osm_id(area) -> str:
    try:
        base = area.orig_id()
    except Exception:
        base = getattr(area, "id", "")
    from_way = getattr(area, "from_way", None)
    kind = "w" if not callable(from_way) or from_way() else "r"
    return f"{kind}{base}"


def _pbf_row(area, tags) -> dict:
    row = {
        column: norm_value(tags.get(key))[:254]
        for key, column in PBF_COLUMNS
    }
    row["osm_id"] = _osm_id(area)[:254]
    return row


def _keep_pbf(tags: dict, field: str, wanted: set[str]) -> bool:
    if "building" not in tags:
        return False
    if not field:
        return is_building_value("building", norm_value(tags.get("building")))
    return norm_value(tags.get(field)) in wanted


def _flush_rows(out: Path, rows: list, mode: str) -> str:
    if not rows:
        return mode
    frame = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    frame.to_file(out, driver="ESRI Shapefile", encoding="utf-8", mode=mode)
    rows.clear()
    return "a"


def _export_pbf(path: str, output: str, field: str, values: list | None) -> dict:
    _require_file(path)
    osmium = _load_osmium()
    wanted = {norm_value(item) for item in (values or [])}
    if field and not wanted:
        raise ValueError("请至少选择一个建筑取值，或改为导出全部建筑")
    out = _shp_output(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    last = None
    for storage in ("flex_mem", "sparse_file_array"):
        _remove_shapefile(out)
        rows: list[dict] = []
        mode = "w"
        count = 0
        factory = osmium.geom.WKBFactory()
        try:
            processor = osmium.FileProcessor(path).with_locations(storage=storage).with_areas()
            for obj in processor:
                if not obj.is_area():
                    continue
                tags = dict(obj.tags)
                if not _keep_pbf(tags, field, wanted):
                    continue
                geom = _area_geometry(obj, factory)
                if geom is None:
                    continue
                row = _pbf_row(obj, tags)
                row["geometry"] = geom
                rows.append(row)
                if len(rows) >= PBF_WRITE_BATCH:
                    mode = _flush_rows(out, rows, mode)
                    count += PBF_WRITE_BATCH
            if rows:
                pending = len(rows)
                _flush_rows(out, rows, mode)
                count += pending
            break
        except MemoryError as exc:
            last = exc
            count = 0
            continue
        except ValueError:
            _remove_shapefile(out)
            raise
        except Exception as exc:
            _remove_shapefile(out)
            raise ValueError(f"读取 PBF 失败：{exc}") from exc
    else:
        _remove_shapefile(out)
        raise ValueError(f"PBF 太大，内存不够：{last}")
    if count <= 0:
        _remove_shapefile(out)
        raise ValueError("没有筛到建筑面，请调整字段或取值")
    return {"output": str(out), "count": count}


def _shp_output(output: str) -> Path:
    out = Path(output)
    if out.suffix.lower() != ".shp":
        if out.exists() and out.is_dir():
            out = out / "buildings.shp"
        else:
            out = out.with_suffix(".shp")
    return out


def export_buildings(path: str, output: str, field: str = "", values: list | None = None) -> dict:
    if not output:
        raise ValueError("请选择保存路径")
    if _is_pbf(path):
        return _export_pbf(path, output, field or "", values)
    gdf = read_vector(path)
    polygons = _polygons(gdf)
    if polygons.empty:
        raise ValueError("里面没有面要素，无法导出建筑")
    if field:
        if field not in polygons.columns:
            raise ValueError(f"没有字段 {field}")
        wanted = {norm_value(item) for item in (values or [])}
        if not wanted:
            raise ValueError("请至少选择一个建筑取值，或改为导出全部面")
        series = polygons[field].map(norm_value)
        polygons = polygons[series.isin(wanted)]
    if polygons.empty:
        raise ValueError("没有筛到建筑面，请调整字段或取值")

    out = _shp_output(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    _remove_shapefile(out)
    polygons.reset_index(drop=True).to_file(out, driver="ESRI Shapefile", encoding="utf-8")
    return {
        "output": str(out),
        "count": int(len(polygons)),
    }
