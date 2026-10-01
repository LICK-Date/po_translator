"""Domain enumerations for PO LLM Translator."""

from enum import Enum


class TranslationStatus(str, Enum):
    """Explicit lifecycle status for a translation entry."""
    PENDING = "pending"
    TRANSLATING = "translating"
    TRANSLATED = "translated"
    CACHED = "cached"
    FAILED = "failed"
    REVIEW_REQUIRED = "review_required"
    SKIPPED = "skipped"


class TranslationMode(str, Enum):
    """Translation pipeline processing mode."""
    FAST = "fast"
    QUALITY = "quality"
    SMART = "smart"


class FilterMode(str, Enum):
    """Filter modes for entries to translate."""
    UNTRANSLATED_ONLY = "untranslated_only"
    ALL = "all"
    FUZZY_ONLY = "fuzzy_only"


class FuzzyHandling(str, Enum):
    """Handling strategy for fuzzy entries."""
    SKIP = "skip"
    RETRANSLATE = "retranslate"
    REVIEW = "review"


class TranslationStage(str, Enum):
    """Stage identifier for translation results/history."""
    INITIAL = "initial"
    IMPROVED = "improved"
    REPAIR = "repair"
    MANUAL = "manual"
