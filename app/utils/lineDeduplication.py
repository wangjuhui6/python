# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pyproj import CRS, Transformer
from shapely.geometry import (
    LineString,
    MultiLineString,
    GeometryCollection,
    shape,
    mapping,
)
from shapely.ops import transform, unary_union, linemerge
from shapely.strtree import STRtree


class LineDeduplicator:
    """
    GeoJSON 多线去重。

    支持：

    1. LineString
    2. MultiLineString
    3. 部分重叠
    4. 完全重叠
    5. 一条线包含另一条线
    6. 坐标存在一定误差
    7. 方向相反
    8. 按米设置容差
    9. 不重复部分独立保留
    10. 最后重新合并连续线段

    处理流程：

        WGS84
          ↓
        UTM 米制坐标
          ↓
        空间索引
          ↓
        找附近线
          ↓
        判断距离 / 方向 / 重叠
          ↓
        删除重复部分
          ↓
        保留独有部分
          ↓
        合并
          ↓
        WGS84
          ↓
        GeoJSON
    """

    def __init__(
        self,
        tolerance: float = 2.0,
        min_overlap_length: float = 1.0,
        direction_tolerance: float = 25.0,
        min_output_length: float = 0.05,
        use_direction: bool = True,
        merge_result: bool = False,
    ):
        """
        参数
        ----

        tolerance:
            两条线之间允许的最大距离，单位：米。

            例如：

                0.1 = 10厘米
                0.5 = 50厘米
                1.0 = 1米
                2.0 = 2米

        min_overlap_length:
            最小重复长度。

            例如：

                两条线只有 0.5m 重合
                不认为是重复。

                两条线重合 5m
                才认为是重复。

        direction_tolerance:
            方向允许误差，单位：度。

            例如：

                0°
                完全同向

                10°
                基本同向

                90°
                垂直

        min_output_length:
            删除非常短的碎线。

        use_direction:
            是否判断方向。

        merge_result:
            最后是否尝试合并相邻线。
        """

        self.tolerance = float(tolerance)
        self.min_overlap_length = float(min_overlap_length)
        self.direction_tolerance = float(direction_tolerance)
        self.min_output_length = float(min_output_length)
        self.use_direction = use_direction
        self.merge_result = merge_result

        self.lines: List[LineString] = []

        self.tree: Optional[STRtree] = None

        self._tree_lines: List[LineString] = []

        self.to_projected: Optional[Transformer] = None
        self.to_wgs84: Optional[Transformer] = None

        self.projected_crs: Optional[CRS] = None

        self.center_lon = 0.0
        self.center_lat = 0.0

        self.stats = {
            "input_lines": 0,
            "output_lines": 0,
            "removed_lines": 0,
            "input_length": 0.0,
            "output_length": 0.0,
            "removed_length": 0.0,
        }

    # ========================================================
    # GeoJSON
    # ========================================================

    def read_geojson(
        self,
        path: str | Path,
    ) -> Dict[str, Any]:

        path = Path(path)

        with path.open(
            "r",
            encoding="utf-8",
        ) as f:
            return json.load(f)

    def write_geojson(
        self,
        geojson: Dict[str, Any],
        path: str | Path,
    ):
        path = Path(path)

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with path.open(
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                geojson,
                f,
                ensure_ascii=False,
                indent=2,
            )

    # ========================================================
    # Geometry
    # ========================================================

    @staticmethod
    def to_2d_line(line: LineString) -> Optional[LineString]:
        """丢弃 Z，避免 (x, y, z) 解包失败。"""

        if line is None or line.is_empty:
            return None

        coords = [
            (coord[0], coord[1])
            for coord in line.coords
        ]

        if len(coords) < 2:
            return None

        result = LineString(coords)

        if result.is_empty or result.length <= 0:
            return None

        return result

    def extract_lines(
        self,
        geometry,
    ) -> List[LineString]:

        if geometry is None:
            return []

        if geometry.is_empty:
            return []

        geom_type = geometry.geom_type

        if geom_type == "LineString":

            line_2d = self.to_2d_line(geometry)

            if line_2d is not None and line_2d.length > 0:
                return [line_2d]

            return []

        if geom_type == "MultiLineString":

            result = []

            for line in geometry.geoms:

                line_2d = self.to_2d_line(line)

                if line_2d is not None and line_2d.length > 0:
                    result.append(line_2d)

            return result

        if geom_type == "GeometryCollection":

            result = []

            for geom in geometry.geoms:

                result.extend(
                    self.extract_lines(geom)
                )

            return result

        return []

    def geojson_to_lines(
        self,
        geojson: Dict[str, Any],
    ) -> List[LineString]:

        result = []

        geojson_type = geojson.get("type")

        if geojson_type == "FeatureCollection":

            features = geojson.get(
                "features",
                [],
            )

            for feature in features:

                geometry_data = feature.get(
                    "geometry"
                )

                if not geometry_data:
                    continue

                try:
                    geometry = shape(
                        geometry_data
                    )
                except Exception:
                    continue

                result.extend(
                    self.extract_lines(
                        geometry
                    )
                )

        elif geojson_type == "Feature":

            geometry_data = geojson.get(
                "geometry"
            )

            if geometry_data:

                geometry = shape(
                    geometry_data
                )

                result.extend(
                    self.extract_lines(
                        geometry
                    )
                )

        else:

            geometry = shape(
                geojson
            )

            result.extend(
                self.extract_lines(
                    geometry
                )
            )

        return result

    # ========================================================
    # 投影
    # ========================================================

    def calculate_center(
        self,
        lines: List[LineString],
    ) -> Tuple[float, float]:

        merged = unary_union(lines)

        center = merged.centroid

        return center.x, center.y

    def create_projection(
        self,
        lon: float,
        lat: float,
    ):
        """
        自动选择 UTM。
        """

        zone = int(
            (lon + 180) / 6
        ) + 1

        if lat >= 0:
            epsg = 32600 + zone
        else:
            epsg = 32700 + zone

        self.projected_crs = CRS.from_epsg(
            epsg
        )

        self.to_projected = Transformer.from_crs(
            "EPSG:4326",
            self.projected_crs,
            always_xy=True,
        )

        self.to_wgs84 = Transformer.from_crs(
            self.projected_crs,
            "EPSG:4326",
            always_xy=True,
        )

    def project(
        self,
        geometry,
    ):

        if self.to_projected is None:
            raise RuntimeError(
                "投影转换器没有初始化"
            )

        return transform(
            self.to_projected.transform,
            geometry,
        )

    def unproject(
        self,
        geometry,
    ):

        if self.to_wgs84 is None:
            raise RuntimeError(
                "反投影转换器没有初始化"
            )

        return transform(
            self.to_wgs84.transform,
            geometry,
        )

    # ========================================================
    # 线方向
    # ========================================================

    @staticmethod
    def longest_linestring(geometry) -> Optional[LineString]:
        """从 LineString / MultiLineString / GeometryCollection 取出最长的单线。"""

        if geometry is None or geometry.is_empty:
            return None

        geom_type = geometry.geom_type

        if geom_type == "LineString":
            return geometry if geometry.length > 0 else None

        parts: List[LineString] = []

        if geom_type in ("MultiLineString", "GeometryCollection"):
            for geom in geometry.geoms:
                part = LineDeduplicator.longest_linestring(geom)
                if part is not None:
                    parts.append(part)

        if not parts:
            return None

        return max(parts, key=lambda item: item.length)

    @staticmethod
    def get_line_angle(
        line,
    ) -> float:
        """
        获取线的大致方向。

        返回：

            0 ~ 180

        方向相反认为相同。
        difference 后可能得到 MultiLineString，取最长一段计算方向。
        """

        line = LineDeduplicator.longest_linestring(line)

        if line is None:
            return 0.0

        coords = list(line.coords)

        if len(coords) < 2:
            return 0.0

        x1, y1 = coords[0][:2]
        x2, y2 = coords[-1][:2]

        angle = math.degrees(
            math.atan2(
                y2 - y1,
                x2 - x1,
            )
        )

        angle %= 180

        return angle

    @staticmethod
    def angle_difference(
        a: float,
        b: float,
    ) -> float:

        diff = abs(a - b)

        if diff > 90:
            diff = 180 - diff

        return diff

    def same_direction(
        self,
        line1: LineString,
        line2: LineString,
    ) -> bool:

        angle1 = self.get_line_angle(
            line1
        )

        angle2 = self.get_line_angle(
            line2
        )

        diff = self.angle_difference(
            angle1,
            angle2,
        )

        return (
            diff <= self.direction_tolerance
        )

    # ========================================================
    # 空间索引
    # ========================================================

    def build_index(
        self,
        lines: List[LineString],
    ):

        self._tree_lines = lines

        if not lines:
            self.tree = None
            return

        self.tree = STRtree(
            lines
        )

    def query_candidates(
        self,
        line: LineString,
    ) -> List[LineString]:

        if self.tree is None:
            return []

        search_area = self.line_corridor(line)

        indexes = self.tree.query(
            search_area
        )

        result = []

        for index in indexes:

            candidate = self._tree_lines[
                int(index)
            ]

            result.append(
                candidate
            )

        return result

    # ========================================================
    # 判断两条线是否可能重复
    # ========================================================

    def line_corridor(self, line: LineString):
        """线周围 tolerance 米的走廊，圆头，避免端点漏切。"""

        return line.buffer(
            self.tolerance,
            cap_style=1,
            join_style=1,
        )

    @staticmethod
    def tangent_angle(
        line: LineString,
        distance: float,
        sample: float = 1.0,
    ) -> float:
        """沿线某位置的局部切线方向，0~180。"""

        if line is None or line.is_empty or line.length <= 0:
            return 0.0

        sample = min(sample, max(line.length / 2.0, 1e-6))
        d1 = max(0.0, distance - sample)
        d2 = min(line.length, distance + sample)

        if abs(d2 - d1) < 1e-9:
            coords = list(line.coords)
            x1, y1 = coords[0][:2]
            x2, y2 = coords[-1][:2]
        else:
            p1 = line.interpolate(d1)
            p2 = line.interpolate(d2)
            x1, y1 = p1.x, p1.y
            x2, y2 = p2.x, p2.y

        return math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180

    def is_similar_line(
        self,
        line1: LineString,
        line2: LineString,
    ) -> bool:
        """
        判断两条线是否局部重复。

        用重叠段的本地方向，而不是整条线起终点方向。
        这样弯道、部分重合、切剩碎线都能对上。
        """

        if (
            line1 is None
            or line2 is None
            or line1.is_empty
            or line2.is_empty
        ):
            return False

        if line1.distance(line2) > self.tolerance:
            return False

        try:
            overlap = line1.intersection(
                self.line_corridor(line2)
            )
        except Exception:
            return False

        overlap_length = self.get_line_length(overlap)

        if overlap_length < self.min_overlap_length:
            return False

        if not self.use_direction:
            return True

        parts = self.extract_lines(overlap)

        if not parts:
            return False

        parallel_length = 0.0

        for part in parts:

            if part.length <= 0:
                continue

            samples = (
                [0.5]
                if part.length < 1.0
                else [0.2, 0.5, 0.8]
            )
            matched = 0

            for frac in samples:

                point = part.interpolate(frac, normalized=True)
                angle1 = self.tangent_angle(
                    part,
                    part.project(point),
                )
                angle2 = self.tangent_angle(
                    line2,
                    line2.project(point),
                )

                if (
                    self.angle_difference(angle1, angle2)
                    <= self.direction_tolerance
                ):
                    matched += 1

            if matched >= (len(samples) + 1) // 2:
                parallel_length += part.length

        return parallel_length >= self.min_overlap_length

    @staticmethod
    def get_line_length(
        geometry,
    ) -> float:

        if geometry is None:
            return 0.0

        if geometry.is_empty:
            return 0.0

        geom_type = geometry.geom_type

        if geom_type == "LineString":
            return geometry.length

        if geom_type == "MultiLineString":

            return sum(
                line.length
                for line in geometry.geoms
            )

        if geom_type == "GeometryCollection":

            return sum(
                LineDeduplicator.get_line_length(
                    geom
                )
                for geom in geometry.geoms
            )

        return 0.0

    # ========================================================
    # 删除重复部分
    # ========================================================

    def remove_duplicate_part(
        self,
        line: LineString,
        existing_lines: List[LineString],
    ) -> List[LineString]:

        remaining = line

        for existing in existing_lines:

            if remaining is None or remaining.is_empty:
                break

            try:
                remaining = remaining.difference(
                    self.line_corridor(existing)
                )
            except Exception:
                continue

        return self.extract_lines(remaining)

    # ========================================================
    # 线标准化
    # ========================================================

    @staticmethod
    def clean_line(
        line: LineString,
    ) -> Optional[LineString]:

        coords = list(
            line.coords
        )

        if len(coords) < 2:
            return None

        cleaned = [
            (coords[0][0], coords[0][1])
        ]

        for coord in coords[1:]:

            last = cleaned[-1]

            if (
                abs(coord[0] - last[0])
                > 1e-10
                or
                abs(coord[1] - last[1])
                > 1e-10
            ):

                cleaned.append(
                    (coord[0], coord[1])
                )

        if len(cleaned) < 2:
            return None

        result = LineString(
            cleaned
        )

        if result.length <= 0:
            return None

        return result

    # ========================================================
    # 主算法
    # ========================================================

    def keep_unique(
        self,
        lines: List[LineString],
    ) -> List[LineString]:
        """
        长线优先：已保留线附近的重复部分裁掉，只留下独有段。
        """

        lines = sorted(
            lines,
            key=lambda item: item.length,
            reverse=True,
        )

        result: List[LineString] = []

        for line in lines:

            if not result:
                result.append(line)
                continue

            self.build_index(result)

            candidates = self.query_candidates(line)

            if not candidates:
                result.append(line)
                continue

            similar_lines = [
                candidate
                for candidate in candidates
                if self.is_similar_line(line, candidate)
            ]

            if not similar_lines:
                result.append(line)
                continue

            remaining = self.remove_duplicate_part(
                line,
                similar_lines,
            )

            for part in remaining:
                if part.length >= self.min_output_length:
                    result.append(part)

        return [
            line
            for line in result
            if line.length >= self.min_output_length
        ]

    def deduplicate(
        self,
        lines: List[LineString],
    ) -> List[LineString]:

        if not lines:
            return []

        cleaned = []

        for line in lines:

            line = self.clean_line(line)

            if line is not None:
                cleaned.append(line)

        lines = cleaned

        self.stats["input_lines"] = len(lines)
        self.stats["input_length"] = sum(
            line.length for line in lines
        )

        # 第一轮：长线优先去重
        result = self.keep_unique(lines)

        # 第二轮：切剩碎线之间仍可能互相重叠
        result = self.keep_unique(result)

        if self.merge_result:
            result = self.merge_lines(result)

        self.stats["output_lines"] = len(result)
        self.stats["output_length"] = sum(
            line.length for line in result
        )
        self.stats["removed_length"] = (
            self.stats["input_length"]
            - self.stats["output_length"]
        )
        self.stats["removed_lines"] = (
            self.stats["input_lines"]
            - self.stats["output_lines"]
        )

        return result

    # ========================================================
    # 合并线
    # ========================================================

    def merge_lines(
        self,
        lines: List[LineString],
    ) -> List[LineString]:

        if not lines:
            return []

        try:

            merged = linemerge(
                unary_union(lines)
            )

        except Exception:

            return lines

        return self.extract_lines(
            merged
        )

    # ========================================================
    # 完整 GeoJSON 处理
    # ========================================================

    def process_geojson(
        self,
        input_path: str | Path,
        output_path: str | Path,
    ) -> Dict[str, Any]:

        print("=" * 70)
        print("LineDeduplicator")
        print("=" * 70)

        print(
            f"tolerance           : "
            f"{self.tolerance} m"
        )

        print(
            f"min_overlap_length  : "
            f"{self.min_overlap_length} m"
        )

        print(
            f"direction_tolerance : "
            f"{self.direction_tolerance}°"
        )

        # ----------------------------------------------------
        # 读取
        # ----------------------------------------------------

        geojson = self.read_geojson(
            input_path
        )

        lines_wgs84 = (
            self.geojson_to_lines(
                geojson
            )
        )

        print(
            f"输入线数量: "
            f"{len(lines_wgs84)}"
        )

        if not lines_wgs84:

            output = {
                "type": "FeatureCollection",
                "features": [],
            }

            self.write_geojson(
                output,
                output_path,
            )

            return output

        # ----------------------------------------------------
        # 中心点
        # ----------------------------------------------------

        self.center_lon, self.center_lat = (
            self.calculate_center(
                lines_wgs84
            )
        )

        print(
            "中心点:",
            self.center_lon,
            self.center_lat,
        )

        # ----------------------------------------------------
        # 创建投影
        # ----------------------------------------------------

        self.create_projection(
            self.center_lon,
            self.center_lat,
        )

        print(
            "投影:",
            self.projected_crs,
        )

        # ----------------------------------------------------
        # WGS84 -> UTM
        # ----------------------------------------------------

        projected_lines = []

        for line in lines_wgs84:

            try:

                projected = self.project(
                    line
                )

                if (
                    projected.length
                    > 0
                ):

                    projected_lines.append(
                        projected
                    )

            except Exception as e:

                print(
                    "投影失败:",
                    e,
                )

        # ----------------------------------------------------
        # 去重
        # ----------------------------------------------------

        result_projected = (
            self.deduplicate(
                projected_lines
            )
        )

        # ----------------------------------------------------
        # UTM -> WGS84
        # ----------------------------------------------------

        result_wgs84 = []

        for line in result_projected:

            try:

                wgs84 = self.unproject(
                    line
                )

                if (
                    wgs84.length
                    > 0
                ):

                    result_wgs84.append(
                        wgs84
                    )

            except Exception as e:

                print(
                    "反投影失败:",
                    e,
                )

        # ----------------------------------------------------
        # GeoJSON
        # ----------------------------------------------------

        features = []

        for index, line in enumerate(
            result_wgs84
        ):

            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "id": index + 1,
                    },
                    "geometry": mapping(
                        line
                    ),
                }
            )

        output = {
            "type": "FeatureCollection",
            "features": features,
        }

        self.write_geojson(
            output,
            output_path,
        )

        # ----------------------------------------------------
        # 输出统计
        # ----------------------------------------------------

        print()
        print("=" * 70)
        print("处理完成")
        print("=" * 70)

        print(
            "输入线数量:",
            self.stats["input_lines"],
        )

        print(
            "输出线数量:",
            self.stats["output_lines"],
        )

        print(
            "输入总长度:",
            f'{self.stats["input_length"]:.3f} m',
        )

        print(
            "输出总长度:",
            f'{self.stats["output_length"]:.3f} m',
        )

        print(
            "去除长度:",
            f'{self.stats["removed_length"]:.3f} m',
        )

        if self.stats["input_length"] > 0:

            percent = (
                self.stats["removed_length"]
                / self.stats["input_length"]
                * 100
            )

            print(
                "重复比例:",
                f"{percent:.2f}%",
            )

        print(
            "输出:",
            output_path,
        )

        return output


# ============================================================
# 示例
# ============================================================

if __name__ == "__main__":

    deduplicator = LineDeduplicator(
        # 两条线距离 2 米以内才允许认为可能重复
        tolerance=2.0,

        # 重复部分至少 1 米
        min_overlap_length=1.0,

        # 重叠段本地方向差不能超过 25°
        direction_tolerance=25.0,

        # 最终小于 5 厘米的碎线删除
        min_output_length=0.05,

        # 判断方向
        use_direction=True,

        # 最后不自动 merge
        merge_result=False,
    )

    deduplicator.process_geojson(
        "input.geojson",
        "output.geojson",
    )