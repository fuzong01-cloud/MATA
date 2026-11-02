"""Run frozen course cases with an append-only, call-limited model ledger."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.agents.llm import (CODE_SYSTEM_PROMPT, EXPERIMENT_PROMPT,
                            GENERAL_SYSTEM_PROMPT, SYNTHESIS_PROMPT, SYSTEM_PROMPT,
                            guard_unverified_claims)
from app.core.config import settings
from app.database.models import Document, Slide, SlideVisual
from app.database.session import SessionLocal
from app.knowledge.search import search_course
from app.knowledge.vector import collection
from sqlalchemy import select

PRIVATE = ROOT / "evaluation" / "private"
RAW = ROOT / "evaluation" / "results" / "raw"
CASE_FILE = PRIVATE / "cases.json"
SNAPSHOT_FILE = PRIVATE / "snapshot.json"
LEDGER_FILE = RAW / "ledger.jsonl"
MAX_CALLS = 120
ARMS = ("single_rag", "single_no_rag", "multi")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def append_event(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def read_events(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def ledger_state(events: list[dict]) -> tuple[int, dict[str, dict]]:
    starts: dict[str, dict] = {}
    finishes: dict[str, dict] = {}
    for event in events:
        if event["event"] == "start":
            if event["job"] in starts:
                raise ValueError(f"重复的请求登记：{event['job']}")
            starts[event["job"]] = event
        elif event["event"] == "finish":
            if event["job"] not in starts or event["job"] in finishes:
                raise ValueError(f"请求结果无对应唯一登记：{event['job']}")
            finishes[event["job"]] = event
    # A pending request counts against the cap: a crash may happen after the API accepted it.
    return len(starts), finishes


def jobs_for(cases: list[dict]) -> list[tuple[str, str, str]]:
    jobs = []
    for case in cases:
        if case["kind"] == "text":
            jobs.extend((case["id"], arm, "answer") for arm in ARMS[:2])
            if case["type"] == "composite":
                jobs.extend((case["id"], "multi", step) for step in ("course", "guide", "synthesis"))
        else:
            jobs.append((case["id"], case["kind"], "answer"))
    return jobs


def job_key(case_id: str, arm: str, step: str) -> str:
    return f"{case_id}:{arm}:{step}"


def source_text(evidence: list[dict]) -> str:
    return "\n\n".join(
        f"[{index}] {item['filename']} 第 {item['slide_number']} 页，{item['module']}\n{item['excerpt']}"
        for index, item in enumerate(evidence, 1)
    )


def prompt_for(case: dict, arm: str, step: str, finishes: dict[str, dict]) -> list[dict]:
    question = case["question"]
    evidence = case.get("retrieved", [])
    if arm == "single_no_rag":
        return [{"role": "system", "content": GENERAL_SYSTEM_PROMPT},
                {"role": "user", "content": f"课程问题：{question}\n本轮不提供课程资料。请直接回答，并说明无法核实的课程专属细节。"}]
    if arm == "multi" and step == "synthesis":
        course = finishes[job_key(case["id"], "multi", "course")]["answer"]
        guide = finishes[job_key(case["id"], "multi", "guide")]["answer"]
        body = f"问题：{question}\n\n课程依据：\n{source_text(evidence)}\n\n课程问答草稿：\n{course}\n\n实验指导草稿：\n{guide}"
        return [{"role": "system", "content": SYNTHESIS_PROMPT}, {"role": "user", "content": body}]
    if arm in {"single_rag", "multi"}:
        role = "course" if step == "course" or (arm == "single_rag" and case["type"] == "knowledge") else "guide"
        system = SYSTEM_PROMPT if role == "course" else EXPERIMENT_PROMPT
        body = f"课程问题：{question}\n\n本轮课程依据：\n{source_text(evidence)}"
        return [{"role": "system", "content": system}, {"role": "user", "content": body}]
    if arm == "visual":
        image = (ROOT / case["image_path"]).resolve()
        if not image.is_relative_to(settings.slide_visual_path.resolve()):
            raise ValueError("图片路径超出课程图像目录")
        data = "data:image/png;base64," + base64.b64encode(image.read_bytes()).decode("ascii")
        return [{"role": "system", "content": EXPERIMENT_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": f"课程问题：{question}\n课程依据：\n{source_text(evidence)}\n请只描述图上可辨认的信息。"},
                    {"type": "image_url", "image_url": {"url": data}},
                ]}]
    if arm == "code":
        return [{"role": "system", "content": CODE_SYSTEM_PROMPT},
                {"role": "user", "content": f"课程场景：{case['module']}\n问题：{question}\n待分析代码：\n{case['code']}"}]
    raise ValueError(f"未知实验组：{arm}")


def freeze_cases(cases: list[dict], destination: Path = SNAPSHOT_FILE) -> dict:
    if destination.exists():
        raise FileExistsError(f"资料快照已存在：{destination}")
    with SessionLocal() as db:
        frozen = []
        for case in cases:
            item = dict(case)
            gold = []
            for ref in case["gold_sources"]:
                document = db.scalar(select(Document).where(Document.filename == ref["filename"],
                                                              Document.module == case["module"]))
                if not document:
                    raise ValueError(f"缺少资料：{ref['filename']}")
                slide = db.scalar(select(Slide).where(Slide.document_id == document.id,
                                                       Slide.slide_number == ref["slide_number"]))
                if not slide:
                    raise ValueError(f"缺少资料页：{ref}")
                gold.append({"filename": document.filename, "module": document.module,
                             "slide_number": slide.slide_number, "source_hash": document.zip_sha256,
                             "text_hash": sha256(slide.text.encode("utf-8")), "reference_text": slide.text[:2500]})
                if case["kind"] == "visual":
                    visual = db.scalar(select(SlideVisual).where(SlideVisual.slide_id == slide.id))
                    if not visual:
                        raise ValueError(f"缺少图像索引：{ref}")
                    item["image_path"] = visual.image_path
                    item["image_hash"] = sha256((ROOT / visual.image_path).read_bytes())
            item["gold"] = gold
            item["retrieved"] = search_course(case["question"], case["module"], 5) if case["kind"] != "code" else []
            frozen.append(item)
    snapshot = {"format": 1, "model": settings.model_name, "index_count": collection().count(),
                "cases": frozen}
    snapshot["snapshot_sha256"] = sha256(canonical(snapshot))
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot


def _run_unlocked(snapshot: dict, ledger: Path, cap: int,
                  client_factory, max_new_calls: int | None) -> dict:
    if not settings.model_api_key and client_factory is None:
        raise ValueError("模型密钥未配置")
    if snapshot["model"] != settings.model_name:
        raise ValueError("快照模型与当前配置不一致")
    cases = snapshot["cases"]
    events = read_events(ledger)
    used, finishes = ledger_state(events)
    started = {item["job"] for item in events if item["event"] == "start"}
    if used > cap:
        raise ValueError("已有调用数超过上限")
    from openai import OpenAI
    factory = client_factory or (lambda: OpenAI(api_key=settings.model_api_key,
                                                base_url=settings.model_base_url,
                                                timeout=90.0, max_retries=0))
    if any(item["snapshot_sha256"] != snapshot["snapshot_sha256"]
           for item in events if item["event"] == "start"):
        raise ValueError("账本与资料快照不一致")
    new_calls = 0
    for case_id, arm, step in jobs_for(cases):
        key = job_key(case_id, arm, step)
        if key in started:
            continue
        if arm == "multi" and step == "synthesis" and any(
            finishes.get(job_key(case_id, "multi", prerequisite), {}).get("status") != "ok"
            for prerequisite in ("course", "guide")
        ):
            continue
        if used >= cap or (max_new_calls is not None and new_calls >= max_new_calls):
            break
        case = next(item for item in cases if item["id"] == case_id)
        messages = prompt_for(case, arm, step, finishes)
        request_hash = sha256(canonical(messages))
        started_at = time.time()
        append_event(ledger, {"event": "start", "job": key, "snapshot_sha256": snapshot["snapshot_sha256"],
                              "request_hash": request_hash, "at": started_at})
        started.add(key)
        used += 1
        new_calls += 1
        try:
            client = factory()
            try:
                response = client.chat.completions.create(
                    model=snapshot["model"], messages=messages, max_tokens=1700,
                    extra_body={**settings.thinking_options, "thinking_budget": 900},
                )
            finally:
                client.close()
            answer = guard_unverified_claims(
                (response.choices[0].message.content or "").strip(),
                case["question"], code=case.get("code", "") if arm == "code" else "")
            if not answer:
                raise ValueError("模型未返回正文")
            usage = getattr(response, "usage", None)
            event = {"event": "finish", "job": key, "status": "ok", "answer": answer,
                     "duration_seconds": round(time.time() - started_at, 3),
                     "prompt_tokens": getattr(usage, "prompt_tokens", None),
                     "completion_tokens": getattr(usage, "completion_tokens", None)}
        except Exception as exc:
            event = {"event": "finish", "job": key, "status": "error", "error": type(exc).__name__,
                     "duration_seconds": round(time.time() - started_at, 3)}
        append_event(ledger, event)
        finishes[key] = event
    return {"calls_used": used, "calls_remaining": cap - used, "completed": len(finishes),
            "pending": used - len(finishes), "planned": len(jobs_for(cases))}


def run(snapshot: dict, ledger: Path = LEDGER_FILE, cap: int = MAX_CALLS,
        client_factory=None, max_new_calls: int | None = None) -> dict:
    lock = ledger.with_suffix(ledger.suffix + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError(f"已有实验运行器占用账本：{lock}") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(str(os.getpid()))
        return _run_unlocked(snapshot, ledger, cap, client_factory, max_new_calls)
    finally:
        lock.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["freeze", "run", "status"])
    parser.add_argument("--max-new-calls", type=int)
    args = parser.parse_args()
    if args.action == "freeze":
        cases = load_json(CASE_FILE)
        snapshot = freeze_cases(cases)
        print(json.dumps({"snapshot_sha256": snapshot["snapshot_sha256"],
                          "cases": len(snapshot["cases"]), "jobs": len(jobs_for(snapshot["cases"]))}))
    elif args.action == "run":
        print(json.dumps(run(load_json(SNAPSHOT_FILE), max_new_calls=args.max_new_calls), ensure_ascii=False))
    else:
        used, finishes = ledger_state(read_events(LEDGER_FILE))
        print(json.dumps({"calls_used": used, "calls_remaining": MAX_CALLS - used,
                          "finished": len(finishes), "pending": used - len(finishes)}))


if __name__ == "__main__":
    main()
