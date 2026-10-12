"""Score pre-annotated tokens in pre-annotated regions; never infer semantic accuracy."""
import argparse
import csv
import json
import re
import statistics
import unicodedata
from pathlib import Path

from prepare import LOCAL


def normalize(text):
    # Keep decimal points, signs, inequality, significant digits and prefix case.
    text = unicodedata.normalize("NFKC", text).replace("−", "-").replace("µ", "μ")
    text = re.sub(r"\s+", "", text)
    return text.replace("μs", "us")


def contains_token(text, expected):
    # Keep separators between distinct OCR lines/numbers. Permit layout spacing
    # inside a token instead of deleting all spaces and accidentally joining 2 values.
    text = unicodedata.normalize("NFKC", text).replace("−", "-").replace("µ", "μ").replace("μs", "us")
    expected = normalize(expected)
    pattern = r"\s*".join(re.escape(char) for char in expected)
    if expected and expected[0] in "+-<0123456789":
        pattern = r"(?<![0-9.<>+\-])" + pattern
    pattern += r"(?![0-9.A-Za-zμ])"
    return re.search(pattern, text) is not None


def bounds(points):
    return [min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points), max(p[1] for p in points)]


def overlap(a, b):
    intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    area = min(max(0, a[2]-a[0]) * max(0, a[3]-a[1]), max(0, b[2]-b[0]) * max(0, b[3]-b[1]))
    return intersection / area if area else 0


def field_input_box(case, field_box, variant):
    if variant == "crop_1800":
        width, height = case["crop_input_size"]
        return [v * (width if i % 2 == 0 else height) for i, v in enumerate(field_box)]
    left, top, right, bottom = case["screen_box_pixels"]
    width, height = case["source_size"]
    out_width, out_height = case["full_input_size"]
    return [(left + field_box[0]*(right-left))*out_width/width,
            (top + field_box[1]*(bottom-top))*out_height/height,
            (left + field_box[2]*(right-left))*out_width/width,
            (top + field_box[3]*(bottom-top))*out_height/height]


def region_text(lines, region):
    selected = [line for line in lines if overlap(bounds(line["box"]), region) >= 0.25]
    # Different-size digits, a plus sign and a unit can share a baseline while
    # having different top coordinates. Group vertically overlapping boxes first.
    rows = []
    for line in sorted(selected, key=lambda line: bounds(line["box"])[1]):
        box = bounds(line["box"])
        target = None
        for row in rows:
            row_top = min(bounds(item["box"])[1] for item in row)
            row_bottom = max(bounds(item["box"])[3] for item in row)
            common = max(0, min(box[3], row_bottom)-max(box[1], row_top))
            smaller_height = min(box[3]-box[1], row_bottom-row_top)
            if smaller_height and common/smaller_height >= 0.5:
                target = row
                break
        if target is None:
            rows.append([line])
        else:
            target.append(line)
    ordered = [line for row in rows for line in sorted(row, key=lambda line: bounds(line["box"])[0])]
    return "\n".join(" ".join(line["text"] for line in sorted(row, key=lambda line: bounds(line["box"])[0])) for row in rows), ordered


def score(model_size="server"):
    cases = {c["id"]: c for c in json.loads((LOCAL / "source_manifest.json").read_text(encoding="utf-8"))}
    raw = json.loads((LOCAL / f"raw_{model_size}.json").read_text(encoding="utf-8"))
    expected_pairs = {(case_id, variant) for case_id in cases for variant in ["full_1800", "crop_1800"]}
    actual_pairs = [(r["case_id"], r["variant"]) for r in raw]
    if set(actual_pairs) != expected_pairs or len(actual_pairs) != len(expected_pairs):
        raise ValueError("识别结果不完整或重复；不生成最终评分。")
    fields, negative = [], []
    for record in raw:
        case = cases[record["case_id"]]
        for field in case["fields"]:
            text, lines = region_text(record["lines"], field_input_box(case, field["box"], record["variant"]))
            fields.append({"case_id": case["id"], "kind": case["kind"], "variant": record["variant"],
                           "field_id": field["id"], "category": field["category"], "expected": field["text"],
                           "observed_region_text": text, "exact_token_found": contains_token(text, field["text"]),
                           "max_line_confidence": max([line["confidence"] for line in lines], default=None)})
        if not case["numeric_readings_expected"]:
            text, lines = region_text(record["lines"], field_input_box(case, [0,0,1,1], record["variant"]))
            negative.append({"case_id": case["id"], "variant": record["variant"], "screen_text": text,
                             "numeric_fragments": re.findall(r"(?<![A-Za-z0-9])[+\-]?\d+(?:\.\d+)?(?![A-Za-z0-9])", text),
                             "numeric_unit_like_strings": re.findall(r"[+\-]?\d+(?:\.\d+)?\s*(?:[kMGmunμ]?Hz|[munμ]?V(?:pp|dc|AC)?|[munμ]?A|[munμ]?s)", text)})
    summary = []
    for kind in ["real_photo", "manual_figure"]:
        for variant in ["full_1800", "crop_1800"]:
            selected = [f for f in fields if f["kind"] == kind and f["variant"] == variant and f["category"] == "numeric_unit"]
            count = sum(f["exact_token_found"] for f in selected)
            timing = [r["median_seconds"] for r in raw if r["kind"] == kind and r["variant"] == variant]
            summary.append({"kind": kind, "variant": variant, "matched": count, "total": len(selected),
                            "region_token_recall": count/len(selected) if selected else None,
                            "median_case_seconds": statistics.median(timing)})
    result = {"metric": "Exact critical-string presence within annotated region; NOT semantic field accuracy or VLM accuracy.",
              "annotation_method": "Assistant visual labels established before viewing OCR output, not independently human-verified.",
              "summary": summary, "fields": fields, "negative_cases": negative,
              "source_images": len({c["source_sha256"] for c in cases.values()}), "screen_regions": len(cases),
              "input_conditions": len(raw), "recognition_calls": sum(len(r["seconds"]) for r in raw),
              "vlm_baseline": {"status": "not_run", "reason": "No Qwen API key configured; DEMO_MODE cannot be used as benchmark."},
              "vlm_crop": {"status": "not_run"}, "vlm_with_ocr": {"status": "not_run"}}
    (LOCAL / f"scored_{model_size}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    with (LOCAL / f"field_scores_{model_size}.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(fields[0]))
        writer.writeheader()
        writer.writerows(fields)
    print(json.dumps({"summary": summary, "negative_cases": negative}, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-size", default="server")
    score(parser.parse_args().model_size)
