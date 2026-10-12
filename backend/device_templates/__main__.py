"""Preview prompts or Qwen payloads locally without sending any API request."""
from __future__ import annotations

import argparse
import json
import mimetypes
from pathlib import Path

from .catalog import build_visual_content, list_templates, render_prompt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--template-id")
    parser.add_argument("--question", default="请识别与当前任务相关的屏幕、按键和接口")
    parser.add_argument("--panel", choices=["front", "rear", "screen", "all"], default="front")
    parser.add_argument("--mode", choices=["observation", "fast"], default="observation")
    parser.add_argument("--image", type=Path, help="Build payload with this current photo (no network call)")
    parser.add_argument("--no-reference-images", action="store_true")
    parser.add_argument("--model", default="qwen-vl-plus")
    args = parser.parse_args()
    if args.list:
        print(json.dumps(list_templates(), ensure_ascii=False, indent=2))
        return
    if not args.template_id:
        parser.error("--template-id is required unless --list is used")
    if args.image:
        content_type = mimetypes.guess_type(args.image.name)[0] or "application/octet-stream"
        content = build_visual_content(args.template_id, args.image.read_bytes(), content_type,
                                       args.question, args.panel, args.mode, not args.no_reference_images)
        print(json.dumps({"model": args.model, "messages": [{"role": "user", "content": content}],
                          "temperature": 0.1, "max_tokens": 1600}, ensure_ascii=False, indent=2))
    else:
        print(render_prompt(args.template_id, args.question, args.panel, args.mode))


if __name__ == "__main__":
    main()
