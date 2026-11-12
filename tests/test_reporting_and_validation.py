"""
tests/test_reporting_and_validation.py — Test suite for Milestone 3 Modules 5-9.

Covers:
  1. Module 6: PDF Report generation (ReportLab) and format validation.
  2. Module 6: Excel Workbook generation (openpyxl) and 6-sheet structure validation.
  3. Module 6: Report download endpoints (GET /reports/pdf, GET /reports/excel).
  4. Module 7: Locust performance test suite structure and user simulation (isolated subprocess).
  5. Module 8: Consistency validation service and assertion checks (12 invariants).
"""

import io
import os
import sys
import subprocess
import pytest
from unittest.mock import patch, MagicMock
import openpyxl

from app.services.report_service import generate_pdf_report, generate_excel_report
from app.services.consistency_validator import run_consistency_validation


# ═════════════════════════════════════════════════════════════════════════════
# 1. MODULE 6 — REPORT GENERATION (PDF & EXCEL)
# ═════════════════════════════════════════════════════════════════════════════

def test_generate_pdf_report(db_session):
    """Verifies that generate_pdf_report produces a valid PDF document with binary magic bytes."""
    pdf_bytes = generate_pdf_report(db_session)
    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF"), "Generated file does not match PDF file format signature"


def test_generate_excel_report(db_session):
    """Verifies that generate_excel_report produces a valid multi-sheet OpenPyXL workbook."""
    excel_bytes = generate_excel_report(db_session)
    assert isinstance(excel_bytes, bytes)
    assert len(excel_bytes) > 5000
    assert excel_bytes.startswith(b"PK\x03\x04"), "Generated file does not match ZIP/OOXML format signature"

    # Load workbook from memory and verify tabs
    wb = openpyxl.load_workbook(io.BytesIO(excel_bytes))
    sheet_names = wb.sheetnames
    expected_sheets = [
        "Revenue Analytics",
        "Vendor Performance",
        "Customer Analytics",
        "Inventory Summary",
        "Sales Transactions",
        "Forecasting Results",
    ]
    for sheet in expected_sheets:
        assert sheet in sheet_names, f"Missing required worksheet '{sheet}' in generated Excel workbook"

    # Verify Revenue Analytics sheet title
    ws_rev = wb["Revenue Analytics"]
    assert "StockPilot" in str(ws_rev["A1"].value)


def test_api_download_pdf_report(client):
    """Tests GET /reports/pdf returns 200 OK with correct media type and disposition headers."""
    with patch("app.routes.report_routes.generate_pdf_report", return_value=b"%PDF-1.4 test binary data"):
        resp = client.get("/reports/pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert "attachment" in resp.headers["content-disposition"]
        assert resp.content.startswith(b"%PDF")


def test_api_download_excel_report(client):
    """Tests GET /reports/excel returns 200 OK with correct spreadsheet media type."""
    with patch("app.routes.report_routes.generate_excel_report", return_value=b"PK\x03\x04 test binary data"):
        resp = client.get("/reports/excel")
        assert resp.status_code == 200
        assert "spreadsheetml" in resp.headers["content-type"]
        assert "attachment" in resp.headers["content-disposition"]
        assert resp.content.startswith(b"PK\x03\x04")


# ═════════════════════════════════════════════════════════════════════════════
# 2. MODULE 7 — PERFORMANCE TESTING (LOCUST & RUNNER)
# ═════════════════════════════════════════════════════════════════════════════

def test_locust_user_definition():
    """
    Validates structure and task weights of StockPilotAnalyticsUser in an isolated
    process to prevent gevent monkey-patching from conflicting with pytest threads.
    """
    code = """
from locustfile import StockPilotAnalyticsUser
assert len(StockPilotAnalyticsUser.tasks) > 0
methods = [
    'test_total_revenue', 'test_vendor_performance', 'test_customer_metrics',
    'test_revenue_growth', 'test_vendor_benchmarking', 'test_inventory_forecast',
    'test_personalized_recommendation'
]
for m in methods:
    assert hasattr(StockPilotAnalyticsUser, m), f'Missing method: {m}'
print('LOCUST_USER_VALID')
"""
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert res.returncode == 0, f"Locust definition error: {res.stderr}"
    assert "LOCUST_USER_VALID" in res.stdout


def test_locust_task_simulation():
    """
    Simulates Locust user task invocation in an isolated subprocess with a mock client.
    """
    code = """
from unittest.mock import MagicMock
from locustfile import StockPilotAnalyticsUser

mock_client = MagicMock()
mock_resp = MagicMock()
mock_resp.status_code = 200
mock_client.get.return_value.__enter__.return_value = mock_resp

StockPilotAnalyticsUser.host = 'http://127.0.0.1:8000'
env = MagicMock()
user = StockPilotAnalyticsUser(environment=env)
user.client = mock_client
user.test_total_revenue()
user.test_vendor_performance()
user.test_customer_metrics()
user.test_revenue_growth()
user.test_vendor_benchmarking()
user.test_inventory_forecast()
user.test_personalized_recommendation()

assert mock_client.get.call_count == 7
print('SIMULATION_SUCCESS')
"""
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert res.returncode == 0, f"Locust simulation error: {res.stderr}"
    assert "SIMULATION_SUCCESS" in res.stdout


# ═════════════════════════════════════════════════════════════════════════════
# 3. MODULE 8 — DATA-CONSISTENCY VALIDATION
# ═════════════════════════════════════════════════════════════════════════════

def test_run_consistency_validation(db_session):
    """Validates that consistency validation suite executes and returns structured report."""
    report = run_consistency_validation(db_session)

    assert "consistency_pct" in report
    assert "total_checks" in report
    assert "passed_checks" in report
    assert "target_met" in report
    assert report["total_checks"] == 12
    assert report["consistency_pct"] >= 90.0
    assert len(report["checks"]) == 12

    # Verify check categories exist
    categories = {c["category"] for c in report["checks"]}
    assert "Revenue Intelligence" in categories
    assert "Customer Intelligence" in categories
    assert "Inventory Intelligence" in categories
    assert "Recommendation Intelligence" in categories


def test_consistency_check_details(db_session):
    """Verifies that each of the 12 assertions produces expected metadata."""
    report = run_consistency_validation(db_session)
    for chk in report["checks"]:
        assert "name" in chk
        assert "category" in chk
        assert "passed" in chk
        assert "actual" in chk
        assert isinstance(chk["passed"], bool)
