"""Presentable PDF rendering for DeepTrace forensic reports.

The Section 65B page is deliberately a draft: DeepTrace prepares factual and
technical content but does not certify or sign evidence on behalf of a human
custodian or investigating officer.
"""

from __future__ import annotations

import html
import os
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


NAVY = colors.HexColor("#17202D")
BLUE = colors.HexColor("#1F6FEB")
MUTED = colors.HexColor("#687386")
LINE = colors.HexColor("#DDE3EA")
PALE_BLUE = colors.HexColor("#EDF4FF")
PALE_RED = colors.HexColor("#FFF1F1")


def _text(value: Any) -> str:
    return html.escape(str(value if value is not None else "-"))


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("CoverTitle", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=26, leading=31, textColor=NAVY, spaceAfter=10))
    styles.add(ParagraphStyle("Subtitle", parent=styles["Normal"], fontName="Helvetica", fontSize=11, leading=16, textColor=MUTED))
    styles.add(ParagraphStyle("Section", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=18, leading=23, textColor=NAVY, spaceBefore=2, spaceAfter=12))
    styles.add(ParagraphStyle("Subsection", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=15, textColor=NAVY, spaceBefore=9, spaceAfter=7))
    styles.add(ParagraphStyle("BodySmall", parent=styles["BodyText"], fontName="Helvetica", fontSize=9, leading=13, textColor=NAVY))
    styles.add(ParagraphStyle("MutedSmall", parent=styles["BodyText"], fontName="Helvetica", fontSize=8, leading=11, textColor=MUTED))
    styles.add(ParagraphStyle("Mono", parent=styles["BodyText"], fontName="Courier", fontSize=7.5, leading=10, textColor=NAVY))
    styles.add(ParagraphStyle("TableHead", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=7.5, leading=9, textColor=colors.white))
    styles.add(ParagraphStyle("TableCell", parent=styles["BodyText"], fontName="Helvetica", fontSize=7.5, leading=10, textColor=NAVY))
    styles.add(ParagraphStyle("Disclaimer", parent=styles["BodyText"], fontName="Helvetica-Bold", fontSize=9, leading=14, textColor=colors.HexColor("#8E3333"), alignment=TA_LEFT))
    return styles


def _p(value: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_text(value), style)


def _table(data: list[list[Any]], widths: list[float], styles, header: bool = True) -> Table:
    converted = []
    for row_index, row in enumerate(data):
        row_style = styles["TableHead"] if header and row_index == 0 else styles["TableCell"]
        converted.append([_p(cell, row_style) for cell in row])
    table = Table(converted, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    commands = [
        ("GRID", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]
    if header:
        commands += [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
        if len(data) > 1:
            commands.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]))
    table.setStyle(TableStyle(commands))
    return table


def _label_value_rows(rows: list[tuple[str, Any]], styles) -> Table:
    data = [[_p(label, styles["MutedSmall"]), _p(value, styles["BodySmall"])] for label, value in rows]
    table = Table(data, colWidths=[48 * mm, 125 * mm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.35, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table


def _footer(canvas, document) -> None:
    canvas.saveState()
    canvas.setStrokeColor(LINE)
    canvas.line(20 * mm, 14 * mm, 190 * mm, 14 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(20 * mm, 9 * mm, "DeepTrace | Forensic recovery report | DRAFT 65B CONTENT")
    canvas.drawRightString(190 * mm, 9 * mm, f"Page {document.page}")
    canvas.restoreState()


def render_pdf(report: dict[str, Any], out_path: str) -> None:
    """Render a forensic report and draft Section 65B content as a PDF."""
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    styles = _styles()
    document = SimpleDocTemplate(
        out_path,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=21 * mm,
        title="DeepTrace Forensic Report",
        author="DeepTrace",
    )
    disk = report.get("disk_metadata", {})
    device = report.get("device_identification", {})
    stats = report.get("recovery_stats", {})
    rate = stats.get("recovery_rate", {}).get("recovery_rate_pct", "N/A")
    case = report.get("case_metadata", {})
    custody = report.get("chain_of_custody", {})
    story = []

    story += [Spacer(1, 20 * mm), _p("DEEPTRACE", styles["CoverTitle"]), _p("FORENSIC EVIDENCE RECOVERY REPORT", styles["Subtitle"]), Spacer(1, 10 * mm), HRFlowable(width="100%", thickness=2, color=BLUE), Spacer(1, 13 * mm)]
    story.append(_p("Case reference", styles["Section"]))
    story.append(_label_value_rows([
        ("Case number", case.get("case_number", "UNKNOWN_CASE")),
        ("Source image", disk.get("filename")),
        ("Source SHA-256", disk.get("sha256")),
        ("Processed", disk.get("processed_at")),
        ("Tool", report.get("tool")),
    ], styles))
    story += [Spacer(1, 18 * mm), _p("Technical findings prepared for human review", styles["Subsection"]), _p("This report records the technical output of a read-only recovery process. It is not a legal opinion and the Section 65B material included later is a draft requiring review and signature by the appropriate human custodian.", styles["BodySmall"]), PageBreak()]

    story += [_p("Recovery summary", styles["Section"]), _p(f"{_text(device.get('vendor_name', 'Unknown'))} parser identified the source format with {_text(device.get('detection_confidence', 'unknown'))} confidence.", styles["BodySmall"]), Spacer(1, 7 * mm)]
    story.append(_table([
        ["Metric", "Result", "Interpretation"],
        ["Recovery rate", f"{rate}%", "Recovered valid frames against available ground truth when present"],
        ["Frames scanned", stats.get("total_frames_scanned", 0), "Candidate frame records examined"],
        ["Valid frames", stats.get("valid_frames", 0), "Frames passing format and integrity checks"],
        ["Rejected / false-positive estimate", stats.get("invalid_frames", 0), "Candidates rejected by parser validation"],
        ["Sequences", stats.get("sequences_found", 0), "Contiguous reconstructed timelines"],
        ["Gaps detected", stats.get("gaps_detected", 0), "Temporal or frame-number discontinuities"],
    ], [53 * mm, 30 * mm, 87 * mm], styles))
    story += [Spacer(1, 9 * mm), _p("Rejection reasons", styles["Subsection"])]
    reasons = [["Reason", "Count"]] + [[reason, count] for reason, count in stats.get("invalid_by_rejection_reason", {}).items()]
    story.append(_table(reasons, [125 * mm, 45 * mm], styles))
    story.append(PageBreak())

    story += [_p("Recovered evidence index", styles["Section"]), _p("Every output artifact is listed below with its forensic hashes and time range.", styles["BodySmall"]), Spacer(1, 6 * mm)]
    evidence = [["Filename", "Timestamp range", "Frames", "SHA-256", "MD5"]]
    for item in report.get("recovered_files", []):
        evidence.append([item.get("filename"), f"{item.get('start_ts')}\nto\n{item.get('end_ts')}", item.get("frame_count"), item.get("sha256"), item.get("md5")])
    if len(evidence) == 1:
        evidence.append(["No recovered artifacts", "-", "0", "-", "-"])
    story.append(_table(evidence, [39 * mm, 39 * mm, 16 * mm, 45 * mm, 40 * mm], styles))
    story.append(PageBreak())

    story += [_p("Methodology appendix", styles["Section"]), _p("Signature detection scans the source image for vendor-specific markers and frame magic, allowing the correct parser to be selected without modifying the original media. Dual-signature validation checks independent header and footer markers, declared sizes, and checksums before a frame is accepted. Adaptive temporal sequencing orders valid frames by channel and timestamp, learns the running median inter-frame interval, and flags unusually large time or frame-number discontinuities as gaps. Invalid candidates remain visible in the report so rejection and recovery statistics retain their evidentiary denominator.", styles["BodySmall"]), Spacer(1, 8 * mm), _p("Processing record", styles["Subsection"]), _label_value_rows([
        ("Device", f"{device.get('vendor_name', 'Unknown')} DVR/NVR"),
        ("Signature offset", device.get("signature_found_at_offset", "-")),
        ("Source hash", custody.get("source_image_sha256", disk.get("sha256"))),
        ("Read-only statement", custody.get("processing_note", "-")),
    ], styles), PageBreak()]

    story += [_p("Draft Section 65B Certificate", styles["Section"]), _p("Technical content for review and completion by the person in lawful control of the source device or system.", styles["Subtitle"]), Spacer(1, 8 * mm)]
    story.append(_label_value_rows([
        ("Case reference", case.get("case_number", "")),
        ("Device / system", f"{device.get('vendor_name', 'Unknown')} DVR/NVR"),
        ("Source filename", disk.get("filename", "")),
        ("Source SHA-256", disk.get("sha256", "")),
        ("Extraction date/time", report.get("generated_at", "")),
        ("Examiner / custodian name", "________________________________________"),
        ("Designation / address", "________________________________________"),
    ], styles))
    story += [Spacer(1, 9 * mm), _p("Draft factual statement", styles["Subsection"]), _p("The undersigned human custodian may review and, if accurate, attest that the electronic record identified above was recovered from the stated source using the DeepTrace read-only process described in this report. The custodian must independently verify the device, circumstances, hash values, and all other facts before signing.", styles["BodySmall"]), Spacer(1, 10 * mm)]
    disclaimer = Table([[_p("DRAFT ONLY - REQUIRES HUMAN REVIEW AND SIGNATURE\n\nThis is a draft prepared by DeepTrace for review. It must be reviewed and signed by the person in lawful control of the source device/system before submission as evidence under Section 65B, Indian Evidence Act. DeepTrace cannot legally issue this certificate and does not certify the evidence itself.", styles["Disclaimer"])]], colWidths=[170 * mm])
    disclaimer.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PALE_RED), ("BOX", (0, 0), (-1, -1), 1.1, colors.HexColor("#C85A5A")), ("LEFTPADDING", (0, 0), (-1, -1), 11), ("RIGHTPADDING", (0, 0), (-1, -1), 11), ("TOPPADDING", (0, 0), (-1, -1), 11), ("BOTTOMPADDING", (0, 0), (-1, -1), 11)]))
    story += [disclaimer, Spacer(1, 17 * mm), _table([["Signature of lawful custodian / investigating officer", "Date"], ["\n\n________________________________________", "\n\n__________________"]], [120 * mm, 50 * mm], styles, header=False), Spacer(1, 10 * mm), _p("This page is intentionally unsigned. Completion, legal review, and signature remain the responsibility of the appropriate human custodian.", styles["MutedSmall"])]

    document.build(story, onFirstPage=_footer, onLaterPages=_footer)
