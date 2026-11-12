"""
validate_consistency.py — Standalone CLI runner for Dashboard Data-Consistency Validation.
"""

import os
import sys
import json
from app.database import SessionLocal
from app.services.consistency_validator import run_consistency_validation


def main():
    print("=" * 75)
    print("StockPilot - Dashboard & Database Data-Consistency Validation")
    print("=" * 75)
    db = SessionLocal()
    try:
        report = run_consistency_validation(db)
        print(f"Timestamp:          {report['timestamp']}")
        print(f"Total Checks:       {report['total_checks']}")
        print(f"Passed Checks:      {report['passed_checks']}")
        print(f"Failed Checks:      {report['failed_checks']}")
        print(f"Consistency Score:  {report['consistency_pct']}% (Target: >= {report['target_pct']}%) -> {'TARGET MET' if report['target_met'] else 'TARGET MISSED'}")
        print("-" * 75)
        print(f"{'Status':<8} {'Category':<24} {'Check Description':<40}")
        print("-" * 75)
        for c in report["checks"]:
            st = "PASS" if c["passed"] else "FAIL"
            print(f"[{st:<4}] {c.get('category', ''):<24} {c['name']:<40}")
        print("=" * 75)

        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(out_dir, exist_ok=True)
        report_file = os.path.join(out_dir, "consistency_report.json")
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"Saved consistency report to: {report_file}")
        return 0 if report["target_met"] else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
