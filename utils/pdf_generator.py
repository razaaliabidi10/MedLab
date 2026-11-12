import io
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, KeepTogether
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, mm


def generate_diagnostic_report_pdf(booking, items, results_by_item=None):
    """
    Generates a professional, clinical diagnostic laboratory report in PDF format
    using ReportLab Platypus.
    
    Args:
        booking (dict): Booking record with patient details and release info.
        items (list of dict): Booking items (tests, specimen type, barcode).
        results_by_item (dict): Map of item_id -> list of result dicts (measured_value, unit, min_range, max_range, flag_status).
    
    Returns:
        bytes: Compiled PDF binary data.
    """
    buf = io.BytesIO()
    
    # 36pt = 0.5 inch margins
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Custom typography
    c_primary = colors.HexColor('#166534')      # Clinical Forest Green
    c_dark = colors.HexColor('#0F172A')         # Slate 900
    c_slate = colors.HexColor('#475569')        # Slate 600
    c_border = colors.HexColor('#E2E8F0')       # Slate 200
    c_bg_light = colors.HexColor('#F8FAFC')     # Slate 50
    c_green_bg = colors.HexColor('#DCFCE7')     # Green tint
    c_flag_high = colors.HexColor('#DC2626')     # Red
    c_flag_low = colors.HexColor('#D97706')      # Amber
    c_flag_normal = colors.HexColor('#166534')   # Green

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        leading=24,
        textColor=c_primary,
        spaceAfter=2
    )

    sub_style = ParagraphStyle(
        'DocSub',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=c_slate
    )

    badge_style = ParagraphStyle(
        'DocBadge',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=12,
        textColor=c_primary,
        alignment=2 # Right
    )

    ref_style = ParagraphStyle(
        'DocRef',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=c_dark,
        alignment=2 # Right
    )

    section_header_style = ParagraphStyle(
        'SectionHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=c_primary,
        textTransform='uppercase',
        spaceAfter=4
    )

    label_style = ParagraphStyle(
        'MetaLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=7.5,
        leading=9.5,
        textColor=c_slate
    )

    val_style = ParagraphStyle(
        'MetaVal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=c_dark
    )

    tbl_header_style = ParagraphStyle(
        'TblHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=colors.white
    )

    tbl_cell_style = ParagraphStyle(
        'TblCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=c_dark
    )

    tbl_cell_bold = ParagraphStyle(
        'TblCellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=10,
        textColor=c_dark
    )

    elements = []

    # ── 1. Top Header & Logo ──
    header_data = [
        [
            Paragraph("<b>MedLab Diagnostics</b>", title_style),
            Paragraph("OFFICIAL DIAGNOSTIC REPORT", badge_style)
        ],
        [
            Paragraph("ISO-15189 Certified Clinical Laboratory · Quality Assurance Reference Lab<br/>Karachi, Pakistan · Tel: +92 (21) 3456-7890 · Web: medlab.pk", sub_style),
            Paragraph(f"Ref: <b>{booking.get('booking_ref', '—')}</b>", ref_style)
        ]
    ]
    header_table = Table(header_data, colWidths=[340, 183])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 1),
        ('TOPPADDING', (0,0), (-1,-1), 1),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 10))
    elements.append(HRFlowable(width="100%", thickness=2, color=c_primary, spaceBefore=0, spaceAfter=8))

    # ── 2. Patient & Encounter Details Table ──
    rel_at = booking.get('released_at')
    rel_str = rel_at.strftime('%d %b %Y, %I:%M %p') if isinstance(rel_at, datetime) else (str(rel_at) if rel_at else '—')
    
    patient_info_data = [
        [
            Paragraph("<b>Patient Name:</b>", label_style),
            Paragraph(booking.get('patient_name', '—'), val_style),
            Paragraph("<b>Booking Ref:</b>", label_style),
            Paragraph(f"<b>{booking.get('booking_ref', '—')}</b>", val_style),
        ],
        [
            Paragraph("<b>Phone Number:</b>", label_style),
            Paragraph(booking.get('phone', booking.get('patient_phone', '—')), val_style),
            Paragraph("<b>Appointment Date:</b>", label_style),
            Paragraph(f"{booking.get('appointment_date', '—')} ({booking.get('appointment_slot', '—')})", val_style),
        ],
        [
            Paragraph("<b>Email:</b>", label_style),
            Paragraph(booking.get('email', booking.get('patient_email', '—')), val_style),
            Paragraph("<b>Report Released:</b>", label_style),
            Paragraph(rel_str, val_style),
        ],
        [
            Paragraph("<b>Gender / Blood:</b>", label_style),
            Paragraph(f"{booking.get('gender', '—')} / {booking.get('blood_group', '—')}", val_style),
            Paragraph("<b>Status:</b>", label_style),
            Paragraph("<font color='#166534'><b>Verified &amp; Released</b></font>", val_style),
        ],
    ]
    patient_table = Table(patient_info_data, colWidths=[95, 165, 105, 158])
    patient_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_bg_light),
        ('GRID', (0,0), (-1,-1), 0.5, c_border),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(patient_table)
    elements.append(Spacer(1, 12))

    # ── 3. Diagnostic Tests & Biomarker Results ──
    for item in items:
        item_id = item.get('item_id')
        test_name = item.get('test_name', 'Diagnostic Test')
        test_code = item.get('test_code', '')
        sample_type = item.get('sample_type', '')
        barcode = item.get('barcode_string', '—')

        test_header_text = f"<b>{test_name}</b>"
        if test_code:
            test_header_text += f" ({test_code})"
        if sample_type:
            test_header_text += f" · Specimen: {sample_type}"
        if barcode:
            test_header_text += f" · Barcode: {barcode}"

        elements.append(Paragraph(test_header_text, section_header_style))

        # Parameter rows
        results = results_by_item.get(item_id, []) if results_by_item else item.get('results', [])

        param_table_data = [
            [
                Paragraph("Biomarker / Parameter", tbl_header_style),
                Paragraph("Measured Value", tbl_header_style),
                Paragraph("Reference Range", tbl_header_style),
                Paragraph("Unit", tbl_header_style),
                Paragraph("Clinical Flag", tbl_header_style),
            ]
        ]

        table_styles = [
            ('BACKGROUND', (0,0), (-1,0), c_primary),
            ('GRID', (0,0), (-1,-1), 0.5, c_border),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (-1,-1), 6),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]

        if not results:
            param_table_data.append([
                Paragraph("No measured parameters recorded.", tbl_cell_style),
                Paragraph("—", tbl_cell_style),
                Paragraph("—", tbl_cell_style),
                Paragraph("—", tbl_cell_style),
                Paragraph("—", tbl_cell_style),
            ])
        else:
            for r_idx, r in enumerate(results, start=1):
                m_val = str(r.get('measured_value', ''))
                flag = str(r.get('flag_status') or ('HIGH' if r.get('is_abnormal') else 'NORMAL')).upper()
                min_r = str(r.get('min_range', ''))
                max_r = str(r.get('max_range', ''))
                ref_range = f"{min_r} – {max_r}" if (min_r and max_r) else "—"
                unit = str(r.get('unit', '—') or '—')

                # Flag color
                if flag == 'HIGH':
                    flag_p = Paragraph(f"<font color='#DC2626'><b>HIGH</b></font>", tbl_cell_bold)
                    val_p = Paragraph(f"<font color='#DC2626'><b>{m_val}</b></font>", tbl_cell_bold)
                    table_styles.append(('BACKGROUND', (0, r_idx), (-1, r_idx), colors.HexColor('#FEF2F2')))
                elif flag == 'LOW':
                    flag_p = Paragraph(f"<font color='#D97706'><b>LOW</b></font>", tbl_cell_bold)
                    val_p = Paragraph(f"<font color='#D97706'><b>{m_val}</b></font>", tbl_cell_bold)
                    table_styles.append(('BACKGROUND', (0, r_idx), (-1, r_idx), colors.HexColor('#FFFBEB')))
                else:
                    flag_p = Paragraph(f"<font color='#166534'>NORMAL</font>", tbl_cell_style)
                    val_p = Paragraph(f"<b>{m_val}</b>", tbl_cell_bold)

                param_table_data.append([
                    Paragraph(r.get('param_name', 'Parameter'), tbl_cell_bold),
                    val_p,
                    Paragraph(ref_range, tbl_cell_style),
                    Paragraph(unit, tbl_cell_style),
                    flag_p
                ])

        res_table = Table(param_table_data, colWidths=[173, 100, 110, 70, 70])
        res_table.setStyle(TableStyle(table_styles))
        elements.append(res_table)
        elements.append(Spacer(1, 12))

    # ── 4. Official Sign-off & Verification Seal ──
    pathologist_name = booking.get('pathologist_name') or 'Dr. Huzaifa Faheem'
    if not pathologist_name.startswith('Dr.'):
        pathologist_name = f"Dr. {pathologist_name}"

    signoff_data = [
        [
            Paragraph("<b>LABORATORY ANALYSIS</b>", label_style),
            Paragraph("<b>MEDICALLY VERIFIED &amp; RELEASED BY</b>", label_style),
        ],
        [
            Paragraph("<b>Medical Technologist</b><br/><font color='#64748B' size='7.5'>Clinical Diagnostics Laboratory<br/>MedLab Automated Diagnostic Systems</font>", val_style),
            Paragraph(f"<b>{pathologist_name}</b><br/><font color='#64748B' size='7.5'>Consultant Clinical Pathologist (MBBS, FCPS Pathology)<br/>Verified: {rel_str}<br/><b>Status: Digitally Signed &amp; Approved</b></font>", val_style),
        ]
    ]
    signoff_table = Table(signoff_data, colWidths=[260, 263])
    signoff_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), c_bg_light),
        ('GRID', (0,0), (-1,-1), 0.5, c_border),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('RIGHTPADDING', (0,0), (-1,-1), 8),
    ]))

    signoff_block = KeepTogether([
        HRFlowable(width="100%", thickness=1, color=c_border, spaceBefore=6, spaceAfter=8),
        signoff_table,
        Spacer(1, 10),
        Paragraph(
            "<font size='6.5' color='#64748B'><b>IMPORTANT CLINICAL NOTICE:</b> This official diagnostic report has been verified under standard MedLab quality control protocols. Diagnostic findings should be clinically correlated by the treating physician. For medical inquiries, contact lab administration at reports@medlab.pk.</font>",
            sub_style
        )
    ])
    elements.append(signoff_block)

    doc.build(elements)
    return buf.getvalue()

