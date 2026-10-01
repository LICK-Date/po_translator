"""Efficient terminology matcher for scanning batch text against glossary."""

from __future__ import annotations

import re
from collections.abc import Sequence

from po_translator.terminology.models import Glossary, GlossaryTerm

RE_CJK = re.compile(r"[\u4e00-\u9fa5\u3040-\u30ff]")


class GlossaryMatcher:
    """Detects terms appearing within input text and returns matching glossary records."""

    @classmethod
    def match_text(
        cls,
        text: str,
        glossary: Glossary | Sequence[GlossaryTerm],
    ) -> list[GlossaryTerm]:
        """Find all glossary terms present in text.

        Uses case-insensitive word-boundary matching for Latin terms,
        and substring matching for CJK terms. Sorted by term length descending.
        """
        if not text:
            return []

        all_terms = glossary.all_terms() if isinstance(glossary, Glossary) else list(glossary)
        if not all_terms:
            return []

        # Sort terms from longest to shortest to ensure maximal phrasing matches first
        sorted_terms = sorted(all_terms, key=lambda t: len(t.source), reverse=True)

        matched: list[GlossaryTerm] = []

        for term in sorted_terms:
            src = term.source.strip()
            if not src:
                continue

            # Check for CJK character
            if RE_CJK.search(src):
                # Substring check for CJK
                if src in text:
                    matched.append(term)
            else:
                # Word boundary check for Latin / English terms
                pat = r"\b" + re.escape(src) + r"\b"
                if re.search(pat, text, re.IGNORECASE):
                    matched.append(term)

        return matched

    @classmethod
    def match_batch(
        cls,
        texts: Sequence[str],
        glossary: Glossary | Sequence[GlossaryTerm],
    ) -> list[GlossaryTerm]:
        """Find unique glossary terms appearing across multiple batch strings."""
        combined_text = "\n".join(texts)
        return cls.match_text(combined_text, glossary)
