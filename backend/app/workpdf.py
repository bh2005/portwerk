"""Arbeitsanweisung als PDF (A4 quer): ein Patchauftrag oder eine Patchliste aus mehreren Aufträgen, nach Ort gruppiert,
mit Abhak-Kästchen, Unterschriftenfeld und QR-Code zum Auftrag.

Schrift: DejaVu Sans (im Container über ``fonts-dejavu-core``), sonst Helvetica mit Ersatzzeichen für Pfeile und Kästchen.
"""
from __future__ import annotations

import io
import os
import time
from typing import Optional

import segno
from fpdf import FPDF
from fpdf.fonts import FontFace

FONT_DIRS = ("/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/dejavu", "/usr/share/fonts/TTF")
FALLBACK = {"→": "->", "↔": "<->", "☐": "[ ]", "☑": "[x]", "☒": "[!]", "–": "-", "…": "...", "„": '"', "“": '"', "·": "-"}
STATUS_BOX = {"open": "☐", "done": "☑", "deviation": "☒"}
GREY = (241, 245, 249)


def _font_dir() -> Optional[str]:
    for d in FONT_DIRS:
        if os.path.isfile(os.path.join(d, "DejaVuSans.ttf")) and os.path.isfile(os.path.join(d, "DejaVuSans-Bold.ttf")):
            return d
    return None


class _Doc(FPDF):
    def __init__(self, footer_text: str):
        super().__init__(orientation="L", unit="mm", format="A4")
        self.footer_text = footer_text
        d = _font_dir()
        if d:
            self.add_font("doc", "", os.path.join(d, "DejaVuSans.ttf"))
            self.add_font("doc", "B", os.path.join(d, "DejaVuSans-Bold.ttf"))
            self.family, self.unicode = "doc", True
        else:
            self.family, self.unicode = "helvetica", False
        self.set_margins(10, 10, 10)
        self.set_auto_page_break(True, margin=14)
        self.alias_nb_pages()

    def t(self, s) -> str:
        """Text für die gewählte Schrift: ohne Unicode-Schrift Ersatzzeichen und nur Latin-1."""
        s = "" if s is None else str(s)
        if self.unicode:
            return s
        for k, v in FALLBACK.items():
            s = s.replace(k, v)
        return s.encode("latin-1", "replace").decode("latin-1")

    def font(self, size: float, bold: bool = False) -> None:
        self.set_font(self.family, "B" if bold else "", size)

    def footer(self) -> None:
        self.set_y(-10)
        self.font(7.5)
        self.set_text_color(100, 116, 139)
        self.cell(0, 4, self.t(self.footer_text), align="L")
        self.set_x(-40)
        self.cell(30, 4, self.t(f"Seite {self.page_no()}/{{nb}}"), align="R")
        self.set_text_color(0, 0, 0)


def _qr_png(url: str) -> io.BytesIO:
    buf = io.BytesIO()
    segno.make(url, error="m", micro=False).save(buf, kind="png", scale=8, border=2)
    buf.seek(0)
    return buf


def _fmt_date(d: Optional[str]) -> str:
    if not d:
        return ""
    try:
        y, m, dd = d.split("-")
        return f"{dd}.{m}.{y}"
    except ValueError:
        return d


def _cable(x: dict) -> str:
    parts = [x["cable_label"], x["cable_type"], f"{x['length_m']:g} m" if x["length_m"] else "", x["color"]]
    return " · ".join(p for p in parts if p)


def render(data: dict, *, title: str, subtitle: str, meta: list[tuple[str, str]], notes: list[str], qr_url: str = "",
           warning: str = "", by: str = "", multi: bool = False) -> bytes:
    """``data``: Ergebnis von ``patchlists.build``. ``multi``: Spalte „Auftrag“ (Patchliste aus mehreren Aufträgen)."""
    now = time.strftime("%d.%m.%Y %H:%M")
    pdf = _Doc(f"Portwerk · {title} · erstellt {now}" + (f" von {by}" if by else ""))
    pdf.add_page()
    t = pdf.t

    # Kopf: Titel links, QR-Code rechts
    qr_size = 26 if qr_url else 0
    top = pdf.get_y()
    pdf.font(17, True)
    pdf.multi_cell(pdf.epw - qr_size - 4, 8, t(title), new_x="LMARGIN", new_y="NEXT")
    if subtitle:
        pdf.font(11)
        pdf.multi_cell(pdf.epw - qr_size - 4, 5.5, t(subtitle), new_x="LMARGIN", new_y="NEXT")
    if qr_url:
        pdf.image(_qr_png(qr_url), x=pdf.w - pdf.r_margin - qr_size, y=top, w=qr_size, h=qr_size)
        pdf.set_xy(pdf.w - pdf.r_margin - qr_size - 10, top + qr_size)
        pdf.font(6.5)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(qr_size + 10, 3, t("Auf dem Handy abhaken"), align="C")
        pdf.set_text_color(0, 0, 0)
        pdf.set_xy(pdf.l_margin, max(pdf.get_y(), top + 2))
    pdf.ln(2)

    if warning:
        pdf.font(10, True)
        pdf.set_fill_color(254, 226, 226)
        pdf.set_text_color(185, 28, 28)
        pdf.multi_cell(pdf.epw - qr_size - 4, 6, t(warning), fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        pdf.set_fill_color(255, 255, 255)
        pdf.ln(1)

    # Eckdaten in zwei Spalten
    meta = [(k, v) for k, v in meta if v]
    if meta:
        pdf.font(9)
        colw = (pdf.epw - qr_size - 4) / 2
        half = (len(meta) + 1) // 2
        y0 = pdf.get_y()
        for col, chunk in enumerate((meta[:half], meta[half:])):
            pdf.set_xy(pdf.l_margin + col * colw, y0)
            for k, v in chunk:
                pdf.set_x(pdf.l_margin + col * colw)
                pdf.font(9, True)
                pdf.cell(32, 5, t(k))
                pdf.font(9)
                pdf.multi_cell(colw - 32, 5, t(v), new_x="LMARGIN", new_y="NEXT")
            if col == 0:
                y_left = pdf.get_y()
        pdf.set_y(max(pdf.get_y(), y_left, top + qr_size + 4))
    for n in notes:
        if n:
            pdf.ln(1)
            pdf.font(9)
            pdf.multi_cell(0, 4.6, t(n), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    # Positionen, nach Gruppen (Ort bzw. Auftrag)
    items = data["items"]
    if not items:
        pdf.font(10)
        pdf.cell(0, 8, t("Keine Positionen."), new_x="LMARGIN", new_y="NEXT")
    heads = ["", "Nr"] + (["Auftrag"] if multi else []) + ["Aktion", "Von (Gerät:Port / Ort)", "Nach (Gerät:Port / Ort)", "Kabel", "Bemerkung"]
    widths = [7, 9] + ([20] if multi else []) + [27, 58, 58, 44, 0]
    widths[-1] = pdf.epw - sum(widths)
    groups: list[tuple[str, list]] = []
    for x in items:
        if not groups or groups[-1][0] != x.get("group", ""):
            groups.append((x.get("group", ""), []))
        groups[-1][1].append(x)
    n = 0
    for name, rows in groups:
        if name:
            if pdf.get_y() > pdf.h - 40:
                pdf.add_page()
            pdf.font(10.5, True)
            pdf.cell(0, 7, t(name), new_x="LMARGIN", new_y="NEXT")
        pdf.font(8.5)
        with pdf.table(col_widths=widths, line_height=4.4, text_align="LEFT", v_align="TOP", padding=1.2, repeat_headings=1,
                       headings_style=FontFace(emphasis="BOLD", fill_color=GREY), borders_layout="HORIZONTAL_LINES") as table:
            h = table.row()
            for c in heads:
                h.cell(t(c))
            for x in rows:
                n += 1
                r = table.row()
                r.cell(t(STATUS_BOX.get(x["item_status"], "☐")), style=FontFace(size_pt=11))
                r.cell(str(n))
                if multi:
                    r.cell(t(x["order"]))
                r.cell(t(x["action_label"]))
                r.cell(t(x["a"] + (f"\n{x['a_location']}" if x["a_location"] else "") + (f" · HE {x['a_unit']}" if x.get("a_unit") else "")))
                b_where = " · ".join(p for p in ((x["b_location"] if x["b_location"] != x["a_location"] else ""),
                                                 (f"HE {x['b_unit']}" if x.get("b_unit") else "")) if p)
                b = x["b"] + (f"\n{b_where}" if x["b"] and b_where else "")
                if x.get("old_b"):
                    b += f"\n(bisher: {x['old_b']})"
                r.cell(t(b))
                r.cell(t(_cable(x)))
                note = "\n".join(p for p in (f"Konfiguration: {x['cfg_text']}" if x.get("cfg_text") else "", x["note"]) if p)
                if x["item_status"] == "deviation" and x["deviation_note"]:
                    note = (note + "\n" if note else "") + f"Abweichung: {x['deviation_note']}"
                elif x["item_status"] == "done" and x["executed_by"]:
                    note = (note + "\n" if note else "") + f"erledigt: {x['executed_by']}"
                r.cell(t(note))
        pdf.ln(2)

    # Unterschriften und Abweichungen
    if pdf.get_y() > pdf.h - 52:
        pdf.add_page()
    pdf.ln(4)
    pdf.font(9, True)
    pdf.cell(0, 5, t("Abweichungen / Bemerkungen"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(148, 163, 184)
    for _ in range(3):
        pdf.ln(7)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(12)
    third = pdf.epw / 3
    y = pdf.get_y()
    for i, label in enumerate(("Ausgeführt von (Name)", "Datum", "Unterschrift")):
        x0 = pdf.l_margin + i * third
        pdf.line(x0, y, x0 + third - 8, y)
        pdf.set_xy(x0, y + 0.8)
        pdf.font(7.5)
        pdf.cell(third - 8, 4, t(label))
    pdf.set_draw_color(0, 0, 0)
    return bytes(pdf.output())
