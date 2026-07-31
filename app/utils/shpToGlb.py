import os
import json
import math
import gc
from pathlib import Path

import geopandas as gpd
import trimesh

from shapely.geometry import Polygon, MultiPolygon, box
from pyproj import Transformer


class ShpToGlb:
    """
    SHP -> GLB -> 3D Tiles 1.1

    坐标方案：
        WGS84 经纬度
             ↓
        ECEF EPSG:4978
             ↓
        Tile 中心建立 ENU 局部坐标
             ↓
        GLB 使用 ENU：
            X = East
            Y = North
            Z = Up

    tileset：
        root 使用 WGS84 region
        child 使用 local box + transform
        每一个 Tile 都有自己的 transform

    输出：
        tileset.json
        Tile_+000_+000.glb
        Tile_+000_+001.glb
        Tile_+001_+000.glb
        ...
    """

    # 每个 Tile 的经纬度大小
    TILE_LON_SIZE = 1.0
    TILE_LAT_SIZE = 1.0

    def __init__(self, data: dict):

        # ---------------------------------------------------------
        # 基础配置
        # ---------------------------------------------------------

        self.file = data.get("file")
        self.savePath = data.get("savePath")

        if not self.file:
            raise ValueError("缺少 file")

        if not self.savePath:
            raise ValueError("缺少 savePath")

        # ---------------------------------------------------------
        # 建筑高度
        # ---------------------------------------------------------

        self.heightType = data.get("heightType")
        self.height = data.get("height")

        self.heightField = data.get("heightField")
        self.heightMultiple = self.to_float(
            data.get("heightMultiple"),
            1
        )

        # ---------------------------------------------------------
        # 底部高度
        # ---------------------------------------------------------

        self.bottomHeightType = data.get("bottomHeightType")
        self.bottomHeight = data.get("bottomHeight")

        self.bottomHeightField = data.get(
            "bottomHeightField"
        )

        self.bottomHeightMultiple = self.to_float(
            data.get("bottomHeightMultiple"),
            1
        )

        Path(self.savePath).mkdir(
            parents=True,
            exist_ok=True
        )

        # ---------------------------------------------------------
        # WGS84 -> ECEF
        #
        # EPSG:4979 = WGS84 3D
        # EPSG:4978 = WGS84 ECEF
        # ---------------------------------------------------------

        self.wgs84_to_ecef = Transformer.from_crs(
            "EPSG:4979",
            "EPSG:4978",
            always_xy=True
        )

        # ---------------------------------------------------------
        # 读取 SHP
        # ---------------------------------------------------------

        print("开始读取 SHP...")

        self.gdf = self.load_data()

        if self.gdf.empty:
            raise ValueError("SHP 数据为空")

        print(
            f"SHP Feature 数量: {len(self.gdf)}"
        )

        # ---------------------------------------------------------
        # 数据范围
        # ---------------------------------------------------------

        (
            min_lon,
            min_lat,
            max_lon,
            max_lat
        ) = self.get_bounds(self.gdf)

        print(
            "数据范围:",
            min_lon,
            min_lat,
            max_lon,
            max_lat
        )

        # ---------------------------------------------------------
        # Tile 数量
        # ---------------------------------------------------------

        tile_count = self.get_tile_count(
            min_lon,
            min_lat,
            max_lon,
            max_lat
        )

        print(
            f"预计 Tile 数量: {tile_count}"
        )

        # ---------------------------------------------------------
        # 流式生成 Tile
        #
        # 不再：
        # tiles = [...]
        #
        # 而是：
        # for tile in generator
        # ---------------------------------------------------------

        generated_tiles = []

        for tile_index, tile in enumerate(
            self.create_tiles(
                min_lon,
                min_lat,
                max_lon,
                max_lat
            ),
            start=1
        ):

            print(
                f"\n[{tile_index}/{tile_count}] "
                f"处理 "
                f"Tile_{tile['x']:+04d}_{tile['y']:+04d}"
            )

            result = self.generate_tile(
                tile,
                self.gdf,
                self.savePath
            )

            if result is not None:
                generated_tiles.append(result)

            # 当前 Tile 完成后主动回收
            gc.collect()

        print(
            f"\n实际生成 Tile 数量: "
            f"{len(generated_tiles)}"
        )

        if not generated_tiles:
            raise ValueError(
                "没有生成任何 GLB，请检查 SHP 几何和 Tile 范围"
            )

        # ---------------------------------------------------------
        # 生成 tileset.json
        # ---------------------------------------------------------

        self.generate_tileset(
            generated_tiles,
            self.savePath
        )

        print("\n转换完成")
        print(
            f"输出目录: {self.savePath}"
        )

    # =========================================================
    # 工具
    # =========================================================

    @staticmethod
    def to_float(value, default=0):
        try:
            if value is None:
                return float(default)

            value = float(value)

            if math.isnan(value):
                return float(default)

            return value

        except (
            TypeError,
            ValueError
        ):
            return float(default)

    # =========================================================
    # SHP
    # =========================================================

    def load_data(self):

        gdf = gpd.read_file(
            self.file
        )

        if gdf.empty:
            return gdf

        if gdf.crs is None:
            raise ValueError(
                "SHP 没有 CRS，无法转换到 EPSG:4326"
            )

        gdf = gdf.to_crs(
            "EPSG:4326"
        )

        # 创建空间索引
        _ = gdf.sindex

        return gdf

    def get_bounds(self, gdf):

        (
            min_lon,
            min_lat,
            max_lon,
            max_lat
        ) = gdf.total_bounds

        return (
            float(min_lon),
            float(min_lat),
            float(max_lon),
            float(max_lat)
        )

    # =========================================================
    # Tile
    # =========================================================

    def get_tile_count(
        self,
        min_lon,
        min_lat,
        max_lon,
        max_lat
    ):

        start_lon = (
            math.floor(
                min_lon / self.TILE_LON_SIZE
            )
            * self.TILE_LON_SIZE
        )

        start_lat = (
            math.floor(
                min_lat / self.TILE_LAT_SIZE
            )
            * self.TILE_LAT_SIZE
        )

        end_lon = (
            math.ceil(
                max_lon / self.TILE_LON_SIZE
            )
            * self.TILE_LON_SIZE
        )

        end_lat = (
            math.ceil(
                max_lat / self.TILE_LAT_SIZE
            )
            * self.TILE_LAT_SIZE
        )

        x_count = max(
            1,
            int(
                round(
                    (
                        end_lon -
                        start_lon
                    )
                    / self.TILE_LON_SIZE
                )
            )
        )

        y_count = max(
            1,
            int(
                round(
                    (
                        end_lat -
                        start_lat
                    )
                    / self.TILE_LAT_SIZE
                )
            )
        )

        return x_count * y_count

    def create_tiles(
        self,
        min_lon,
        min_lat,
        max_lon,
        max_lat
    ):
        """
        Generator。

        不保存所有 Tile。
        """

        start_lon = (
            math.floor(
                min_lon / self.TILE_LON_SIZE
            )
            * self.TILE_LON_SIZE
        )

        start_lat = (
            math.floor(
                min_lat / self.TILE_LAT_SIZE
            )
            * self.TILE_LAT_SIZE
        )

        end_lon = (
            math.ceil(
                max_lon / self.TILE_LON_SIZE
            )
            * self.TILE_LON_SIZE
        )

        end_lat = (
            math.ceil(
                max_lat / self.TILE_LAT_SIZE
            )
            * self.TILE_LAT_SIZE
        )

        tile_x = 0
        lon = start_lon

        while lon < end_lon:

            next_lon = min(
                lon + self.TILE_LON_SIZE,
                end_lon
            )

            tile_y = 0
            lat = start_lat

            while lat < end_lat:

                next_lat = min(
                    lat + self.TILE_LAT_SIZE,
                    end_lat
                )

                yield {
                    "x": tile_x,
                    "y": tile_y,
                    "min_lon": float(lon),
                    "min_lat": float(lat),
                    "max_lon": float(next_lon),
                    "max_lat": float(next_lat)
                }

                lat = next_lat
                tile_y += 1

            lon = next_lon
            tile_x += 1

    # =========================================================
    # ENU / ECEF
    # =========================================================

    def get_tile_transform(
        self,
        lon,
        lat
    ):
        """
        创建：

            ENU Local -> ECEF

        ENU:
            X = East
            Y = North
            Z = Up

        返回：
            transform
            origin_ecef
        """

        lon_rad = math.radians(
            lon
        )

        lat_rad = math.radians(
            lat
        )

        # -----------------------------------------------------
        # Tile 原点 ECEF
        # -----------------------------------------------------

        origin_x, origin_y, origin_z = (
            self.wgs84_to_ecef.transform(
                lon,
                lat,
                0
            )
        )

        # -----------------------------------------------------
        # East
        # -----------------------------------------------------

        east = (
            -math.sin(lon_rad),
            math.cos(lon_rad),
            0.0
        )

        # -----------------------------------------------------
        # North
        # -----------------------------------------------------

        north = (
            -math.sin(lat_rad)
            * math.cos(lon_rad),

            -math.sin(lat_rad)
            * math.sin(lon_rad),

            math.cos(lat_rad)
        )

        # -----------------------------------------------------
        # Up
        # -----------------------------------------------------

        up = (
            math.cos(lat_rad)
            * math.cos(lon_rad),

            math.cos(lat_rad)
            * math.sin(lon_rad),

            math.sin(lat_rad)
        )

        # -----------------------------------------------------
        # 3D Tiles Matrix4
        #
        # 3D Tiles 使用 column-major
        #
        #       East    North   Up      Translation
        #
        # X     e.x     n.x     u.x     origin.x
        # Y     e.y     n.y     u.y     origin.y
        # Z     e.z     n.z     u.z     origin.z
        # W     0       0       0       1
        # -----------------------------------------------------

        transform = [
            east[0],
            east[1],
            east[2],
            0.0,

            north[0],
            north[1],
            north[2],
            0.0,

            up[0],
            up[1],
            up[2],
            0.0,

            origin_x,
            origin_y,
            origin_z,
            1.0
        ]

        return (
            transform,
            (
                origin_x,
                origin_y,
                origin_z
            )
        )

    def wgs84_to_enu(
        self,
        lon,
        lat,
        origin_lon,
        origin_lat,
        east,
        north,
        up
    ):
        """
        WGS84 经纬度 -> Tile ENU。
        """

        x, y, z = (
            self.wgs84_to_ecef.transform(
                lon,
                lat,
                0
            )
        )

        ox, oy, oz = (
            self.wgs84_to_ecef.transform(
                origin_lon,
                origin_lat,
                0
            )
        )

        dx = x - ox
        dy = y - oy
        dz = z - oz

        local_x = (
            dx * east[0] +
            dy * east[1] +
            dz * east[2]
        )

        local_y = (
            dx * north[0] +
            dy * north[1] +
            dz * north[2]
        )

        local_z = (
            dx * up[0] +
            dy * up[1] +
            dz * up[2]
        )

        return (
            local_x,
            local_y,
            local_z
        )

    def polygon_to_local(
        self,
        polygon,
        origin_lon,
        origin_lat
    ):
        """
        Polygon：

            WGS84
              ↓
            ENU

        X = East
        Y = North
        Z = 0
        """

        lon_rad = math.radians(
            origin_lon
        )

        lat_rad = math.radians(
            origin_lat
        )

        east = (
            -math.sin(lon_rad),
            math.cos(lon_rad),
            0.0
        )

        north = (
            -math.sin(lat_rad)
            * math.cos(lon_rad),

            -math.sin(lat_rad)
            * math.sin(lon_rad),

            math.cos(lat_rad)
        )

        up = (
            math.cos(lat_rad)
            * math.cos(lon_rad),

            math.cos(lat_rad)
            * math.sin(lon_rad),

            math.sin(lat_rad)
        )

        exterior = []

        for lon, lat in polygon.exterior.coords:

            x, y, z = self.wgs84_to_enu(
                lon,
                lat,
                origin_lon,
                origin_lat,
                east,
                north,
                up
            )

            exterior.append([
                x,
                y
            ])

        holes = []

        for ring in polygon.interiors:

            hole = []

            for lon, lat in ring.coords:

                x, y, z = self.wgs84_to_enu(
                    lon,
                    lat,
                    origin_lon,
                    origin_lat,
                    east,
                    north,
                    up
                )

                hole.append([
                    x,
                    y
                ])

            holes.append(hole)

        return Polygon(
            exterior,
            holes=holes
        )

    # =========================================================
    # Tile Feature
    # =========================================================

    def get_tile_features(
        self,
        gdf,
        tile
    ):

        tile_polygon = box(
            tile["min_lon"],
            tile["min_lat"],
            tile["max_lon"],
            tile["max_lat"]
        )

        index = gdf.sindex.query(
            tile_polygon,
            predicate="intersects"
        )

        if len(index) == 0:
            return gdf.iloc[0:0]

        return gdf.iloc[index]

    # =========================================================
    # Polygon
    # =========================================================

    def fix_polygon(
        self,
        polygon
    ):

        if polygon is None:
            return None

        if polygon.is_empty:
            return None

        if not polygon.is_valid:

            try:
                polygon = polygon.buffer(0)

            except Exception:
                return None

        if polygon is None:
            return None

        if polygon.is_empty:
            return None

        return polygon

    # =========================================================
    # Height
    # =========================================================

    def get_height(
        self,
        row
    ):

        if not self.heightField:
            return self.to_float(
                self.height,
                10
            )

        value = row.get(
            self.heightField
        )

        if value is None:
            return self.to_float(
                self.height,
                10
            )

        try:
            value = float(value)

        except (
            TypeError,
            ValueError
        ):
            return self.to_float(
                self.height,
                10
            )

        if math.isnan(value):
            return self.to_float(
                self.height,
                10
            )

        return (
            value *
            self.heightMultiple
        )

    def get_base_height(
        self,
        row
    ):

        if not self.bottomHeightField:
            return self.to_float(
                self.bottomHeight,
                0
            )

        value = row.get(
            self.bottomHeightField
        )

        if value is None:
            return self.to_float(
                self.bottomHeight,
                0
            )

        try:
            value = float(value)

        except (
            TypeError,
            ValueError
        ):
            return self.to_float(
                self.bottomHeight,
                0
            )

        if math.isnan(value):
            return self.to_float(
                self.bottomHeight,
                0
            )

        return (
            value *
            self.bottomHeightMultiple
        )

    # =========================================================
    # Polygon -> Mesh
    # =========================================================

    def polygon_to_mesh(
        self,
        polygon,
        height,
        base_height
    ):

        polygon = self.fix_polygon(
            polygon
        )

        if polygon is None:
            return None

        if not isinstance(
            polygon,
            Polygon
        ):
            return None

        extrusion_height = (
            height -
            base_height
        )

        if extrusion_height <= 0:
            return None

        try:

            # 推荐 mapbox-earcut
            #
            # pip install mapbox-earcut
            #
            mesh = (
                trimesh.creation.extrude_polygon(
                    polygon,
                    extrusion_height,
                    engine="earcut"
                )
            )

            mesh.apply_translation([
                0,
                0,
                base_height
            ])

            return mesh

        except Exception as e:

            print(
                "Polygon 转 Mesh 失败:",
                e
            )

            return None

    # =========================================================
    # 生成 Tile GLB
    # =========================================================

    def generate_tile(
        self,
        tile,
        gdf,
        output_dir
    ):

        tile_x = tile["x"]
        tile_y = tile["y"]

        tile_name = (
            f"Tile_"
            f"{tile_x:+04d}_"
            f"{tile_y:+04d}"
        )

        # -----------------------------------------------------
        # 当前 Tile 中心
        # -----------------------------------------------------

        center_lon = (
            tile["min_lon"] +
            tile["max_lon"]
        ) / 2.0

        center_lat = (
            tile["min_lat"] +
            tile["max_lat"]
        ) / 2.0

        # -----------------------------------------------------
        # 当前 Tile 的 ENU transform
        # -----------------------------------------------------

        transform, origin_ecef = (
            self.get_tile_transform(
                center_lon,
                center_lat
            )
        )

        tile_gdf = self.get_tile_features(
            gdf,
            tile
        )

        if tile_gdf.empty:
            return None

        # -----------------------------------------------------
        # 当前 Tile WGS84 Polygon
        # -----------------------------------------------------

        tile_polygon = box(
            tile["min_lon"],
            tile["min_lat"],
            tile["max_lon"],
            tile["max_lat"]
        )

        meshes = []

        building_count = 0

        try:

            for _, row in tile_gdf.iterrows():

                geometry = row.geometry

                if (
                    geometry is None
                    or geometry.is_empty
                ):
                    continue

                height = (
                    self.height
                    if self.heightType == "fixed"
                    else self.get_height(row)
                )

                base_height = (
                    self.bottomHeight
                    if self.bottomHeightType == "fixed"
                    else self.get_base_height(row)
                )

                height = self.to_float(
                    height,
                    10
                )

                base_height = self.to_float(
                    base_height,
                    0
                )

                if height <= base_height:
                    continue

                # -------------------------------------------------
                # Polygon
                # -------------------------------------------------

                if isinstance(
                    geometry,
                    Polygon
                ):

                    polygons = [
                        geometry
                    ]

                elif isinstance(
                    geometry,
                    MultiPolygon
                ):

                    polygons = list(
                        geometry.geoms
                    )

                else:
                    continue

                # -------------------------------------------------
                # 每一个 Polygon
                # -------------------------------------------------

                for polygon in polygons:

                    polygon = (
                        self.fix_polygon(
                            polygon
                        )
                    )

                    if polygon is None:
                        continue

                    # -------------------------------------------------
                    # 裁剪到当前 Tile
                    # -------------------------------------------------

                    clipped = (
                        polygon.intersection(
                            tile_polygon
                        )
                    )

                    clipped = (
                        self.fix_polygon(
                            clipped
                        )
                    )

                    if clipped is None:
                        continue

                    # -------------------------------------------------
                    # intersection 以后可能是 MultiPolygon
                    # -------------------------------------------------

                    if isinstance(
                        clipped,
                        MultiPolygon
                    ):

                        clipped_polygons = list(
                            clipped.geoms
                        )

                    elif isinstance(
                        clipped,
                        Polygon
                    ):

                        clipped_polygons = [
                            clipped
                        ]

                    else:
                        continue

                    # -------------------------------------------------
                    # 转 ENU
                    # -------------------------------------------------

                    for clipped_polygon in clipped_polygons:

                        clipped_polygon = (
                            self.fix_polygon(
                                clipped_polygon
                            )
                        )

                        if clipped_polygon is None:
                            continue

                        local_polygon = (
                            self.polygon_to_local(
                                clipped_polygon,
                                center_lon,
                                center_lat
                            )
                        )

                        local_polygon = (
                            self.fix_polygon(
                                local_polygon
                            )
                        )

                        if local_polygon is None:
                            continue

                        # -------------------------------------------------
                        # ENU Polygon -> Mesh
                        # -------------------------------------------------

                        mesh = (
                            self.polygon_to_mesh(
                                local_polygon,
                                height,
                                base_height
                            )
                        )

                        if mesh is None:
                            continue

                        meshes.append(
                            mesh
                        )

                        building_count += 1

            if not meshes:
                return None

            # -----------------------------------------------------
            # 只 concatenate 一次
            # -----------------------------------------------------

            combined = (
                trimesh.util.concatenate(
                    meshes
                )
            )

        finally:

            del tile_gdf
            del meshes

            gc.collect()

        # ---------------------------------------------------------
        # Material
        # ---------------------------------------------------------

        material = (
            trimesh.visual.material.PBRMaterial(
                baseColorFactor=[
                    0.85,
                    0.85,
                    0.85,
                    1.0
                ],
                metallicFactor=0.0,
                roughnessFactor=0.9
            )
        )

        combined.visual.material = material

        # ---------------------------------------------------------
        # GLB
        # ---------------------------------------------------------

        glb_name = (
            tile_name +
            ".glb"
        )

        glb_path = os.path.join(
            output_dir,
            glb_name
        )

        combined.export(
            glb_path,
            file_type="glb"
        )

        # ---------------------------------------------------------
        # Local Bounds
        # ---------------------------------------------------------

        bounds = combined.bounds

        local_min = bounds[0]
        local_max = bounds[1]

        local_center = (
            local_min +
            local_max
        ) / 2.0

        half_size = (
            local_max -
            local_min
        ) / 2.0

        # ---------------------------------------------------------
        # Cesium 3D Tiles box
        #
        # box:
        #
        # [cx, cy, cz,
        #  hx, 0, 0,
        #  0, hy, 0,
        #  0, 0, hz]
        #
        # 这是 Local ENU 坐标
        # ---------------------------------------------------------

        box_volume = [
            float(local_center[0]),
            float(local_center[1]),
            float(local_center[2]),

            float(half_size[0]),
            0.0,
            0.0,

            0.0,
            float(half_size[1]),
            0.0,

            0.0,
            0.0,
            float(half_size[2])
        ]

        # ---------------------------------------------------------
        # WGS84 Tile Region
        #
        # 用于 root
        # ---------------------------------------------------------

        result = {
            "id": (
                f"{tile_x:+04d}_"
                f"{tile_y:+04d}"
            ),

            "x": tile_x,
            "y": tile_y,

            "glb": glb_name,

            "min_lon": float(
                tile["min_lon"]
            ),
            "min_lat": float(
                tile["min_lat"]
            ),
            "max_lon": float(
                tile["max_lon"]
            ),
            "max_lat": float(
                tile["max_lat"]
            ),

            "min_height": float(
                local_min[2]
            ),
            "max_height": float(
                local_max[2]
            ),

            "building_count":
                building_count,

            "box": box_volume,

            "transform": transform,

            "origin_ecef": [
                float(origin_ecef[0]),
                float(origin_ecef[1]),
                float(origin_ecef[2])
            ]
        }

        print(
            f"完成 {glb_name} "
            f"建筑={building_count} "
            f"顶点={len(combined.vertices):,} "
            f"三角面={len(combined.faces):,}"
        )

        # ---------------------------------------------------------
        # 释放大 Mesh
        # ---------------------------------------------------------

        del combined

        gc.collect()

        return result

    # =========================================================
    # Tileset
    # =========================================================

    def generate_tileset(
        self,
        tiles,
        savePath
    ):

        if not tiles:
            raise ValueError(
                "没有有效 Tile"
            )

        # ---------------------------------------------------------
        # Root WGS84 Region
        # ---------------------------------------------------------

        min_lon = min(
            tile["min_lon"]
            for tile in tiles
        )

        min_lat = min(
            tile["min_lat"]
            for tile in tiles
        )

        max_lon = max(
            tile["max_lon"]
            for tile in tiles
        )

        max_lat = max(
            tile["max_lat"]
            for tile in tiles
        )

        min_height = min(
            tile["min_height"]
            for tile in tiles
        )

        max_height = max(
            tile["max_height"]
            for tile in tiles
        )

        # ---------------------------------------------------------
        # Children
        #
        # 每一个 child 都有自己的：
        #
        #   box
        #   transform
        #   glb
        #
        # 这是关键。
        #
        # 因为每个 Tile 的 Local ENU 原点不同。
        # ---------------------------------------------------------

        children = []

        for tile in tiles:

            children.append({
                "boundingVolume": {
                    "box": tile["box"]
                },

                "geometricError": 0,

                "refine": "REPLACE",

                "transform": tile["transform"],

                "content": {
                    "uri": tile["glb"]
                }
            })

        # ---------------------------------------------------------
        # Tileset
        # ---------------------------------------------------------

        tileset = {
            "asset": {
                "version": "1.1",
                "gltfUpAxis": "Z"
            },

            "geometricError": 500,

            "refine": "REPLACE",

            "root": {
                # Root 使用 WGS84 region
                # 不使用单一 transform。
                #
                # 因为每一个 child 有自己的 ENU 原点。
                "boundingVolume": {
                    "region": [
                        math.radians(
                            min_lon
                        ),
                        math.radians(
                            min_lat
                        ),
                        math.radians(
                            max_lon
                        ),
                        math.radians(
                            max_lat
                        ),
                        min_height,
                        max_height
                    ]
                },

                "geometricError": 500,

                "refine": "REPLACE",

                "children": children
            }
        }

        # ---------------------------------------------------------
        # 保存
        # ---------------------------------------------------------

        tileset_path = os.path.join(
            savePath,
            "tileset.json"
        )

        with open(
            tileset_path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                tileset,
                f,
                ensure_ascii=False,
                indent=2
            )

        print(
            f"tileset.json 已生成:"
            f"\n{tileset_path}"
        )


# =============================================================
# 直接运行测试
# =============================================================
#
# 如果你是 FastAPI 调用：
#
#     shpToGlb = ShpToGlb(data)
#
# 就不需要执行下面的 main。
#
# 如果直接运行：
#
#     python shpToGlb_memory_optimized.py
#
# 可以取消下面注释。
# =============================================================

# if __name__ == "__main__":

#     data = {
#         "file": r"D:\data\building.shp",
#         "savePath": r"D:\data\output",

#         "heightType": "fixed",
#         "height": 20,

#         "heightField": None,
#         "heightMultiple": 1,

#         "bottomHeightType": "fixed",
#         "bottomHeight": 0,

#         "bottomHeightField": None,
#         "bottomHeightMultiple": 1
#     }

#     ShpToGlb(data)