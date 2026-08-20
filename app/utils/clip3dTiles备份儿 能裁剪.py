import copy
import json
import shutil
import struct
from pathlib import Path

import numpy as np
import trimesh

from pyproj import Transformer

from shapely.geometry import (
    shape,
    Polygon,
    MultiPolygon,
    GeometryCollection,
)

from shapely.ops import triangulate, unary_union
from shapely.prepared import prep


class Clip3dTiles:
    """
    3D Tiles / B3DM / GLB XY 裁剪

    坐标处理：

        GeoJSON WGS84
            |
            v
        WGS84 -> ECEF
            |
            v
           ENU
            |
            v
        裁剪区域 XY


    B3DM：

        GLB POSITION
            |
            v
        GLTF Node Transform
            |
            v
        + RTC_CENTER
            |
            v
        Tileset Transform
            |
            v
        ECEF / Local / ENU
            |
            v
           ENU
            |
            v
         XY 裁剪
            |
            v
        裁剪后的 ENU
            |
            v
        转回原 GLB Local
            |
            v
        新 GLB


    mode:

        keep
            只保留 GeoJSON 内部

        remove
            删除 GeoJSON 内部


    b3dmCoordinateMode:

        auto
            自动判断

        ecef
            RTC_CENTER 是 ECEF

        local_rtc
            GLB POSITION + RTC_CENTER 是模型局部坐标

        enu
            GLB POSITION + RTC_CENTER 本身就是 ENU
    """

    # ================================================================
    # 初始化
    # ================================================================

    def __init__(self, options: dict):

        self.input_path = Path(
            options["inputPath"]
        ).resolve()

        self.output_path = Path(
            options["outputPath"]
        ).resolve()

        self.clip_file = Path(
            options["clipPolygon"]
        ).resolve()

        self.mode = options.get(
            "mode",
            "keep"
        )

        if self.mode not in (
            "keep",
            "remove",
        ):
            raise ValueError(
                "mode 必须是 keep 或 remove"
            )

        self.b3dm_coordinate_mode = options.get(
            "b3dmCoordinateMode",
            "local_rtc",
        )

        if self.b3dm_coordinate_mode not in (
            "auto",
            "ecef",
            "local_rtc",
            "enu",
        ):
            raise ValueError(
                "b3dmCoordinateMode 必须是 "
                "auto / ecef / local_rtc / enu"
            )

        # ------------------------------------------------------------
        # WGS84 -> ECEF
        # ------------------------------------------------------------

        self.wgs84_to_ecef = Transformer.from_crs(
            "EPSG:4979",
            "EPSG:4978",
            always_xy=True,
        )

        # ------------------------------------------------------------
        # 文件检查
        # ------------------------------------------------------------

        if not self.input_path.exists():
            raise FileNotFoundError(
                f"输入不存在：{self.input_path}"
            )

        if not self.clip_file.exists():
            raise FileNotFoundError(
                f"GeoJSON 不存在：{self.clip_file}"
            )

        self.output_path.mkdir(
            parents=True,
            exist_ok=True,
        )

        # ------------------------------------------------------------
        # GeoJSON
        # ------------------------------------------------------------

        self.clip_polygon_wgs84 = self.load_geojson()

        if (
            self.clip_polygon_wgs84 is None
            or self.clip_polygon_wgs84.is_empty
        ):
            raise ValueError(
                "GeoJSON geometry 为空"
            )

        self.clip_polygon_wgs84 = (
            self.clip_polygon_wgs84.buffer(0)
        )

        if self.clip_polygon_wgs84.is_empty:
            raise ValueError(
                "GeoJSON Polygon 无效"
            )

        # ------------------------------------------------------------
        # ENU 原点
        # ------------------------------------------------------------

        self.enu_origin = (
            self.calculate_enu_origin(
                self.clip_polygon_wgs84
            )
        )

        self.enu_origin_ecef = (
            self.wgs84_to_ecef_xyz(
                self.enu_origin[0],
                self.enu_origin[1],
                self.enu_origin[2],
            )
        )

        self.ecef_to_enu_matrix = (
            self.build_ecef_to_enu_matrix(
                self.enu_origin[0],
                self.enu_origin[1],
            )
        )

        # ------------------------------------------------------------
        # GeoJSON -> ENU
        # ------------------------------------------------------------

        self.clip_polygon = (
            self.convert_polygon_to_enu(
                self.clip_polygon_wgs84
            )
        )

        self.clip_polygon = (
            self.clip_polygon.buffer(0)
        )

        if self.clip_polygon.is_empty:
            raise ValueError(
                "GeoJSON 转 ENU 后为空"
            )

        self.clip_bbox = (
            self.clip_polygon.bounds
        )

        self.clip_prepared = prep(
            self.clip_polygon
        )

        # ------------------------------------------------------------
        # 统计
        # ------------------------------------------------------------

        self.stats = {

            "tilesets": 0,
            "tiles": 0,

            "glb_total": 0,
            "glb_copied": 0,
            "glb_clipped": 0,
            "glb_removed": 0,

            "b3dm_total": 0,
            "b3dm_copied": 0,
            "b3dm_clipped": 0,
            "b3dm_removed": 0,

            "json_total": 0,
            "json_written": 0,

            "other_copied": 0,

            "triangles_input": 0,
            "triangles_output": 0,
        }

        self.processed_json = set()

        # 避免重复处理同一个文件
        self.processed_resources = set()

        self.run()

    # ================================================================
    # 主流程
    # ================================================================

    def run(self):

        print()
        print("=" * 100)
        print("开始处理 3D Tiles")
        print("=" * 100)

        print(
            "输入:",
            self.input_path,
        )

        print(
            "输出:",
            self.output_path,
        )

        print(
            "GeoJSON:",
            self.clip_file,
        )

        print(
            "模式:",
            self.mode,
        )

        print(
            "B3DM 坐标模式:",
            self.b3dm_coordinate_mode,
        )

        print()
        print("ENU 原点:")

        print(
            "  lon:",
            self.enu_origin[0],
        )

        print(
            "  lat:",
            self.enu_origin[1],
        )

        print(
            "  height:",
            self.enu_origin[2],
        )

        print()
        print(
            "ENU 原点 ECEF:",
            self.enu_origin_ecef,
        )

        print()
        print("GeoJSON ENU XY:")

        print(
            "  min:",
            self.clip_bbox[0],
            self.clip_bbox[1],
        )

        print(
            "  max:",
            self.clip_bbox[2],
            self.clip_bbox[3],
        )

        print()
        print(
            "GeoJSON geometry:",
            self.clip_polygon.geom_type,
        )

        print("=" * 100)

        # ------------------------------------------------------------
        # 查找 tileset
        # ------------------------------------------------------------

        if self.input_path.is_file():

            if (
                self.input_path.name.lower()
                != "tileset.json"
            ):
                raise ValueError(
                    "inputPath 如果是文件，必须是 tileset.json"
                )

            tilesets = [
                self.input_path
            ]

        else:

            print(
                "正在递归查找 tileset.json..."
            )

            tilesets = sorted(
                p
                for p in self.input_path.rglob(
                    "tileset.json"
                )
                if p.is_file()
            )

        if not tilesets:
            raise FileNotFoundError(
                "没有找到 tileset.json"
            )

        print(
            f"找到 {len(tilesets)} 个 tileset.json"
        )

        # ------------------------------------------------------------
        # 处理
        # ------------------------------------------------------------

        for index, tileset_file in enumerate(
            tilesets,
            start=1,
        ):

            print()
            print("#" * 100)

            print(
                f"[{index}/{len(tilesets)}]",
                tileset_file,
            )

            print("#" * 100)

            self.process_tileset_file(
                tileset_file
            )

        print()
        print("=" * 100)
        print("全部处理完成")
        print("=" * 100)

        print(
            json.dumps(
                self.stats,
                ensure_ascii=False,
                indent=2,
            )
        )

        print()
        print(
            "输出目录:",
            self.output_path,
        )

        print("=" * 100)

    # ================================================================
    # WGS84 -> ECEF
    # ================================================================

    def wgs84_to_ecef_xyz(
        self,
        lon,
        lat,
        height=0.0,
    ):

        x, y, z = (
            self.wgs84_to_ecef.transform(
                lon,
                lat,
                height,
            )
        )

        return np.array(
            [x, y, z],
            dtype=np.float64,
        )

    # ================================================================
    # ECEF -> ENU
    # ================================================================

    def ecef_to_enu(
        self,
        xyz,
    ):

        xyz = np.asarray(
            xyz,
            dtype=np.float64,
        )

        if xyz.ndim == 1:
            xyz = xyz.reshape(1, 3)

            result = (
                self.ecef_to_enu(
                    xyz
                )
            )

            return result[0]

        delta = (
            xyz
            - self.enu_origin_ecef
        )

        return (
            delta
            @ self.ecef_to_enu_matrix.T
        )

    # ================================================================
    # ENU -> ECEF
    # ================================================================

    def enu_to_ecef(
        self,
        enu,
    ):

        enu = np.asarray(
            enu,
            dtype=np.float64,
        )

        if enu.ndim == 1:
            enu = enu.reshape(1, 3)

            result = (
                self.enu_to_ecef(
                    enu
                )
            )

            return result[0]

        delta = (
            enu
            @ self.ecef_to_enu_matrix
        )

        return (
            delta
            + self.enu_origin_ecef
        )

    # ================================================================
    # ENU 原点
    # ================================================================

    def calculate_enu_origin(
        self,
        polygon,
    ):

        centroid = polygon.centroid

        return (
            centroid.x,
            centroid.y,
            0.0,
        )

    # ================================================================
    # ECEF -> ENU Matrix
    # ================================================================

    @staticmethod
    def build_ecef_to_enu_matrix(
        lon,
        lat,
    ):

        lon_rad = np.radians(lon)
        lat_rad = np.radians(lat)

        sin_lon = np.sin(lon_rad)
        cos_lon = np.cos(lon_rad)

        sin_lat = np.sin(lat_rad)
        cos_lat = np.cos(lat_rad)

        return np.array(

            [
                [
                    -sin_lon,
                    cos_lon,
                    0,
                ],

                [
                    -sin_lat * cos_lon,
                    -sin_lat * sin_lon,
                    cos_lat,
                ],

                [
                    cos_lat * cos_lon,
                    cos_lat * sin_lon,
                    sin_lat,
                ],
            ],

            dtype=np.float64,
        )

    # ================================================================
    # GeoJSON -> ENU
    # ================================================================

    def convert_polygon_to_enu(
        self,
        geometry,
    ):

        if (
            geometry is None
            or geometry.is_empty
        ):
            return geometry

        if isinstance(
            geometry,
            Polygon,
        ):

            exterior = []

            for coord in geometry.exterior.coords:

                lon = coord[0]
                lat = coord[1]

                ecef = (
                    self.wgs84_to_ecef_xyz(
                        lon,
                        lat,
                        0.0,
                    )
                )

                enu = (
                    self.ecef_to_enu(
                        ecef
                    )
                )

                exterior.append(
                    (
                        enu[0],
                        enu[1],
                    )
                )

            interiors = []

            for ring in geometry.interiors:

                coords = []

                for coord in ring.coords:

                    lon = coord[0]
                    lat = coord[1]

                    ecef = (
                        self.wgs84_to_ecef_xyz(
                            lon,
                            lat,
                            0.0,
                        )
                    )

                    enu = (
                        self.ecef_to_enu(
                            ecef
                        )
                    )

                    coords.append(
                        (
                            enu[0],
                            enu[1],
                        )
                    )

                interiors.append(
                    coords
                )

            return Polygon(
                exterior,
                interiors,
            )

        if isinstance(
            geometry,
            MultiPolygon,
        ):

            polygons = []

            for polygon in geometry.geoms:

                result = (
                    self.convert_polygon_to_enu(
                        polygon
                    )
                )

                if (
                    result is not None
                    and not result.is_empty
                ):

                    polygons.append(
                        result
                    )

            if not polygons:
                return Polygon()

            return MultiPolygon(
                polygons
            )

        if isinstance(
            geometry,
            GeometryCollection,
        ):

            geometries = []

            for geom in geometry.geoms:

                result = (
                    self.convert_polygon_to_enu(
                        geom
                    )
                )

                if (
                    result is not None
                    and not result.is_empty
                ):

                    geometries.append(
                        result
                    )

            return GeometryCollection(
                geometries
            )

        return geometry

    # ================================================================
    # Tileset transform
    # ================================================================

    @staticmethod
    def parse_tileset_transform(
        transform,
    ):

        if (
            transform is None
            or len(transform) != 16
        ):

            return np.eye(
                4,
                dtype=np.float64,
            )

        # 3D Tiles matrix 是 column-major
        return np.array(
            transform,
            dtype=np.float64,
        ).reshape(
            4,
            4,
            order="F",
        )

    # ================================================================
    # Transform points
    # ================================================================

    @staticmethod
    def transform_points(
        points,
        matrix,
    ):

        points = np.asarray(
            points,
            dtype=np.float64,
        )

        if len(points) == 0:
            return points.copy()

        ones = np.ones(
            (
                len(points),
                1,
            ),
            dtype=np.float64,
        )

        p = np.concatenate(
            [
                points,
                ones,
            ],
            axis=1,
        )

        result = (
            p
            @ matrix.T
        )

        w = result[:, 3]

        valid = (
            np.abs(w)
            > 1e-15
        )

        result[valid, :3] /= (
            w[valid, None]
        )

        return result[:, :3]

    # ================================================================
    # Local -> World
    # ================================================================

    def local_to_world(
        self,
        vertices,
        matrix,
    ):

        return self.transform_points(
            vertices,
            matrix,
        )

    # ================================================================
    # World -> Local
    # ================================================================

    def world_to_local(
        self,
        vertices,
        matrix,
    ):

        inverse = np.linalg.inv(
            matrix
        )

        return self.transform_points(
            vertices,
            inverse,
        )

    # ================================================================
    # identity
    # ================================================================

    @staticmethod
    def is_identity_matrix(
        matrix,
    ):

        return np.allclose(
            matrix,
            np.eye(
                4,
                dtype=np.float64,
            ),
            atol=1e-12,
        )

    # ================================================================
    # Tileset
    # ================================================================

    def process_tileset_file(
        self,
        tileset_file: Path,
    ):

        key = str(
            tileset_file.resolve()
        )

        if key in self.processed_json:
            return True

        self.processed_json.add(
            key
        )

        self.stats[
            "tilesets"
        ] += 1

        self.stats[
            "json_total"
        ] += 1

        try:

            with tileset_file.open(
                "r",
                encoding="utf-8",
            ) as f:

                tileset = json.load(f)

        except Exception as e:

            print(
                "读取 JSON 失败:",
                e,
            )

            return False

        if "root" not in tileset:

            self.copy_preserve_path(
                tileset_file
            )

            return True

        new_tileset = copy.deepcopy(
            tileset
        )

        root_transform = (
            self.parse_tileset_transform(
                tileset["root"].get(
                    "transform"
                )
            )
        )

        print()
        print("tileset root transform:")

        print(
            root_transform
        )

        base_dir = (
            tileset_file.parent
        )

        new_root = self.process_tile(
            new_tileset["root"],
            base_dir,
            root_transform,
        )

        if new_root is None:

            print(
                "tileset 裁剪后为空:",
                tileset_file,
            )

            return False

        new_tileset[
            "root"
        ] = new_root

        output_file = (
            self.get_output_path(
                tileset_file
            )
        )

        output_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with output_file.open(
            "w",
            encoding="utf-8",
        ) as f:

            json.dump(
                new_tileset,
                f,
                ensure_ascii=False,
                indent=2,
            )

        self.stats[
            "json_written"
        ] += 1

        print(
            "输出:",
            output_file,
        )

        return True

    # ================================================================
    # Tile
    # ================================================================

    def process_tile(
        self,
        tile,
        base_dir,
        parent_transform,
    ):

        self.stats[
            "tiles"
        ] += 1

        tile = copy.deepcopy(
            tile
        )

        tile_transform = (
            self.parse_tileset_transform(
                tile.get(
                    "transform"
                )
            )
        )

        if "transform" in tile:

            effective_transform = (
                parent_transform
                @ tile_transform
            )

        else:

            effective_transform = (
                parent_transform
            )

        # ------------------------------------------------------------
        # content
        # ------------------------------------------------------------

        if (
            "content" in tile
            and tile["content"] is not None
        ):

            content = (
                self.process_content(
                    tile["content"],
                    base_dir,
                    tile,
                    effective_transform,
                )
            )

            if content is None:

                tile.pop(
                    "content",
                    None,
                )

            else:

                tile[
                    "content"
                ] = content

        # ------------------------------------------------------------
        # contents
        # ------------------------------------------------------------

        if (
            "contents" in tile
            and tile["contents"] is not None
        ):

            new_contents = []

            for content in tile["contents"]:

                result = (
                    self.process_content(
                        content,
                        base_dir,
                        tile,
                        effective_transform,
                    )
                )

                if result is not None:

                    new_contents.append(
                        result
                    )

            if new_contents:

                tile[
                    "contents"
                ] = new_contents

            else:

                tile.pop(
                    "contents",
                    None,
                )

        # ------------------------------------------------------------
        # children
        # ------------------------------------------------------------

        children = tile.get(
            "children",
            [],
        )

        new_children = []

        for child in children:

            result = (
                self.process_tile(
                    child,
                    base_dir,
                    effective_transform,
                )
            )

            if result is not None:

                new_children.append(
                    result
                )

        if new_children:

            tile[
                "children"
            ] = new_children

        else:

            tile.pop(
                "children",
                None,
            )

        # ------------------------------------------------------------
        # 裁剪后的 BoundingVolume
        #
        # bounds 是 Tile Local 坐标
        # ------------------------------------------------------------

        if "_clip_bounds" in tile:

            bounds = tile.pop(
                "_clip_bounds"
            )

            tile[
                "boundingVolume"
            ] = (
                self.make_box_bounding_volume(
                    bounds
                )
            )

        # ------------------------------------------------------------
        # 没有内容 / children
        # ------------------------------------------------------------

        if not any(
            key in tile
            for key in (
                "content",
                "contents",
                "children",
            )
        ):

            return None

        return tile

    # ================================================================
    # Content
    # ================================================================

    def process_content(
        self,
        content,
        base_dir,
        tile,
        transform,
    ):

        content = copy.deepcopy(
            content
        )

        if "uri" in content:

            uri_key = "uri"

        elif "url" in content:

            uri_key = "url"

        else:

            return content

        uri = content[
            uri_key
        ]

        clean_uri = self.clean_uri(
            uri
        )

        src = (
            base_dir
            / clean_uri
        ).resolve()

        if not src.exists():

            print(
                "资源不存在:",
                src,
            )

            return None

        suffix = (
            src.suffix.lower()
        )

        # ------------------------------------------------------------
        # B3DM
        # ------------------------------------------------------------

        if suffix == ".b3dm":

            result, bounds = (
                self.process_b3dm(
                    src,
                    transform,
                )
            )

            if result == "removed":

                return None

            if bounds is not None:

                tile[
                    "_clip_bounds"
                ] = bounds

            return content

        # ------------------------------------------------------------
        # GLB
        # ------------------------------------------------------------

        if suffix == ".glb":

            result, bounds = (
                self.process_glb(
                    src,
                    transform,
                )
            )

            if result == "removed":

                return None

            if bounds is not None:

                tile[
                    "_clip_bounds"
                ] = bounds

            return content

        # ------------------------------------------------------------
        # 外部 tileset
        # ------------------------------------------------------------

        if suffix == ".json":

            ok = (
                self.process_tileset_file(
                    src
                )
            )

            if not ok:

                return None

            return content

        # ------------------------------------------------------------
        # 其它
        # ------------------------------------------------------------

        self.copy_preserve_path(
            src
        )

        self.stats[
            "other_copied"
        ] += 1

        return content

    # ================================================================
    # GLB Parser
    # ================================================================

    @staticmethod
    def parse_glb(
        glb_data,
    ):

        if not glb_data.startswith(
            b"glTF"
        ):

            raise ValueError(
                "不是 GLB"
            )

        magic, version, length = (
            struct.unpack_from(
                "<4sII",
                glb_data,
                0,
            )
        )

        if length > len(glb_data):

            raise ValueError(
                "GLB length 错误"
            )

        offset = 12

        json_data = None
        bin_data = None

        while offset + 8 <= length:

            chunk_length, chunk_type = (
                struct.unpack_from(
                    "<II",
                    glb_data,
                    offset,
                )
            )

            offset += 8

            chunk_data = glb_data[
                offset:
                offset + chunk_length
            ]

            offset += chunk_length

            if chunk_type == 0x4E4F534A:

                text = (
                    chunk_data
                    .decode(
                        "utf-8"
                    )
                    .rstrip(
                        "\x00 "
                    )
                )

                json_data = json.loads(
                    text
                )

            elif chunk_type == 0x004E4942:

                bin_data = (
                    chunk_data
                )

        if json_data is None:

            raise ValueError(
                "GLB 没有 JSON"
            )

        if bin_data is None:

            raise ValueError(
                "GLB 没有 BIN"
            )

        return (
            json_data,
            bin_data,
        )

    # ================================================================
    # Accessor
    # ================================================================

    @staticmethod
    def read_accessor(
        gltf,
        bin_data,
        accessor_index,
    ):

        accessors = gltf.get(
            "accessors",
            [],
        )

        buffer_views = gltf.get(
            "bufferViews",
            [],
        )

        accessor = accessors[
            accessor_index
        ]

        count = accessor[
            "count"
        ]

        component_type = accessor[
            "componentType"
        ]

        accessor_type = accessor[
            "type"
        ]

        type_count = {

            "SCALAR": 1,
            "VEC2": 2,
            "VEC3": 3,
            "VEC4": 4,
            "MAT2": 4,
            "MAT3": 9,
            "MAT4": 16,

        }.get(
            accessor_type
        )

        if type_count is None:

            raise ValueError(
                f"不支持 accessor type: "
                f"{accessor_type}"
            )

        component_dtype = {

            5120: np.int8,
            5121: np.uint8,
            5122: np.int16,
            5123: np.uint16,
            5125: np.uint32,
            5126: np.float32,

        }.get(
            component_type
        )

        if component_dtype is None:

            raise ValueError(
                f"不支持 componentType: "
                f"{component_type}"
            )

        component_size = np.dtype(
            component_dtype
        ).itemsize

        result = np.zeros(
            (
                count,
                type_count,
            ),
            dtype=component_dtype,
        )

        # ------------------------------------------------------------
        # 普通数据
        # ------------------------------------------------------------

        if "bufferView" in accessor:

            view_index = accessor[
                "bufferView"
            ]

            view = buffer_views[
                view_index
            ]

            view_offset = view.get(
                "byteOffset",
                0,
            )

            accessor_offset = accessor.get(
                "byteOffset",
                0,
            )

            start = (
                view_offset
                + accessor_offset
            )

            stride = view.get(
                "byteStride",
                component_size
                * type_count,
            )

            if stride == (
                component_size
                * type_count
            ):

                raw = np.frombuffer(
                    bin_data,
                    dtype=component_dtype,
                    count=count
                    * type_count,
                    offset=start,
                )

                result = raw.reshape(
                    count,
                    type_count,
                ).copy()

            else:

                for i in range(
                    count
                ):

                    pos = (
                        start
                        + i * stride
                    )

                    values = np.frombuffer(
                        bin_data,
                        dtype=component_dtype,
                        count=type_count,
                        offset=pos,
                    )

                    result[i] = values

        # ------------------------------------------------------------
        # Sparse
        # ------------------------------------------------------------

        sparse = accessor.get(
            "sparse"
        )

        if sparse is not None:

            sparse_count = sparse[
                "count"
            ]

            indices_info = sparse[
                "indices"
            ]

            values_info = sparse[
                "values"
            ]

            index_view = buffer_views[
                indices_info[
                    "bufferView"
                ]
            ]

            index_component_type = (
                indices_info[
                    "componentType"
                ]
            )

            index_dtype = {

                5121: np.uint8,
                5123: np.uint16,
                5125: np.uint32,

            }.get(
                index_component_type
            )

            if index_dtype is None:

                raise ValueError(
                    "不支持 sparse index 类型"
                )

            index_offset = (
                index_view.get(
                    "byteOffset",
                    0,
                )
                +
                indices_info.get(
                    "byteOffset",
                    0,
                )
            )

            sparse_indices = np.frombuffer(
                bin_data,
                dtype=index_dtype,
                count=sparse_count,
                offset=index_offset,
            )

            value_view = buffer_views[
                values_info[
                    "bufferView"
                ]
            ]

            value_offset = (
                value_view.get(
                    "byteOffset",
                    0,
                )
                +
                values_info.get(
                    "byteOffset",
                    0,
                )
            )

            sparse_values = np.frombuffer(
                bin_data,
                dtype=component_dtype,
                count=(
                    sparse_count
                    * type_count
                ),
                offset=value_offset,
            )

            sparse_values = (
                sparse_values.reshape(
                    sparse_count,
                    type_count,
                )
            )

            result[
                sparse_indices
            ] = sparse_values

        return result

    # ================================================================
    # GLTF Node Matrix
    # ================================================================

    @staticmethod
    def gltf_node_matrix(
        node,
    ):

        if "matrix" in node:

            return np.array(
                node["matrix"],
                dtype=np.float64,
            ).reshape(
                4,
                4,
                order="F",
            )

        translation = np.array(
            node.get(
                "translation",
                [0, 0, 0],
            ),
            dtype=np.float64,
        )

        rotation = np.array(
            node.get(
                "rotation",
                [0, 0, 0, 1],
            ),
            dtype=np.float64,
        )

        scale = np.array(
            node.get(
                "scale",
                [1, 1, 1],
            ),
            dtype=np.float64,
        )

        x, y, z, w = rotation

        R = np.array(

            [
                [
                    1 - 2 * (y * y + z * z),
                    2 * (x * y - z * w),
                    2 * (x * z + y * w),
                ],

                [
                    2 * (x * y + z * w),
                    1 - 2 * (x * x + z * z),
                    2 * (y * z - x * w),
                ],

                [
                    2 * (x * z - y * w),
                    2 * (y * z + x * w),
                    1 - 2 * (x * x + y * y),
                ],
            ],

            dtype=np.float64,
        )

        matrix = np.eye(
            4,
            dtype=np.float64,
        )

        matrix[:3, :3] = (
            R
            @ np.diag(scale)
        )

        matrix[:3, 3] = (
            translation
        )

        return matrix

    # ================================================================
    # GLB Mesh
    # ================================================================

    def extract_glb_meshes(
        self,
        glb_data,
    ):

        gltf, bin_data = (
            self.parse_glb(
                glb_data
            )
        )

        meshes = gltf.get(
            "meshes",
            [],
        )

        nodes = gltf.get(
            "nodes",
            [],
        )

        scenes = gltf.get(
            "scenes",
            [],
        )

        default_scene = gltf.get(
            "scene",
            0,
        )

        if not scenes:

            raise ValueError(
                "GLB 没有 scenes"
            )

        root_nodes = scenes[
            default_scene
        ].get(
            "nodes",
            [],
        )

        results = []

        def visit_node(
            node_index,
            parent_matrix,
        ):

            node = nodes[
                node_index
            ]

            local_matrix = (
                self.gltf_node_matrix(
                    node
                )
            )

            world_matrix = (
                parent_matrix
                @ local_matrix
            )

            mesh_index = node.get(
                "mesh"
            )

            if mesh_index is not None:

                gltf_mesh = meshes[
                    mesh_index
                ]

                for primitive_index, primitive in enumerate(
                    gltf_mesh.get(
                        "primitives",
                        [],
                    )
                ):

                    attributes = (
                        primitive.get(
                            "attributes",
                            {},
                        )
                    )

                    position_accessor = (
                        attributes.get(
                            "POSITION"
                        )
                    )

                    if position_accessor is None:
                        continue

                    positions = (
                        self.read_accessor(
                            gltf,
                            bin_data,
                            position_accessor,
                        )
                    )

                    positions = positions.astype(
                        np.float64
                    )

                    positions_world = (
                        self.transform_points(
                            positions,
                            world_matrix,
                        )
                    )

                    if "indices" in primitive:

                        indices = (
                            self.read_accessor(
                                gltf,
                                bin_data,
                                primitive[
                                    "indices"
                                ],
                            )
                            .reshape(-1)
                            .astype(
                                np.int64
                            )
                        )

                    else:

                        indices = np.arange(
                            len(
                                positions_world
                            ),
                            dtype=np.int64,
                        )

                    mode = primitive.get(
                        "mode",
                        4,
                    )

                    if mode == 4:

                        count = (
                            len(indices)
                            // 3
                        )

                        faces = (
                            indices[
                                :count * 3
                            ]
                            .reshape(
                                -1,
                                3,
                            )
                        )

                    else:

                        faces = np.empty(
                            (
                                0,
                                3,
                            ),
                            dtype=np.int64,
                        )

                    results.append({

                        "positions":
                            positions_world,

                        "faces":
                            faces,

                        "node_index":
                            node_index,

                        "mesh_index":
                            mesh_index,

                        "primitive_index":
                            primitive_index,

                    })

            for child in node.get(
                "children",
                [],
            ):

                visit_node(
                    child,
                    world_matrix,
                )

        identity = np.eye(
            4,
            dtype=np.float64,
        )

        for node_index in root_nodes:

            visit_node(
                node_index,
                identity,
            )

        return (
            gltf,
            results,
        )

    # ================================================================
    # Feature Table
    # ================================================================

    @staticmethod
    def parse_feature_table(
        feature_json,
    ):

        if not feature_json:
            return {}

        try:

            text = (
                feature_json
                .decode(
                    "utf-8"
                )
                .rstrip(
                    "\x00 "
                )
            )

            if not text:
                return {}

            return json.loads(
                text
            )

        except Exception:

            return {}

    # ================================================================
    # RTC_CENTER
    # ================================================================

    def get_rtc_center(
        self,
        b3dm,
    ):

        feature_table = (
            self.parse_feature_table(
                b3dm[
                    "feature_json"
                ]
            )
        )

        rtc = feature_table.get(
            "RTC_CENTER"
        )

        if rtc is None:

            return np.zeros(
                3,
                dtype=np.float64,
            )

        rtc = np.asarray(
            rtc,
            dtype=np.float64,
        )

        if rtc.shape != (3,):

            raise ValueError(
                f"RTC_CENTER 格式错误: {rtc}"
            )

        return rtc

    # ================================================================
    # 自动判断 B3DM 坐标
    # ================================================================

    def detect_b3dm_coordinate_mode(
        self,
        rtc,
    ):

        if self.b3dm_coordinate_mode != "auto":

            return self.b3dm_coordinate_mode

        magnitude = np.linalg.norm(
            rtc
        )

        if magnitude > 1_000_000:

            return "ecef"

        return "local_rtc"

    # ================================================================
    # B3DM Local -> ENU
    #
    # 这里是整套程序最重要的坐标函数
    # ================================================================

    def b3dm_positions_to_enu(
        self,
        positions,
        rtc_center,
        tileset_transform,
    ):

        positions = np.asarray(
            positions,
            dtype=np.float64,
        )

        rtc = np.asarray(
            rtc_center,
            dtype=np.float64,
        )

        mode = (
            self.detect_b3dm_coordinate_mode(
                rtc
            )
        )

        # ------------------------------------------------------------
        # GLB POSITION
        # +
        # RTC_CENTER
        # ------------------------------------------------------------

        local_rtc = (
            positions
            + rtc
        )

        # ------------------------------------------------------------
        # ENU
        #
        # 如果数据已经是 ENU，
        # 不再进行 ECEF 转换
        # ------------------------------------------------------------

        if mode == "enu":

            return local_rtc

        # ------------------------------------------------------------
        # local_rtc
        #
        # 对你目前的数据：
        #
        # transform = identity
        # RTC_CENTER = [305,15,-30]
        #
        # 这里把 local_rtc 作为 ENU
        # ------------------------------------------------------------

        if mode == "local_rtc":

            if self.is_identity_matrix(
                tileset_transform
            ):

                return local_rtc

            # 非 identity：
            #
            # 假定 tileset transform
            # 最终把 local 坐标转换到 ECEF
            world = self.local_to_world(
                local_rtc,
                tileset_transform,
            )

            return self.ecef_to_enu(
                world
            )

        # ------------------------------------------------------------
        # ECEF
        # ------------------------------------------------------------

        if mode == "ecef":

            world = self.local_to_world(
                local_rtc,
                tileset_transform,
            )

            return self.ecef_to_enu(
                world
            )

        raise ValueError(
            f"未知 B3DM 坐标模式: {mode}"
        )

    # ================================================================
    # ENU -> B3DM GLB Local
    #
    # 这是修复 RTC_CENTER 重复平移的关键
    # ================================================================

    def enu_to_b3dm_positions(
        self,
        enu_positions,
        rtc_center,
        tileset_transform,
    ):

        enu_positions = np.asarray(
            enu_positions,
            dtype=np.float64,
        )

        rtc = np.asarray(
            rtc_center,
            dtype=np.float64,
        )

        mode = (
            self.detect_b3dm_coordinate_mode(
                rtc
            )
        )

        # ------------------------------------------------------------
        # ENU
        #
        # ENU = POSITION + RTC
        #
        # 所以：
        #
        # POSITION = ENU - RTC
        # ------------------------------------------------------------

        if mode == "enu":

            return (
                enu_positions
                - rtc
            )

        # ------------------------------------------------------------
        # local_rtc
        #
        # identity:
        #
        # ENU = POSITION + RTC
        #
        # 所以：
        #
        # POSITION = ENU - RTC
        # ------------------------------------------------------------

        if mode == "local_rtc":

            if self.is_identity_matrix(
                tileset_transform
            ):

                return (
                    enu_positions
                    - rtc
                )

            # ENU -> ECEF
            world = self.enu_to_ecef(
                enu_positions
            )

            # ECEF -> Tile Local
            local_rtc = self.world_to_local(
                world,
                tileset_transform,
            )

            # 去掉 RTC_CENTER
            return (
                local_rtc
                - rtc
            )

        # ------------------------------------------------------------
        # ECEF
        # ------------------------------------------------------------

        if mode == "ecef":

            world = self.enu_to_ecef(
                enu_positions
            )

            local_rtc = self.world_to_local(
                world,
                tileset_transform,
            )

            return (
                local_rtc
                - rtc
            )

        raise ValueError(
            f"未知 B3DM 坐标模式: {mode}"
        )

    # ================================================================
    # 普通 GLB Local -> ENU
    # ================================================================

    def local_vertices_to_enu(
        self,
        vertices,
        transform,
    ):

        world = self.local_to_world(
            vertices,
            transform,
        )

        # identity 时，
        # 当前数据假定本地坐标就是 ENU
        if self.is_identity_matrix(
            transform
        ):

            return world

        # 非 identity：
        # 假定 transform 后是 ECEF
        return self.ecef_to_enu(
            world
        )

    # ================================================================
    # 普通 GLB ENU -> Local
    # ================================================================

    def enu_vertices_to_local(
        self,
        vertices,
        transform,
    ):

        vertices = np.asarray(
            vertices,
            dtype=np.float64,
        )

        if self.is_identity_matrix(
            transform
        ):

            return vertices

        world = self.enu_to_ecef(
            vertices
        )

        return self.world_to_local(
            world,
            transform,
        )

    # ================================================================
    # Bounds XY
    # ================================================================

    @staticmethod
    def bounds_from_positions(
        positions,
    ):

        if len(positions) == 0:
            return None

        return np.array(
            [
                positions.min(
                    axis=0
                ),
                positions.max(
                    axis=0
                ),
            ],
            dtype=np.float64,
        )

    # ================================================================
    # B3DM
    # ================================================================

    def process_b3dm(
        self,
        input_path,
        transform,
    ):

        self.stats[
            "b3dm_total"
        ] += 1

        print()
        print("=" * 90)

        print(
            "B3DM:",
            input_path,
        )

        print("=" * 90)

        try:

            b3dm = self.read_b3dm(
                input_path
            )

        except Exception as e:

            print(
                "B3DM 解析失败:",
                e,
            )

            self.copy_preserve_path(
                input_path
            )

            self.stats[
                "b3dm_copied"
            ] += 1

            return (
                "copied",
                None,
            )

        rtc_center = (
            self.get_rtc_center(
                b3dm
            )
        )

        coordinate_mode = (
            self.detect_b3dm_coordinate_mode(
                rtc_center
            )
        )

        print()
        print(
            "RTC_CENTER:",
            rtc_center,
        )

        print(
            "坐标模式:",
            coordinate_mode,
        )

        print()
        print(
            "Tileset Transform:"
        )

        print(
            transform
        )

        # ------------------------------------------------------------
        # GLB
        # ------------------------------------------------------------

        try:

            gltf, meshes = (
                self.extract_glb_meshes(
                    b3dm["glb"]
                )
            )

        except Exception as e:

            print(
                "GLB 解析失败:",
                e,
            )

            self.copy_preserve_path(
                input_path
            )

            self.stats[
                "b3dm_copied"
            ] += 1

            return (
                "copied",
                None,
            )

        print()
        print(
            "========== GLB POSITION DEBUG =========="
        )

        print(
            "geometry count:",
            len(meshes),
        )

        all_positions = []

        for index, item in enumerate(
            meshes
        ):

            positions = item[
                "positions"
            ]

            faces = item[
                "faces"
            ]

            print()
            print(
                "geometry:",
                index,
            )

            print(
                "node:",
                item["node_index"],
            )

            print(
                "vertices:",
                len(positions),
            )

            print(
                "faces:",
                len(faces),
            )

            if len(positions) > 0:

                print(
                    "GLTF transformed min:",
                    positions.min(
                        axis=0
                    ),
                )

                print(
                    "GLTF transformed max:",
                    positions.max(
                        axis=0
                    ),
                )

            all_positions.append(
                positions
            )

        print(
            "========================================"
        )

        if not all_positions:

            print(
                "GLB 没有 POSITION"
            )

            self.copy_preserve_path(
                input_path
            )

            self.stats[
                "b3dm_copied"
            ] += 1

            return (
                "copied",
                None,
            )

        all_positions = np.concatenate(
            all_positions,
            axis=0,
        )

        # ------------------------------------------------------------
        # 转 ENU
        # ------------------------------------------------------------

        positions_enu = (
            self.b3dm_positions_to_enu(
                all_positions,
                rtc_center,
                transform,
            )
        )

        bounds_enu = (
            self.bounds_from_positions(
                positions_enu
            )
        )

        print()
        print(
            "B3DM ENU XY:"
        )

        print(
            "  min:",
            bounds_enu[0, :2],
        )

        print(
            "  max:",
            bounds_enu[1, :2],
        )

        relation = (
            self.bbox_relation(
                bounds_enu
            )
        )

        print(
            "B3DM XY relation:",
            relation,
        )

        # ------------------------------------------------------------
        # 完全外部
        # ------------------------------------------------------------

        if relation == "outside":

            if self.mode == "keep":

                self.stats[
                    "b3dm_removed"
                ] += 1

                print(
                    "  XY 完全外部 -> 删除"
                )

                return (
                    "removed",
                    None,
                )

            self.copy_preserve_path(
                input_path
            )

            self.stats[
                "b3dm_copied"
            ] += 1

            return (
                "copied",
                self.bounds_to_6(
                    self.positions_bounds_to_local(
                        bounds_enu,
                        rtc_center,
                        transform,
                    )
                ),
            )

        # ------------------------------------------------------------
        # 完全内部
        # ------------------------------------------------------------

        if relation == "inside":

            if self.mode == "keep":

                self.copy_preserve_path(
                    input_path
                )

                self.stats[
                    "b3dm_copied"
                ] += 1

                local_bounds = (
                    self.bounds_from_positions(
                        self.b3dm_positions_to_enu(
                            all_positions,
                            rtc_center,
                            transform,
                        )
                    )
                )

                # 使用原始 GLB Local bounds
                local_bounds = (
                    self.bounds_from_positions(
                        all_positions
                    )
                )

                return (
                    "copied",
                    self.bounds_to_6(
                        local_bounds
                    ),
                )

            self.stats[
                "b3dm_removed"
            ] += 1

            print(
                "  XY 完全内部 -> 删除"
            )

            return (
                "removed",
                None,
            )

        # ------------------------------------------------------------
        # 相交
        # ------------------------------------------------------------

        print(
            "  XY 相交 -> 开始精确裁剪"
        )

        new_meshes = []

        for item in meshes:

            positions = item[
                "positions"
            ]

            faces = item[
                "faces"
            ]

            if (
                len(faces) == 0
                or len(positions) == 0
            ):
                continue

            # --------------------------------------------------------
            # 当前 positions：
            #
            # GLTF node transform 后
            #
            # 转 ENU
            # --------------------------------------------------------

            enu_vertices = (
                self.b3dm_positions_to_enu(
                    positions,
                    rtc_center,
                    transform,
                )
            )

            mesh = trimesh.Trimesh(
                vertices=enu_vertices,
                faces=faces,
                process=False,
            )

            result = self.clip_mesh(
                mesh
            )

            if result is None:
                continue

            new_meshes.append(
                result
            )

        if not new_meshes:

            self.stats[
                "b3dm_removed"
            ] += 1

            print(
                "  裁剪后为空"
            )

            return (
                "removed",
                None,
            )

        # ------------------------------------------------------------
        # 创建新的 GLB
        #
        # 注意：
        #
        # clip_mesh 得到的是 ENU
        #
        # 必须转换回：
        #
        # GLB Local
        # ------------------------------------------------------------

        new_scene = trimesh.Scene()

        local_bounds = []

        for index, mesh_enu in enumerate(
            new_meshes
        ):

            mesh_local = (
                self.enu_mesh_to_b3dm_local(
                    mesh_enu,
                    rtc_center,
                    transform,
                )
            )

            new_scene.add_geometry(
                mesh_local,
                node_name=f"mesh_{index}",
            )

            local_bounds.append(
                mesh_local.bounds
            )

        temp_glb = (
            input_path.parent
            /
            (
                input_path.name
                + ".clip.glb"
            )
        )

        try:

            new_scene.export(
                str(temp_glb)
            )

            new_glb_data = (
                temp_glb.read_bytes()
            )

            # --------------------------------------------------------
            # B3DM：
            #
            # RTC_CENTER 保留原值
            # --------------------------------------------------------

            new_b3dm = (
                self.build_b3dm(
                    b3dm,
                    new_glb_data,
                )
            )

            output_path = (
                self.get_output_path(
                    input_path
                )
            )

            output_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            output_path.write_bytes(
                new_b3dm
            )

            self.stats[
                "b3dm_clipped"
            ] += 1

            print(
                "  输出:",
                output_path,
            )

            merged = (
                self.merge_bounds(
                    local_bounds
                )
            )

            return (
                "clipped",
                merged,
            )

        finally:

            try:

                if temp_glb.exists():

                    temp_glb.unlink()

            except Exception:
                pass

    # ================================================================
    # ENU Mesh -> B3DM Local Mesh
    # ================================================================

    def enu_mesh_to_b3dm_local(
        self,
        mesh_enu,
        rtc_center,
        transform,
    ):

        vertices_enu = np.asarray(
            mesh_enu.vertices,
            dtype=np.float64,
        )

        vertices_local = (
            self.enu_to_b3dm_positions(
                vertices_enu,
                rtc_center,
                transform,
            )
        )

        return trimesh.Trimesh(
            vertices=vertices_local,
            faces=np.asarray(
                mesh_enu.faces,
                dtype=np.int64,
            ),
            process=False,
        )

    # ================================================================
    # Bounds ENU -> Local
    #
    # 主要用于非裁剪 copy 场景
    # ================================================================

    def positions_bounds_to_local(
        self,
        bounds,
        rtc_center,
        transform,
    ):

        bounds = np.asarray(
            bounds,
            dtype=np.float64,
        )

        if bounds.shape != (2, 3):
            bounds = bounds.reshape(
                2,
                3,
            )

        corners = np.array(

            [
                [
                    bounds[0, 0],
                    bounds[0, 1],
                    bounds[0, 2],
                ],

                [
                    bounds[0, 0],
                    bounds[0, 1],
                    bounds[1, 2],
                ],

                [
                    bounds[0, 0],
                    bounds[1, 1],
                    bounds[0, 2],
                ],

                [
                    bounds[0, 0],
                    bounds[1, 1],
                    bounds[1, 2],
                ],

                [
                    bounds[1, 0],
                    bounds[0, 1],
                    bounds[0, 2],
                ],

                [
                    bounds[1, 0],
                    bounds[0, 1],
                    bounds[1, 2],
                ],

                [
                    bounds[1, 0],
                    bounds[1, 1],
                    bounds[0, 2],
                ],

                [
                    bounds[1, 0],
                    bounds[1, 1],
                    bounds[1, 2],
                ],
            ],

            dtype=np.float64,
        )

        local = (
            self.enu_to_b3dm_positions(
                corners,
                rtc_center,
                transform,
            )
        )

        return self.bounds_from_positions(
            local
        )

    # ================================================================
    # 普通 GLB
    # ================================================================

    def process_glb(
        self,
        input_path,
        transform,
    ):

        self.stats[
            "glb_total"
        ] += 1

        print()
        print(
            "GLB:",
            input_path,
        )

        try:

            glb_data = (
                input_path.read_bytes()
            )

            gltf, meshes = (
                self.extract_glb_meshes(
                    glb_data
                )
            )

        except Exception as e:

            print(
                "GLB 解析失败:",
                e,
            )

            self.copy_preserve_path(
                input_path
            )

            self.stats[
                "glb_copied"
            ] += 1

            return (
                "copied",
                None,
            )

        if not meshes:

            return (
                "removed",
                None,
            )

        all_positions = np.concatenate(
            [
                item["positions"]
                for item in meshes
            ],
            axis=0,
        )

        enu = (
            self.local_vertices_to_enu(
                all_positions,
                transform,
            )
        )

        bounds = (
            self.bounds_from_positions(
                enu
            )
        )

        relation = (
            self.bbox_relation(
                bounds
            )
        )

        print(
            "GLB XY relation:",
            relation,
        )

        # ------------------------------------------------------------
        # outside
        # ------------------------------------------------------------

        if relation == "outside":

            if self.mode == "keep":

                self.stats[
                    "glb_removed"
                ] += 1

                return (
                    "removed",
                    None,
                )

            self.copy_preserve_path(
                input_path
            )

            self.stats[
                "glb_copied"
            ] += 1

            local_bounds = (
                self.bounds_from_positions(
                    all_positions
                )
            )

            return (
                "copied",
                self.bounds_to_6(
                    local_bounds
                ),
            )

        # ------------------------------------------------------------
        # inside
        # ------------------------------------------------------------

        if relation == "inside":

            if self.mode == "keep":

                self.copy_preserve_path(
                    input_path
                )

                self.stats[
                    "glb_copied"
                ] += 1

                local_bounds = (
                    self.bounds_from_positions(
                        all_positions
                    )
                )

                return (
                    "copied",
                    self.bounds_to_6(
                        local_bounds
                    ),
                )

            self.stats[
                "glb_removed"
            ] += 1

            return (
                "removed",
                None,
            )

        # ------------------------------------------------------------
        # intersect
        # ------------------------------------------------------------

        new_scene = trimesh.Scene()

        result_bounds = []

        for index, item in enumerate(
            meshes
        ):

            vertices_enu = (
                self.local_vertices_to_enu(
                    item["positions"],
                    transform,
                )
            )

            faces = item[
                "faces"
            ]

            if len(faces) == 0:
                continue

            mesh = trimesh.Trimesh(
                vertices=vertices_enu,
                faces=faces,
                process=False,
            )

            result = self.clip_mesh(
                mesh
            )

            if result is None:
                continue

            # ENU -> 原始 GLB Local
            result_local = (
                self.enu_mesh_to_glb_local(
                    result,
                    transform,
                )
            )

            new_scene.add_geometry(
                result_local,
                node_name=f"mesh_{index}",
            )

            result_bounds.append(
                result_local.bounds
            )

        if not new_scene.geometry:

            self.stats[
                "glb_removed"
            ] += 1

            return (
                "removed",
                None,
            )

        output_path = (
            self.get_output_path(
                input_path
            )
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        new_scene.export(
            str(output_path)
        )

        self.stats[
            "glb_clipped"
        ] += 1

        print(
            "输出:",
            output_path,
        )

        return (
            "clipped",
            self.merge_bounds(
                result_bounds
            ),
        )

    # ================================================================
    # ENU -> 普通 GLB Local
    # ================================================================

    def enu_mesh_to_glb_local(
        self,
        mesh_enu,
        transform,
    ):

        vertices = np.asarray(
            mesh_enu.vertices,
            dtype=np.float64,
        )

        local = (
            self.enu_vertices_to_local(
                vertices,
                transform,
            )
        )

        return trimesh.Trimesh(
            vertices=local,
            faces=np.asarray(
                mesh_enu.faces,
                dtype=np.int64,
            ),
            process=False,
        )

    # ================================================================
    # BBox Relation
    # ================================================================

    def bbox_relation(
        self,
        bounds,
    ):

        bounds = np.asarray(
            bounds,
            dtype=np.float64,
        )

        if bounds.shape == (6,):

            bounds = bounds.reshape(
                2,
                3,
            )

        min_x = bounds[
            0,
            0,
        ]

        min_y = bounds[
            0,
            1,
        ]

        max_x = bounds[
            1,
            0,
        ]

        max_y = bounds[
            1,
            1,
        ]

        clip_min_x = (
            self.clip_bbox[0]
        )

        clip_min_y = (
            self.clip_bbox[1]
        )

        clip_max_x = (
            self.clip_bbox[2]
        )

        clip_max_y = (
            self.clip_bbox[3]
        )

        # ------------------------------------------------------------
        # BBox 完全外部
        # ------------------------------------------------------------

        if (
            max_x < clip_min_x
            or min_x > clip_max_x
            or max_y < clip_min_y
            or min_y > clip_max_y
        ):

            return "outside"

        bbox = Polygon(

            [
                (
                    min_x,
                    min_y,
                ),

                (
                    max_x,
                    min_y,
                ),

                (
                    max_x,
                    max_y,
                ),

                (
                    min_x,
                    max_y,
                ),
            ]

        )

        if not self.clip_prepared.intersects(
            bbox
        ):

            return "outside"

        if self.clip_polygon.covers(
            bbox
        ):

            return "inside"

        return "intersect"

    # ================================================================
    # Mesh Clip
    # ================================================================

    def clip_mesh(
        self,
        mesh,
    ):

        vertices = np.asarray(
            mesh.vertices,
            dtype=np.float64,
        )

        faces = np.asarray(
            mesh.faces,
            dtype=np.int64,
        )

        if (
            len(vertices) == 0
            or len(faces) == 0
        ):

            return None

        self.stats[
            "triangles_input"
        ] += len(faces)

        new_vertices = []
        new_faces = []

        vertex_cache = {}

        def add_vertex(
            position,
        ):

            position = np.asarray(
                position,
                dtype=np.float64,
            )

            key = tuple(
                np.round(
                    position,
                    8,
                )
            )

            if key in vertex_cache:

                return vertex_cache[
                    key
                ]

            index = len(
                new_vertices
            )

            new_vertices.append(
                position
            )

            vertex_cache[
                key
            ] = index

            return index

        for face in faces:

            ia, ib, ic = face

            a = vertices[
                ia
            ]

            b = vertices[
                ib
            ]

            c = vertices[
                ic
            ]

            triangle = Polygon(

                [
                    (
                        a[0],
                        a[1],
                    ),

                    (
                        b[0],
                        b[1],
                    ),

                    (
                        c[0],
                        c[1],
                    ),
                ]

            )

            if (
                triangle.is_empty
                or triangle.area < 1e-12
            ):
                continue

            # --------------------------------------------------------
            # Triangle BBox
            # --------------------------------------------------------

            tri_min_x = min(
                a[0],
                b[0],
                c[0],
            )

            tri_min_y = min(
                a[1],
                b[1],
                c[1],
            )

            tri_max_x = max(
                a[0],
                b[0],
                c[0],
            )

            tri_max_y = max(
                a[1],
                b[1],
                c[1],
            )

            if (
                tri_max_x < self.clip_bbox[0]
                or
                tri_min_x > self.clip_bbox[2]
                or
                tri_max_y < self.clip_bbox[1]
                or
                tri_min_y > self.clip_bbox[3]
            ):

                relation = "outside"

            elif not self.clip_prepared.intersects(
                triangle
            ):

                relation = "outside"

            elif self.clip_polygon.covers(
                triangle
            ):

                relation = "inside"

            else:

                relation = "intersect"

            # --------------------------------------------------------
            # KEEP
            # --------------------------------------------------------

            if self.mode == "keep":

                if relation == "outside":
                    continue

                if relation == "inside":

                    new_faces.append(

                        [
                            add_vertex(a),
                            add_vertex(b),
                            add_vertex(c),
                        ]

                    )

                    continue

                geometry = (
                    triangle.intersection(
                        self.clip_polygon
                    )
                )

            # --------------------------------------------------------
            # REMOVE
            # --------------------------------------------------------

            else:

                if relation == "outside":

                    new_faces.append(

                        [
                            add_vertex(a),
                            add_vertex(b),
                            add_vertex(c),
                        ]

                    )

                    continue

                if relation == "inside":
                    continue

                geometry = (
                    triangle.difference(
                        self.clip_polygon
                    )
                )

            polygons = (
                self.extract_polygons(
                    geometry
                )
            )

            for polygon in polygons:

                if polygon.area < 1e-12:
                    continue

                triangles = (
                    triangulate(
                        polygon
                    )
                )

                for tri in triangles:

                    if not polygon.covers(
                        tri
                    ):
                        continue

                    coords = list(
                        tri.exterior.coords
                    )[:3]

                    indices = []

                    valid = True

                    for x, y in coords:

                        position = (
                            self.interpolate_z(
                                x,
                                y,
                                a,
                                b,
                                c,
                            )
                        )

                        if position is None:

                            valid = False
                            break

                        indices.append(
                            add_vertex(
                                position
                            )
                        )

                    if (
                        valid
                        and len(indices) == 3
                    ):

                        new_faces.append(
                            indices
                        )

        if not new_faces:
            return None

        self.stats[
            "triangles_output"
        ] += len(
            new_faces
        )

        result = trimesh.Trimesh(

            vertices=np.asarray(
                new_vertices,
                dtype=np.float64,
            ),

            faces=np.asarray(
                new_faces,
                dtype=np.int64,
            ),

            process=False,
        )

        try:

            result.remove_unreferenced_vertices()

        except Exception:
            pass

        return result

    # ================================================================
    # Z 插值
    # ================================================================

    @staticmethod
    def interpolate_z(
        x,
        y,
        a,
        b,
        c,
    ):

        ax, ay = a[:2]
        bx, by = b[:2]
        cx, cy = c[:2]

        denominator = (
            (by - cy)
            * (ax - cx)
            +
            (cx - bx)
            * (ay - cy)
        )

        if abs(
            denominator
        ) < 1e-15:

            return None

        w1 = (

            (
                (by - cy)
                * (x - cx)
            )

            +

            (
                (cx - bx)
                * (y - cy)
            )

        ) / denominator

        w2 = (

            (
                (cy - ay)
                * (x - cx)
            )

            +

            (
                (ax - cx)
                * (y - cy)
            )

        ) / denominator

        w3 = (
            1
            - w1
            - w2
        )

        return (
            a * w1
            + b * w2
            + c * w3
        )

    # ================================================================
    # Polygon
    # ================================================================

    @staticmethod
    def extract_polygons(
        geometry,
    ):

        if (
            geometry is None
            or geometry.is_empty
        ):

            return []

        if isinstance(
            geometry,
            Polygon,
        ):

            return [
                geometry
            ]

        if isinstance(
            geometry,
            MultiPolygon,
        ):

            return list(
                geometry.geoms
            )

        if isinstance(
            geometry,
            GeometryCollection,
        ):

            result = []

            for geom in geometry.geoms:

                result.extend(
                    Clip3dTiles.extract_polygons(
                        geom
                    )
                )

            return result

        return []

    # ================================================================
    # Merge Bounds
    # ================================================================

    @staticmethod
    def merge_bounds(
        bounds,
    ):

        if not bounds:
            return None

        arr = np.asarray(
            bounds,
            dtype=np.float64,
        )

        return np.array(

            [
                arr[:, 0, 0].min(),
                arr[:, 0, 1].min(),
                arr[:, 0, 2].min(),

                arr[:, 1, 0].max(),
                arr[:, 1, 1].max(),
                arr[:, 1, 2].max(),
            ],

            dtype=np.float64,
        )

    # ================================================================
    # Bounds -> 6
    # ================================================================

    @staticmethod
    def bounds_to_6(
        bounds,
    ):

        bounds = np.asarray(
            bounds,
            dtype=np.float64,
        )

        if bounds.shape == (6,):
            return bounds.copy()

        return np.array(

            [
                bounds[0, 0],
                bounds[0, 1],
                bounds[0, 2],

                bounds[1, 0],
                bounds[1, 1],
                bounds[1, 2],
            ],

            dtype=np.float64,
        )

    # ================================================================
    # Bounding Volume
    #
    # 注意：
    #
    # 这里使用 Tile Local 坐标
    #
    # 不再使用 ENU 坐标
    # ================================================================

    @staticmethod
    def make_box_bounding_volume(
        bounds,
    ):

        bounds = np.asarray(
            bounds,
            dtype=np.float64,
        )

        if bounds.shape == (6,):

            min_x = bounds[0]
            min_y = bounds[1]
            min_z = bounds[2]

            max_x = bounds[3]
            max_y = bounds[4]
            max_z = bounds[5]

        else:

            min_x = bounds[0, 0]
            min_y = bounds[0, 1]
            min_z = bounds[0, 2]

            max_x = bounds[1, 0]
            max_y = bounds[1, 1]
            max_z = bounds[1, 2]

        cx = (
            min_x
            + max_x
        ) * 0.5

        cy = (
            min_y
            + max_y
        ) * 0.5

        cz = (
            min_z
            + max_z
        ) * 0.5

        hx = (
            max_x
            - min_x
        ) * 0.5

        hy = (
            max_y
            - min_y
        ) * 0.5

        hz = (
            max_z
            - min_z
        ) * 0.5

        return {

            "box": [

                cx,
                cy,
                cz,

                hx,
                0,
                0,

                0,
                hy,
                0,

                0,
                0,
                hz,
            ]

        }

    # ================================================================
    # B3DM Read
    # ================================================================

    @staticmethod
    def read_b3dm(
        path: Path,
    ):

        data = path.read_bytes()

        if len(data) < 28:

            raise ValueError(
                "B3DM 文件长度小于 28"
            )

        (
            magic,
            version,
            byte_length,
            feature_json_len,
            feature_bin_len,
            batch_json_len,
            batch_bin_len,
        ) = struct.unpack_from(
            "<4sIIIIII",
            data,
            0,
        )

        if magic != b"b3dm":

            raise ValueError(
                f"不是 B3DM: {magic!r}"
            )

        if byte_length > len(data):

            raise ValueError(
                "B3DM byteLength 大于实际文件长度"
            )

        offset = 28

        feature_json = data[
            offset:
            offset + feature_json_len
        ]

        offset += feature_json_len

        feature_bin = data[
            offset:
            offset + feature_bin_len
        ]

        offset += feature_bin_len

        batch_json = data[
            offset:
            offset + batch_json_len
        ]

        offset += batch_json_len

        batch_bin = data[
            offset:
            offset + batch_bin_len
        ]

        offset += batch_bin_len

        glb = data[
            offset:
        ]

        if not glb.startswith(
            b"glTF"
        ):

            raise ValueError(
                "B3DM 中没有 GLB"
            )

        return {

            "version":
                version,

            "feature_json":
                feature_json,

            "feature_bin":
                feature_bin,

            "batch_json":
                batch_json,

            "batch_bin":
                batch_bin,

            "glb":
                glb,
        }

    # ================================================================
    # B3DM Build
    # ================================================================

    @staticmethod
    def build_b3dm(
        b3dm,
        glb_data,
    ):

        feature_json = (
            b3dm[
                "feature_json"
            ]
        )

        feature_bin = (
            b3dm[
                "feature_bin"
            ]
        )

        batch_json = (
            b3dm[
                "batch_json"
            ]
        )

        batch_bin = (
            b3dm[
                "batch_bin"
            ]
        )

        byte_length = (

            28

            + len(
                feature_json
            )

            + len(
                feature_bin
            )

            + len(
                batch_json
            )

            + len(
                batch_bin
            )

            + len(
                glb_data
            )
        )

        header = struct.pack(

            "<4sIIIIII",

            b"b3dm",

            b3dm[
                "version"
            ],

            byte_length,

            len(
                feature_json
            ),

            len(
                feature_bin
            ),

            len(
                batch_json
            ),

            len(
                batch_bin
            ),
        )

        return (

            header

            + feature_json

            + feature_bin

            + batch_json

            + batch_bin

            + glb_data
        )

    # ================================================================
    # GeoJSON
    # ================================================================

    def load_geojson(
        self,
    ):

        with self.clip_file.open(
            "r",
            encoding="utf-8",
        ) as f:

            data = json.load(f)

        if data["type"] == (
            "FeatureCollection"
        ):

            geometries = []

            for feature in data[
                "features"
            ]:

                geometry = feature.get(
                    "geometry"
                )

                if geometry:

                    geometries.append(
                        shape(
                            geometry
                        )
                    )

            if not geometries:

                raise ValueError(
                    "FeatureCollection 没有 geometry"
                )

            return unary_union(
                geometries
            )

        if data["type"] == "Feature":

            return shape(
                data["geometry"]
            )

        return shape(
            data
        )

    # ================================================================
    # Output Path
    # ================================================================

    def get_output_path(
        self,
        source: Path,
    ):

        if self.input_path.is_file():

            relative = (
                source.relative_to(
                    self.input_path.parent
                )
            )

        else:

            relative = (
                source.relative_to(
                    self.input_path
                )
            )

        return (
            self.output_path
            / relative
        )

    # ================================================================
    # Copy
    # ================================================================

    def copy_preserve_path(
        self,
        source: Path,
    ):

        destination = (
            self.get_output_path(
                source
            )
        )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        shutil.copy2(
            source,
            destination
        )

    # ================================================================
    # URI
    # ================================================================

    @staticmethod
    def clean_uri(
        uri,
    ):

        return (
            uri
            .split(
                "?",
                1
            )[0]
            .split(
                "#",
                1
            )[0]
        )


# ====================================================================
# main
# ====================================================================

if __name__ == "__main__":

    Clip3dTiles({

        # ============================================================
        # 原始 3D Tiles
        # ============================================================

        "inputPath":
            r"D:\lyg\lianyungangdiyirenminyiyuan",

        # ============================================================
        # 输出目录
        # ============================================================

        "outputPath":
            r"D:\lyg\a",

        # ============================================================
        # WGS84 GeoJSON
        # ============================================================

        "clipPolygon":
            r"D:\lyg\clip.geojson",

        # ============================================================
        # 裁剪模式
        #
        # keep
        #   只保留 GeoJSON 内部
        #
        # remove
        #   删除 GeoJSON 内部
        # ============================================================

        "mode":
            "keep",

        # ============================================================
        # B3DM 坐标模式
        #
        # auto
        #   自动判断
        #
        # ecef
        #   RTC_CENTER / 数据位于 ECEF
        #
        # local_rtc
        #   POSITION + RTC_CENTER 为本地坐标
        #
        # enu
        #   POSITION + RTC_CENTER 已经是 ENU
        #
        # 你目前的数据：
        #
        # tileset transform:
        #
        # [[1,0,0,0],
        #  [0,1,0,0],
        #  [0,0,1,0],
        #  [0,0,0,1]]
        #
        # RTC_CENTER:
        #
        # [305, 15, -30]
        #
        # 建议：
        #
        # local_rtc
        # ============================================================

        "b3dmCoordinateMode":
            "local_rtc",
    })