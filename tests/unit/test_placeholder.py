"""Unit tests for placeholder extraction and validation engine."""


from po_translator.po.placeholder import (
    PlaceholderType,
    extract_placeholders,
    validate_placeholders,
)


class TestPlaceholderExtraction:
    def test_extract_printf_specifiers(self):
        text = "Score: %d, Rate: %.2f, Name: %s, Pos: %1$s, Dict: %(count)d, Literal: %%"
        phs = extract_placeholders(text)
        raws = [p.raw for p in phs]

        assert "%d" in raws
        assert "%.2f" in raws
        assert "%s" in raws
        assert "%1$s" in raws
        assert "%(count)d" in raws
        assert "%%" in raws
        for p in phs:
            assert p.placeholder_type == PlaceholderType.PRINTF

    def test_extract_python_format(self):
        text = "Hello {}, user {0}, named {username}, converted {val!r}, formatted {balance:.2f}."
        phs = extract_placeholders(text)
        raws = [p.raw for p in phs]

        assert "{}" in raws
        assert "{0}" in raws
        assert "{username}" in raws
        assert "{val!r}" in raws
        assert "{balance:.2f}" in raws
        for p in phs:
            assert p.placeholder_type == PlaceholderType.PYTHON_FORMAT

    def test_extract_html_tags(self):
        text = "Click <b>OK</b> or <color=red>Cancel</color> to proceed.<br/>"
        phs = extract_placeholders(text)
        raws = [p.raw for p in phs]

        assert "<b>" in raws
        assert "</b>" in raws
        assert "<color=red>" in raws
        assert "</color>" in raws
        assert "<br/>" in raws
        for p in phs:
            assert p.placeholder_type == PlaceholderType.HTML_TAG

    def test_extract_escape_sequences(self):
        text = "Line 1\\nLine 2\\tTabbed\\\\Backslash\\rReturn"
        phs = extract_placeholders(text)
        raws = [p.raw for p in phs]

        assert "\\n" in raws
        assert "\\t" in raws
        assert "\\\\" in raws
        assert "\\r" in raws
        for p in phs:
            assert p.placeholder_type == PlaceholderType.ESCAPE

    def test_extract_game_variables(self):
        text = "Player [PLAYER] met <COMPANION> at {{town}} with $coins and ${diamonds}."
        phs = extract_placeholders(text)
        raws = [p.raw for p in phs]

        assert "[PLAYER]" in raws
        assert "<COMPANION>" in raws
        assert "{{town}}" in raws
        assert "$coins" in raws
        assert "${diamonds}" in raws
        for p in phs:
            assert p.placeholder_type == PlaceholderType.GAME_VARIABLE


class TestPlaceholderValidation:
    def test_validate_exact_match(self):
        src = "Hello {username}, you have %d coins.\\nEnjoy!"
        trans = "你好 {username}，你有 %d 个金币。\\n玩得开心！"
        res = validate_placeholders(src, trans)
        assert res.is_valid is True
        assert len(res.issues) == 0

    def test_validate_reordered_placeholders_valid(self):
        src = "Current: {current} / Max: {max}"
        trans = "上限: {max} / 当前: {current}"
        res = validate_placeholders(src, trans)
        assert res.is_valid is True
        assert len(res.issues) == 0

    def test_validate_missing_placeholder(self):
        src = "Player %s has %d gold."
        trans = "玩家 %s 有很多金币。"
        res = validate_placeholders(src, trans)
        assert res.is_valid is False
        assert any(issue.issue_type == "missing" and issue.placeholder == "%d" for issue in res.issues)

    def test_validate_extra_placeholder(self):
        src = "Hello %s"
        trans = "你好 %s，第 %d 次登录"
        res = validate_placeholders(src, trans)
        assert res.is_valid is False
        assert any(issue.issue_type == "extra" and issue.placeholder == "%d" for issue in res.issues)

    def test_validate_count_mismatch(self):
        src = "Value: %d"
        trans = "值：%d %d"
        res = validate_placeholders(src, trans)
        assert res.is_valid is False
        assert any(issue.issue_type == "count_mismatch" for issue in res.issues)

    def test_validate_translated_variable_name(self):
        src = "Welcome, {username}!"
        trans = "欢迎，{用户名}！"
        res = validate_placeholders(src, trans)
        assert res.is_valid is False
        assert any(issue.issue_type == "missing" and issue.placeholder == "{username}" for issue in res.issues)
        assert any(issue.issue_type == "changed" for issue in res.issues)

    def test_empty_and_whitespace_text(self):
        assert extract_placeholders("") == []
        assert extract_placeholders("   ") == []
        res = validate_placeholders("", "")
        assert res.is_valid is True
        assert len(res.issues) == 0

    def test_combined_multiple_complex_types(self):
        src = "%s: [LEVEL] {pct:.1f}%% <b>DONE</b>\\n"
        trans = "%s: [LEVEL] {pct:.1f}%% <b>完成</b>\\n"
        res = validate_placeholders(src, trans)
        assert res.is_valid is True
        assert len(res.issues) == 0
