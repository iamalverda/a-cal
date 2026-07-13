"""Local storage for self-model facts.

The store is local-first by design. In the full atom deployment, this wraps
atom's LanceDB episodic memory for vector search; in the open-source / stub
mode, it falls back to a JSON file store. Either way, the API is the same.

The store never raises on read failures — it returns empty results so the
self-model degrades gracefully when storage is unavailable.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from datetime import datetime, timezone, UTC
from typing import Any, Dict, List, Optional

from a_cal.self_model.types import SelfModelFact

logger = logging.getLogger(__name__)


class SelfModelStore:
    """Persistence layer for self-model facts.

    Two backends:
      1. JSON file (default, no deps) — facts stored in a single JSON file
         per user, loaded into memory.
      2. LanceDB (when atom's full LanceDBService is available) — vector
         search for semantic recall. Detected lazily.

    The JSON backend is intentionally simple: it's the source of truth for
    self-hosted users who don't need vector search. LanceDB adds semantic
    recall on top but never replaces it.
    """

    def __init__(self, user_id: str, data_dir: str | None = None) -> None:
        self.user_id = user_id
        self._data_dir = Path(data_dir or os.path.expanduser("~/.a-cal/self_model"))
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._file_path = self._data_dir / f"{user_id}_facts.json"
        self._facts: dict[str, SelfModelFact] = {}
        self._lancedb = None  # lazy — only if available and configured
        self._load()

    def _load(self) -> None:
        """Load facts from the JSON store. Never raises."""
        try:
            if self._file_path.exists():
                raw = self._file_path.read_text(encoding="utf-8")
                data = json.loads(raw)
                self._facts = {
                    fid: SelfModelFact.from_dict(fdata)
                    for fid, fdata in data.items()
                }
        except Exception as exc:
            logger.warning("self-model store load failed for %s: %s", self.user_id, exc)
            self._facts = {}

    def _save(self) -> None:
        """Persist facts to JSON. Never raises."""
        try:
            data = {fid: f.to_dict() for fid, f in self._facts.items()}
            self._file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("self-model store save failed for %s: %s", self.user_id, exc)

    def upsert(self, fact: SelfModelFact) -> SelfModelFact:
        """Insert or update a fact.

        If a fact with the same content hash already exists and is active,
        bump its confidence (EWMA) rather than creating a duplicate. If the
        new fact has higher confidence by >0.1, supersede the old one.
        """
        existing = self._find_by_hash(fact.content_hash())
        if existing and existing.is_active():
            if fact.confidence > existing.confidence + 0.1:
                existing.status = "superseded"
                existing.superseded_by = fact.id
                self._facts[fact.id] = fact
            else:
                # EWMA confidence bump
                alpha = 0.3
                existing.confidence = (1 - alpha) * existing.confidence + alpha * max(
                    fact.confidence, existing.confidence
                )
                existing.updated_at = fact.created_at
                # Merge source event ids
                for eid in fact.source_event_ids:
                    if eid not in existing.source_event_ids:
                        existing.source_event_ids.append(eid)
                fact = existing
        else:
            self._facts[fact.id] = fact
        self._save()
        return fact

    def get(self, fact_id: str) -> SelfModelFact | None:
        return self._facts.get(fact_id)

    def delete(self, fact_id: str) -> bool:
        """Soft-delete a fact (user-initiated)."""
        fact = self._facts.get(fact_id)
        if fact:
            fact.status = "deleted"
            self._save()
            return True
        return False

    def update(self, fact_id: str, content: str) -> SelfModelFact | None:
        """User-corrected edit of a fact's content.

        Sets confidence to 1.0 (user override) and marks provenance as
        user-corrected. Returns the updated fact, or None if not found.
        """
        fact = self._facts.get(fact_id)
        if not fact:
            return None
        fact.content = content
        fact.confidence = 1.0
        fact.provenance = f"user-corrected:{fact.provenance}"
        fact.updated_at = datetime.now(UTC).isoformat()
        self._save()
        return fact

    def all_active(self) -> list[SelfModelFact]:
        """All active facts, sorted by confidence descending."""
        return sorted(
            [f for f in self._facts.values() if f.is_active()],
            key=lambda f: f.confidence,
            reverse=True,
        )

    def by_category(self, category: str) -> list[SelfModelFact]:
        """Active facts in a specific category."""
        return [f for f in self.all_active() if f.category == category]

    def search(self, query: str, limit: int = 10) -> list[SelfModelFact]:
        """Simple keyword search over fact content.

        In the full LanceDB deployment this becomes semantic vector search.
        Here it's a case-insensitive substring match — adequate for self-hosted.
        """
        q = query.lower()
        scored: list[tuple[float, SelfModelFact]] = []
        for fact in self.all_active():
            content = fact.content.lower()
            if q in content:
                score = fact.confidence
                # Boost if query matches category name
                if q in fact.category.lower():
                    score += 0.1
                scored.append((score, fact))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [f for _, f in scored[:limit]]

    def clear_all(self) -> int:
        """Delete all facts for this user. Returns the count removed."""
        count = len([f for f in self._facts.values() if f.is_active()])
        for f in self._facts.values():
            f.status = "deleted"
        self._save()
        return count

    def _find_by_hash(self, content_hash: str) -> SelfModelFact | None:
        """Find an active fact by its content hash."""
        for fact in self._facts.values():
            if fact.is_active() and fact.content_hash() == content_hash:
                return fact
        return None

    def export(self) -> dict[str, Any]:
        """Export all facts as a dict (for the transparency view in settings)."""
        return {
            "user_id": self.user_id,
            "fact_count": len([f for f in self._facts.values() if f.is_active()]),
            "facts": [f.to_dict() for f in self.all_active()],
        }
