import base64
import json
import unittest

from backend.device_templates.catalog import (
    PACKAGE_DIR, build_visual_content, get_template, list_templates, render_prompt,
)


class DeviceTemplateTests(unittest.TestCase):
    def test_catalog_sources_and_unique_component_ids(self):
        self.assertEqual(len(list_templates()), 3)
        for entry in list_templates():
            template = get_template(entry["template_id"])
            ids = [c["id"] for c in template["components"]]
            self.assertEqual(len(ids), len(set(ids)))
            references = {r["id"] for r in template["reference_images"]}
            for component in template["components"]:
                self.assertIn(component["reference"], references)
                self.assertGreater(component["pdf_page"], 0)
                self.assertTrue(component["printed_page"])
            for focus in template["task_focus"].values():
                self.assertTrue(set(focus) <= set(ids))
            for ref in template["reference_images"]:
                self.assertTrue((PACKAGE_DIR / ref["path"]).is_file())

    def test_plus_is_not_hd_and_arbitrary_selectors_are_rejected(self):
        for selector in ("SDS2202X Plus", "../../main.py", "SDM3055", "unknown"):
            with self.assertRaises(ValueError):
                get_template(selector)
        self.assertEqual(get_template("SDG2082X")["template_id"], "siglent_sdg2000x")

    def test_live_image_is_first_and_references_are_labelled(self):
        content = build_visual_content("SDG2082X", b"current-photo", "image/jpeg", "看输出")
        images = [c for c in content if c["type"] == "image_url"]
        self.assertEqual(len(images), 3)
        self.assertEqual(base64.b64decode(images[0]["image_url"]["url"].split(",", 1)[1]), b"current-photo")
        self.assertIn("本轮现场照片", content[1]["text"])
        self.assertIn("不是当前现场", content[3]["text"])

    def test_rear_scope_does_not_require_screen_or_front_reference(self):
        content = build_visual_content("SDM3055X-E", b"rear", "image/png", "看后面板", panel="rear")
        self.assertEqual(len([c for c in content if c["type"] == "image_url"]), 2)
        self.assertIn("外触发接口", content[0]["text"])
        self.assertNotIn("LCD 显示屏 | front", content[0]["text"])

    def test_text_only_reference_and_input_validation(self):
        content = build_visual_content("SDG2082X", b"x", "image/png", "q", include_references=False)
        self.assertEqual(len(content), 3)
        for image, mime in ((b"", "image/png"), (b"x", "text/plain")):
            with self.assertRaises(ValueError):
                build_visual_content("SDG2082X", image, mime, "q")

    def test_fast_mode_keeps_plan_protocol_and_separates_reference_state(self):
        prompt = render_prompt("SDG2082X", "设置频率", mode="fast", manual_context="证据1", history=[{"question":"上轮"}])
        self.assertIn("observation 和 plan", prompt)
        self.assertIn("evidence_sufficient=false", prompt)
        self.assertIn("不是本轮设备状态", prompt)
        self.assertIn("证据1", prompt)
        self.assertIn("上轮", prompt)

    def test_unknown_example_has_existing_app_keys(self):
        state = json.loads((PACKAGE_DIR / "examples" / "observation_unknown.json").read_text(encoding="utf-8"))
        self.assertEqual(state["observations"]["temporal_stability"], "unknown")
        self.assertIsNone(state["measurement_values"]["frequency_setting"]["value"])
        self.assertTrue(state["need_retake"])
        for field in ("image_quality", "observations", "measurement_values", "visible_text",
                      "uncertain_items", "safety_flags", "confidence", "need_retake"):
            self.assertIn(field, state)


if __name__ == "__main__":
    unittest.main()
