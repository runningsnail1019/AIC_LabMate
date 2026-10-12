"""Render annotation overlays only for manual QA; never use these as OCR input."""
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from prepare import LOCAL


def main():
    cases = json.loads((Path(__file__).parent / "cases.json").read_text(encoding="utf-8"))["cases"]
    for case in cases:
        if not case["fields"]:
            continue
        image = Image.open(LOCAL / f"{case['id']}_screen_original.png").convert("RGB")
        draw = ImageDraw.Draw(image)
        width, height = image.size
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", max(9, round(width/100)))
        for index, field in enumerate(case["fields"], 1):
            box = [round(v * (width if i % 2 == 0 else height)) for i,v in enumerate(field["box"])]
            draw.rectangle(box, outline="cyan", width=max(1, round(width/900)))
            draw.text((box[0], max(0, box[1]-font.size)), str(index), font=font, fill="cyan")
        image.save(LOCAL / f"{case['id']}_annotation_audit.png")


if __name__ == "__main__":
    main()
