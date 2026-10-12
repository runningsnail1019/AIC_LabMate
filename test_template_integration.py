"""Offline HTTP integration checks. Never read .env or send model requests."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

with patch("dotenv.load_dotenv", return_value=False):
    from backend.app import main

from backend.device_templates.catalog import PACKAGE_DIR, get_template
from backend.device_templates.validation import validate_observation


TEMPLATE = "siglent_sdg2000x"


def observation(template_id=TEMPLATE):
    return {"image_quality": "good", "observations": {
        "template_id": template_id, "panel_view": "front", "screen_state": "blank",
        "temporal_stability": "unknown", "components": []},
        "measurement_values": {}, "visible_text": [], "uncertain_items": [],
        "safety_flags": [], "confidence": 0.5, "need_retake": False}


def plan():
    return {"goal": "识别输出接口", "need_clarification": False, "questions": [],
            "next_action": "查看 CH1 标记。", "status": "GUIDANCE", "reason": "依据本轮照片。",
            "expected_result": None, "evidence_sufficient": True, "safety_notes": []}


class TemplateIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="labmate-integration-")
        self.addCleanup(self.tmp.cleanup)
        self.stack = []
        for name, value in (
            ("UPLOAD_DIR", Path(self.tmp.name)), ("DEMO_MODE", False),
            ("QWEN_API_KEY", "offline-test-not-a-real-key"), ("FAST_MODE", True),
        ):
            p = patch.object(main, name, value)
            p.start()
            self.addCleanup(p.stop)
        for name, value in (("save_checkpoint", None), ("_load_manual_context", "旧说明书证据"),
                            ("_load_manual_evidence", [])):
            p = patch.object(main, name, return_value=value)
            mock = p.start()
            self.addCleanup(p.stop)
            setattr(self, name, mock)
        self.client = TestClient(main.app)
        self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        self.reply({"observation": observation(), "plan": plan()})

    def reply(self, result, raw=False):
        response = httpx.Response(200, request=httpx.Request("POST", "https://example.invalid"),
                                  json={"choices": [{"message": {"content": result if raw else json.dumps(result)}}]})
        self.post = AsyncMock(return_value=response)
        p = patch.object(main.app.state.qwen_client, "post", self.post)
        p.start()
        self.addCleanup(p.stop)

    def analyze(self, **fields):
        data = {"version": "SDG2000X", "question": "识别 CH1 输出接口", "template_id": TEMPLATE}
        data.update(fields)
        return self.client.post("/api/analyze", data=data,
                                files={"image": ("offline.png", b"offline-test-image", "image/png")})

    def payload(self):
        return self.post.call_args.kwargs["json"]

    def test_template_catalog_and_frontend_are_served(self):
        result = self.client.get("/api/device-templates")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(result.json()["templates"]), 3)
        self.assertIn("SDG2082X", result.json()["templates"][0]["selectors"])
        page = self.client.get("/")
        self.assertIn('id="template"', page.text)
        self.assertIn("SDS2202X Plus", page.text)
        self.assertTrue(self.client.get("/api/health").json()["device_templates_available"])

    def test_fast_template_sends_live_photo_and_two_labelled_references(self):
        result = self.analyze()
        self.assertEqual(result.status_code, 200, result.text)
        payload = self.payload()
        contents = payload["messages"][0]["content"]
        self.assertEqual(sum(c["type"] == "image_url" for c in contents), 3)
        self.assertIn("本轮现场照片", contents[1]["text"])
        self.assertIn("不是当前现场", contents[3]["text"])
        self.assertGreater(payload["max_tokens"], 650)
        self.assertTrue(result.json()["template"]["applied"])
        # Even a model's true flag is rejected without matching operation evidence.
        self.assertFalse(result.json()["decision"]["evidence_sufficient"])
        self._load_manual_context.assert_not_called()

    def test_original_no_template_request_keeps_original_payload(self):
        result = self.analyze(template_id="", version="EPI-EWB204+")
        self.assertEqual(result.status_code, 200, result.text)
        payload = self.payload()
        self.assertEqual(payload["max_tokens"], 650)
        contents = payload["messages"][0]["content"]
        self.assertEqual(len(contents), 2)
        self.assertIn("EPI-EWB204+", contents[0]["text"])
        self.assertIsNone(result.json()["template"]["id"])
        self._load_manual_context.assert_called_once()

    def test_rear_panel_only_adds_one_reference(self):
        result = self.analyze(panel="rear")
        self.assertEqual(result.status_code, 200, result.text)
        contents = self.payload()["messages"][0]["content"]
        self.assertEqual(sum(c["type"] == "image_url" for c in contents), 2)
        self.assertIn("参考图 rear", contents[3]["text"])

    def test_text_template_option_sends_only_current_photo(self):
        result = self.analyze(include_references="false")
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(sum(c["type"] == "image_url" for c in self.payload()["messages"][0]["content"]), 1)
        self.assertFalse(result.json()["template"]["references_included"])

    def test_unknown_selector_invalid_panel_and_wrong_manual_are_rejected(self):
        for fields in ({"template_id": "../../x"}, {"panel": "bad"}, {"version": "EPI-EWB204+"},
                       {"template_id": "siglent_sds2000x_hd", "version": "SDS2202X Plus"}):
            with self.subTest(fields=fields):
                self.assertEqual(self.analyze(**fields).status_code, 400)
        self.post.assert_not_called()
        self.assertEqual(list(Path(self.tmp.name).iterdir()), [])

    def test_selected_sdg_actual_model_alias_is_accepted(self):
        self.assertEqual(self.analyze(version="SDG2082X").status_code, 200)

    def test_incomplete_model_observation_is_rejected(self):
        self.reply({"observation": {}, "plan": plan()})
        result = self.analyze()
        self.assertEqual(result.status_code, 502)
        self.assertIn("模板观察字段", result.json()["detail"])

    def test_model_cannot_claim_temporal_stability_from_single_photo(self):
        state = observation()
        state["observations"]["temporal_stability"] = "stable"
        self.reply({"observation": state, "plan": plan()})
        self.assertEqual(self.analyze().status_code, 502)

    def test_unreadable_photo_still_uses_existing_quality_gate(self):
        state = observation()
        state["need_retake"] = True
        self.reply({"observation": state, "plan": plan()})
        result = self.analyze().json()
        self.assertEqual(result["decision"]["status"], "NEED_MORE_INFORMATION")
        self.assertFalse(result["decision"]["evidence_sufficient"])

    def test_slow_mode_uses_template_vision_and_existing_planner(self):
        self.reply(observation())
        with patch.object(main, "FAST_MODE", False), patch.object(main, "_qwen_plan", AsyncMock(return_value=plan())) as planner:
            result = self.analyze()
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(sum(c["type"] == "image_url" for c in self.payload()["messages"][0]["content"]), 3)
        self.assertEqual(self.payload()["model"], main.QWEN_VISION_MODEL)
        planner.assert_awaited_once()
        self.assertEqual(planner.call_args.args[2]["observations"]["template_id"], TEMPLATE)

    def test_demo_and_missing_key_never_send_photos_to_model(self):
        for fast in (True, False):
            for flag, value in (("DEMO_MODE", True), ("QWEN_API_KEY", "")):
                with self.subTest(fast=fast, flag=flag), patch.object(main, "FAST_MODE", fast), patch.object(main, flag, value):
                    result = self.analyze()
                    self.assertEqual(result.status_code, 200, result.text)
                    body = result.json()
                    self.assertEqual(body["mode"], "demo")
                    self.assertFalse(body["template"]["applied"])
                    self.assertEqual(body["state"]["observations"]["components"], [])
                    self.assertEqual(body["state"]["confidence"], 0)
                    self.assertIn("未调用视觉模型", body["guidance"])
        self.post.assert_not_called()

    def test_template_retrieval_never_uses_default_pdf_or_wrong_device(self):
        hit = {"device_model": "EPI-EWB204+", "rank": 1, "title": "EPI", "page": 1,
               "section": "x", "source_level": "manual", "content": "不能混入"}
        self._load_manual_evidence.return_value = [hit]
        result = self.analyze()
        self.assertEqual(result.json()["evidence"], [])
        self.assertNotIn("不能混入", self.payload()["messages"][0]["content"][0]["text"])
        self._load_manual_context.assert_not_called()
        self._load_manual_evidence.return_value = [{**hit, "device_model": "SDG2000X", "title": "SDG"}]
        result = self.analyze()
        self.assertTrue(result.json()["decision"]["evidence_sufficient"])
        self.assertEqual(len(result.json()["evidence"]), 1)

    def test_missing_reference_has_actionable_error(self):
        with patch.object(main, "build_visual_content", side_effect=FileNotFoundError("missing")):
            result = self.analyze()
        self.assertEqual(result.status_code, 500)
        self.post.assert_not_called()


class ObservationValidationTests(unittest.TestCase):
    def test_template_examples_still_validate(self):
        example = json.loads((PACKAGE_DIR / "examples" / "observation_unknown.json").read_text(encoding="utf-8"))
        validate_observation(example, example["observations"]["template_id"])

    def test_unknown_part_wrong_template_and_reversed_box_are_rejected(self):
        state = observation()
        part = {"component_id": get_template(TEMPLATE)["components"][0]["id"],
                "visibility": "visible", "label_text": None, "state": None, "bbox": None, "evidence": "测试"}
        state["observations"]["components"] = [part]
        validate_observation(state, TEMPLATE)
        for change in ({"component_id": "invented"}, {"bbox": [0.9, 0.9, 0.1, 0.1]}, {"bbox": [0, 0, 2, 1]}):
            invalid = copy.deepcopy(state)
            invalid["observations"]["components"][0].update(change)
            with self.assertRaises(ValueError):
                validate_observation(invalid, TEMPLATE)
        state["observations"]["template_id"] = "wrong"
        with self.assertRaises(ValueError):
            validate_observation(state, TEMPLATE)


if __name__ == "__main__":
    unittest.main()
