# memory_vector_store.py
from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import error as url_error
from urllib import request as url_request

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
        self._embed_cache: Dict[str, List[float]] = {}

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
        provider = os.getenv("EMBEDDINGS_PROVIDER", "openai").lower()
        cache_key = hashlib.sha256(text.encode("utf-8")).hexdigest()
        cached = self._embed_cache.get(cache_key)
        if cached is not None:
            return list(cached)

        if provider == "none":
            vector = [0.0] * 768
            self._embed_cache[cache_key] = vector
            return list(vector)

        if provider == "ollama":
            base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
            embed_model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
            payload = {"model": embed_model, "prompt": text}
            url = f"{base_url}/api/embeddings"
            req = url_request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with url_request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except url_error.HTTPError as exc:  # pragma: no cover - network/API path
                detail = exc.read().decode("utf-8") if exc.fp else str(exc)
                raise RuntimeError(f"Ollama embeddings failed ({exc.code}): {detail}") from exc
            except url_error.URLError as exc:  # pragma: no cover - network/API path
                raise RuntimeError(
                    f"Ollama server unreachable at {base_url}. Is it running? ({exc.reason})"
                ) from exc
            except Exception as exc:  # pragma: no cover - network/API path
                raise RuntimeError(f"Failed to call Ollama embeddings: {exc}") from exc

            if not data:
                raise RuntimeError("Ollama embeddings returned an empty response.")
            if isinstance(data, dict) and data.get("error"):
                raise RuntimeError(f"Ollama embeddings error: {data['error']}")

            vector = data.get("embedding") if isinstance(data, dict) else None
            if not vector:
                raise RuntimeError("Ollama embeddings returned empty embedding.")
            vector = list(vector)
        else:
            if provider != "openai":
                raise RuntimeError(
                    f"Unsupported EMBEDDINGS_PROVIDER '{provider}'. Use openai, ollama, or none."
                )
            api_key = os.getenv(self.api_key_env)
            if not api_key:
                raise RuntimeError(f"{self.api_key_env} environment variable is not set.")

            client = OpenAI(api_key=api_key)
            resp = client.embeddings.create(model=self.embedding_model, input=text)
            vector = list(resp.data[0].embedding)

        if len(self._embed_cache) >= 200:
            self._embed_cache.pop(next(iter(self._embed_cache)))
        self._embed_cache[cache_key] = vector
        return list(vector)

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
        if os.getenv("EMBEDDINGS_PROVIDER", "openai").lower() == "none":
            return []
        q_emb = self.embed(query)
        scored: List[Tuple[float, MemoryItem]] = []
        for item in self.items:
            score = cosine_similarity(q_emb, item.embedding)
            scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_k]
