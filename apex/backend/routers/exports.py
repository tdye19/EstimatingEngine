"""Estimate export router — PDF and XLSX downloads."""

import io
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.estimate import Estimate
from apex.backend.models.project import Project
from apex.backend.models.organization import Organization
from apex.backend.models.user import User
from apex.backend.utils.auth import require_auth

router = APIRouter(prefix="/api/exports", tags=["exports"])


def _get_estimate_or_404(project_id: int, db: Session):
    project = db.query(Project).filter(
        Project.id == project_id,
        Project.is_deleted == False,  # noqa: E712
    ).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    estimate = db.query(Estimate).filter(
        Estimate.project_id == project_id,
        Estimate.is_deleted == False,  # noqa: E712
    ).order_by(Estimate.version.desc()).first()
    if not estimate:
        raise HTTPException(status_code=404, detail="No estimate available for this project")

    org = db.query(Organization).filter(Organization.id == project.organization_id).first()
    return project, estimate, org


# ─────────────────────────── PDF ───────────────────────────

@router.get("/projects/{project_id}/estimate/pdf")
def export_estimate_pdf(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable,
    )

    project, estimate, org = _get_estimate_or_404(project_id, db)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    APEX_BLUE = colors.HexColor("#1e40af")
    LIGHT_GRAY = colors.HexColor("#f1f5f9")
    MID_GRAY = colors.HexColor("#94a3b8")

    style_org = ParagraphStyle("org", parent=styles["Normal"], fontSize=9, textColor=MID_GRAY)
    style_title = ParagraphStyle("title", parent=styles["Normal"], fontSize=20, fontName="Helvetica-Bold", textColor=APEX_BLUE, spaceAfter=2)
    style_meta = ParagraphStyle("meta", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#475569"))
    style_section = ParagraphStyle("section", parent=styles["Normal"], fontSize=11, fontName="Helvetica-Bold", textColor=APEX_BLUE, spaceBefore=12, spaceAfter=6)
    style_footer = ParagraphStyle("footer", parent=styles["Normal"], fontSize=8, textColor=MID_GRAY, alignment=1)

    def fmt_dollar(val):
        return f"${val:,.0f}" if val is not None else "$0"

    def fmt_pct(val):
        return f"{val:.1f}%" if val is not None else "0.0%"

    story = []

    # ── Header ──
    org_name = org.name if org else "General Contractor"
    story.append(Paragraph(org_name.upper(), style_org))
    story.append(Spacer(1, 4))
    story.append(Paragraph(project.name, style_title))
    story.append(HRFlowable(width="100%", thickness=2, color=APEX_BLUE, spaceAfter=6))

    meta_text = (
        f"<b>Project #:</b> {project.project_number} &nbsp;&nbsp; "
        f"<b>Type:</b> {(project.project_type or '').title()} &nbsp;&nbsp; "
        f"<b>Location:</b> {project.location or '—'} &nbsp;&nbsp; "
        f"<b>Date:</b> {date.today().strftime('%B %d, %Y')}"
    )
    story.append(Paragraph(meta_text, style_meta))
    story.append(Spacer(1, 16))

    # ── Line Items Table ──
    story.append(Paragraph("Estimate Line Items", style_section))

    line_items = estimate.line_items or []

    # Group by division for subtotals
    divisions = {}
    for li in line_items:
        div = li.division_number or "00"
        if div not in divisions:
            divisions[div] = []
        divisions[div].append(li)

    col_widths = [0.45 * inch, 0.85 * inch, 2.5 * inch, 0.6 * inch, 0.45 * inch, 0.85 * inch, 0.85 * inch]
    header_row = [
        Paragraph("<b>Div</b>", styles["Normal"]),
        Paragraph("<b>CSI Code</b>", styles["Normal"]),
        Paragraph("<b>Description</b>", styles["Normal"]),
        Paragraph("<b>Qty</b>", styles["Normal"]),
        Paragraph("<b>Unit</b>", styles["Normal"]),
        Paragraph("<b>Unit Cost</b>", styles["Normal"]),
        Paragraph("<b>Total</b>", styles["Normal"]),
    ]

    tbl_data = [header_row]
    tbl_style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), APEX_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]

    row_idx = 1
    for div_num in sorted(divisions.keys()):
        items = divisions[div_num]
        div_total = 0
        for li in items:
            qty = li.quantity or 0
            unit_cost = li.unit_cost or 0
            total = li.total_cost or 0
            div_total += total
            tbl_data.append([
                li.division_number or "",
                li.csi_code or "",
                li.description or "",
                f"{qty:,.1f}",
                li.unit_of_measure or "",
                fmt_dollar(unit_cost),
                fmt_dollar(total),
            ])
            row_idx += 1

        # Subtotal row
        tbl_data.append([
            "", "", Paragraph(f"<b>Division {div_num} Subtotal</b>", styles["Normal"]),
            "", "", "", Paragraph(f"<b>{fmt_dollar(div_total)}</b>", styles["Normal"]),
        ])
        tbl_style_cmds.append(("BACKGROUND", (0, row_idx), (-1, row_idx), colors.HexColor("#dbeafe")))
        tbl_style_cmds.append(("FONTNAME", (0, row_idx), (-1, row_idx), "Helvetica-Bold"))
        row_idx += 1

    tbl = Table(tbl_data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle(tbl_style_cmds))
    story.append(tbl)
    story.append(Spacer(1, 20))

    # ── Summary Section ──
    story.append(Paragraph("Bid Summary", style_section))

    summary_rows = [
        [Paragraph("<b>Item</b>", styles["Normal"]), Paragraph("<b>Amount</b>", styles["Normal"])],
        ["Subtotal (Direct Cost)", fmt_dollar(estimate.total_direct_cost)],
        [f"Overhead ({fmt_pct(estimate.overhead_pct)})", fmt_dollar(estimate.overhead_amount)],
        [f"Profit ({fmt_pct(estimate.profit_pct)})", fmt_dollar(estimate.profit_amount)],
        [f"Contingency ({fmt_pct(estimate.contingency_pct)})", fmt_dollar(estimate.contingency_amount)],
    ]
    if estimate.bid_bond_required:
        summary_rows.append(["Bond", "Included"])

    summary_rows.append([
        Paragraph("<b>GRAND TOTAL BID</b>", styles["Normal"]),
        Paragraph(f"<b>{fmt_dollar(estimate.total_bid_amount)}</b>", styles["Normal"]),
    ])

    sum_tbl = Table(
        summary_rows,
        colWidths=[4.5 * inch, 1.5 * inch],
    )
    grand_row = len(summary_rows) - 1
    sum_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), APEX_BLUE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, grand_row - 1), [colors.white, LIGHT_GRAY]),
        ("BACKGROUND", (0, grand_row), (-1, grand_row), colors.HexColor("#1e3a8a")),
        ("TEXTCOLOR", (0, grand_row), (-1, grand_row), colors.white),
        ("FONTNAME", (0, grand_row), (-1, grand_row), "Helvetica-Bold"),
        ("FONTSIZE", (0, grand_row), (-1, grand_row), 11),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(sum_tbl)
    story.append(Spacer(1, 24))

    # ── Exclusions & Assumptions ──
    if estimate.exclusions:
        story.append(Paragraph("Exclusions", style_section))
        for ex in estimate.exclusions:
            story.append(Paragraph(f"• {ex}", styles["Normal"]))
        story.append(Spacer(1, 8))

    if estimate.assumptions:
        story.append(Paragraph("Assumptions", style_section))
        for asm in estimate.assumptions:
            story.append(Paragraph(f"• {asm}", styles["Normal"]))
        story.append(Spacer(1, 8))

    # ── Footer ──
    story.append(HRFlowable(width="100%", thickness=1, color=MID_GRAY, spaceBefore=12, spaceAfter=6))
    story.append(Paragraph(
        f"Prepared by {current_user.full_name} &nbsp;|&nbsp; Generated by APEX Estimating Platform",
        style_footer,
    ))

    doc.build(story)
    buf.seek(0)

    filename = f"{project.project_number}_estimate.pdf"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────── XLSX ───────────────────────────

@router.get("/projects/{project_id}/estimate/xlsx")
def export_estimate_xlsx(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_auth),
):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    project, estimate, org = _get_estimate_or_404(project_id, db)

    wb = Workbook()
    ws = wb.active
    ws.title = "Estimate"

    APEX_BLUE = "1E40AF"
    LIGHT_BLUE = "DBEAFE"
    LIGHT_GRAY = "F1F5F9"
    DARK_BLUE = "1E3A8A"
    WHITE = "FFFFFF"

    thin = Side(style="thin", color="CBD5E1")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def hdr_font(color="FFFFFF", size=10, bold=True):
        return Font(name="Calibri", bold=bold, color=color, size=size)

    def cell_font(bold=False, size=9):
        return Font(name="Calibri", bold=bold, size=size)

    def fill(hex_color):
        return PatternFill(fill_type="solid", fgColor=hex_color)

    def currency_fmt(ws, row, col):
        ws.cell(row=row, column=col).number_format = '"$"#,##0.00'

    # ── Rows 1-3: Header info ──
    org_name = org.name if org else "General Contractor"
    ws["A1"] = org_name
    ws["A1"].font = Font(name="Calibri", bold=True, size=14, color=APEX_BLUE)

    ws["A2"] = project.name
    ws["A2"].font = Font(name="Calibri", bold=True, size=12)

    ws["A3"] = (
        f"Project #: {project.project_number}  |  "
        f"Location: {project.location or '—'}  |  "
        f"Date: {date.today().strftime('%B %d, %Y')}"
    )
    ws["A3"].font = Font(name="Calibri", size=9, color="64748B")

    # Merge header cells across table width (8 cols)
    for row in [1, 2, 3]:
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)

    ws.row_dimensions[4].height = 6  # blank spacer

    # ── Row 5: Column headers ──
    headers = ["Item #", "CSI Code", "Description", "Quantity", "Unit", "Unit Cost", "Total", "Notes"]
    for col, hdr in enumerate(headers, start=1):
        c = ws.cell(row=5, column=col, value=hdr)
        c.font = hdr_font()
        c.fill = fill(APEX_BLUE)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        c.border = border

    ws.row_dimensions[5].height = 18

    # ── Data rows (starting at row 6) ──
    line_items = estimate.line_items or []

    # Group by division
    divisions = {}
    for li in line_items:
        div = li.division_number or "00"
        if div not in divisions:
            divisions[div] = []
        divisions[div].append(li)

    current_row = 6
    item_num = 1
    data_start_rows = {}  # div -> (first_data_row, last_data_row)

    row_bg = [LIGHT_GRAY, WHITE]

    for div_num in sorted(divisions.keys()):
        items = divisions[div_num]
        div_first = current_row

        for li in items:
            bg = row_bg[(current_row - 6) % 2]
            ws.cell(row=current_row, column=1, value=item_num).font = cell_font()
            ws.cell(row=current_row, column=2, value=li.csi_code or "").font = cell_font()
            ws.cell(row=current_row, column=3, value=li.description or "").font = cell_font()
            ws.cell(row=current_row, column=4, value=li.quantity or 0).font = cell_font()
            ws.cell(row=current_row, column=5, value=li.unit_of_measure or "").font = cell_font()
            ws.cell(row=current_row, column=6, value=li.unit_cost or 0).font = cell_font()
            ws.cell(row=current_row, column=7, value=li.total_cost or 0).font = cell_font()
            ws.cell(row=current_row, column=8, value=li.notes or "").font = cell_font()

            ws.cell(row=current_row, column=6).number_format = '"$"#,##0.00'
            ws.cell(row=current_row, column=7).number_format = '"$"#,##0.00'

            for col in range(1, 9):
                c = ws.cell(row=current_row, column=col)
                c.fill = fill(bg)
                c.border = border
                c.alignment = Alignment(vertical="center")

            ws.cell(row=current_row, column=4).alignment = Alignment(horizontal="right", vertical="center")
            ws.cell(row=current_row, column=6).alignment = Alignment(horizontal="right", vertical="center")
            ws.cell(row=current_row, column=7).alignment = Alignment(horizontal="right", vertical="center")

            item_num += 1
            current_row += 1

        data_start_rows[div_num] = (div_first, current_row - 1)

        # Division subtotal row with SUM formula
        div_last = current_row - 1
        subtotal_col_g = f"G{div_first}:G{div_last}"
        ws.cell(row=current_row, column=3, value=f"Division {div_num} Subtotal").font = hdr_font(color=APEX_BLUE, size=9)
        ws.cell(row=current_row, column=7, value=f"=SUM({subtotal_col_g})").font = hdr_font(color=APEX_BLUE, size=9)
        ws.cell(row=current_row, column=7).number_format = '"$"#,##0.00'

        for col in range(1, 9):
            c = ws.cell(row=current_row, column=col)
            c.fill = fill(LIGHT_BLUE)
            c.border = border
            c.alignment = Alignment(vertical="center")
        ws.cell(row=current_row, column=7).alignment = Alignment(horizontal="right", vertical="center")

        current_row += 1

    # ── Summary section ──
    current_row += 1  # blank row
    summary_start = current_row

    def sum_row(label, formula_or_val, is_pct=False, bold=False, bg=WHITE, text_color="000000"):
        ws.cell(row=current_row, column=6, value=label).font = Font(name="Calibri", bold=bold, size=9, color=text_color)
        c = ws.cell(row=current_row, column=7, value=formula_or_val)
        c.font = Font(name="Calibri", bold=bold, size=9, color=text_color)
        if not is_pct:
            c.number_format = '"$"#,##0.00'
        c.alignment = Alignment(horizontal="right", vertical="center")
        for col in [6, 7]:
            ws.cell(row=current_row, column=col).fill = fill(bg)
            ws.cell(row=current_row, column=col).border = border

    # Collect all division subtotal rows to build the overall subtotal formula
    div_subtotal_row_refs = []
    row_scan = 6
    while row_scan < summary_start:
        val = ws.cell(row=row_scan, column=3).value
        if val and isinstance(val, str) and "Subtotal" in val:
            div_subtotal_row_refs.append(f"G{row_scan}")
        row_scan += 1

    subtotal_formula = "=" + "+".join(div_subtotal_row_refs) if div_subtotal_row_refs else "=0"

    overhead_pct = (estimate.overhead_pct or 0) / 100
    profit_pct = (estimate.profit_pct or 0) / 100
    contingency_pct = (estimate.contingency_pct or 0) / 100

    subtotal_ref = f"G{current_row}"
    sum_row(f"Subtotal (Direct Cost)", subtotal_formula, bg=LIGHT_GRAY, bold=True)
    current_row += 1

    overhead_ref = f"G{current_row}"
    sum_row(f"Overhead ({estimate.overhead_pct or 0:.1f}%)", f"={subtotal_ref}*{overhead_pct}", bg=LIGHT_GRAY)
    current_row += 1

    profit_ref = f"G{current_row}"
    sum_row(f"Profit ({estimate.profit_pct or 0:.1f}%)", f"=({subtotal_ref}+{overhead_ref})*{profit_pct}", bg=LIGHT_GRAY)
    current_row += 1

    contingency_ref = f"G{current_row}"
    sum_row(f"Contingency ({estimate.contingency_pct or 0:.1f}%)", f"=({subtotal_ref}+{overhead_ref}+{profit_ref})*{contingency_pct}", bg=LIGHT_GRAY)
    current_row += 1

    sum_row(
        "GRAND TOTAL BID",
        f"={subtotal_ref}+{overhead_ref}+{profit_ref}+{contingency_ref}",
        bold=True, bg=DARK_BLUE, text_color=WHITE,
    )
    for col in [6, 7]:
        ws.cell(row=current_row, column=col).font = Font(name="Calibri", bold=True, size=11, color=WHITE)
    current_row += 1

    # ── Column widths ──
    col_widths = [7, 12, 45, 10, 8, 14, 14, 20]
    for i, w in enumerate(col_widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # ── Freeze panes ──
    ws.freeze_panes = "A6"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"{project.project_number}_estimate.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
