from __future__ import annotations

import re

from app.knowledge.vector import collection, embed_query


def search_course_overview(question: str, modules: tuple[str, ...] | list[str],
                           per_module: int = 2) -> list[dict]:
    """Retrieve balanced evidence for broad curriculum questions instead of global top-k only."""
    selected: list[dict] = []
    seen: set[tuple[int, int]] = set()

    def add(items: list[dict], limit: int, expected_module: str | None = None) -> None:
        added = 0
        for item in items:
            key = (item["document_id"], item["slide_number"])
            if key in seen or item.get("score", 0) < 0.38:
                continue
            if expected_module and item.get("module") != expected_module:
                continue
            seen.add(key)
            selected.append(item)
            added += 1
            if added >= limit:
                break

    for module in modules:
        query = f"{module} 课程模块 学习内容 知识体系 实训目标 主要知识点 {question}"
        add(search_course(query, module, per_module + 3), per_module, module)

    # General course-outline documents can provide an overview that the module decks omit.
    general = search_course(f"课程整体模块安排 课程体系 学习内容 {question}", None, 8)
    add([item for item in general if item.get("module") == "通用课程资料"], 2)
    return selected


def _bigrams(text: str) -> set[str]:
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", text.lower())
    return {normalized[i:i + 2] for i in range(max(0, len(normalized) - 1))}


def _technical_terms(text: str) -> set[str]:
    """Keep distinctive Latin model/protocol names from the student's query."""
    return {
        re.sub(r"[^a-z0-9]", "", term.lower())
        for term in re.findall(r"[A-Za-z][A-Za-z0-9_.+-]{2,}", text)
        if len(re.sub(r"[^a-z0-9]", "", term.lower())) >= 3
        and term.lower() not in {"the", "and", "for", "with", "how", "what"}
    }


def search_course(question: str, module: str | None = None, top_k: int = 5) -> list[dict]:
    vector_collection = collection()
    if vector_collection.count() == 0:
        return []
    # The local index already scores every chunk. Keep all scores so exact topic
    # matches are not lost when the embedding ranks an unrelated module first.
    candidate_count = vector_collection.count()
    kwargs = {"query_embeddings": [embed_query(question)], "n_results": candidate_count,
              "include": ["documents", "metadatas", "distances"]}
    if module:
        kwargs["where"] = {"module": module}
    result = vector_collection.query(**kwargs)
    query_grams = _bigrams(question)
    technical_terms = _technical_terms(question)
    ranked = []
    task_intent = any(word in question for word in ("任务", "作业", "实操", "要求", "布置", "完成什么", "怎么做"))
    for chunk_id, text, meta, distance in zip(
        result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]
    ):
        matched_terms = technical_terms & _technical_terms(text + " " + meta["filename"])
        if technical_terms and not matched_terms:
            continue
        grams = _bigrams(text)
        lexical = len(query_grams & grams) / max(1, len(query_grams))
        semantic = max(0.0, 1.0 - float(distance))
        score = min(1.0, 0.8 * semantic + 0.2 * lexical)
        if matched_terms:
            score = min(1.0, score + 0.12 + 0.04 * (len(matched_terms) - 1))
        if task_intent and meta.get("material_category") == "任务说明与实操脚本":
            score = min(1.0, score + 0.12)
        ranked.append({
            "chunk_id": chunk_id,
            "document_id": meta["document_id"],
            "filename": meta["filename"],
            "module": meta["module"],
            "slide_number": meta["slide_number"],
            "unit_label": meta.get("unit_label", "页"),
            "source_type": meta.get("source_type", "pptx"),
            "material_category": meta.get("material_category", "课程资料"),
            "lesson_label": re.sub(r"\s+", "", meta["lesson_label"])
            if meta.get("lesson_label") else None,
            "source_path": meta.get("source_path"),
            "version": meta.get("version"),
            "excerpt": text[:550],
            "score": round(score, 4),
            "download_url": f"/api/materials/{meta['document_id']}/download",
        })
    ranked.sort(key=lambda item: item["score"], reverse=True)
    distinct = []
    seen = set()
    for item in ranked:
        key = (item["document_id"], item["slide_number"])
        if key not in seen:
            seen.add(key)
            distinct.append(item)
    return distinct[:top_k]
