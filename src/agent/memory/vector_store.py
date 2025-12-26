# memory_vector_store.py
from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI


@dataclass
class MemoryItem:
    id: str
    text: str
    embedding: List[float]
    meta: Dict[str, Any]


def cosine_similarity(a: List[float], b: List[float]) -> float:
    # Robust cosine similarity
    # https://www.youtube.com/watch?v=e9U0QAFbfLI
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


class LocalVectorStore:
    """
    Minimal local vector store using a JSON file.
    Stores: [{id, text, embedding, meta}, ...]
    """

    def __init__(
        self,
        path: str | Path = "data/memory_vectors.json",
        embedding_model: str = "text-embedding-3-small",
        api_key_env: str = "OPENAI_API_KEY",
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.embedding_model = embedding_model
        self.api_key_env = api_key_env

        # Load existing items
        self.items: List[MemoryItem] = []
        if self.path.exists():
            raw = json.loads(self.path.read_text(encoding="utf-8") or "[]")
            for obj in raw:
                self.items.append(
                    MemoryItem(
                        id=obj["id"],
                        text=obj["text"],
                        embedding=obj["embedding"],
                        meta=obj.get("meta", {}),
                    )
                )

    def _save(self) -> None:
        data = [asdict(item) for item in self.items]
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def embed(self, text: str) -> List[float]:
        api_key = __import__("os").getenv(self.api_key_env)
        if not api_key:
            raise RuntimeError(f"{self.api_key_env} environment variable is not set.")

        client = OpenAI(api_key=api_key)
        resp = client.embeddings.create(model=self.embedding_model, input=text)
        vec = resp.data[0].embedding
        return list(vec)

    def add(self, text: str, meta: Optional[Dict[str, Any]] = None, item_id: Optional[str] = None) -> str:
        meta = meta or {}
        if not item_id:
            # stable-ish id: len + hash of text prefix
            item_id = f"mem_{len(self.items) + 1}"
        emb = self.embed(text)
        self.items.append(MemoryItem(id=item_id, text=text, embedding=emb, meta=meta))
        self._save()
        return item_id

    def search(self, query: str, top_k: int = 5) -> List[Tuple[float, MemoryItem]]:
        if not self.items:
            return []
        q_emb = self.embed(query)
        scored: List[Tuple[float, MemoryItem]] = []
        for item in self.items:
            score = cosine_similarity(q_emb, item.embedding)
            scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_k]
