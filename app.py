"""
Network Switch Compliance Checker - Main Application
Flask web application providing a one-click dashboard for network compliance auditing.
"""

import os
import sys
import json
import logging
import threading
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_file, Response

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.ssh_connector import SSHConnector, DemoSSHConnector
from modules.compliance_checker import ComplianceChecker
from modules.report_generator import ReportGenerator

# ============================================================================
# Configuration
# ============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

os.makedirs(REPORTS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOGS_DIR, "app.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ============================================================================
# Flask App
# ============================================================================
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-me-in-production")

# Global state for audit progress
audit_state = {
    "running": False,
    "progress": 0,
    "total": 0,
    "current_switch": "",
    "status": "idle",  # idle, running, completed, error
    "last_audit": None,
    "last_audit_time": None,
    "errors": [],
}
audit_lock = threading.Lock()

# Mode: "demo" for testing without real switches, "live" for real SSH
MODE = os.environ.get("COMPLIANCE_MODE", "demo").lower()


def get_connector():
    """Return the appropriate SSH connector based on mode."""
    inventory_path = os.path.join(CONFIG_DIR, "inventory.yaml")
    if MODE == "demo":
        return DemoSSHConnector(inventory_path)
    return SSHConnector(inventory_path)


def get_checker():
    """Return a ComplianceChecker instance."""
    template_path = os.path.join(CONFIG_DIR, "golden_template.yaml")
    return ComplianceChecker(template_path)


def get_report_gen():
    """Return a ReportGenerator instance."""
    return ReportGenerator(REPORTS_DIR)


# ============================================================================
# Routes
# ============================================================================

@app.route("/")
def dashboard():
    """Main dashboard page."""
    return render_template("dashboard.html", mode=MODE)


@app.route("/api/status")
def api_status():
    """Return current audit status and progress."""
    with audit_lock:
        return jsonify(audit_state)


@app.route("/api/inventory")
def api_inventory():
    """Return the switch inventory."""
    try:
        connector = get_connector()
        switches = connector.get_all_switches()
        regions = {}
        for sw in switches:
            region = sw.get("region", "Unknown")
            if region not in regions:
                regions[region] = []
            regions[region].append({
                "name": sw["name"],
                "hostname": sw["hostname"],
                "device_type": sw["device_type"],
                "location": sw.get("location", "Unknown"),
            })
        return jsonify({
            "total_switches": len(switches),
            "regions": regions,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/template")
def api_template():
    """Return golden template summary."""
    try:
        checker = get_checker()
        categories = []
        for cat in checker.categories:
            categories.append({
                "name": cat["name"],
                "id": cat["id"],
                "rule_count": len(cat.get("rules", [])),
                "rules": [
                    {
                        "id": r["id"],
                        "description": r["description"],
                        "severity": r.get("severity", "medium"),
                    }
                    for r in cat.get("rules", [])
                ],
            })
        return jsonify({
            "total_rules": checker.get_rule_count(),
            "categories": categories,
            "metadata": checker.template.get("metadata", {}),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/run-audit", methods=["POST"])
def api_run_audit():
    """Start a compliance audit (runs in background thread)."""
    global audit_state

    with audit_lock:
        if audit_state["running"]:
            return jsonify({"error": "Audit already in progress"}), 409

        audit_state["running"] = True
        audit_state["progress"] = 0
        audit_state["total"] = 0
        audit_state["current_switch"] = ""
        audit_state["status"] = "running"
        audit_state["errors"] = []

    def run_audit():
        global audit_state
        try:
            logger.info("=" * 60)
            logger.info(f"Starting compliance audit (mode: {MODE})")
            logger.info("=" * 60)

            connector = get_connector()
            checker = get_checker()

            switches = connector.get_all_switches()
            with audit_lock:
                audit_state["total"] = len(switches)

            def progress_callback(completed, total, switch_name, status):
                with audit_lock:
                    audit_state["progress"] = completed
                    audit_state["current_switch"] = switch_name
                logger.info(f"[{completed}/{total}] {switch_name}: {status}")

            # Collect configs
            logger.info(f"Collecting configs from {len(switches)} switches...")
            with audit_lock:
                audit_state["current_switch"] = "Collecting configurations..."

            max_workers = int(os.environ.get("MAX_SSH_WORKERS", "10"))
            switch_results = connector.collect_all_configs(
                max_workers=max_workers,
                progress_callback=progress_callback,
            )

            # Run compliance checks
            logger.info("Running compliance checks...")
            with audit_lock:
                audit_state["current_switch"] = "Analyzing compliance..."

            audit_data = checker.check_all(switch_results)

            # Generate reports
            logger.info("Generating reports...")
            with audit_lock:
                audit_state["current_switch"] = "Generating reports..."

            report_gen = get_report_gen()
            pdf_path = report_gen.generate_pdf(audit_data)
            csv_summary_path = report_gen.generate_csv_summary(audit_data)
            csv_detailed_path = report_gen.generate_csv_detailed(audit_data)

            audit_data["report_files"] = {
                "pdf": os.path.basename(pdf_path) if pdf_path else None,
                "csv_summary": os.path.basename(csv_summary_path),
                "csv_detailed": os.path.basename(csv_detailed_path),
            }

            with audit_lock:
                audit_state["running"] = False
                audit_state["status"] = "completed"
                audit_state["last_audit"] = audit_data
                audit_state["last_audit_time"] = datetime.now().isoformat()
                audit_state["current_switch"] = ""

            logger.info("=" * 60)
            logger.info(f"Audit completed. Overall compliance: {audit_data['overall_compliance_pct']}%")
            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"Audit failed: {e}", exc_info=True)
            with audit_lock:
                audit_state["running"] = False
                audit_state["status"] = "error"
                audit_state["errors"].append(str(e))
                audit_state["current_switch"] = ""

    thread = threading.Thread(target=run_audit, daemon=True)
    thread.start()

    return jsonify({"message": "Audit started", "status": "running"})


@app.route("/api/audit-results")
def api_audit_results():
    """Return the latest audit results."""
    with audit_lock:
        if audit_state["last_audit"] is None:
            return jsonify({"error": "No audit results available. Run an audit first."}), 404
        return jsonify(audit_state["last_audit"])


@app.route("/api/switch-report/<switch_name>")
def api_switch_report(switch_name):
    """Return detailed report for a specific switch."""
    with audit_lock:
        if audit_state["last_audit"] is None:
            return jsonify({"error": "No audit results available"}), 404

        for report in audit_state["last_audit"].get("switch_reports", []):
            if report["switch_name"] == switch_name:
                return jsonify(report)

    return jsonify({"error": f"Switch '{switch_name}' not found in results"}), 404


@app.route("/api/download/<report_type>")
def api_download(report_type):
    """Download a generated report file."""
    with audit_lock:
        if audit_state["last_audit"] is None:
            return jsonify({"error": "No audit results available"}), 404

        report_files = audit_state["last_audit"].get("report_files", {})

    if report_type == "pdf":
        filename = report_files.get("pdf")
        if not filename:
            return jsonify({"error": "PDF report not available"}), 404
        filepath = os.path.join(REPORTS_DIR, filename)
        return send_file(filepath, as_attachment=True, download_name=filename)

    elif report_type == "csv_summary":
        filename = report_files.get("csv_summary")
        if not filename:
            return jsonify({"error": "CSV summary not available"}), 404
        filepath = os.path.join(REPORTS_DIR, filename)
        return send_file(filepath, as_attachment=True, download_name=filename)

    elif report_type == "csv_detailed":
        filename = report_files.get("csv_detailed")
        if not filename:
            return jsonify({"error": "Detailed CSV not available"}), 404
        filepath = os.path.join(REPORTS_DIR, filename)
        return send_file(filepath, as_attachment=True, download_name=filename)

    return jsonify({"error": "Invalid report type"}), 400


# ============================================================================
# Entry Point
# ============================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"

    print("=" * 60)
    print("  Network Switch Compliance Checker")
    print(f"  Mode: {'DEMO (simulated data)' if MODE == 'demo' else 'LIVE (real SSH)'}")
    print(f"  Dashboard: http://localhost:{port}")
    print("=" * 60)

    if MODE == "demo":
        print("\n  ⚠  Running in DEMO mode with simulated switch data.")
        print("  Set COMPLIANCE_MODE=live for real SSH connections.\n")

    app.run(host="0.0.0.0", port=port, debug=debug)
