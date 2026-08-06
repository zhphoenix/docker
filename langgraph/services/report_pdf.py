"""日报 Markdown → PDF 导出（reportlab，内置 STSong-Light 中文字体）

将 watchlist 日报的 Markdown 内容渲染为带页眉/页脚（平台名 + 日期 + 页码）的 PDF。
"""

import html
import io

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    PageTemplate,
    Paragraph,
    Spacer,
)

logger = __import__("logging").getLogger(__name__)

# 平台品牌与配色
_PLATFORM_NAME = "AI Platform · Watchlist Intelligence Center"
_PRIMARY = HexColor("#4f46e5")
_MUTED = HexColor("#9ca3af")
_BODY = HexColor("#1f2937")

_FONT = "STSong-Light"


def _register_font() -> None:
    try:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    except Exception as e:  # noqa: BLE001
        logger.warning("[ReportPdf] font register failed | %s", e)


def _build_styles() -> dict[str, ParagraphStyle]:
    return {
        "h1": ParagraphStyle(
            "h1", fontName=_FONT, fontSize=18, leading=24,
            textColor=_PRIMARY, spaceAfter=6, spaceBefore=4,
        ),
        "h2": ParagraphStyle(
            "h2", fontName=_FONT, fontSize=14, leading=20,
            textColor=_PRIMARY, spaceBefore=10, spaceAfter=4,
        ),
        "h3": ParagraphStyle(
            "h3", fontName=_FONT, fontSize=12, leading=18,
            textColor=_BODY, spaceBefore=8, spaceAfter=3,
        ),
        "body": ParagraphStyle(
            "body", fontName=_FONT, fontSize=10, leading=16,
            textColor=_BODY, spaceAfter=4,
        ),
        "bullet": ParagraphStyle(
            "bullet", fontName=_FONT, fontSize=10, leading=16,
            textColor=_BODY, spaceAfter=3, leftIndent=12, bulletIndent=2,
        ),
        "title": ParagraphStyle(
            "title", fontName=_FONT, fontSize=20, leading=26,
            textColor=_PRIMARY, alignment=TA_CENTER, spaceBefore=6, spaceAfter=2,
        ),
    }


class _HeaderFooterCanvas(pdfcanvas.Canvas):
    """在每页绘制页眉（平台名）与页脚（日期 + 页码）"""

    def __init__(self, *args, report_date: str = "", **kwargs):  # noqa: ANN002
        super().__init__(*args, **kwargs)
        self._report_date = report_date

    def _draw_deco(self) -> None:
        self.saveState()
        w, h = A4
        self.setFont(_FONT, 8)
        self.setFillColor(_MUTED)
        # 页眉
        self.drawString(20 * mm, h - 14 * mm, _PLATFORM_NAME)
        self.setStrokeColor(_MUTED)
        self.setLineWidth(0.5)
        self.line(20 * mm, h - 17 * mm, w - 20 * mm, h - 17 * mm)
        # 页脚
        self.drawString(20 * mm, 12 * mm, f"报告日期：{self._report_date}")
        self.drawRightString(w - 20 * mm, 12 * mm, f"第 {self.getPageNumber()} 页")
        self.restoreState()

    def showPage(self) -> None:
        self._draw_deco()
        super().showPage()

    def save(self) -> None:
        self._draw_deco()
        super().save()


def _md_to_flowables(text: str, styles: dict[str, ParagraphStyle]) -> list:
    story: list = []
    for raw in text.split("\n"):
        line = raw.rstrip()
        if not line.strip():
            story.append(Spacer(1, 4))
            continue
        stripped = line.strip()
        # 分隔线（--- 或 ===，且长度 > 2）
        if len(stripped) > 2 and set(stripped) <= set("-=_="):
            story.append(HRFlowable(width="100%", thickness=0.6, color=_MUTED))
            continue
        if stripped.startswith("### "):
            story.append(Paragraph(html.escape(stripped[4:]), styles["h3"]))
        elif stripped.startswith("## "):
            story.append(Paragraph(html.escape(stripped[3:]), styles["h2"]))
        elif stripped.startswith("# "):
            story.append(Paragraph(html.escape(stripped[2:]), styles["h1"]))
        elif stripped.startswith("- "):
            story.append(
                Paragraph(html.escape(stripped[2:]), styles["bullet"], bulletText="•")
            )
        else:
            story.append(Paragraph(html.escape(stripped), styles["body"]))
    return story


def markdown_to_pdf_bytes(
    md_text: str, title: str | None = None, report_date: str = ""
) -> bytes:
    """把日报 Markdown 渲染为 PDF 字节（标题行正常渲染，页眉/页脚含平台名与日期）"""
    _register_font()
    styles = _build_styles()
    buf = io.BytesIO()

    doc = BaseDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=24 * mm,
        bottomMargin=20 * mm,
        title=title or "Watchlist Daily Report",
        author="AI Platform",
        canvasmaker=lambda *a, **kw: _HeaderFooterCanvas(
            *a, report_date=report_date, **kw
        ),
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="page", frames=[frame])])

    story = _md_to_flowables(md_text, styles)
    doc.build(story)
    return buf.getvalue()