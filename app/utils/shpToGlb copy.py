import os
import json
import math
from pathlib import Path
import numpy as np
import geopandas as gpd
import trimesh
from shapely.geometry import (
    Polygon,
    MultiPolygon,
    box
)
from pyproj import Transformer


# ============================================================
# 配置
# ============================================================

# 输入 SHP / GeoJSON
INPUT_FILE = r"D:\gis\buildings.geojson"

# 输出目录
OUTPUT_DIR = r"D:\gis\output"


# ============================================================
# Tile 大小
#
# 每个 Tile：
#
# 经度差 1 度
# 纬度差 1 度
#
# 可以修改成：
#
# 0.5
# 0.1
# 0.01
# ============================================================

TILE_LON_SIZE = 1.0
TILE_LAT_SIZE = 1.0


# ============================================================
# 高度字段
# ============================================================

HEIGHT_FIELD = "height"

# 如果没有底部高度，None
#
# 如果有：
#
# BASE_HEIGHT_FIELD = "base_height"
#
BASE_HEIGHT_FIELD = None


# 没有高度属性时默认高度
DEFAULT_HEIGHT = 10.0

# 最小建筑高度
MIN_HEIGHT = 0.1


# ============================================================
# WGS84 -> ECEF
# ============================================================

def lonlat_to_ecef(
    lon,
    lat,
    height=0.0
):

    a = 6378137.0

    f = 1.0 / 298.257223563

    e2 = f * (2.0 - f)

    lon = math.radians(lon)

    lat = math.radians(lat)

    sin_lat = math.sin(lat)

    cos_lat = math.cos(lat)

    sin_lon = math.sin(lon)

    cos_lon = math.cos(lon)

    N = a / math.sqrt(
        1.0 -
        e2 *
        sin_lat *
        sin_lat
    )

    x = (
        N + height
    ) * cos_lat * cos_lon

    y = (
        N + height
    ) * cos_lat * sin_lon

    z = (
        N * (1.0 - e2) + height
    ) * sin_lat

    return np.array([
        x,
        y,
        z
    ])


# ============================================================
# 读取数据
# ============================================================

def load_data():

    print()
    print("==============================")
    print("读取数据")
    print("==============================")

    gdf = gpd.read_file(
        INPUT_FILE
    )

    if gdf.empty:

        raise RuntimeError(
            "输入数据为空"
        )

    print(
        "Feature 数量:",
        len(gdf)
    )

    print(
        "原始 CRS:",
        gdf.crs
    )

    if gdf.crs is None:

        raise RuntimeError(
            "数据没有 CRS"
        )

    # 统一转换为 WGS84
    gdf = gdf.to_crs(
        "EPSG:4326"
    )

    return gdf


# ============================================================
# 获取数据范围
# ============================================================

def get_bounds(
    gdf
):

    min_lon, min_lat, max_lon, max_lat = (
        gdf.total_bounds
    )

    return (
        min_lon,
        min_lat,
        max_lon,
        max_lat
    )


# ============================================================
# 根据经纬度范围自动生成 Tile
#
# 例如：
#
# min_lon = 108.2
# max_lon = 110.6
#
# TILE_LON_SIZE = 1
#
# 得到：
#
# 108~109
# 109~110
# 110~111
#
# 注意：
# Tile 会对齐到整度边界
# ============================================================

def create_tiles(
    min_lon,
    min_lat,
    max_lon,
    max_lat
):

    tiles = []

    # --------------------------------------------------------
    # 对齐到 Tile 网格
    # --------------------------------------------------------

    start_lon = (
        math.floor(
            min_lon / TILE_LON_SIZE
        )
        * TILE_LON_SIZE
    )

    start_lat = (
        math.floor(
            min_lat / TILE_LAT_SIZE
        )
        * TILE_LAT_SIZE
    )

    end_lon = (
        math.ceil(
            max_lon / TILE_LON_SIZE
        )
        * TILE_LON_SIZE
    )

    end_lat = (
        math.ceil(
            max_lat / TILE_LAT_SIZE
        )
        * TILE_LAT_SIZE
    )

    print()
    print("==============================")
    print("Tile 范围")
    print("==============================")

    print(
        "Lon:",
        start_lon,
        "~",
        end_lon
    )

    print(
        "Lat:",
        start_lat,
        "~",
        end_lat
    )

    # --------------------------------------------------------
    # 生成 Tile
    # --------------------------------------------------------

    tile_id = 0

    lon = start_lon

    while lon < end_lon:

        next_lon = min(
            lon + TILE_LON_SIZE,
            end_lon
        )

        lat = start_lat

        while lat < end_lat:

            next_lat = min(
                lat + TILE_LAT_SIZE,
                end_lat
            )

            tile = {

                "id": tile_id,

                "min_lon": lon,

                "min_lat": lat,

                "max_lon": next_lon,

                "max_lat": next_lat
            }

            tiles.append(
                tile
            )

            print(
                f"tile_{tile_id}: "
                f"{lon},{lat} -> "
                f"{next_lon},{next_lat}"
            )

            tile_id += 1

            lat = next_lat

        lon = next_lon

    print()
    print(
        "Tile 总数量:",
        len(tiles)
    )

    return tiles


# ============================================================
# 高度
# ============================================================

def get_height(
    row
):

    value = row.get(
        HEIGHT_FIELD
    )

    if value is None:

        return DEFAULT_HEIGHT

    try:

        height = float(value)

        if math.isnan(height):

            return DEFAULT_HEIGHT

        if height < MIN_HEIGHT:

            return MIN_HEIGHT

        return height

    except:

        return DEFAULT_HEIGHT


# ============================================================
# 底部高度
# ============================================================

def get_base_height(
    row
):

    if not BASE_HEIGHT_FIELD:

        return 0.0

    value = row.get(
        BASE_HEIGHT_FIELD
    )

    if value is None:

        return 0.0

    try:

        return float(value)

    except:

        return 0.0


# ============================================================
# Polygon 修复
# ============================================================

def fix_polygon(
    polygon
):

    if polygon is None:

        return None

    if polygon.is_empty:

        return None

    if not polygon.is_valid:

        polygon = polygon.buffer(0)

    if polygon.is_empty:

        return None

    return polygon


# ============================================================
# Polygon -> Mesh
# ============================================================

def polygon_to_mesh(
    polygon,
    height,
    base_height
):

    polygon = fix_polygon(
        polygon
    )

    if polygon is None:

        return None

    if height <= base_height:

        height = (
            base_height +
            MIN_HEIGHT
        )

    try:

        mesh = trimesh.creation.extrude_polygon(

            polygon,

            height - base_height
        )

        mesh.apply_translation([
            0,
            0,
            base_height
        ])

        return mesh

    except Exception as e:

        print(
            "Polygon 拉伸失败:",
            e
        )

        return None


# ============================================================
# Polygon 转 Local Polygon
# ============================================================

def polygon_to_local(
    polygon,
    transformer,
    origin_x,
    origin_y
):

    # --------------------------------------------------------
    # 外环
    # --------------------------------------------------------

    exterior = []

    for lon, lat in polygon.exterior.coords:

        x, y = transformer.transform(
            lon,
            lat
        )

        x -= origin_x

        y -= origin_y

        exterior.append([
            x,
            y
        ])

    # --------------------------------------------------------
    # 洞
    # --------------------------------------------------------

    holes = []

    for interior in polygon.interiors:

        hole = []

        for lon, lat in interior.coords:

            x, y = transformer.transform(
                lon,
                lat
            )

            x -= origin_x

            y -= origin_y

            hole.append([
                x,
                y
            ])

        holes.append(
            hole
        )

    return Polygon(
        exterior,
        holes=holes
    )


# ============================================================
# 获取 Tile 中的建筑
# ============================================================

def get_tile_features(
    gdf,
    tile
):

    tile_polygon = box(

        tile["min_lon"],

        tile["min_lat"],

        tile["max_lon"],

        tile["max_lat"]
    )

    # --------------------------------------------------------
    # 空间索引
    # --------------------------------------------------------

    try:

        index = gdf.sindex.query(
            tile_polygon,
            predicate="intersects"
        )

        return gdf.iloc[index]

    except Exception:

        # 没有空间索引时的备用方案
        return gdf[
            gdf.geometry.intersects(
                tile_polygon
            )
        ]


# ============================================================
# 生成一个 Tile GLB
# ============================================================

def generate_tile(
    tile,
    gdf,
    output_dir
):

    tile_id = tile["id"]

    print()
    print("--------------------------------")
    print(
        f"生成 tile_{tile_id}.glb"
    )

    # --------------------------------------------------------
    # Tile 中的数据
    # --------------------------------------------------------

    tile_gdf = get_tile_features(
        gdf,
        tile
    )

    print(
        "建筑数量:",
        len(tile_gdf)
    )

    if tile_gdf.empty:

        return None

    # --------------------------------------------------------
    # Tile 中心
    #
    # GLB 使用 Tile 自己的局部坐标
    #
    # 这样每个 GLB 顶点都不会太大
    # --------------------------------------------------------

    center_lon = (
        tile["min_lon"] +
        tile["max_lon"]
    ) / 2.0

    center_lat = (
        tile["min_lat"] +
        tile["max_lat"]
    ) / 2.0

    # --------------------------------------------------------
    # 自动选择 UTM
    # --------------------------------------------------------

    zone = int(
        (center_lon + 180) / 6
    ) + 1

    if center_lat >= 0:

        epsg = 32600 + zone

    else:

        epsg = 32700 + zone

    transformer = Transformer.from_crs(

        "EPSG:4326",

        f"EPSG:{epsg}",

        always_xy=True
    )

    # --------------------------------------------------------
    # Tile 原点
    # --------------------------------------------------------

    origin_x, origin_y = transformer.transform(

        center_lon,

        center_lat
    )

    # --------------------------------------------------------
    # Mesh
    # --------------------------------------------------------

    meshes = []

    building_count = 0

    for index, row in tile_gdf.iterrows():

        geometry = row.geometry

        if geometry is None:

            continue

        if geometry.is_empty:

            continue

        height = get_height(
            row
        )

        base_height = get_base_height(
            row
        )

        # ----------------------------------------------------
        # Polygon
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # 生成建筑
        # ----------------------------------------------------

        for polygon in polygons:

            polygon = fix_polygon(
                polygon
            )

            if polygon is None:

                continue

            local_polygon = polygon_to_local(

                polygon,

                transformer,

                origin_x,

                origin_y
            )

            local_polygon = fix_polygon(
                local_polygon
            )

            if local_polygon is None:

                continue

            mesh = polygon_to_mesh(

                local_polygon,

                height,

                base_height
            )

            if mesh is None:

                continue

            meshes.append(
                mesh
            )

            building_count += 1

    # --------------------------------------------------------
    # 没有建筑
    # --------------------------------------------------------

    if not meshes:

        print(
            "没有生成 Mesh"
        )

        return None

    # --------------------------------------------------------
    # 合并
    # --------------------------------------------------------

    combined = trimesh.util.concatenate(
        meshes
    )

    # --------------------------------------------------------
    # 白膜材质
    # --------------------------------------------------------

    material = trimesh.visual.material.PBRMaterial(

        baseColorFactor=[
            0.85,
            0.85,
            0.85,
            1.0
        ],

        metallicFactor=0.0,

        roughnessFactor=0.9
    )

    combined.visual.material = material

    # --------------------------------------------------------
    # GLB
    # --------------------------------------------------------

    glb_name = (
        f"tile_{tile_id}.glb"
    )

    glb_path = os.path.join(

        output_dir,

        glb_name
    )

    combined.export(

        glb_path,

        file_type="glb"
    )

    print(
        "生成:",
        glb_name
    )

    # --------------------------------------------------------
    # Mesh Bounds
    # --------------------------------------------------------

    bounds = combined.bounds

    local_min = bounds[0]

    local_max = bounds[1]

    # --------------------------------------------------------
    # 转换成 WGS84
    # --------------------------------------------------------

    inverse_transformer = Transformer.from_crs(

        f"EPSG:{epsg}",

        "EPSG:4326",

        always_xy=True
    )

    min_x = (
        local_min[0] +
        origin_x
    )

    min_y = (
        local_min[1] +
        origin_y
    )

    max_x = (
        local_max[0] +
        origin_x
    )

    max_y = (
        local_max[1] +
        origin_y
    )

    min_lon, min_lat = (
        inverse_transformer.transform(
            min_x,
            min_y
        )
    )

    max_lon, max_lat = (
        inverse_transformer.transform(
            max_x,
            max_y
        )
    )

    return {

        "id": tile_id,

        "glb": glb_name,

        "min_lon": min_lon,

        "min_lat": min_lat,

        "max_lon": max_lon,

        "max_lat": max_lat,

        "min_height": float(
            local_min[2]
        ),

        "max_height": float(
            local_max[2]
        ),

        "building_count": building_count
    }


# ============================================================
# 生成 Cesium Region
# ============================================================

def create_region(
    tile
):

    return [

        math.radians(
            tile["min_lon"]
        ),

        math.radians(
            tile["min_lat"]
        ),

        math.radians(
            tile["max_lon"]
        ),

        math.radians(
            tile["max_lat"]
        ),

        tile["min_height"],

        tile["max_height"]
    ]


# ============================================================
# 生成 tileset.json
# ============================================================

def generate_tileset(
    tiles,
    output_dir
):

    valid_tiles = [
        tile
        for tile in tiles
        if tile is not None
    ]

    if not valid_tiles:

        raise RuntimeError(
            "没有有效 Tile"
        )

    # --------------------------------------------------------
    # Root 范围
    # --------------------------------------------------------

    min_lon = min(
        tile["min_lon"]
        for tile in valid_tiles
    )

    min_lat = min(
        tile["min_lat"]
        for tile in valid_tiles
    )

    max_lon = max(
        tile["max_lon"]
        for tile in valid_tiles
    )

    max_lat = max(
        tile["max_lat"]
        for tile in valid_tiles
    )

    min_height = min(
        tile["min_height"]
        for tile in valid_tiles
    )

    max_height = max(
        tile["max_height"]
        for tile in valid_tiles
    )

    # --------------------------------------------------------
    # Children
    # --------------------------------------------------------

    children = []

    for tile in valid_tiles:

        children.append({

            "boundingVolume": {

                "region": create_region(
                    tile
                )
            },

            "geometricError": 0,

            "content": {

                "uri": tile["glb"]
            }
        })

    # --------------------------------------------------------
    # Tileset
    # --------------------------------------------------------

    tileset = {

        "asset": {

            "version": "1.1",

            "gltfUpAxis": "Z"
        },

        "geometricError": 500,

        "root": {

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

            "geometricError": 100,

            "refine": "ADD",

            "children": children
        }
    }

    json_path = os.path.join(

        output_dir,

        "tileset.json"
    )

    with open(

        json_path,

        "w",

        encoding="utf-8"

    ) as f:

        json.dump(

            tileset,

            f,

            indent=2,

            ensure_ascii=False
        )

    print()
    print(
        "生成 tileset.json"
    )

    print(
        "有效 Tile:",
        len(valid_tiles)
    )


# ============================================================
# Main
# ============================================================

def main():

    print()
    print("==========================================")
    print(" SHP / GeoJSON -> Cesium 3D Tiles 白膜")
    print("==========================================")

    # --------------------------------------------------------
    # 输出目录
    # --------------------------------------------------------

    Path(
        OUTPUT_DIR
    ).mkdir(

        parents=True,

        exist_ok=True
    )

    # --------------------------------------------------------
    # 读取
    # --------------------------------------------------------

    gdf = load_data()

    # --------------------------------------------------------
    # 数据范围
    # --------------------------------------------------------

    (
        min_lon,
        min_lat,
        max_lon,
        max_lat
    ) = get_bounds(
        gdf
    )

    print()
    print(
        "数据范围:"
    )

    print(
        f"Lon: {min_lon} ~ {max_lon}"
    )

    print(
        f"Lat: {min_lat} ~ {max_lat}"
    )

    # --------------------------------------------------------
    # 创建 Tile
    # --------------------------------------------------------

    tiles = create_tiles(

        min_lon,

        min_lat,

        max_lon,

        max_lat
    )

    # --------------------------------------------------------
    # 生成 GLB
    # --------------------------------------------------------

    generated_tiles = []

    for tile in tiles:

        result = generate_tile(

            tile,

            gdf,

            OUTPUT_DIR
        )

        if result:

            generated_tiles.append(
                result
            )

    # --------------------------------------------------------
    # tileset.json
    # --------------------------------------------------------

    generate_tileset(

        generated_tiles,

        OUTPUT_DIR
    )

    # --------------------------------------------------------
    # 完成
    # --------------------------------------------------------

    print()
    print("==========================================")
    print("生成完成")
    print("==========================================")

    print()

    for file in sorted(
        os.listdir(
            OUTPUT_DIR
        )
    ):

        print(
            file
        )


# ============================================================
# Run
# ============================================================

if __name__ == "__main__":

    main()