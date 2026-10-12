"""Validate model observations only on the opt-in template path."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator

from .catalog import PACKAGE_DIR, get_template


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    schema = json.loads((PACKAGE_DIR / "schemas" / "observation.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def validate_observation(state: Any, template_id: str) -> None:
    """Reject incomplete JSON, reference IDs masquerading as parts, and bad boxes."""
    error = next(_validator().iter_errors(state), None)
    if error is not None:
        location = ".".join(map(str, error.absolute_path)) or "observation"
        raise ValueError(f"模板观察字段不符合协议：{location}")
    template = get_template(template_id)
    if state["observations"]["template_id"] != template["template_id"]:
        raise ValueError("模型返回的 template_id 与选择不一致")
    ids = {component["id"] for component in template["components"]}
    for component in state["observations"]["components"]:
        if component["component_id"] not in ids:
            raise ValueError("模型返回了模板目录以外的 component_id")
        bbox = component["bbox"]
        if bbox is not None and (bbox[0] > bbox[2] or bbox[1] > bbox[3]):
            raise ValueError("bbox 必须按左上角到右下角排列")
    for value in state["measurement_values"].values():
        if value["source_component"] and value["source_component"] not in ids:
            raise ValueError("读数来源不在模板部件目录中")
