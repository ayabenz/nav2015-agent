from nav_ai.control_flow import analyze_control_flow, tokenize


def test_nested_if_else_preserves_true_false_paths():
    source = """IF Header.Status = Header.Status::Released THEN BEGIN
  Post();
END ELSE
  ERROR('Not released');"""
    result = analyze_control_flow(source, procedure="PostHeader")
    outer = result["nodes"][0]
    assert outer["type"] == "if"
    assert outer["condition"] == "Header.Status = Header.Status::Released"
    assert outer["true_branch"]["type"] == "block"
    assert outer["true_branch"]["children"][0]["source"] == "Post();"
    assert outer["false_branch"]["source"] == "ERROR('Not released');"
    assert result["runtime_evaluated"] is False


def test_nested_if_is_attached_to_true_branch():
    source = """IF A = 1 THEN
 IF B = 2 THEN X := 1 ELSE X := 2
ELSE X := 3;"""
    outer = analyze_control_flow(source)["nodes"][0]
    assert outer["condition"] == "A = 1"
    assert outer["true_branch"]["type"] == "if"
    assert outer["false_branch"]["source"] == "X := 3;"


def test_case_arms_and_default():
    source = """CASE Header.Status OF
  Header.Status::Open: OpenProc();
  Header.Status::Released: ReleaseProc();
ELSE
  ERROR('Invalid');
END;"""
    node = analyze_control_flow(source)["nodes"][0]
    assert node["type"] == "case"
    assert len(node["arms"]) == 2
    assert node["arms"][0]["labels"] == "Header.Status::Open"
    assert node["default"]["source"] == "ERROR('Invalid');"


def test_tokenizer_ignores_control_keywords_inside_comments_and_strings():
    tokens = tokenize("MESSAGE('IF A = 1 THEN'); // ELSE\nIF A THEN X := 1;")
    values = [x["upper"] for x in tokens]
    assert values.count("IF") == 1
    assert "ELSE" not in values


def test_condition_source_lines_are_retained():
    result = analyze_control_flow("\nIF X = 1 THEN\n  DoIt;\nELSE\n  Stop;\n")
    node = result["nodes"][0]
    assert node["condition_span"]["line_start"] == 2
    assert node["line_start"] == 2
