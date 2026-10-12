"""Make local-only, pixel-preserving screen regions and app-style JPEG inputs."""
import hashlib
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / "runtime" / "ocr_eval_local"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def app_jpeg(image, path):
    image = image.convert("RGB")
    image.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
    image.save(path, format="JPEG", quality=84, optimize=True)
    return list(image.size)


def prepare():
    cases = json.loads((Path(__file__).parent / "cases.json").read_text(encoding="utf-8"))["cases"]
    LOCAL.mkdir(parents=True, exist_ok=True)
    manifest = []
    for case in cases:
        source = ROOT / case["source"]
        with Image.open(source) as image:
            image = image.convert("RGB")
            width, height = image.size
            box = [round(v * (width if i % 2 == 0 else height)) for i, v in enumerate(case["screen_box"])]
            crop = image.crop(box)
            crop.save(LOCAL / f"{case['id']}_screen_original.png")
            whole_size = app_jpeg(image.copy(), LOCAL / f"{case['id']}_full_1800.jpg")
            crop_size = app_jpeg(crop.copy(), LOCAL / f"{case['id']}_crop_1800.jpg")
            manifest.append({**case, "source_sha256": sha256(source), "source_size": [width, height],
                             "screen_box_pixels": box, "full_input_size": whole_size, "crop_input_size": crop_size})
            print(case["id"], [width, height], box, whole_size, crop_size, flush=True)
    (LOCAL / "source_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    prepare()
