"""Regression tests for C/AL-aware tokenization and string masking."""
from nav_ai.semantic_diff import lexical_tokens, mask_cal_strings


def test_semantic_diff_preserves_url_inside_string():
    tokens = lexical_tokens("Url := 'https://example.com/a//b';")
    assert "'https://example.com/a//b'" in tokens


def test_semantic_diff_removes_line_comment_outside_string():
    tokens = lexical_tokens("x := 'keep'; // remove this")
    assert "'keep'" in tokens
    assert "remove" not in tokens


def test_semantic_diff_preserves_braces_inside_string():
    tokens = lexical_tokens("x := '{json}'; { real comment }")
    assert "'{json}'" in tokens
    assert "real" not in tokens


def test_semantic_diff_handles_escaped_single_quote():
    tokens = lexical_tokens("x := 'It''s // valid'; // comment")
    assert "'It''s // valid'" in tokens
    assert "comment" not in tokens


def test_mask_cal_strings_preserves_code_and_line_count():
    source = "OtherProc();\nMESSAGE('OtherProc');\n"
    masked = mask_cal_strings(source)
    assert "OtherProc();" in masked
    assert "MESSAGE(" in masked
    assert "'OtherProc'" not in masked
    assert masked.count("\n") == source.count("\n")
