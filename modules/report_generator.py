"""
Report Generator Module
Generates downloadable PDF and CSV compliance reports.
"""

import csv
import io
import os
import logging
from datetime import datetime

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch, mm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,
        PageBreak, Image, HRFlowable
    )
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.graphics.shapes import Drawing, Rect, String
    from reportlab.graphics.charts.piecharts import Pie
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates PDF and CSV compliance reports."""

    def __init__(self, reports_dir="reports"):
        self.reports_dir = reports_dir
        os.makedirs(reports_dir, exist_ok=True)

    def _get_status_color(self, status):
        """Return color for compliance status."""
        status_colors = {
            "compliant": colors.HexColor("#059669"),
            "partially_compliant": colors.HexColor("#D97706"),
            "non_compliant": colors.HexColor("#DC2626"),
            "unreachable": colors.HexColor("#6B7280"),
        }
        return status_colors.get(status, colors.grey)

    def _get_severity_color(self, severity):
        """Return color for severity level."""
        severity_colors = {
            "critical": colors.HexColor("#DC2626"),
            "high": colors.HexColor("#EA580C"),
            "medium": colors.HexColor("#D97706"),
            "low": colors.HexColor("#2563EB"),
        }
        return severity_colors.get(severity, colors.grey)

    def generate_pdf(self, audit_data, filename=None):
        """
        Generate a detailed PDF compliance report.
        
        Args:
            audit_data: Full audit dict from ComplianceChecker.check_all()
            filename: Optional filename (auto-generated if not provided)
        
        Returns:
            Path to the generated PDF file.
        """
        if not REPORTLAB_AVAILABLE:
            logger.error("ReportLab not installed. Install with: pip install reportlab")
            return None

        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"compliance_report_{timestamp}.pdf"

        filepath = os.path.join(self.reports_dir, filename)

        doc = SimpleDocTemplate(
            filepath,
            pagesize=A4,
            rightMargin=15 * mm,
            leftMargin=15 * mm,
            topMargin=20 * mm,
            bottomMargin=20 * mm,
        )

        styles = getSampleStyleSheet()
        # Custom styles
        styles.add(ParagraphStyle(
            'ReportTitle', parent=styles['Title'],
            fontSize=22, spaceAfter=6, textColor=colors.HexColor("#1E293B"),
            fontName='Helvetica-Bold'
        ))
        styles.add(ParagraphStyle(
            'ReportSubtitle', parent=styles['Normal'],
            fontSize=11, spaceAfter=12, textColor=colors.HexColor("#64748B"),
        ))
        styles.add(ParagraphStyle(
            'SectionHeader', parent=styles['Heading2'],
            fontSize=14, spaceAfter=8, spaceBefore=16,
            textColor=colors.HexColor("#1E40AF"), fontName='Helvetica-Bold',
            borderWidth=0, borderPadding=0,
        ))
        styles.add(ParagraphStyle(
            'SubSection', parent=styles['Heading3'],
            fontSize=11, spaceAfter=6, spaceBefore=10,
            textColor=colors.HexColor("#334155"), fontName='Helvetica-Bold',
        ))
        styles.add(ParagraphStyle(
            'CellText', parent=styles['Normal'],
            fontSize=7, leading=9,
        ))
        styles.add(ParagraphStyle(
            'CellTextSmall', parent=styles['Normal'],
            fontSize=6, leading=8,
        ))

        elements = []

        # ===== TITLE PAGE =====
        elements.append(Spacer(1, 40))
        elements.append(Paragraph("Network Switch Compliance Report", styles['ReportTitle']))
        elements.append(Paragraph(
            f"Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}",
            styles['ReportSubtitle']
        ))
        elements.append(Paragraph(
            f"Standard: {audit_data.get('template_standard', 'N/A')} "
            f"(Template v{audit_data.get('template_version', 'N/A')})",
            styles['ReportSubtitle']
        ))
        elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#1E40AF")))
        elements.append(Spacer(1, 20))

        # ===== EXECUTIVE SUMMARY =====
        elements.append(Paragraph("Executive Summary", styles['SectionHeader']))

        summary_data = [
            ["Metric", "Value"],
            ["Total Switches Audited", str(audit_data.get("total_switches", 0))],
            ["Switches Reached", str(audit_data.get("switches_reached", 0))],
            ["Switches Unreachable", str(audit_data.get("switches_unreachable", 0))],
            ["Overall Compliance", f"{audit_data.get('overall_compliance_pct', 0)}%"],
            ["Fully Compliant (≥95%)", str(audit_data.get("compliant_switches", 0))],
            ["Partially Compliant (70-94%)", str(audit_data.get("partially_compliant_switches", 0))],
            ["Non-Compliant (<70%)", str(audit_data.get("non_compliant_switches", 0))],
            ["Rules Per Switch", str(audit_data.get("total_rules_per_switch", 0))],
        ]

        # Add severity summary
        sev = audit_data.get("summary_by_severity", {})
        summary_data.append(["Critical Findings (Total)", str(sev.get("critical", 0))])
        summary_data.append(["High Findings (Total)", str(sev.get("high", 0))])
        summary_data.append(["Medium Findings (Total)", str(sev.get("medium", 0))])
        summary_data.append(["Low Findings (Total)", str(sev.get("low", 0))])

        summary_table = Table(summary_data, colWidths=[200, 200])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E40AF")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 16))

        # ===== COMPLIANCE BY REGION =====
        region_data = audit_data.get("summary_by_region", {})
        if region_data:
            elements.append(Paragraph("Compliance by Region", styles['SectionHeader']))
            region_table_data = [["Region", "Total", "Compliant", "Partial", "Non-Compliant", "Avg %"]]
            for region, data in sorted(region_data.items()):
                region_table_data.append([
                    region,
                    str(data["total"]),
                    str(data["compliant"]),
                    str(data["partial"]),
                    str(data["non_compliant"]),
                    f"{data['avg_compliance']}%",
                ])

            region_table = Table(region_table_data, colWidths=[120, 55, 70, 55, 85, 55])
            region_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E40AF")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(region_table)
            elements.append(Spacer(1, 16))

        # ===== COMPLIANCE BY CATEGORY =====
        cat_data = audit_data.get("summary_by_category", {})
        if cat_data:
            elements.append(Paragraph("Compliance by Category", styles['SectionHeader']))
            cat_table_data = [["Category", "Total Checks", "Compliant", "Non-Compliant", "Compliance %"]]
            for cat_name, data in sorted(cat_data.items()):
                cat_table_data.append([
                    cat_name,
                    str(data["total_checks"]),
                    str(data["compliant"]),
                    str(data["non_compliant"]),
                    f"{data.get('compliance_pct', 0)}%",
                ])

            cat_table = Table(cat_table_data, colWidths=[140, 75, 75, 85, 80])
            cat_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E40AF")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(cat_table)
            elements.append(Spacer(1, 16))

        # ===== TOP NON-COMPLIANT RULES =====
        top_rules = audit_data.get("top_non_compliant_rules", [])
        if top_rules:
            elements.append(Paragraph("Top Non-Compliant Rules (Most Frequent)", styles['SectionHeader']))
            top_table_data = [["Rule ID", "Description", "Severity", "Failing Switches"]]
            for rule in top_rules[:15]:
                top_table_data.append([
                    rule["rule_id"],
                    Paragraph(rule["description"], styles['CellText']),
                    rule["severity"].upper(),
                    str(rule["count"]),
                ])

            top_table = Table(top_table_data, colWidths=[60, 250, 60, 85])
            top_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#DC2626")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                ('ALIGN', (2, 0), (-1, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#FEF2F2")]),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ]))
            elements.append(top_table)

        elements.append(PageBreak())

        # ===== PER-SWITCH DETAILED REPORTS =====
        elements.append(Paragraph("Detailed Switch Reports", styles['SectionHeader']))
        elements.append(Spacer(1, 8))

        for i, report in enumerate(audit_data.get("switch_reports", [])):
            switch_name = report.get("switch_name", "Unknown")
            status = report.get("overall_status", "unknown")
            compliance_pct = report.get("compliance_percentage", 0)

            # Switch header
            status_label = status.replace("_", " ").title()
            elements.append(Paragraph(
                f"<b>{switch_name}</b> — {report.get('hostname', 'N/A')} "
                f"| {report.get('region', '?')} / {report.get('location', '?')} "
                f"| Status: <b>{status_label}</b> ({compliance_pct}%)",
                styles['SubSection']
            ))

            if status == "unreachable":
                elements.append(Paragraph(
                    f"<i>Switch unreachable: {report.get('collection_error', 'N/A')}</i>",
                    styles['Normal']
                ))
                elements.append(Spacer(1, 8))
                continue

            # Non-compliant findings for this switch
            non_compliant_findings = [
                f for f in report.get("all_findings", [])
                if f["status"] == "non_compliant"
            ]

            if non_compliant_findings:
                findings_data = [["Rule", "Description", "Severity", "Remediation"]]
                for finding in non_compliant_findings:
                    findings_data.append([
                        finding["rule_id"],
                        Paragraph(finding["description"], styles['CellTextSmall']),
                        finding["severity"].upper(),
                        Paragraph(finding.get("remediation", ""), styles['CellTextSmall']),
                    ])

                findings_table = Table(findings_data, colWidths=[50, 170, 50, 190])
                findings_table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#991B1B")),
                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 7),
                    ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                    ('ALIGN', (2, 0), (2, -1), 'CENTER'),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.HexColor("#FFF7ED"), colors.white]),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('TOPPADDING', (0, 0), (-1, -1), 3),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ]))
                elements.append(findings_table)
            else:
                elements.append(Paragraph(
                    "✓ All compliance checks passed.",
                    ParagraphStyle('pass', parent=styles['Normal'],
                                   textColor=colors.HexColor("#059669"), fontSize=9)
                ))

            elements.append(Spacer(1, 12))

            # Page break every 3 switches to keep it readable
            if (i + 1) % 3 == 0 and i < len(audit_data.get("switch_reports", [])) - 1:
                elements.append(PageBreak())

        # Build PDF
        doc.build(elements)
        logger.info(f"PDF report generated: {filepath}")
        return filepath

    def generate_csv_summary(self, audit_data, filename=None):
        """
        Generate a CSV summary report with one row per switch.
        
        Returns:
            Path to the generated CSV file.
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"compliance_summary_{timestamp}.csv"

        filepath = os.path.join(self.reports_dir, filename)

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            # Header
            writer.writerow([
                "Switch Name", "Hostname", "Region", "Location", "Device Type",
                "Status", "Compliance %", "Total Rules", "Compliant", "Non-Compliant",
                "N/A", "Critical Findings", "High Findings", "Medium Findings",
                "Low Findings", "Collection Timestamp"
            ])

            for report in audit_data.get("switch_reports", []):
                sev = report.get("severity_counts", {})
                writer.writerow([
                    report.get("switch_name", ""),
                    report.get("hostname", ""),
                    report.get("region", ""),
                    report.get("location", ""),
                    report.get("device_type", ""),
                    report.get("overall_status", "").replace("_", " ").title(),
                    report.get("compliance_percentage", 0),
                    report.get("total_rules", 0),
                    report.get("compliant_count", 0),
                    report.get("non_compliant_count", 0),
                    report.get("na_count", 0),
                    sev.get("critical", 0),
                    sev.get("high", 0),
                    sev.get("medium", 0),
                    sev.get("low", 0),
                    report.get("collection_timestamp", ""),
                ])

        logger.info(f"CSV summary report generated: {filepath}")
        return filepath

    def generate_csv_detailed(self, audit_data, filename=None):
        """
        Generate a detailed CSV with one row per finding per switch.
        
        Returns:
            Path to the generated CSV file.
        """
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"compliance_detailed_{timestamp}.csv"

        filepath = os.path.join(self.reports_dir, filename)

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            # Header
            writer.writerow([
                "Switch Name", "Hostname", "Region", "Location",
                "Rule ID", "Category", "Description", "Severity",
                "Status", "Detail", "Remediation"
            ])

            for report in audit_data.get("switch_reports", []):
                for finding in report.get("all_findings", []):
                    writer.writerow([
                        report.get("switch_name", ""),
                        report.get("hostname", ""),
                        report.get("region", ""),
                        report.get("location", ""),
                        finding.get("rule_id", ""),
                        finding.get("category", ""),
                        finding.get("description", ""),
                        finding.get("severity", ""),
                        finding.get("status", ""),
                        finding.get("detail", ""),
                        finding.get("remediation", ""),
                    ])

        logger.info(f"CSV detailed report generated: {filepath}")
        return filepath

    def generate_csv_string(self, audit_data, report_type="summary"):
        """Generate CSV content as a string (for API download)."""
        output = io.StringIO()
        writer = csv.writer(output)

        if report_type == "summary":
            writer.writerow([
                "Switch Name", "Hostname", "Region", "Location", "Device Type",
                "Status", "Compliance %", "Total Rules", "Compliant", "Non-Compliant",
                "N/A", "Critical", "High", "Medium", "Low", "Timestamp"
            ])
            for report in audit_data.get("switch_reports", []):
                sev = report.get("severity_counts", {})
                writer.writerow([
                    report.get("switch_name", ""),
                    report.get("hostname", ""),
                    report.get("region", ""),
                    report.get("location", ""),
                    report.get("device_type", ""),
                    report.get("overall_status", "").replace("_", " ").title(),
                    report.get("compliance_percentage", 0),
                    report.get("total_rules", 0),
                    report.get("compliant_count", 0),
                    report.get("non_compliant_count", 0),
                    report.get("na_count", 0),
                    sev.get("critical", 0),
                    sev.get("high", 0),
                    sev.get("medium", 0),
                    sev.get("low", 0),
                    report.get("collection_timestamp", ""),
                ])
        else:  # detailed
            writer.writerow([
                "Switch Name", "Hostname", "Region", "Location",
                "Rule ID", "Category", "Description", "Severity",
                "Status", "Detail", "Remediation"
            ])
            for report in audit_data.get("switch_reports", []):
                for finding in report.get("all_findings", []):
                    writer.writerow([
                        report.get("switch_name", ""),
                        report.get("hostname", ""),
                        report.get("region", ""),
                        report.get("location", ""),
                        finding.get("rule_id", ""),
                        finding.get("category", ""),
                        finding.get("description", ""),
                        finding.get("severity", ""),
                        finding.get("status", ""),
                        finding.get("detail", ""),
                        finding.get("remediation", ""),
                    ])

        return output.getvalue()
