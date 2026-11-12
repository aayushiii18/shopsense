"""
app/routes/report_routes.py — FastAPI endpoints for PDF and Excel analytical report exports.
"""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.report_service import generate_pdf_report, generate_excel_report

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.get("/pdf", summary="Download analytical executive report in PDF format")
def download_pdf_report(db: Session = Depends(get_db)):
    """Generates and streams an executive PDF analytics report."""
    pdf_bytes = generate_pdf_report(db)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": "attachment; filename=StockPilot_Analytics_Report.pdf",
        },
    )


@router.get("/excel", summary="Download comprehensive analytics workbook in Excel format")
def download_excel_report(db: Session = Depends(get_db)):
    """Generates and streams a multi-sheet analytical Excel workbook."""
    excel_bytes = generate_excel_report(db)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": "attachment; filename=StockPilot_Analytics_Report.xlsx",
        },
    )
