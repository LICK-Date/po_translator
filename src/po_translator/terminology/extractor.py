"""Algorithmic candidate term extraction with noise reduction and frequency scoring."""

from __future__ import annotations

import collections
import re
from collections.abc import Sequence

from po_translator.domain.models import TranslationEntry
from po_translator.po.placeholder import extract_placeholders
from po_translator.terminology.models import TermCandidate

# Common Chinese stop words and particles that shouldn't stand as terms
CHINESE_STOP_WORDS = {
    "一个", "这是", "那是", "这个", "那个", "可以", "如果", "但是", "因为", "所以",
    "以及", "而且", "根据", "通过", "进行", "对于", "关于", "包括", "可能", "应该",
    "点击", "继续", "完成", "取消", "确定", "成功", "失败", "请稍", "之后", "之前",
}

# Common English stop words
ENGLISH_STOP_WORDS = {
    "the", "and", "for", "with", "this", "that", "from", "into", "your",
    "have", "more", "will", "been", "they", "were", "then", "them", "some",
    "what", "when", "where", "which", "there", "their", "about", "other",
}

RE_CHINESE_CHAR = re.compile(r"[\u4e00-\u9fa5]")
RE_JAPANESE_CHAR = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]")
RE_ENGLISH_TITLE = re.compile(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b")


class TermExtractor:
    """Extracts candidate terms algorithmically using frequency, length, and noise filtering."""

    def __init__(
        self,
        min_freq: int = 2,
        min_length: int = 2,
        max_length: int = 12,
        max_candidates: int = 200,
    ) -> None:
        self.min_freq = min_freq
        self.min_length = min_length
        self.max_length = max_length
        self.max_candidates = max_candidates

    def clean_text(self, text: str) -> str:
        """Strip all placeholders, tags, and formatting characters from text."""
        # 1. Strip placeholders
        phs = extract_placeholders(text)
        cleaned = text
        for p in reversed(phs):
            cleaned = cleaned[:p.start] + " " + cleaned[p.end:]

        # 2. Strip punctuation and whitespace normalization
        cleaned = re.sub(r"[^\w\s\u4e00-\u9fa5\u3040-\u30ff]", " ", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    def extract_from_entries(
        self,
        entries: Sequence[TranslationEntry],
        lang: str = "en",
    ) -> list[TermCandidate]:
        """Extract candidate terminology across all entries."""
        freq_counter: collections.Counter[str] = collections.Counter()
        examples_map: dict[str, list[str]] = collections.defaultdict(list)

        is_cjk = lang.lower().startswith(("zh", "ja", "ko", "cn"))

        for entry in entries:
            raw_text = entry.msgid
            if not raw_text or not raw_text.strip():
                continue

            cleaned = self.clean_text(raw_text)
            if not cleaned:
                continue

            has_cjk = bool(RE_CHINESE_CHAR.search(cleaned)) or bool(RE_JAPANESE_CHAR.search(cleaned))
            if is_cjk or has_cjk:
                # Extract CJK n-grams
                # Remove spaces for CJK substrings
                cjk_stripped = re.sub(r"\s+", "", cleaned)
                text_len = len(cjk_stripped)
                for n in range(self.min_length, min(self.max_length + 1, text_len + 1)):
                    for i in range(text_len - n + 1):
                        sub = cjk_stripped[i:i + n]
                        if sub not in CHINESE_STOP_WORDS and not sub.isdigit():
                            freq_counter[sub] += 1
                            if len(examples_map[sub]) < 3 and raw_text not in examples_map[sub]:
                                examples_map[sub].append(raw_text)
            else:
                # English / Western language extraction
                # 1. Extract Title Case phrases (common for game items, skills, proper nouns)
                title_matches = RE_ENGLISH_TITLE.findall(cleaned)
                for tm in title_matches:
                    clean_tm = tm.strip()
                    if (
                        self.min_length <= len(clean_tm) <= self.max_length * 3
                        and clean_tm.lower() not in ENGLISH_STOP_WORDS
                    ):
                        freq_counter[clean_tm] += 1
                        if len(examples_map[clean_tm]) < 3 and raw_text not in examples_map[clean_tm]:
                            examples_map[clean_tm].append(raw_text)

                # 2. Extract repeated word n-grams (2 to 4 words)
                words = [w for w in cleaned.split() if w.lower() not in ENGLISH_STOP_WORDS and not w.isdigit()]
                for n in range(2, 4):
                    for i in range(len(words) - n + 1):
                        ngram = " ".join(words[i:i + n])
                        if self.min_length <= len(ngram) <= self.max_length * 3:
                            freq_counter[ngram] += 1
                            if len(examples_map[ngram]) < 3 and raw_text not in examples_map[ngram]:
                                examples_map[ngram].append(raw_text)

        candidates: list[TermCandidate] = []
        for text, freq in freq_counter.items():
            if freq >= self.min_freq:
                # Score formula rewarding higher frequency and moderate length
                score = freq * (len(text) ** 0.5)
                candidates.append(
                    TermCandidate(
                        text=text,
                        frequency=freq,
                        length=len(text),
                        examples=examples_map.get(text, []),
                        score=round(score, 2),
                    )
                )

        # Sort primarily by score descending, then frequency
        candidates.sort(key=lambda c: (c.score, c.frequency), reverse=True)
        return candidates[:self.max_candidates]
