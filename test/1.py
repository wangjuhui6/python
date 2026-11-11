# 命令行入口。切瓦片的实现在 app/utils/image_mbtiles.py。
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from utils.image_mbtiles import ImageMbtilesError, build


def main():
  parser = argparse.ArgumentParser(description="按图片四个角的经纬度生成栅格 MBTiles")
  parser.add_argument("folder", nargs="?", help="包含 json 和图片的文件夹")
  parser.add_argument("-o", "--output", help="输出的 .mbtiles 路径")
  parser.add_argument("--minzoom", type=int)
  parser.add_argument("--maxzoom", type=int)
  args = parser.parse_args()
  folder = args.folder or Path(__file__).resolve().parent
  try:
    result = build(folder, args.output, args.minzoom, args.maxzoom)
  except ImageMbtilesError as exc:
    raise SystemExit(str(exc))
  west, south, east, north = result["bounds"]
  print(f"已写入 {result['output']}")
  print(f"图片 {result['images']} 张，瓦片 {result['tiles']} 个，级别 {result['minzoom']}–{result['maxzoom']}")
  print(f"范围 {west:.6f},{south:.6f},{east:.6f},{north:.6f}")


if __name__ == "__main__":
  main()
