from __future__ import annotations

import base64
import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.workflow import classify_question, save_checkpoint

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend"
UPLOAD_DIR = ROOT / "runtime" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

load_dotenv(ROOT / "backend" / ".env")

DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() not in {"0", "false", "no"}
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")
QWEN_BASE_URL = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
QWEN_VISION_MODEL = os.getenv("QWEN_VISION_MODEL", "qwen-vl-max")
QWEN_TEXT_MODEL = os.getenv("QWEN_TEXT_MODEL", "qwen-plus")
QWEN_FAST_MODEL = os.getenv("QWEN_FAST_MODEL", "qwen-vl-plus")
# Ignore inherited HTTP(S)_PROXY variables by default. A stale local proxy
# (for example 127.0.0.1:9) otherwise makes every Qwen request time out.
QWEN_TRUST_ENV = os.getenv("QWEN_TRUST_ENV", "false").lower() in {"1", "true", "yes"}
# Fast mode is the default for interactive use: one multimodal request returns
# both the visual observation and this turn's plan. Set false for the slower,
# two-call diagnostic mode when evaluating the planner separately.
FAST_MODE = os.getenv("FAST_MODE", "true").lower() in {"1", "true", "yes"}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Reuse a connection pool across turns. Creating a new AsyncClient for
    # every upload adds avoidable TCP/TLS setup time on Windows.
    app.state.qwen_client = httpx.AsyncClient(
        timeout=httpx.Timeout(45.0, connect=10.0), trust_env=QWEN_TRUST_ENV
    )
    try:
        yield
    finally:
        await app.state.qwen_client.aclose()

app = FastAPI(title="LabMate Demo API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


def _load_manual_context(version: str, question: str) -> str:
    """Read a small, relevant context from the configured PDF manual.

    For a first demo, keyword matching keeps startup fast and makes the source
    page visible to the user. A vector index can replace this function later.
    """
    # Prefer the prebuilt, device-filtered SQLite/FTS index. The PDF fallback
    # keeps the demo usable before the first import command is run.
    try:
        from backend.knowledge.retrieve import search
        indexed = search(question, version)
        if indexed:
            return indexed
    except Exception:
        pass
    pdf_name = os.getenv("KNOWLEDGE_PDF", "EPI-EWB204+ 使用(1).pdf")
    pdf_path = ROOT / pdf_name
    if not pdf_path.exists():
        return "知识库中暂未找到该设备的 PDF 说明书。"
    try:
        import fitz  # type: ignore

        keywords = set(re.findall(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]{2,}", f"{version} {question}".lower()))
        pages: list[tuple[int, str, int]] = []
        with fitz.open(pdf_path) as doc:
            for index, page in enumerate(doc):
                text = page.get_text("text") or ""
                score = sum(1 for word in keywords if word and word in text.lower())
                if score:
                    pages.append((score, text, index + 1))
        pages.sort(reverse=True, key=lambda item: item[0])
        if not pages:
            return "已加载设备说明书，但未检索到与当前问题直接匹配的页面。"
        snippets = []
        for _, text, page in pages[:3]:
            clean = re.sub(r"\s+", " ", text).strip()
            snippets.append(f"[说明书第 {page} 页]\n{clean[:1800]}")
        return "\n\n".join(snippets)
    except ImportError:
        return "已配置说明书文件；当前环境未安装 PyMuPDF，暂无法读取 PDF。"
    except Exception as exc:
        return f"说明书读取失败：{exc}"


def _load_manual_evidence(version: str, question: str) -> list[dict[str, Any]]:
    """Return citation-ready records for the UI and the model context."""
    try:
        from backend.knowledge.retrieve import search_hits

        return list(search_hits(question, version))
    except Exception:
        return []


def _compress_for_model(image_bytes: bytes, content_type: str) -> tuple[bytes, str]:
    """Shrink phone photos while preserving enough detail for screen reading."""
    try:
        from io import BytesIO
        from PIL import Image

        with Image.open(BytesIO(image_bytes)) as image:
            image = image.convert("RGB")
            image.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="JPEG", quality=84, optimize=True)
            return output.getvalue(), "image/jpeg"
    except Exception:
        return image_bytes, content_type


def _constraint_check(state: dict[str, Any]) -> dict[str, Any]:
    """Small, task-independent safety/quality gate.

    This deliberately does not decide the task or prescribe a fixed sequence.
    It only prevents confident planning when the image is unusable or the
    vision model has explicitly detected a safety concern.
    """
    uncertain = state.get("uncertain_items") or []
    if state.get("need_retake") is True or state.get("image_quality") in {"poor", "unusable"}:
        return {"blocked": True, "reason": "当前照片信息不足，请补拍一张更清晰、包含屏幕和相关操作区域的照片。"}
    safety_flags = state.get("safety_flags") or []
    if safety_flags:
        return {"blocked": True, "reason": "图像中检测到可能的安全风险：" + "、".join(map(str, safety_flags)) + "。请先人工确认安全条件。"}
    if len(uncertain) > 8:
        return {"blocked": True, "reason": "当前画面中有较多关键状态无法确认，请调整拍摄角度或距离后重拍。"}
    return {"blocked": False, "reason": ""}


def _clean_identity_questions(decision: dict[str, Any]) -> dict[str, Any]:
    """Remove model-generated device identity checks from user-facing output.

    Device identity is intentionally an input/routing concern in this product;
    the uploaded image is assumed to be the selected device's current view.
    """
    identity_terms = ("型号", "版本", "品牌", "铭牌", "设备是否", "是否对应", "实际设备")
    questions = decision.get("questions") or []
    decision["questions"] = [q for q in questions if not any(term in str(q) for term in identity_terms)]
    for field in ("reason", "next_action"):
        value = decision.get(field)
        if isinstance(value, str):
            lines = [line for line in value.splitlines() if not any(term in line for term in identity_terms)]
            decision[field] = "\n".join(lines).strip()
    if not decision.get("questions") and decision.get("status") == "NEED_MORE_INFORMATION" and not decision.get("next_action"):
        decision["next_action"] = "请补拍一张能清楚看到相关屏幕、按钮或接口的照片，我会根据当前画面继续指导。"
    decision.pop("device_model", None)
    decision.pop("visual_device_model", None)
    decision.pop("identity_conflict", None)
    return decision


def _demo_state(question: str) -> dict[str, Any]:
    # Deterministic fallback makes the UI demonstrable without a paid API key.
    q = question.lower()
    if any(word in q for word in ["完成", "结果", "频率", "frequency"]):
        return {
            "image_quality": "good",
            "channel_1_enabled": True,
            "waveform_visible": True,
            "waveform_stable": True,
            "frequency_value": None,
            "confidence": 0.78,
            "image_quality": "good",
            "observations": {"waveform": "visible and stable", "channel_1": "on"},
            "uncertain_items": [],
        }
    return {
        "image_quality": "good",
        "channel_1_enabled": True,
        "waveform_visible": True,
        "waveform_stable": False,
        "frequency_value": None,
        "confidence": 0.74,
        "image_quality": "good",
        "observations": {"waveform": "visible but stability is unclear"},
        "uncertain_items": ["trigger_level"],
    }


def _demo_plan(question: str, state: dict[str, Any], context: str) -> dict[str, Any]:
    if state.get("need_retake"):
        return {"goal": question, "need_clarification": True, "questions": ["请补拍一张包含屏幕和相关操作区域的清晰照片。"], "next_action": None, "status": "NEED_MORE_INFORMATION", "reason": "当前图片信息不足。", "expected_result": "获得清晰的设备状态画面。", "evidence_sufficient": False, "safety_notes": []}
    return {"goal": question, "need_clarification": False, "questions": [], "next_action": "请根据当前画面执行最相关的一步操作，完成后再次上传照片，我会继续确认。", "status": "GUIDANCE", "reason": "已根据当前画面和用户目标生成本轮建议。", "expected_result": "设备状态发生与本轮操作相符的变化。", "evidence_sufficient": bool(context and "未检索到" not in context), "safety_notes": []}


async def _qwen_vision(image_bytes: bytes, content_type: str, question: str, version: str) -> dict[str, Any]:
    if DEMO_MODE or not QWEN_API_KEY:
        return _demo_state(question)
    data_url = f"data:{content_type};base64,{base64.b64encode(image_bytes).decode()}"
    prompt = f"""你是科研仪器视觉观察模块。用户已经在系统中选择了知识库版本：{version}。
这个版本号只用于后端查找知识库，图片是否出现型号文字、图片中的品牌或铭牌都不需要核对，也不能阻止回答。不要输出或讨论设备型号一致性。
学生的问题是：{question}
请只报告图片中能观察到的事实，不要替用户规划完整流程，不要凭常识补全看不清的内容。严格只返回 JSON，不要 Markdown，字段必须包含：
image_quality（good/poor/unusable）、observations（自由键值对象，记录看见的屏幕、通道、菜单、接线和控制状态）、measurement_values（对象）、visible_text（数组）、uncertain_items（数组）、safety_flags（数组）、confidence（0到1）、need_retake（布尔值）。
看不清或无法从图片确认的内容必须放入 uncertain_items，不得猜测。"""
    payload = {"model": QWEN_VISION_MODEL, "messages": [{"role": "user", "content": [
        {"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": data_url}}
    ]}], "temperature": 0.1}
    response = await app.state.qwen_client.post(f"{QWEN_BASE_URL}/chat/completions", headers={"Authorization": f"Bearer {QWEN_API_KEY}"}, json=payload)
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    return json.loads(content)


async def _qwen_fast_turn(image_bytes: bytes, content_type: str, question: str, version: str, context: str, history: list[dict[str, str]], route: str = "general") -> tuple[dict[str, Any], dict[str, Any]]:
    """One VLM request for the interactive path.

    The model still separates observation from planning in the response JSON,
    but network latency is paid only once instead of once for vision and once
    for text planning.
    """
    if DEMO_MODE or not QWEN_API_KEY:
        state = _demo_state(question)
        return state, _demo_plan(question, state, context)
    data_url = f"data:{content_type};base64,{base64.b64encode(image_bytes).decode()}"
    prompt = f"""你是 LabMate 的多模态科研仪器助教。请在一次响应中完成‘观察’和‘本轮规划’，但严格区分两者。
用户选择的知识库版本是：{version}。它只用于检索对应数据库。默认用户上传的图片就是本次要分析的设备现场，不要检查、质疑或输出图片品牌/型号与该版本是否一致。
问题类型：{route}
学生问题：{question}
最近历史：{json.dumps(history[-3:], ensure_ascii=False)}
设备说明书检索证据：\n{context[:2600]}

只返回 JSON，不要 Markdown。顶层必须包含 observation 和 plan。
observation 必须包含：image_quality（good/poor/unusable）、observations、measurement_values、visible_text、uncertain_items、safety_flags、confidence（0到1）、need_retake。
plan 必须包含：goal、need_clarification、questions（数组）、next_action（字符串或 null）、status（GUIDANCE/NEED_MORE_INFORMATION/COMPLETED/ESCALATE）、reason、expected_result（字符串或 null）、evidence_sufficient（布尔值）、safety_notes（数组）。
要求：只陈述图片能支持的事实；一次只给最重要的一步或短动作组；信息不足就追问或要求补拍；没有明确的设备专属证据时 evidence_sufficient=false，不要编造按钮和页码。不得因为图片中没有版本文字、出现其他品牌或无法读到铭牌而追问型号。"""
    payload = {"model": QWEN_FAST_MODEL, "messages": [{"role": "user", "content": [
        {"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": data_url}}
    ]}], "temperature": 0.1, "max_tokens": 650}
    response = await app.state.qwen_client.post(f"{QWEN_BASE_URL}/chat/completions", headers={"Authorization": f"Bearer {QWEN_API_KEY}"}, json=payload, timeout=httpx.Timeout(45.0, connect=10.0))
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    result = json.loads(content)
    return result.get("observation", {}), result.get("plan", {})


async def _qwen_plan(question: str, version: str, state: dict[str, Any], context: str, history: list[dict[str, str]], gate: dict[str, Any]) -> dict[str, Any]:
    """Plan one conversational turn instead of selecting a fixed workflow step."""
    if DEMO_MODE or not QWEN_API_KEY:
        if gate["blocked"]:
            return {"goal": question, "need_clarification": True, "questions": [gate["reason"]], "next_action": None, "status": "NEED_MORE_INFORMATION", "reason": gate["reason"], "expected_result": None, "evidence_sufficient": False}
        return {"goal": question, "need_clarification": False, "questions": [], "next_action": "请根据图片中已经确认的状态继续操作；完成后再次上传照片，我会继续判断。", "status": "GUIDANCE", "reason": "已根据当前画面和用户目标生成本轮建议。", "expected_result": "设备状态发生与本轮操作相符的变化。", "evidence_sufficient": bool(context and "未检索到" not in context)}
    history_text = json.dumps(history[-8:], ensure_ascii=False)
    prompt = f"""你是 LabMate 的任务规划器，负责陪伴学生完成任意科研仪器操作任务。用户选择的知识库版本是：{version}，只用于检索对应数据库。
默认用户上传的图片就是本次要分析的设备现场。图片里没有型号文字、出现其他品牌或铭牌无法读取都不是阻断条件；不要追问型号，不要输出型号一致性判断。
学生当前问题：{question}
此前对话和操作记录：{history_text}
本轮图片观察（只代表看见的事实）：{json.dumps(state, ensure_ascii=False)}
说明书/SOP检索内容：\n{context}\n
请动态规划当前这一轮，不要假设任务一定是测量频率，也不要强行套用固定状态机。可以选择：直接给一个最重要的下一步、先提出澄清问题、要求补拍照片、告知已完成，或在没有可靠依据时建议联系管理员。
必须严格只返回 JSON，不要 Markdown，字段必须包含：
goal（理解后的目标）、need_clarification（布尔值）、questions（数组）、next_action（字符串或 null）、status（GUIDANCE/NEED_MORE_INFORMATION/COMPLETED/ESCALATE）、reason（依据当前状态的原因）、expected_result（执行后应观察到的变化或 null）、evidence_sufficient（布尔值）、safety_notes（数组）。
要求：一次只给最重要的一步或一组很短的连续动作；不能编造说明书没有的型号专属按钮；如果说明书片段不足以支持具体操作，evidence_sufficient 必须为 false，并把不确定性说清楚。"""
    payload = {"model": QWEN_TEXT_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2}
    response = await app.state.qwen_client.post(f"{QWEN_BASE_URL}/chat/completions", headers={"Authorization": f"Bearer {QWEN_API_KEY}"}, json=payload, timeout=httpx.Timeout(90.0, connect=15.0))
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    return json.loads(content)


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "demo_mode": DEMO_MODE or not bool(QWEN_API_KEY),
        "qwen_key_configured": bool(QWEN_API_KEY),
        "base_url": QWEN_BASE_URL,
        "vision_model": QWEN_VISION_MODEL,
        "text_model": QWEN_TEXT_MODEL,
        "fast_model": QWEN_FAST_MODEL,
        "trust_env_proxy": QWEN_TRUST_ENV,
        "fast_mode": FAST_MODE,
    }


@app.post("/api/analyze")
async def analyze(
    image: UploadFile = File(...),
    question: str = Form(...),
    version: str = Form(...),
    history: str = Form("[]"),
    session_id: str = Form(""),
) -> dict[str, Any]:
    if not question.strip() or not version.strip():
        raise HTTPException(status_code=400, detail="问题和设备版本号不能为空")
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="请上传图片文件")
    image_bytes = await image.read()
    if len(image_bytes) > 12 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="图片不能超过 12MB")
    image_id = f"{uuid.uuid4().hex}_{Path(image.filename or 'image').name}"
    (UPLOAD_DIR / image_id).write_bytes(image_bytes)
    try:
        model_bytes, model_content_type = _compress_for_model(image_bytes, image.content_type)
        try:
            history_items = json.loads(history) if history else []
            if not isinstance(history_items, list):
                history_items = []
        except json.JSONDecodeError:
            history_items = []
        # Retrieve a small initial evidence set before the VLM call. This lets
        # fast mode ground its single response without a second model round.
        route = classify_question(question)
        context = _load_manual_context(version, question)
        evidence = _load_manual_evidence(version, question)
        if FAST_MODE:
            state, decision = await _qwen_fast_turn(model_bytes, model_content_type, question, version, context, history_items, route)
        else:
            state = await _qwen_vision(model_bytes, model_content_type, question, version)
            context = _load_manual_context(version, question + " " + json.dumps(state, ensure_ascii=False))
            evidence = _load_manual_evidence(version, question + " " + json.dumps(state, ensure_ascii=False))
            gate = _constraint_check(state)
            decision = await _qwen_plan(question, version, state, context, history_items, gate)
        gate = _constraint_check(state)
        if not FAST_MODE and gate["blocked"] and decision.get("status") == "GUIDANCE":
            decision.update({"status": "NEED_MORE_INFORMATION", "need_clarification": True, "questions": [gate["reason"]], "next_action": None, "reason": gate["reason"]})
        if FAST_MODE and gate["blocked"]:
            decision.update({"status": "NEED_MORE_INFORMATION", "need_clarification": True, "questions": [gate["reason"]], "next_action": None, "reason": gate["reason"], "evidence_sufficient": False})
        decision = _clean_identity_questions(decision)
        save_checkpoint(session_id, state, decision, route)
        guidance = decision.get("next_action") or "\n".join(decision.get("questions") or [decision.get("reason", "请补充更多信息。")])
        return {
            "request_id": image_id.split("_")[0], "state": state, "decision": decision,
            "guidance": guidance, "knowledge_context": context[:5000],
            "evidence": evidence,
            "route": route, "session_id": session_id,
            "mode": "demo" if DEMO_MODE or not QWEN_API_KEY else "qwen",
        }
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Qwen 服务响应超时，请检查模型名称、网络连接和账户额度后重试。") from exc
    except httpx.HTTPStatusError as exc:
        body = exc.response.text.strip().replace("\n", " ")[:600]
        raise HTTPException(status_code=502, detail=f"Qwen 接口返回 HTTP {exc.response.status_code}：{body or '未返回错误详情'}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"无法连接 Qwen 服务（{type(exc).__name__}）：{str(exc) or '请检查网络和接口地址'}") from exc
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail=f"模型返回格式无法解析：{exc}") from exc
