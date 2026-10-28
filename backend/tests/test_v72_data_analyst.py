from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.v72.data_analyst import (
    analyze_data_file,
    analyze_records,
    health_snapshot,
    validate_bounded_python,
)


class Settings:
    pass


def test_v72_profiles_real_csv_data():
    data = (
        "region,sales,profit\n"
        "North,100,20\n"
        "South,200,40\n"
        "North,300,60\n"
        "South,400,80\n"
    ).encode()
    report = analyze_records("sales.csv", data)
    assert report["rows"] == 4
    assert report["columns_count"] == 3
    assert report["missing_cells"] == 0
    sales = next(item for item in report["columns"] if item["name"] == "sales")
    assert sales["type"] == "numeric"
    assert sales["stats"]["mean"] == 250.0
    assert report["correlations"][0]["r"] == 1.0
    assert report["group_insights"]


def test_v72_rejects_unsafe_python_imports():
    with pytest.raises(ValueError):
        validate_bounded_python("import os\nprint(os.getcwd())")
    validate_bounded_python("import csv, statistics\nprint('ok')")


def test_v72_analysis_has_truthful_execution_proof(monkeypatch):
    async def fake_route(*args, **kwargs):
        return "Sales average is 150.", "fake-provider"

    monkeypatch.setattr("app.v72.data_analyst.route_chat_v10", fake_route)
    result = asyncio.run(
        analyze_data_file(
            Settings(),
            filename="sales.csv",
            data=b"sales\n100\n200\n",
            prompt="What is the average?",
        )
    )
    assert result["ok"] is True
    assert result["analysis"]["rows"] == 2
    assert result["execution_proof"]["computed_statistics"] is True
    assert result["execution_proof"]["network_used_for_dataset_computation"] is False


def test_v72_health_does_not_fake_arbitrary_python():
    health = health_snapshot()
    assert health["version"] == "v72"
    assert health["deterministic_data_computation"] is True
    assert health["arbitrary_server_python_execution"] is False
    assert health["new_database_migration_required"] is False


def test_v72_production_wiring_present():
    repo = Path(__file__).resolve().parents[2]
    main = (repo / "backend/app/main_v11.py").read_text(encoding="utf-8")
    api = (repo / "frontend/lib/api.ts").read_text(encoding="utf-8")
    chat = (repo / "frontend/components/ChatApp.tsx").read_text(encoding="utf-8")

    assert '"/health/v72"' in main
    assert '"/api/v72/analyze"' in main
    assert '"/api/v72/python"' in main
    assert "analyzeDataV72" in api
    assert "analyzeDataV72" in chat
    assert 'mode === "analyze"' in chat
    assert '".csv"' in chat
    assert '".xlsx"' in chat
