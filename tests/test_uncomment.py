"""Regression tests for uncomment() string masking in depgraph.py."""
from nav_ai.depgraph import uncomment


def test_uncomment_removes_plain_line_comment():
    # // comment replaced with single space; existing space before // preserved
    assert uncomment("x := 1; // this is a comment") == "x := 1;  "


def test_uncomment_preserves_string_with_double_slash():
    # // inside a single-quoted C/AL string must NOT be removed
    s = "url := 'http://example.com/path'; // real comment"
    result = uncomment(s)
    assert "http://example.com/path" in result
    assert "real comment" not in result


def test_uncomment_preserves_string_with_brace():
    # { inside a string must not be treated as brace comment when braces=True
    s = "x := '{json}'; { real comment }"
    result = uncomment(s, braces=True)
    assert "{json}" in result
    assert "real comment" not in result


def test_uncomment_multiple_strings():
    s = "a := 'a//b'; b := 'c//d'; // end"
    result = uncomment(s)
    assert "a//b" in result
    assert "c//d" in result
    assert "end" not in result


def test_uncomment_escaped_quote_in_string():
    s = "msg := 'It''s a // test'; // comment"
    result = uncomment(s)
    assert "It''s a // test" in result
    assert "comment" not in result


def test_uncomment_empty_string():
    assert uncomment("") == ""


def test_uncomment_no_comments():
    assert uncomment("x := 1; y := 2;") == "x := 1; y := 2;"
