from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

from openpyxl import Workbook

from app.v48.data_analysis import analyze_tabular_bytes, spreadsheet_text
from app.v48.file_library import _assert_owned, _safe_filename
from app.v48.tool_hub import tool_hub_health


def test_v48_csv_data_analysis_profiles_numeric_and_categorical_columns():
    data = b"name,score,city\nA,10,Jaipur\nB,20,Delhi\nC,30,Jaipur\n"
    report = analyze_tabular_bytes("scores.csv", data)
    assert report["version"] == "v48"
    assert report["rows"] == 3
    assert report["columns_count"] == 3
    score = next(row for row in report["columns"] if row["name"] == "score")
    assert score["type"] == "numeric"
    assert score["mean"] == 20.0
    city = next(row for row in report["columns"] if row["name"] == "city")
    assert city["top_values"][0] == {"value": "Jaipur", "count": 2}


def test_v48_json_data_analysis_accepts_records():
    report = analyze_tabular_bytes("rows.json", b'[{"a":1,"b":"x"},{"a":2,"b":"y"}]')
    assert report["rows"] == 2
    assert report["preview"][0]["a"] == 1


def test_v48_xlsx_analysis_works_without_server_code_execution():
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["month", "sales"])
    sheet.append(["Jan", 100])
    sheet.append(["Feb", 150])
    buffer = BytesIO()
    workbook.save(buffer)
    report = analyze_tabular_bytes("sales.xlsx", buffer.getvalue())
    assert report["format"] == "xlsx"
    assert report["rows"] == 2
    assert any(item["name"] == "sales" and item["type"] == "numeric" for item in report["columns"])
    assert "sales" in spreadsheet_text("sales.xlsx", buffer.getvalue())


def test_v48_library_filename_and_ownership_guards():
    assert _safe_filename("../my:file?.pdf") == "_my_file_.pdf"
    assert _assert_owned("user-1", "user-1/abc.pdf") == "user-1/abc.pdf"
    try:
        _assert_owned("user-1", "user-2/abc.pdf")
    except PermissionError:
        pass
    else:
        raise AssertionError("cross-user file path must be rejected")


def test_v48_tool_hub_contract_marks_proprietary_computer_use_not_enabled():
    settings = SimpleNamespace(
        supabase_url="https://example.supabase.co",
        supabase_service_role_key="secret",
        v11_github_token="token",
        v11_video_api_base_url="",
        v11_video_api_key="",
    )
    health = tool_hub_health(settings)
    tools = {item["id"]: item for item in health["tools"]}
    assert health["version"] == "v48"
    assert tools["data-analysis"]["status"] == "ready"
    assert tools["file-library"]["status"] == "ready"
    assert tools["scheduled-tasks"]["status"] == "ready"
    assert tools["computer-use"]["status"] == "not-enabled"
    assert health["new_database_migration_required"] is False


def test_v48_is_wired_into_production_main_v11():
    backend = Path(__file__).resolve().parents[1]
    source = (backend / "app" / "main_v11.py").read_text(encoding="utf-8")
    assert "VASUKI_V48_UNIFIED_TOOLS_HUB" in source
    assert "app.include_router(build_v48_router(settings))" in source
    assert "v48_spreadsheet_text" in source
