from __future__ import annotations

import re

from app.knowledge.vector import collection, embed_query


def _bigrams(text: str) -> set[str]:
    normalized = re.sub(r"[^\w\u4e00-\u9fff]+", "", text.lower())
    return {normalized[i:i + 2] for i in range(max(0, len(normalized) - 1))}


def search_course(question: str, module: str | None = None, top_k: int = 5) -> list[dict]:
    vector_collection = collection()
    if vector_collection.count() == 0:
        return []
    candidate_count = min(vector_collection.count(), max(20, top_k * 6))
    kwargs = {"query_embeddings": [embed_query(question)], "n_results": candidate_count,
              "include": ["documents", "metadatas", "distances"]}
    if module:
        kwargs["where"] = {"module": module}
    result = vector_collection.query(**kwargs)
    query_grams = _bigrams(question)
    ranked = []
    task_intent = any(word in question for word in ("任务", "作业", "实操", "要求", "布置", "完成什么", "怎么做"))
    for chunk_id, text, meta, distance in zip(
        result["ids"][0], result["documents"][0], result["metadatas"][0], result["distances"][0]
    ):
        grams = _bigrams(text)
        lexical = len(query_grams & grams) / max(1, len(query_grams))
        semantic = max(0.0, 1.0 - float(distance))
        score = min(1.0, 0.8 * semantic + 0.2 * lexical)
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
