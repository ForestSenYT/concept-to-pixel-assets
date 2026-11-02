"""Review PDF for background / CG packs (one per delivered pack).

    pdf = ReviewPDF('BG05_review.pdf', 'BG05 林间小路 · 评审稿', footer='BG05 v2')
    pdf.cover('BG05 林间小路', 'v2 · 分层视差 + 动画', ['规格：640×360 ...', '日期：...'], overview_png)
    pdf.text('1  做法', lines)
    pdf.compare('2  原图 → 成品', src_img, out_img, '原图', '成品')
    pdf.detail('2  局部：护栏', src_img, out_img, (x0, y0, x1, y1))      # crop box in native px
    pdf.keyframes('3  loop 关键帧', [f0, f12, f24, f36], ['帧 0', '帧 12', '帧 24', '帧 36'])
    pdf.image('4  总览', overview)
    pdf.save()
Pixel images are upscaled by an integer factor (nearest) before embedding so they stay crisp.
"""
import os
import tempfile
import numpy as np
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_CANDIDATES = [
    ('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc', 0),
    ('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', 0),
    ('/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc', 0),
    ('/System/Library/Fonts/PingFang.ttc', 0),
    ('C:/Windows/Fonts/msyh.ttc', 0),
]


def _font():
    for p, i in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                pdfmetrics.registerFont(TTFont('CJK', p, subfontIndex=i))
                return 'CJK'
            except Exception:
                continue
    return 'Helvetica'


class ReviewPDF:
    W, H = 1280, 720
    BG = (0.094, 0.094, 0.11)
    FG = (0.92, 0.92, 0.92)
    MUT = (0.62, 0.62, 0.66)
    ACC = (1, 0.78, 0.55)

    def __init__(self, path, title, footer=''):
        self.c = canvas.Canvas(path, pagesize=(self.W, self.H))
        self.c.setTitle(title)
        self.font = _font()
        self.footer = footer
        self.tmp = tempfile.mkdtemp(prefix='review_pdf_')
        self.k = 0

    def _page(self, title=None, sub=None):
        c = self.c
        c.setFillColorRGB(*self.BG)
        c.rect(0, 0, self.W, self.H, stroke=0, fill=1)
        if title:
            c.setFillColorRGB(*self.FG)
            c.setFont(self.font, 22)
            c.drawString(36, self.H - 46, title)
        if sub:
            c.setFillColorRGB(*self.MUT)
            c.setFont(self.font, 13)
            c.drawString(36, self.H - 68, sub)
        c.setFillColorRGB(*self.MUT)
        c.setFont(self.font, 10)
        c.drawRightString(self.W - 30, 18, f'{self.footer} · {c.getPageNumber()}')

    def _img(self, im, x, y, w, h):
        if isinstance(im, np.ndarray):
            im = Image.fromarray(im.astype(np.uint8))
        elif isinstance(im, str):
            im = Image.open(im)
        s = min(w / im.width, h / im.height)
        if s > 1:
            f = int(np.ceil(s))
            im = im.resize((im.width * f, im.height * f), Image.NEAREST)
        s = min(w / im.width, h / im.height)
        dw, dh = im.width * s, im.height * s
        self.k += 1
        fn = os.path.join(self.tmp, f'i{self.k}.png')
        im.convert('RGB').save(fn)
        self.c.drawImage(fn, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh)

    def _label(self, t, x, y, size=13):
        self.c.setFillColorRGB(*self.MUT)
        self.c.setFont(self.font, size)
        self.c.drawString(x, y, t)

    def _text(self, lines, x, y, size=14, lead=1.55, maxw=1200):
        c = self.c
        for ln in lines:
            col = self.FG
            if isinstance(ln, tuple):
                ln, col = ln
            c.setFont(self.font, size)
            cur = ''
            for ch in ln:
                if pdfmetrics.stringWidth(cur + ch, self.font, size) > maxw:
                    c.setFillColorRGB(*col)
                    c.drawString(x, y, cur)
                    y -= size * lead
                    cur = ch
                    if y < 40:
                        c.showPage()
                        self._page()
                        y = self.H - 60
                else:
                    cur += ch
            c.setFillColorRGB(*col)
            c.drawString(x, y, cur)
            y -= size * lead
            if y < 40:
                c.showPage()
                self._page()
                y = self.H - 60
        return y

    def cover(self, title, subtitle, lines, image=None):
        self._page()
        c = self.c
        c.setFillColorRGB(*self.FG)
        c.setFont(self.font, 40)
        c.drawString(80, self.H - 200, title)
        c.setFillColorRGB(*self.ACC)
        c.setFont(self.font, 20)
        c.drawString(80, self.H - 245, subtitle)
        self._text(lines, 80, self.H - 310, 16, maxw=600 if image is not None else 1100)
        if image is not None:
            self._img(image, 720, 90, 520, 520)
        c.showPage()

    def text(self, title, lines, size=14):
        self._page(title)
        self._text(lines, 40, self.H - 100, size)
        self.c.showPage()

    def compare(self, title, left, right, llabel, rlabel, sub=None):
        self._page(title, sub)
        self._img(left, 36, 120, 590, 480)
        self._img(right, 654, 120, 590, 480)
        self._label(llabel, 36, 100)
        self._label(rlabel, 654, 100)
        self.c.showPage()

    def detail(self, title, src, out, box, llabel='原图同位置', rlabel='成品（像素放大）'):
        """box in output (native) pixels; the source crop is scaled to match"""
        src = Image.fromarray(src) if isinstance(src, np.ndarray) else (Image.open(src) if isinstance(src, str) else src)
        out = Image.fromarray(out) if isinstance(out, np.ndarray) else (Image.open(out) if isinstance(out, str) else out)
        fx = src.width / out.width
        x0, y0, x1, y1 = box
        a = src.crop((int(x0 * fx), int(y0 * fx), int(x1 * fx), int(y1 * fx)))
        b = out.crop(box)
        self.compare(title, a, b, llabel, rlabel)

    def keyframes(self, title, frames, labels, sub=None):
        self._page(title, sub)
        for i, (f, lab) in enumerate(zip(frames, labels)):
            x = 36 + (i % 2) * 612
            y = self.H - 110 - (i // 2) * 300 - 280
            self._img(f, x, y, 600, 280)
            self._label(lab, x, y - 16)
        self.c.showPage()

    def image(self, title, im, sub=None):
        self._page(title, sub)
        self._img(im, 36, 40, self.W - 72, self.H - 110)
        self.c.showPage()

    def save(self):
        self.c.save()
