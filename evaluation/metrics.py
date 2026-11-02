"""Compute reproducible retrieval and execution metrics; keep semantic review explicit."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluation.runner import (LEDGER_FILE, PRIVATE, ROOT, SNAPSHOT_FILE,
                               job_key, ledger_state, load_json, read_events)

REVIEW_FILE = PRIVATE / "review.csv"
SUMMARY_FILE = ROOT / "evaluation" / "results" / "summary.json"
MANIFEST_FILE = ROOT / "evaluation" / "cases-manifest.json"
FIELDS = ["job", "case_id", "arm", "key_points_total", "key_points_met",
          "factual_error", "source_support", "uncertainty_correct", "review_note"]


def retrieval_scores(cases: list[dict]) -> dict:
    text = [case for case in cases if case["kind"] == "text"]
    page_hits = []
    document_hits = []
    for case in text:
        expected = {(item["filename"], item["slide_number"]) for item in case["gold"]}
        retrieved = {(item["filename"], item["slide_number"]) for item in case["retrieved"][:5]}
        page_hits.append(bool(expected & retrieved))
        document_hits.append(bool({name for name, _ in expected} & {name for name, _ in retrieved}))
    return {"cases": len(text), "recall_at_5": round(sum(page_hits) / len(text), 4) if text else None,
            "source_document_hit_rate": round(sum(document_hits) / len(text), 4) if text else None,
            "page_hit_cases": [case["id"] for case, hit in zip(text, page_hits) if hit],
            "page_miss_cases": [case["id"] for case, hit in zip(text, page_hits) if not hit]}


def valid_citations(answer: str, evidence_count: int) -> bool:
    citations = [int(value) for value in re.findall(r"\[(\d+)\]", answer)]
    return bool(citations) and all(1 <= number <= evidence_count for number in citations)


def export_review_template(cases: list[dict], finishes: dict[str, dict]) -> None:
    by_id = {case["id"]: case for case in cases}
    previous = {}
    if REVIEW_FILE.exists():
        with REVIEW_FILE.open(encoding="utf-8-sig", newline="") as file:
            previous = {row["job"]: row for row in csv.DictReader(file)}
    rows = []
    for job, result in finishes.items():
        if result.get("status") != "ok":
            continue
        case_id, arm, step = job.split(":", 2)
        if arm == "multi" and step != "synthesis":
            continue
        case = by_id[case_id]
        row = {"job": job, "case_id": case_id, "arm": arm,
               "key_points_total": len(case["expected_points"]), "key_points_met": "",
               "factual_error": "", "source_support": "NA" if arm in {"single_no_rag", "code"} else "",
               "uncertainty_correct": "", "review_note": ""}
        row.update(previous.get(job, {}))
        rows.append(row)
    REVIEW_FILE.parent.mkdir(parents=True, exist_ok=True)
    with REVIEW_FILE.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def review_scores() -> dict:
    if not REVIEW_FILE.exists():
        return {"reviewed": 0, "complete": False}
    with REVIEW_FILE.open(encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    reviewed = [row for row in rows if all(row[field] != "" for field in
                ("key_points_met", "factual_error", "source_support", "uncertainty_correct"))]
    for row in reviewed:
        if (not 0 <= int(row["key_points_met"]) <= int(row["key_points_total"])
                or row["factual_error"] not in {"0", "1"}
                or row["source_support"] not in {"0", "1", "NA"}
                or row["uncertainty_correct"] not in {"0", "1"}):
            raise ValueError(f"人工复核值无效：{row['job']}")
    grouped = defaultdict(list)
    for row in reviewed:
        grouped[row["arm"]].append(row)
    by_arm = {}
    for arm, values in grouped.items():
        by_arm[arm] = {
            "reviewed": len(values),
            "key_point_coverage": round(sum(int(row["key_points_met"]) for row in values) /
                                        sum(int(row["key_points_total"]) for row in values), 4),
            "factual_error_rate": round(sum(row["factual_error"] == "1" for row in values) / len(values), 4),
            "source_support_rate": round(sum(row["source_support"] == "1" for row in values) /
                                         sum(row["source_support"] != "NA" for row in values), 4)
                                   if any(row["source_support"] != "NA" for row in values) else None,
            "uncertainty_correct_rate": round(sum(row["uncertainty_correct"] == "1" for row in values) / len(values), 4),
        }
    composite_ids = {row["case_id"] for row in reviewed if row["arm"] == "multi"}
    matched = {}
    for arm in ("single_rag", "single_no_rag", "multi"):
        values = [row for row in reviewed if row["arm"] == arm and row["case_id"] in composite_ids]
        if values:
            matched[arm] = {
                "cases": len(values),
                "key_point_coverage": round(sum(int(row["key_points_met"]) for row in values) /
                                            sum(int(row["key_points_total"]) for row in values), 4),
                "factual_error_rate": round(sum(row["factual_error"] == "1" for row in values) / len(values), 4),
            }
    return {"reviewed": len(reviewed), "total_review_rows": len(rows),
            "complete": len(reviewed) == len(rows), "by_arm": by_arm,
            "matched_composite": matched}


def summarize(snapshot: dict, events: list[dict]) -> dict:
    used, finishes = ledger_state(events)
    by_arm = defaultdict(list)
    cases = {case["id"]: case for case in snapshot["cases"]}
    for job, result in finishes.items():
        case_id, arm, step = job.split(":", 2)
        if arm == "multi":
            continue
        by_arm[arm].append((cases[case_id], result))
    for case in snapshot["cases"]:
        if case["kind"] != "text" or case["type"] != "composite":
            continue
        stages = [finishes.get(job_key(case["id"], "multi", step))
                  for step in ("course", "guide", "synthesis")]
        if not any(stages):
            continue
        synthesis = stages[-1]
        combined = {
            "status": "ok" if synthesis and all(stage and stage["status"] == "ok" for stage in stages) else "error",
            "duration_seconds": sum(stage.get("duration_seconds", 0) for stage in stages if stage),
            "prompt_tokens": sum(stage.get("prompt_tokens") or 0 for stage in stages if stage),
            "completion_tokens": sum(stage.get("completion_tokens") or 0 for stage in stages if stage),
            "answer": synthesis.get("answer", "") if synthesis else "",
        }
        by_arm["multi"].append((case, combined))
    arm_summary = {}
    for arm, items in by_arm.items():
        success = [result for _, result in items if result.get("status") == "ok"]
        cite_items = [(case, result) for case, result in items if result.get("status") == "ok"
                      and arm in {"single_rag", "multi"}]
        arm_summary[arm] = {
            "attempts": len(items), "successes": len(success),
            "mean_latency_seconds": round(sum(result["duration_seconds"] for _, result in items) / len(items), 2),
            "prompt_tokens": sum(item.get("prompt_tokens") or 0 for item in success),
            "completion_tokens": sum(item.get("completion_tokens") or 0 for item in success),
            "valid_citation_rate": round(sum(valid_citations(result["answer"], len(case.get("retrieved", [])))
                                               for case, result in cite_items) / len(cite_items), 4)
                                   if cite_items else None,
        }
    return {"snapshot_sha256": snapshot["snapshot_sha256"], "model": snapshot["model"],
            "cases": len(snapshot["cases"]), "calls_used": used, "call_cap": 120,
            "finished_calls": len(finishes), "retrieval": retrieval_scores(snapshot["cases"]),
            "arms": arm_summary, "manual_review": review_scores(),
            "limitations": ["引用编号有效不代表语义支持，source_support 仅以人工复核计。",
                            "课程资料与模型逐条输出保存在本机，公开汇总不含原文。"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-review", action="store_true")
    args = parser.parse_args()
    snapshot = load_json(SNAPSHOT_FILE)
    events = read_events(LEDGER_FILE)
    _, finishes = ledger_state(events)
    if args.export_review:
        export_review_template(snapshot["cases"], finishes)
    manifest = {"snapshot_sha256": snapshot["snapshot_sha256"], "cases": [
        {"id": case["id"], "kind": case["kind"], "type": case["type"], "module": case["module"]}
        for case in snapshot["cases"]]}
    MANIFEST_FILE.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = summarize(snapshot, events)
    SUMMARY_FILE.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_FILE.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"calls_used": summary["calls_used"], "review": summary["manual_review"],
                      "retrieval": summary["retrieval"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
