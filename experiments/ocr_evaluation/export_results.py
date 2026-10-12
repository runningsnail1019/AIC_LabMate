"""Export only non-identifying numeric/text evaluation records, not lab photographs."""
import csv
import json
from pathlib import Path

from prepare import LOCAL, ROOT


def main():
    destination = ROOT / "docs" / "ocr_evaluation"
    destination.mkdir(parents=True, exist_ok=True)
    complete = {"date": "2026-10-12", "application_commit": "c5cd9b3a62106e6a88957d2df29eb97a1cd447f6",
                "qwen_status": {"demo_mode": True, "qwen_key_configured": False, "vlm_tests": "not_run"},
                "engines": {}, "cases": []}
    manifest = json.loads((LOCAL / "source_manifest.json").read_text(encoding="utf-8"))
    for case in manifest:
        complete["cases"].append({k: case[k] for k in ["id", "kind", "source_sha256", "source_size", "screen_box_pixels", "screen_state", "fields"]})
    for size in ["server", "mobile"]:
        scored = json.loads((LOCAL / f"scored_{size}.json").read_text(encoding="utf-8"))
        config = json.loads((LOCAL / f"engine_{size}.json").read_text(encoding="utf-8"))
        raw = json.loads((LOCAL / f"raw_{size}.json").read_text(encoding="utf-8"))
        used_names = {Path(value).name for value in config["configured_model_paths"].values()}
        used_names.add("ch_ppocr_mobile_v2.0_cls_infer.onnx")
        settings = {k: config[k] for k in ["method", "model_size", "threads", "repeat", "software", "python", "platform"]}
        settings["used_models"] = [m for m in config["models"] if m["name"] in used_names]
        complete["engines"][size] = {"settings": settings, "summary": scored["summary"],
                                    "negative_cases": scored["negative_cases"], "metric": scored["metric"],
                                    "annotation_method": scored["annotation_method"],
                                    "input_conditions": scored["input_conditions"], "recognition_calls": scored["recognition_calls"],
                                    "case_timings": [{k:r[k] for k in ["case_id","kind","variant","median_seconds"]} for r in raw]}
        # Region-level transcripts only. No full-photo background transcriptions.
        with (destination / f"field_scores_{size}.csv").open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(scored["fields"][0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(scored["fields"])
    (destination / "results_summary.json").write_text(json.dumps(complete, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print("Exported evaluation summary and 2 field score CSVs; no photos or credentials included.")


if __name__ == "__main__":
    main()
