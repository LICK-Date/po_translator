"""Unit tests for deterministic validators."""

from po_translator.translation.validator import (
    CompositeValidator,
    EmptyTranslationValidator,
    LengthRatioValidator,
    PlaceholderValidator,
    ValidationSeverity,
)


class TestValidators:
    def test_placeholder_validator(self):
        val = PlaceholderValidator()

        # Valid match
        res_ok = val.validate("Score: %d points", "得分：%d 分")
        assert res_ok.is_valid is True
        assert len(res_ok.errors) == 0

        # Broken placeholder
        res_fail = val.validate("Hello {username}", "你好 {用户名}")
        assert res_fail.is_valid is False
        assert len(res_fail.errors) >= 1
        assert res_fail.errors[0].severity == ValidationSeverity.ERROR
        assert res_fail.errors[0].category == "placeholder"

    def test_empty_validator(self):
        val = EmptyTranslationValidator()

        res_ok = val.validate("Start", "开始")
        assert res_ok.is_valid is True

        res_empty = val.validate("Start", "   ")
        assert res_empty.is_valid is False
        assert len(res_empty.errors) == 1
        assert res_empty.errors[0].category == "empty"

    def test_length_ratio_validator(self):
        val = LengthRatioValidator(max_ratio=3.0, min_chars=10)

        # Normal translation
        res_norm = val.validate("This is a normal sentence.", "这是一个普通的句子。")
        assert res_norm.is_valid is True
        assert len(res_norm.warnings) == 0

        # Excessively verbose hallucination (10 chars source vs 50+ chars translation with max_ratio=2.0)
        res_long = val.validate("Short line", "这是一个非常非常非常非常非常非常非常非常非常非常长而且重复的冗长译文。")
        assert res_long.is_valid is True  # Warning does not block validity
        assert len(res_long.warnings) == 1
        assert res_long.warnings[0].category == "length"

    def test_composite_validator(self):
        comp = CompositeValidator()

        # Clean case
        res = comp.validate("Click <b>OK</b>", "点击 <b>确定</b>")
        assert res.is_valid is True
        assert not res.has_errors
        assert not res.has_warnings

        # Case with both empty and broken placeholder
        res_err = comp.validate("Click <b>OK</b>", "")
        assert res_err.is_valid is False
        assert res_err.has_errors
