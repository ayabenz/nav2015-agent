from nav_ai.entrypoint_intelligence import discover_source_entrypoints


def test_discovers_trigger_action_and_runobject_declarations(tmp_path):
    source = tmp_path / "page.txt"
    source.write_text(
        """OBJECT Page 50000 Demo Page
  PROPERTIES
    RunObject=Page 42;
  ACTIONS
    { 1 ;    ;ActionContainer;
    }
    { 2 ;1   ;Action;
      OnAction=BEGIN
        CODEUNIT.RUN(CODEUNIT::\"Demo\");
      END;
    }
  CODE
    OnOpenPage()
    BEGIN
    END;

    PROCEDURE DoWork()
    BEGIN
    END;
""",
        encoding="utf-8",
    )

    result = discover_source_entrypoints([str(source)])

    kinds = [item["entry_kind"] for item in result["entries"]]
    assert "object_launch_property" in kinds
    assert "page_action_trigger" in kinds
    assert "object_or_dataitem_trigger" in kinds
    assert result["semantics"]["runtime_invoked"] is False


def test_entrypoint_scan_supports_zip_and_reports_source_location(tmp_path):
    import zipfile

    archive_path = tmp_path / "objects.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "report.txt",
            """OBJECT Report 50001 Demo Report
  CODE
    OnPreReport()
    BEGIN
    END;
""",
        )

    result = discover_source_entrypoints([str(archive_path)])
    assert result["entrypoint_count"] == 1
    entry = result["entries"][0]
    assert entry["object"] == "Report 50001"
    assert entry["trigger"] == "OnPreReport"
    assert entry["line"] == 3
    assert entry["runtime_invoked"] is False
