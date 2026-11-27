from nav_ai.entrypoint_bodies import discover_entrypoint_bodies


def test_extracts_individual_page_action_and_trigger_bodies(tmp_path):
    source = tmp_path / "page.txt"
    source.write_text(
        """OBJECT Page 50000 Demo Page
  ACTIONS
    { 10 ;    ;Action;
      Name=Post;
      OnAction=BEGIN
        CODEUNIT.RUN(CODEUNIT::Worker);
      END;
    }
    { 20 ;    ;Action;
      Name=Preview;
      OnAction=BEGIN
        MESSAGE('Preview');
      END;
    }
  CODE
    OnOpenPage()
    BEGIN
      DoSetup;
    END;

    PROCEDURE DoSetup()
    BEGIN
    END;
""",
        encoding="utf-8",
    )

    result = discover_entrypoint_bodies([str(source)])
    entries = result["entries"]
    actions = [item for item in entries if item["entry_kind"] == "page_action_body"]
    trigger = next(item for item in entries if item["trigger"] == "OnOpenPage")

    assert [item["action_id"] for item in actions] == [10, 20]
    assert "CODEUNIT.RUN" in actions[0]["body"]
    assert "MESSAGE" in actions[1]["body"]
    assert "DoSetup" in trigger["body"]
    assert actions[0]["line_start"] < actions[0]["line_end"]
    assert all(item["runtime_invoked"] is False for item in entries)


def test_extracts_action_bodies_from_combined_export_with_absolute_lines(tmp_path):
    source = tmp_path / "combined.txt"
    source.write_text(
        "OBJECT Codeunit 50001 Worker\n  CODE\n    OnRun()\n    BEGIN\n    END;\n"
        "OBJECT Page 50002 Demo\n  ACTIONS\n    { 7 ;    ;Action;\n"
        "      OnAction=BEGIN\n        MESSAGE('x');\n      END;\n    }\n",
        encoding="utf-8",
    )
    result = discover_entrypoint_bodies([str(source)])
    action = next(item for item in result["entries"] if item["entry_kind"] == "page_action_body")
    assert action["action_id"] == 7
    assert action["line_start"] == 8
    assert action["line_end"] == 10
