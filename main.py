import re
import os
import io
from flask import Flask, request, send_file, jsonify
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, NextPageTemplate, Table, \
    TableStyle
from reportlab.lib.utils import ImageReader
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

app = Flask(__name__)

# --- CONFIGURATION ---
TEMPLATE_PATH = "template.png"
# Use a default if not provided, or handle in the drawing function
PHOTO_URL_DEFAULT = "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?ixlib=rb-1.2.1&auto=format&fit=facearea&facepad=2&w=256&h=256&q=80"
FONT_PATH_REGULAR = "IBMPlexSansDevanagari-Regular.ttf"
FONT_NAME_REGULAR = "IBMPlexSansDevanagari-Regular"

# --- PAGE DIMENSIONS & BOX ---
PAGE_WIDTH, PAGE_HEIGHT = A4
BOX_X = 56
BOX_WIDTH = 496
BOX_HEIGHT = 482
BOX_TOP_MARGIN = 302
BOX_BOTTOM_Y = PAGE_HEIGHT - BOX_TOP_MARGIN - BOX_HEIGHT


# --- HELPER FUNCTIONS (Refactored from your script) ---

def register_custom_fonts():
    """Registers the custom font if the file exists."""
    font_available = False
    if os.path.exists(FONT_PATH_REGULAR):
        try:
            pdfmetrics.registerFont(TTFont(FONT_NAME_REGULAR, FONT_PATH_REGULAR))
            font_available = True
        except Exception as e:
            print(f"Warning: Could not register font: {e}")
    return font_available


def parse_full_report(text):
    """Parses the text into structured Q&A and remaining text."""
    # Regex looks for Question -> Score -> Comment blocks
    qa_pattern = r"Question:\s*(.+?)\s*\n\s*Score:\s*(\d+)\s*\n\s*Comment:\s*(.+?)(?=\n\s*Question:|\n\s*[0-9]+\.|\Z)"
    matches = re.findall(qa_pattern, text, re.DOTALL | re.IGNORECASE)

    structured_qa = []
    for q, s, c in matches:
        q_clean = q.replace("Your ", "").strip()
        c_clean = c.strip().replace("\n", " ")
        structured_qa.append((q_clean, int(s), c_clean))

    split_match = re.search(r"(2\.\s*Overall Evaluation:|Overall Evaluation:)", text, re.IGNORECASE)

    if split_match:
        start_index = split_match.start()
        remaining_text = text[start_index:].strip()
    else:
        remaining_text = ""

    return structured_qa, remaining_text


def create_score_chart(parsed_data):
    if not parsed_data: return None

    data = [item[1] for item in parsed_data]
    labels = [f"Q{i + 1}" for i in range(len(data))]

    drawing = Drawing(BOX_WIDTH, 120)
    bc = VerticalBarChart()
    bc.x = 20
    bc.y = 20
    bc.height = 80
    bc.width = BOX_WIDTH - 40
    bc.data = [data]

    bc.strokeColor = colors.white
    bc.valueAxis.valueMin = 0
    bc.valueAxis.valueMax = 10
    bc.categoryAxis.categoryNames = labels
    bc.categoryAxis.labels.boxAnchor = 'n'
    bc.categoryAxis.labels.dy = -5

    for i, val in enumerate(data):
        if val <= 3:
            bc.bars[i].fillColor = colors.HexColor("#e74c3c")
        elif val <= 6:
            bc.bars[i].fillColor = colors.HexColor("#f1c40f")
        else:
            bc.bars[i].fillColor = colors.HexColor("#2ecc71")

    drawing.add(bc)
    return drawing


def create_qa_table(parsed_qa):
    if not parsed_qa: return None

    styles = getSampleStyleSheet()
    normal_style = ParagraphStyle('TabNormal', parent=styles['Normal'], fontSize=9, leading=11)
    header_style = ParagraphStyle('TabHeader', parent=styles['Normal'], fontSize=10, leading=12, textColor=colors.white,
                                  fontName='Helvetica-Bold')

    data = [[
        Paragraph("Question", header_style),
        Paragraph("Analysis / Feedback", header_style),
        Paragraph("Score", header_style)
    ]]

    for q, s, c in parsed_qa:
        score_color = "green" if s > 6 else "orange" if s > 3 else "red"
        score_para = Paragraph(f"<font color='{score_color}'><b>{s}/10</b></font>", normal_style)

        row = [
            Paragraph(q, normal_style),
            Paragraph(c, normal_style),
            score_para
        ]
        data.append(row)

    col_widths = [140, 286, 70]
    t = Table(data, colWidths=col_widths, repeatRows=1)

    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1F2A3C")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#1F2A3C")),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    return t


# --- PAGE DRAWING LOGIC ---

def draw_first_page_bg(canvas, doc):
    canvas.saveState()

    # 1. Template
    if os.path.exists(TEMPLATE_PATH):
        try:
            canvas.drawImage(TEMPLATE_PATH, 0, 0, width=PAGE_WIDTH, height=PAGE_HEIGHT)
        except:
            pass

            # 2. Fonts
    has_custom_font = register_custom_fonts()
    if has_custom_font:
        main_font = FONT_NAME_REGULAR
        name_font = FONT_NAME_REGULAR
    else:
        main_font = "Helvetica"
        name_font = "Helvetica-Bold"

    data = doc.candidate_data

    # 3. Text Details
    canvas.setFillColor(colors.white)

    canvas.setFont(name_font, 14)
    name_y_rl = PAGE_HEIGHT - 125 - 12
    canvas.drawString(43, name_y_rl, str(data.get('candidate_name', '')))

    canvas.setFont(main_font, 11)
    role_y_rl = PAGE_HEIGHT - 147 - 10
    canvas.drawString(43, role_y_rl, str(data.get('candidate_position', '')))

    canvas.setFont(main_font, 10)
    date_y_rl = PAGE_HEIGHT - 165 - 10
    canvas.drawString(43, date_y_rl, str(data.get('date', '')))

    id_y_rl = PAGE_HEIGHT - 180 - 10
    canvas.drawString(43, id_y_rl, f"ID: {data.get('interview_id', '')}")

    # 4. Photo
    img_x = PAGE_WIDTH - 120
    img_y = PAGE_HEIGHT - 120
    img_size = 80
    try:
        # Use provided URL or Default
        p_url = data.get('photo_url', PHOTO_URL_DEFAULT)
        if not p_url: p_url = PHOTO_URL_DEFAULT

        img = ImageReader(p_url)
        path = canvas.beginPath()
        path.circle(img_x + (img_size / 2), img_y + (img_size / 2), img_size / 2)
        canvas.clipPath(path, stroke=0)
        canvas.drawImage(img, img_x, img_y, width=img_size, height=img_size, mask='auto')
    except:
        pass

    canvas.restoreState()


def draw_later_pages_bg(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.black)
    canvas.drawRightString(PAGE_WIDTH - 40, 30, f"Page {doc.page}")
    canvas.restoreState()


# --- API ENDPOINT ---

@app.route('/generate-report', methods=['POST'])
def generate_report_api():
    try:
        # 1. Get JSON Data
        req_data = request.get_json()
        if not req_data:
            return jsonify({"error": "No JSON data provided"}), 400

        # Required fields check
        required_fields = ['candidate_name', 'candidate_position', 'date', 'interview_id', 'ai_overview']
        for field in required_fields:
            if field not in req_data:
                return jsonify({"error": f"Missing field: {field}"}), 400

        ai_text = req_data['ai_overview']

        # 2. Setup PDF Buffer (In-Memory)
        buffer = io.BytesIO()
        doc = BaseDocTemplate(buffer, pagesize=A4)

        # Pass request data to doc for callbacks
        doc.candidate_data = req_data

        # 3. Frames & Templates
        frame_first = Frame(BOX_X, BOX_BOTTOM_Y, BOX_WIDTH, BOX_HEIGHT, id='F1', showBoundary=0)
        frame_later = Frame(40, 50, PAGE_WIDTH - 80, PAGE_HEIGHT - 100, id='F2', showBoundary=0)

        doc.addPageTemplates([
            PageTemplate(id='First', frames=[frame_first], onPage=draw_first_page_bg),
            PageTemplate(id='Later', frames=[frame_later], onPage=draw_later_pages_bg)
        ])

        # 4. Build Story
        styles = getSampleStyleSheet()
        heading_style = ParagraphStyle('Head', parent=styles['Heading3'], fontSize=12,
                                       textColor=colors.HexColor("#1F2A3C"), spaceAfter=6)
        body_style = ParagraphStyle('Body', parent=styles['Normal'], fontSize=10, leading=14)

        story = []
        story.append(NextPageTemplate('Later'))

        # Parse AI Text
        qa_data, remaining_text = parse_full_report(ai_text)

        # Add Chart
        if qa_data:
            story.append(Paragraph("<b>Score Overview</b>", heading_style))
            chart = create_score_chart(qa_data)
            if chart:
                story.append(chart)
                story.append(Spacer(1, 15))

        # Add Table
        if qa_data:
            story.append(Paragraph("<b>Detailed Question Analysis</b>", heading_style))
            story.append(Spacer(1, 5))
            table = create_qa_table(qa_data)
            story.append(table)
            story.append(Spacer(1, 20))

        # Add Remaining Text
        if remaining_text:
            fmt_text = remaining_text.replace("\n", "<br/>")
            fmt_text = re.sub(r"(Overall Evaluation:)", r"<b>\1</b>", fmt_text)
            fmt_text = re.sub(r"(Final Recommendation:)", r"<br/><br/><b>\1</b>", fmt_text)
            fmt_text = re.sub(r"(Strengths:)", r"<b>\1</b>", fmt_text)
            fmt_text = re.sub(r"(Weaknesses:)", r"<b>\1</b>", fmt_text)

            story.append(Paragraph(fmt_text, body_style))

        # 5. Generate PDF
        doc.build(story)
        buffer.seek(0)

        # 6. Return File
        filename = f"Report_{req_data['interview_id']}.pdf"
        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )

    except Exception as e:
        print(f"Error generating PDF: {str(e)}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    # Run on 0.0.0.0 to be accessible externally (e.g., from n8n)
    app.run(host='0.0.0.0', port=5000, debug=True)