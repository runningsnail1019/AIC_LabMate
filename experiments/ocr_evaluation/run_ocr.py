"""Run genuine local PP-OCRv5 via RapidOCR. No VLM calls, no photo uploads."""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import time
import faulthandler
from pathlib import Path

import numpy as np
from rapidocr import EngineType, LangDet, LangRec, ModelType, OCRVersion, RapidOCR

from prepare import LOCAL, prepare


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-size", choices=["server", "mobile"], default="server")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--init-only", action="store_true")
    parser.add_argument("--debug-stacks", action="store_true", help="Print periodic stack traces during slow CPU inference")
    args = parser.parse_args()
    if args.debug_stacks:
        faulthandler.dump_traceback_later(60, repeat=True)
    size = ModelType.SERVER if args.model_size == "server" else ModelType.MOBILE
    params = {"Det.engine_type": EngineType.ONNXRUNTIME, "Det.lang_type": LangDet.CH,
              "Det.model_type": size, "Det.ocr_version": OCRVersion.PPOCRV5,
              "Rec.engine_type": EngineType.ONNXRUNTIME, "Rec.lang_type": LangRec.CH,
              "Rec.model_type": size, "Rec.ocr_version": OCRVersion.PPOCRV5,
              "Global.log_level": "critical", "Global.font_path": "C:/Windows/Fonts/msyh.ttc",
              "EngineConfig.onnxruntime.intra_op_num_threads": 4,
              "EngineConfig.onnxruntime.inter_op_num_threads": 1}
    begin = time.perf_counter()
    engine = RapidOCR(params=params)
    models = Path(importlib.metadata.distribution("rapidocr").locate_file("rapidocr/models"))
    cfg = {"method": "PP-OCRv5 detection+recognition / RapidOCR / ONNX Runtime CPU",
           "model_size": args.model_size, "threads": 4, "repeat": args.repeat,
           "software": {name: importlib.metadata.version(name) for name in ["rapidocr", "onnxruntime", "Pillow", "opencv-python", "numpy"]},
           "python": platform.python_version(), "platform": platform.platform(),
           "initialization_seconds_including_download": round(time.perf_counter() - begin, 3),
           "models": [{"name": p.name, "bytes": p.stat().st_size,
                       "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(models.glob("*.onnx"))],
           "configured_model_paths": {"det": engine.text_det.session.session._model_path,
                                      "rec": engine.text_rec.session.session._model_path}}
    LOCAL.mkdir(parents=True, exist_ok=True)
    (LOCAL / f"engine_{args.model_size}.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print("OCR initialized", cfg["initialization_seconds_including_download"], flush=True)
    if args.init_only:
        return
    manifest = prepare()
    records = []
    for case in manifest:
        for variant in ["full_1800", "crop_1800"]:
            path = LOCAL / f"{case['id']}_{variant}.jpg"
            times, repetitions = [], []
            for iteration in range(args.repeat):
                print("running", case["id"], variant, iteration+1, flush=True)
                start = time.perf_counter()
                result = engine(path, text_score=0.5, box_thresh=0.5)
                times.append(time.perf_counter() - start)
                boxes = [] if result.boxes is None else result.boxes.tolist()
                texts = [] if result.txts is None else list(result.txts)
                scores = [] if result.scores is None else [float(s) for s in result.scores]
                lines = [{"box": b, "text": t, "confidence": s} for b, t, s in zip(boxes, texts, scores)]
                repetitions.append(lines)
            record = {"case_id": case["id"], "kind": case["kind"], "variant": variant,
                      "input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                      "seconds": times, "median_seconds": float(np.median(times)),
                      "deterministic": all(lines == repetitions[0] for lines in repetitions),
                      "lines": repetitions[0]}
            records.append(record)
            (LOCAL / f"raw_{args.model_size}.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
            print(case["id"], variant, "lines", len(record["lines"]), "median", round(record["median_seconds"], 3), flush=True)
    faulthandler.cancel_dump_traceback_later()


if __name__ == "__main__":
    main()
