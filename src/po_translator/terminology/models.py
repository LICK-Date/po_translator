"""Data models for terminology candidates and project glossary."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import ClassVar


class TermOrigin(str, Enum):
    """Origin of a glossary entry."""
    ALGORITHM = "algorithm"
    LLM = "llm"
    USER = "user"
    IMPORT = "import"


@dataclass
class TermCandidate:
    """Algorithmically extracted term candidate prior to LLM verification."""
    text: str
    frequency: int
    length: int
    examples: list[str] = field(default_factory=list)
    score: float = 0.0


@dataclass
class GlossaryTerm:
    """A project glossary term."""
    id: str
    source: str
    target: str | None = None
    category: str | None = None
    description: str | None = None
    locked: bool = False
    frequency: int = 1
    created_by: TermOrigin = TermOrigin.ALGORITHM

    @staticmethod
    def generate_id(source: str) -> str:
        """Deterministic ID based on trimmed source string."""
        return hashlib.sha256(source.strip().lower().encode("utf-8")).hexdigest()[:12]


class Glossary:
    """Project glossary container enforcing priority and lock protections."""

    PRIORITY_MAP: ClassVar[dict[TermOrigin, int]] = {
        TermOrigin.USER: 40,
        TermOrigin.IMPORT: 30,
        TermOrigin.LLM: 20,
        TermOrigin.ALGORITHM: 10,
    }

    def __init__(self, terms: list[GlossaryTerm] | None = None) -> None:
        self._terms_by_source: dict[str, GlossaryTerm] = {}
        if terms:
            for term in terms:
                self.add_term(term)

    def __len__(self) -> int:
        return len(self._terms_by_source)

    def get(self, source: str) -> GlossaryTerm | None:
        return self._terms_by_source.get(source.strip())

    def get_by_id(self, term_id: str) -> GlossaryTerm | None:
        for t in self._terms_by_source.values():
            if t.id == term_id:
                return t
        return None

    def all_terms(self) -> list[GlossaryTerm]:
        return list(self._terms_by_source.values())

    def add_term(self, term: GlossaryTerm, overwrite_locked: bool = False) -> bool:
        """Add or update term respecting lock status and priority hierarchy.

        Hierarchy: User locked > Imported > Reviewed LLM > Automatic candidate.
        Returns True if term was added or updated, False if blocked by lock or lower priority.
        """
        key = term.source.strip()
        existing = self._terms_by_source.get(key)

        if existing is None:
            self._terms_by_source[key] = term
            return True

        # Rule: Locked terms cannot be automatically overwritten unless explicitly requested
        if existing.locked and not overwrite_locked:
            return False

        # Compare origin priority
        existing_prio = self.PRIORITY_MAP.get(existing.created_by, 0)
        new_prio = self.PRIORITY_MAP.get(term.created_by, 0)

        if new_prio >= existing_prio or overwrite_locked:
            # Preserve target if new one is None
            target = term.target if term.target is not None else existing.target
            category = term.category or existing.category
            description = term.description or existing.description
            locked = term.locked or existing.locked

            self._terms_by_source[key] = GlossaryTerm(
                id=existing.id,
                source=existing.source,
                target=target,
                category=category,
                description=description,
                locked=locked,
                frequency=max(existing.frequency, term.frequency),
                created_by=term.created_by if new_prio >= existing_prio else existing.created_by,
            )
            return True

        return False

    def remove_term(self, source: str) -> bool:
        key = source.strip()
        if key in self._terms_by_source:
            del self._terms_by_source[key]
            return True
        return False
