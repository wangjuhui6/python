from pathlib import Path
import json
from collections import Counter
from PIL import Image
from llm.map_legend import detect_features

def run(sample_id):
  root = Path(r"d:\wjh\python\app\data\train-legend")
  img_path = root / "images" / f"{sample_id}.png"
  lab = json.loads((root / "labels" / f"{sample_id}.json").read_text(encoding="utf-8"))
  im = Image.open(img_path)
  w, h = im.size
  feats = detect_features(img_path, [dict(x) for x in lab["legend"]], [[1,0,0],[0,1,0]], w, h, lab.get("legend_box"))
  print("===", lab.get("filename"), "n", len(feats), dict(Counter((f["name"], f["type"]) for f in feats)))
  for f in feats:
    print(f["name"], f["type"], round(f["x"]), round(f["y"]), "px", f.get("pixels"))

run("e1f73dee9dfc46b2b865253c62c11c9b")
print()
run("0435763d996242e285d4a60f55f8d43b")
