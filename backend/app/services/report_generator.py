
from io import BytesIO
from datetime import datetime, timezone
from xml.sax.saxutils import escape
from pathlib import Path
import os
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)


def _register_report_fonts() -> tuple[str, str]:
    registered_fonts = pdfmetrics.getRegisteredFontNames()

    if "ContractReview-Regular" in registered_fonts:
        return "ContractReview-Regular", "ContractReview-Bold"

    font_pairs = [
        (
            os.getenv("REPORT_FONT_REGULAR"),
            os.getenv("REPORT_FONT_BOLD"),
        ),
        (
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
        ),
        (
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ),
        (
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ),
    ]

    for regular_path, bold_path in font_pairs:
        if (
            regular_path
            and bold_path
            and Path(regular_path).is_file()
            and Path(bold_path).is_file()
        ):
            pdfmetrics.registerFont(
                TTFont("ContractReview-Regular", regular_path)
            )
            pdfmetrics.registerFont(
                TTFont("ContractReview-Bold", bold_path)
            )
            return "ContractReview-Regular", "ContractReview-Bold"

    return "Helvetica", "Helvetica-Bold"


def generate_analysis_pdf(
    filename: str,
    document: dict,
    summary: dict,
    clauses: list[dict],
    findings: list[dict],
    policy_checks: list[dict],
    policy_filename: str | None = None,
) -> BytesIO:
    """Generate a PDF report with contract and policy evidence traceability."""

    regular_font, bold_font = _register_report_fonts()

    output = BytesIO()

    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=0.60 * inch,
        leftMargin=0.60 * inch,
        topMargin=0.60 * inch,
        bottomMargin=0.60 * inch,
        title="Contract Analysis Report",
        author="Contract Review System",
    )

    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            fontName=bold_font,
            fontSize=19,
            leading=23,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#17365D"),
            spaceAfter=8,
        )
    )

    styles.add(
        ParagraphStyle(
            name="ReportSubtitle",
            parent=styles["BodyText"],
            fontName=regular_font,
            fontSize=9,
            leading=12,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#555555"),
            spaceAfter=12,
        )
    )

    styles.add(
        ParagraphStyle(
            name="SectionHeading",
            parent=styles["Heading2"],
            fontName=bold_font,
            fontSize=12,
            leading=15,
            textColor=colors.HexColor("#17365D"),
            spaceBefore=12,
            spaceAfter=7,
            keepWithNext=True,
        )
    )

    styles.add(
        ParagraphStyle(
            name="BodySmall",
            parent=styles["BodyText"],
            fontName=regular_font,
            fontSize=8.5,
            leading=11,
            spaceAfter=4,
            splitLongWords=1,
        )
    )

    styles.add(
        ParagraphStyle(
            name="TableCell",
            parent=styles["BodyText"],
            fontName=regular_font,
            fontSize=8,
            leading=10,
            spaceAfter=0,
            splitLongWords=1,
        )
    )

    styles.add(
        ParagraphStyle(
            name="CardHeading",
            parent=styles["Heading4"],
            fontName=bold_font,
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#17365D"),
            spaceAfter=4,
            keepWithNext=True,
        )
    )

    styles.add(
        ParagraphStyle(
            name="CardBody",
            parent=styles["BodyText"],
            fontName=regular_font,
            fontSize=8.3,
            leading=11,
            spaceAfter=4,
            splitLongWords=1,
        )
    )

    def safe_text(value) -> str:
        """Escape text before placing it in a ReportLab paragraph."""
        return escape(str(value if value is not None else ""))

    def clean_heading(value) -> str:
        """Remove existing numbering from headings."""
        heading = str(value if value is not None else "").strip()

        heading = re.sub(
            r"^\s*\d+\s*[\.\)\-:]\s*",
            "",
            heading,
        )

        return heading or "Untitled"

    def cell(value) -> Paragraph:
        return Paragraph(safe_text(value), styles["TableCell"])

    def source_text(item: dict) -> str:
        """Return contract source locations."""
        locations = item.get("source_locations", [])

        if not isinstance(locations, list):
            locations = [locations]

        return (
            ", ".join(str(location) for location in locations)
            or "Not specified"
        )

    def policy_source_text(item: dict) -> str:
        """Return reference policy source locations."""
        locations = item.get("policy_source_locations", [])

        if not isinstance(locations, list):
            locations = [locations]

        return (
            ", ".join(str(location) for location in locations)
            or "Not specified"
        )

    def add_section(title: str) -> None:
        story.append(
            Paragraph(safe_text(title), styles["SectionHeading"])
        )

    def add_detail(label: str, value) -> Paragraph:
        value_text = str(value if value is not None else "").strip()

        if not value_text:
            value_text = "Not specified"

        return Paragraph(
            f"<b>{safe_text(label)}:</b> {safe_text(value_text)}",
            styles["CardBody"],
        )

    story = []

    # ---------------------------------------------------------
    # Report title
    # ---------------------------------------------------------
    story.append(
        Paragraph("Contract Analysis Report", styles["ReportTitle"])
    )

    story.append(
        Paragraph(
            "Agentic AI Contract Review &amp; Risk Identification System",
            styles["ReportSubtitle"],
        )
    )

    # ---------------------------------------------------------
    # Document metadata
    # ---------------------------------------------------------
    metadata = [
        [cell("Contract file"), cell(filename)],
    ]

    if policy_filename:
        metadata.append(
            [cell("Reference policy"), cell(policy_filename)]
        )

    metadata.extend(
        [
            [
                cell("Document type"),
                cell(document.get("file_type", "Unknown")),
            ],
            [
                cell("Extracted sections"),
                cell(document.get("section_count", 0)),
            ],
            [
                cell("Report generated (UTC)"),
                cell(
                    datetime.now(timezone.utc).strftime(
                        "%Y-%m-%d %H:%M UTC"
                    )
                ),
            ],
        ]
    )

    metadata_table = Table(
        metadata,
        colWidths=[1.65 * inch, 4.95 * inch],
        hAlign="LEFT",
    )

    metadata_table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (0, -1),
                    colors.HexColor("#EAF0F8"),
                ),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    story.append(metadata_table)
    story.append(Spacer(1, 5))

    # ---------------------------------------------------------
    # 1. Executive summary
    # ---------------------------------------------------------
    add_section("1. Executive Summary")
    review_status = str(
        summary.get("review_status", "human_review_required")
    ).replace("_", " ").title()
    story.append(
        Paragraph(
            f"<b>Overall review status:</b> {safe_text(review_status)}",
            styles["BodySmall"],
        )
    )

    risk_summary = summary.get("risk_severity", {})
    policy_summary = summary.get("policy_results", {})

    summary_rows = [
        [cell("Metric"), cell("Count")],
        [
            cell("Clauses extracted"),
            cell(summary.get("total_clauses", 0)),
        ],
        [
            cell("Potential risk findings"),
            cell(summary.get("total_risk_findings", 0)),
        ],
        [
            cell("High-severity flags"),
            cell(risk_summary.get("high", 0)),
        ],
        [
            cell("Medium-severity flags"),
            cell(risk_summary.get("medium", 0)),
        ],
        [
            cell("Low-severity flags"),
            cell(risk_summary.get("low", 0)),
        ],
        [
            cell("Confirmed policy deviations"),
            cell(policy_summary.get("deviations_detected", 0)),
        ],
        [
            cell("Missing clause categories"),
            cell(policy_summary.get("missing_clauses", 0)),
        ],
        [
            cell("Policy checks requiring human review"),
            cell(policy_summary.get("needs_review", 0)),
        ],
        [
            cell("Checks with no deviation detected"),
            cell(policy_summary.get("no_deviation_detected", 0)),
        ],
    ]

    summary_table = Table(
        summary_rows,
        colWidths=[4.8 * inch, 1.8 * inch],
        repeatRows=1,
        hAlign="LEFT",
    )

    summary_table.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, 0),
                    colors.HexColor("#17365D"),
                ),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.lightgrey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 7),
                ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    story.append(summary_table)

    # ---------------------------------------------------------
    # 2. Extracted clauses
    # ---------------------------------------------------------
    add_section("2. Extracted Clauses")

    if clauses:
        for index, clause in enumerate(clauses, start=1):
            heading = clean_heading(
                clause.get("heading", "Untitled clause")
            )

            block = [
                Paragraph(
                    f"{index}. {safe_text(heading)}",
                    styles["CardHeading"],
                ),
                add_detail("Category", clause.get("category", "other")),
                add_detail("Source", source_text(clause)),
                add_detail("Text", clause.get("clause_text", "")),
                Spacer(1, 6),
            ]

            story.append(KeepTogether(block))
    else:
        story.append(
            Paragraph("No clauses were extracted.", styles["BodySmall"])
        )

    # ---------------------------------------------------------
    # 3. Potential risk findings
    # ---------------------------------------------------------
    add_section("3. Potential Risk Findings")

    if findings:
        for index, finding in enumerate(findings, start=1):
            heading = clean_heading(
                finding.get("clause_heading", "Unknown")
            )

            risk_type = finding.get("risk_type", "Unknown")

            severity = str(
                finding.get("severity", "Unknown")
            ).upper()

            severity_colors = {
                "HIGH": colors.HexColor("#B42318"),
                "MEDIUM": colors.HexColor("#9A6700"),
                "LOW": colors.HexColor("#237A57"),
            }

            severity_color = severity_colors.get(
                severity,
                colors.HexColor("#555555"),
            )

            risk_title = Paragraph(
                f"{index}. {safe_text(heading)} — "
                f"{safe_text(risk_type)}",
                styles["CardHeading"],
            )

            severity_line = Paragraph(
                f'<b>Severity:</b> <font color="{severity_color.hexval()}">'
                f"{safe_text(severity)}</font>",
                styles["CardBody"],
            )

            risk_block = [
                risk_title,
                severity_line,
                add_detail("Evidence", finding.get("evidence", "")),
                add_detail("Description", finding.get("description", "")),
                add_detail(
                    "Recommendation",
                    finding.get("recommendation", ""),
                ),
                add_detail("Source", source_text(finding)),
                add_detail(
                    "Review status",
                    finding.get("review_status", "pending"),
                ),
                Spacer(1, 8),
            ]

            story.append(KeepTogether(risk_block))
    else:
        story.append(
            Paragraph(
                "No potential risks were flagged by the current rules.",
                styles["BodySmall"],
            )
        )

    # ---------------------------------------------------------
    # 4. Policy comparison with evidence traceability
    # ---------------------------------------------------------
    add_section("4. Policy Comparison")

    if policy_checks:
        for index, item in enumerate(policy_checks, start=1):
            status = str(item.get("status", "Unknown"))
            category = item.get("category", "Unknown")

            policy_title = Paragraph(
                f"{index}. {safe_text(category)}",
                styles["CardHeading"],
            )

            status_line = Paragraph(
                f"<b>Status:</b> {safe_text(status)}",
                styles["CardBody"],
            )

            reviewer_items = summary.get(
                "reviewer_result", {}
            ).get("items", [])

            verification_status = next(
                (
                    review_item.get("policy_evidence_verification")
                    for review_item in reviewer_items
                    if review_item.get("item_type") == "policy_check"
                    and review_item.get("item") == item.get("category")
                ),
                item.get(
                    "policy_evidence_review_status",
                    "not_available",
                ),
            )

            policy_block = [
                policy_title,
                status_line,
                add_detail(
                    "Policy requirement",
                    item.get("policy_requirement", ""),
                ),
                add_detail(
                    "Explanation",
                    item.get("explanation", ""),
                ),
                add_detail(
                    "Difference",
                    item.get("difference", ""),
                ),
                add_detail(
                    "Contract evidence",
                    item.get("evidence", ""),
                ),
                add_detail(
                    "Contract source location",
                    source_text(item),
                ),
                add_detail(
                    "Reference policy evidence",
                    item.get("policy_evidence", ""),
                ),
                add_detail(
                    "Policy source location",
                    policy_source_text(item),
                ),
                add_detail(
                    "Finding review status",
                    item.get("review_status", "pending"),
                ),
                add_detail(
                    "Policy evidence verification",
                    verification_status,
                ),
                Spacer(1, 8),
            ]

            story.append(KeepTogether(policy_block))
    else:
        story.append(
            Paragraph(
                "No policy comparison results are available.",
                styles["BodySmall"],
            )
        )

    # ---------------------------------------------------------
    # 5. Decision reviewer results
    # ---------------------------------------------------------
    review = summary.get("reviewer_result")

    if review:
        add_section("5. Decision Reviewer Results")

        story.append(
            add_detail("Overall status", review.get("status", "Not available"))
        )
        story.append(
            add_detail("Clauses reviewed", review.get("clause_count", 0))
        )
        story.append(
            add_detail(
                "Risk findings reviewed",
                review.get("risk_finding_count", 0),
            )
        )
        story.append(
            add_detail(
                "Policy checks reviewed",
                review.get("policy_check_count", 0),
            )
        )
        story.append(
            add_detail(
                "Human review required",
                review.get("human_review_required", True),
            )
        )

        llm_review = review.get("llm_review", {})
        if llm_review:
            story.append(
                add_detail(
                    "LLM evidence review status",
                    llm_review.get("status", "not_available"),
                )
            )
            story.append(
                add_detail(
                    "LLM provider model",
                    llm_review.get("model", "not configured"),
                )
            )
            story.append(
                add_detail(
                    "Findings reviewed by LLM",
                    llm_review.get("reviewed_count", 0),
                )
            )
            story.append(
                add_detail(
                    "Findings not reviewed by LLM",
                    llm_review.get("not_reviewed_count", 0),
                )
            )

        items = review.get("items", [])

        if items:
            story.append(Spacer(1, 5))
            story.append(
                Paragraph(
                    "<b>Evidence verification details</b>",
                    styles["CardHeading"],
                )
            )

            for index, item in enumerate(items, start=1):
                item_name = item.get("item", "Unknown review item")
                item_type = item.get("item_type", "unknown")

                story.append(
                    Paragraph(
                        f"{index}. {safe_text(item_name)}",
                        styles["CardHeading"],
                    )
                )

                story.append(add_detail("Item type", item_type))

                story.append(
                    add_detail(
                        "Comparison status",
                        item.get("comparison_status", "Not applicable"),
                    )
                )

                story.append(
                    add_detail(
                        "Evidence provided",
                        item.get("evidence_present", "Not applicable")
                        if item_type == "risk_finding"
                        else item.get(
                            "contract_evidence_present",
                            "Not available",
                        ),
                    )
                )

                story.append(
                    add_detail(
                        "Evidence found in contract",
                        item.get("evidence_found_in_contract", False)
                        if item_type == "risk_finding"
                        else item.get("contract_evidence_found", False),
                    )
                )

                if item_type == "policy_check":
                    story.append(
                        add_detail(
                            "Policy evidence provided",
                            item.get("policy_evidence_present", False),
                        )
                    )

                    story.append(
                        add_detail(
                            "Policy evidence found",
                            item.get("policy_evidence_found", False),
                        )
                    )

                    story.append(
                        add_detail(
                            "Policy evidence verification",
                            item.get(
                                "policy_evidence_verification",
                                "not_available",
                            ),
                        )
                    )

                story.append(
                    add_detail(
                        "Review status",
                        item.get("review_status", "pending"),
                    )
                )

                story.append(
                    add_detail(
                        "Verification note",
                        item.get(
                            "verification_note",
                            "Text-presence check only; human review required.",
                        ),
                    )
                )

                llm_item_review = item.get("llm_review")
                if llm_item_review:
                    story.append(
                        add_detail(
                            "LLM assessment",
                            llm_item_review.get("verdict", "uncertain"),
                        )
                    )
                    story.append(
                        add_detail(
                            "LLM rationale",
                            llm_item_review.get("rationale", ""),
                        )
                    )
                    if llm_item_review.get("contract_quote"):
                        story.append(
                            add_detail(
                                "LLM contract quote",
                                (
                                    f"{llm_item_review['contract_quote']} "
                                    f"(verified: "
                                    f"{llm_item_review.get('contract_quote_verified', False)})"
                                ),
                            )
                        )
                    if llm_item_review.get("policy_quote"):
                        story.append(
                            add_detail(
                                "LLM policy quote",
                                (
                                    f"{llm_item_review['policy_quote']} "
                                    f"(verified: "
                                    f"{llm_item_review.get('policy_quote_verified', False)})"
                                ),
                            )
                        )

                story.append(Spacer(1, 4))

        if review.get("notice"):
            story.append(
                Paragraph(
                    safe_text(review["notice"]),
                    styles["BodySmall"],
                )
            )

    # ---------------------------------------------------------
    # 6. Important notice
    # ---------------------------------------------------------
    add_section("6. Important Notice")

    if policy_filename:
        disclaimer = (
            "This report contains preliminary, rule-based findings. "
            "Rules inferred from the supplied reference policy are drafts "
            "and require human confirmation. Results may be incomplete "
            "or incorrect and must be reviewed by an appropriately "
            "qualified person. This report is not legal advice."
        )
    else:
        disclaimer = (
            "This report contains preliminary, rule-based findings. "
            "The default policy is illustrative. Results may be incomplete "
            "or incorrect and must be reviewed by an appropriately "
            "qualified person. This report is not legal advice."
        )

    story.append(
        Paragraph(safe_text(disclaimer), styles["BodySmall"])
    )

    # ---------------------------------------------------------
    # Footer: page number
    # ---------------------------------------------------------
    def add_page_number(canvas, document):
        canvas.saveState()
        canvas.setFont(regular_font, 8)
        canvas.setFillColor(colors.grey)

        canvas.drawCentredString(
            A4[0] / 2,
            0.32 * inch,
            f"Page {document.page}",
        )

        canvas.restoreState()

    doc.build(
        story,
        onFirstPage=add_page_number,
        onLaterPages=add_page_number,
    )

    output.seek(0)
    return output
