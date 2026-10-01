"""Unit tests for TranslationMemory."""

from po_translator.storage.database import DatabaseManager
from po_translator.storage.translation_memory import TranslationMemory, compute_tm_key


class TestTranslationMemory:
    def test_compute_tm_key_consistency(self):
        k1 = compute_tm_key("en", "zh-CN", "Hello", msgctxt="menu")
        k2 = compute_tm_key("en", "zh-CN", "Hello", msgctxt="menu")
        k_diff_ctx = compute_tm_key("en", "zh-CN", "Hello", msgctxt="dialog")
        k_diff_prompt = compute_tm_key("en", "zh-CN", "Hello", msgctxt="menu", prompt_version="2.0")

        assert k1 == k2
        assert k1 != k_diff_ctx
        assert k1 != k_diff_prompt

    def test_store_and_lookup_hit(self):
        db = DatabaseManager(":memory:")
        tm = TranslationMemory(db)

        # Lookup before store: miss
        assert tm.lookup("en", "zh-CN", "Hello World") is None

        # Store entry
        tm.store("en", "zh-CN", "Hello World", "你好世界")

        # Lookup after store: hit
        hit = tm.lookup("en", "zh-CN", "Hello World")
        assert hit == "你好世界"

    def test_disabled_tm(self):
        db = DatabaseManager(":memory:")
        tm = TranslationMemory(db, enabled=False)

        tm.store("en", "zh-CN", "Start", "开始")
        assert tm.lookup("en", "zh-CN", "Start") is None

    def test_clear_tm(self):
        db = DatabaseManager(":memory:")
        tm = TranslationMemory(db)

        tm.store("en", "zh-CN", "Save", "保存")
        assert tm.lookup("en", "zh-CN", "Save") == "保存"

        tm.clear()
        assert tm.lookup("en", "zh-CN", "Save") is None
