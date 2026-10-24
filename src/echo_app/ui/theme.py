"""Lagoon, Echo's look: color tokens, palette, stylesheet, tinted icons, fonts and the wave motif.

Every color in the UI comes from the current `Tokens`. Custom-painted widgets read `current()` at
paint time and icons are tinted when drawn, so switching between light and dark is live.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QGuiApplication, QIcon, QIconEngine, QLinearGradient,
                           QPainter, QPainterPath, QPalette, QPixmap)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QWidget

from .. import paths

ASSETS = Path(__file__).parent / "assets"
DISPLAY = "Manrope"

LIGHT, DARK, SYSTEM = "light", "dark", "system"
MODES = (LIGHT, DARK, SYSTEM)


@dataclass(frozen=True)
class Tokens:
    dark: bool
    canvas: str  # window background behind the cards
    surface: str  # cards, text, dialogs
    raised: str  # hover on surface
    line: str
    ink: str
    muted: str
    accent: str
    accent_deep: str
    accent_soft: str  # selection and tints on surface
    on_accent: str
    deep_top: str  # sidebar gradient
    deep_mid: str
    deep_bottom: str
    on_deep: str
    on_deep_muted: str
    foam: str  # accent on the deep sidebar
    coral: str
    coral_deep: str
    amber: str
    find: str


LAGOON_LIGHT = Tokens(
    dark=False, canvas="#eaf3f5", surface="#ffffff", raised="#f2f8fa", line="#d3e4ea", ink="#0b2a35",
    muted="#5a7883", accent="#0e9db7", accent_deep="#0a6f86", accent_soft="#d3f0f5", on_accent="#ffffff",
    deep_top="#05303f", deep_mid="#09566b", deep_bottom="#0f8299", on_deep="#e8f8fb", on_deep_muted="#93c9d4",
    foam="#7fe3ee", coral="#ff6b6b", coral_deep="#f43f5e", amber="#f2a33a", find="#ffd36e",
)

LAGOON_DARK = Tokens(
    dark=True, canvas="#061419", surface="#0b2129", raised="#112d37", line="#1b3c47", ink="#e2f3f6",
    muted="#8aacb6", accent="#2cc7df", accent_deep="#1aa3bb", accent_soft="#123f4a", on_accent="#04232b",
    deep_top="#020e12", deep_mid="#042630", deep_bottom="#073f4d", on_deep="#e2f6fa", on_deep_muted="#7fb3bf",
    foam="#6fdcea", coral="#ff6b6b", coral_deep="#f43f5e", amber="#f2a33a", find="#b88a1e",
)

_current = LAGOON_LIGHT
_mode = LIGHT


def current() -> Tokens:
    return _current


def mode() -> str:
    return _mode


def color(name: str, alpha: float = 1.0) -> QColor:
    c = QColor(getattr(_current, name))
    if alpha < 1.0:
        c.setAlphaF(alpha)
    return c


def rgba(name: str, alpha: float) -> str:
    c = QColor(getattr(_current, name))
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha:.3f})"


def resolve(mode_: str) -> Tokens:
    if mode_ == SYSTEM:
        hints = QGuiApplication.styleHints()
        return LAGOON_DARK if hints is not None and hints.colorScheme() == Qt.ColorScheme.Dark else LAGOON_LIGHT
    return LAGOON_DARK if mode_ == DARK else LAGOON_LIGHT


# ---- fonts ----------------------------------------------------------------------------------------

_fonts_loaded = False


def load_fonts() -> None:
    global _fonts_loaded
    if not _fonts_loaded:
        for f in sorted((ASSETS / "fonts").glob("Manrope-*.ttf")):
            QFontDatabase.addApplicationFont(str(f))
        _fonts_loaded = True


def ui_font() -> QFont:
    base = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    f = QFont(DISPLAY)
    f.setPointSizeF(max(10.0, base.pointSizeF()))
    return f


def display_font(scale: float = 1.0, weight: QFont.Weight = QFont.Weight.Bold, tabular: bool = False) -> QFont:
    f = ui_font()
    f.setPointSizeF(f.pointSizeF() * scale)
    f.setWeight(weight)
    if tabular:
        f.setFeature(QFont.Tag("tnum"), 1)
    return f


def reading_font(scale: float = 1.12) -> QFont:
    """Long transcripts read in the desktop's own text face."""
    f = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    f.setPointSizeF(max(10.0, f.pointSizeF()) * scale)
    return f


# ---- icons ----------------------------------------------------------------------------------------

FILLED = {"play", "pause", "square"}


@lru_cache(maxsize=None)
def _svg(name: str) -> bytes:
    p = ASSETS / "icons" / f"{name}.svg"
    return p.read_bytes() if p.exists() else b""


class TintedIcon(QIconEngine):
    """An SVG drawn in a token color looked up at paint time; disabled icons fade."""

    def __init__(self, name: str, role: str):
        super().__init__()
        self.name, self.role = name, role

    def paint(self, painter: QPainter, rect: QRect, mode: QIcon.Mode, state: QIcon.State) -> None:
        data = _svg(self.name)
        if not data:
            return
        c = color(self.role)
        if mode == QIcon.Mode.Disabled:
            c.setAlphaF(0.35)
        hexc = c.name(QColor.NameFormat.HexRgb)
        data = data.replace(b"currentColor", hexc.encode())
        if self.name in FILLED:
            data = data.replace(b'fill="none"', f'fill="{hexc}"'.encode())
        r = QSvgRenderer(QByteArray(data))
        painter.save()
        painter.setOpacity(painter.opacity() * c.alphaF())
        r.render(painter, QRectF(rect))
        painter.restore()

    def pixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QPixmap:
        pm = QPixmap(size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.paint(p, QRect(0, 0, size.width(), size.height()), mode, state)
        p.end()
        return pm

    def clone(self) -> QIconEngine:
        return TintedIcon(self.name, self.role)


def tinted(name: str, role: str = "ink") -> QIcon:
    return QIcon(TintedIcon(name, role))


# ---- waves ----------------------------------------------------------------------------------------

def paint_waves(p: QPainter, rect: QRectF, phase: float, swell: float, tint: QColor | None = None) -> None:
    """Three layered swells along the bottom of `rect`. `swell` (0..1) raises the crests."""
    t = _current
    layers = (  # (height share, wavelength px, speed, amplitude px, color, alpha)
        (0.78, 260.0, 0.55, 5.0, t.foam, 0.16),
        (0.58, 190.0, -0.8, 6.0, t.foam, 0.22),
        (0.36, 330.0, 1.0, 7.0, t.accent if not t.dark else t.foam, 0.30),
    )
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    w, h, bottom = rect.width(), rect.height(), rect.bottom()
    for i, (share, wl, speed, amp, c, alpha) in enumerate(layers):
        a = amp * (1.0 + 2.6 * swell)
        base = bottom - h * share
        path = QPainterPath(QPointF(rect.left(), bottom))
        x = 0.0
        while x <= w + 6:
            y = base + a * math.sin(2 * math.pi * x / wl + phase * speed + i * 1.7) \
                + a * 0.35 * math.sin(2 * math.pi * x / (wl * 0.43) - phase * speed * 1.3)
            path.lineTo(rect.left() + x, y)
            x += 6
        path.lineTo(rect.right(), bottom)
        path.closeSubpath()
        col = QColor(tint if (tint is not None and i == len(layers) - 1) else QColor(c))
        col.setAlphaF(alpha)
        p.setBrush(col)
        p.drawPath(path)
    p.restore()


def deep_gradient(rect: QRectF) -> QLinearGradient:
    g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
    t = _current
    g.setColorAt(0.0, QColor(t.deep_top))
    g.setColorAt(0.55, QColor(t.deep_mid))
    g.setColorAt(1.0, QColor(t.deep_bottom))
    return g


class DeepBackground(QWidget):
    """A container painted with the sidebar's deep gradient."""

    def paintEvent(self, _):
        p = QPainter(self)
        r = QRectF(self.rect())
        p.fillRect(r, deep_gradient(r))
        p.end()


# ---- palette and stylesheet ------------------------------------------------------------------------

def palette(t: Tokens) -> QPalette:
    R = QPalette.ColorRole
    pal = QPalette()
    for role, v in [(R.Window, t.canvas), (R.WindowText, t.ink), (R.Base, t.surface), (R.AlternateBase, t.raised),
                    (R.Text, t.ink), (R.Button, t.surface), (R.ButtonText, t.ink), (R.BrightText, t.on_accent),
                    (R.Highlight, t.accent), (R.HighlightedText, t.on_accent), (R.Link, t.accent_deep),
                    (R.LinkVisited, t.accent_deep), (R.PlaceholderText, t.muted), (R.ToolTipBase, t.deep_mid),
                    (R.ToolTipText, t.on_deep), (R.Light, t.surface), (R.Midlight, t.line), (R.Mid, t.line),
                    (R.Dark, t.muted), (R.Shadow, t.deep_top)]:
        pal.setColor(role, QColor(v))
    for role in (R.Text, R.WindowText, R.ButtonText):
        dis = QColor(getattr(t, "muted"))
        dis.setAlphaF(0.6)
        pal.setColor(QPalette.ColorGroup.Disabled, role, dis)
    return pal


_GLYPHS = {"chevron": "m6 9 6 6 6-6", "chevron-up": "m18 15-6-6-6 6", "check": "M20 6 9 17l-5-5"}


def _glyph(name: str, c: str) -> str:
    """A small stroked glyph in color `c`, cached as a file for stylesheet `image:` rules."""
    d = paths.cache_dir() / "theme"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{name}-{c.lstrip('#')}.svg"
    if not f.exists():
        f.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" '
                     f'stroke="{c}" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round">'
                     f'<path d="{_GLYPHS[name]}"/></svg>', encoding="utf-8")
    return f.as_posix()


def _chevron(c: str) -> str:
    return _glyph("chevron", c)


def stylesheet(t: Tokens) -> str:
    ink_chev, deep_chev = _chevron(t.muted), _chevron(t.on_deep_muted)
    glass = rgba("on_deep", 0.10)
    glass_hover = rgba("on_deep", 0.16)
    glass_line = rgba("on_deep", 0.20)
    return f"""
* {{ outline: none; }}
QMainWindow, QDialog {{ background: {t.canvas}; }}
QDialog {{ background: {t.surface}; }}
QToolTip {{ background: {t.deep_mid}; color: {t.on_deep}; border: none; border-radius: 8px; padding: 6px 9px; }}
QStatusBar {{ background: {t.canvas}; color: {t.muted}; }}
QStatusBar::item {{ border: none; }}
QMenuBar {{ background: {t.canvas}; color: {t.ink}; padding: 2px 4px; }}
QMenuBar::item {{ padding: 5px 10px; border-radius: 6px; background: transparent; }}
QMenuBar::item:selected {{ background: {t.accent_soft}; }}
QMenu {{ background: {t.surface}; color: {t.ink}; border: 1px solid {t.line}; padding: 6px; }}
QMenu::item {{ padding: 6px 22px 6px 10px; border-radius: 6px; }}
QMenu::item:selected {{ background: {t.accent_soft}; color: {t.ink}; }}
QMenu::item:disabled {{ color: {rgba('muted', 0.55)}; }}
QMenu::separator {{ height: 1px; background: {t.line}; margin: 5px 6px; }}
QMenu::icon {{ padding-left: 8px; }}

QSplitter::handle {{ background: transparent; }}
QFrame[frameShape="4"], QFrame[frameShape="5"] {{ border: none; background: {t.line}; max-height: 1px; }}
QSplitter#content::handle:vertical {{ height: 10px; }}
QSplitter#main::handle:horizontal {{ width: 1px; background: transparent; }}

QPushButton {{ background: {t.surface}; color: {t.ink}; border: 1px solid {t.line}; border-radius: 10px;
    padding: 7px 14px; }}
QPushButton:hover {{ border-color: {t.accent}; background: {t.raised}; }}
QPushButton:pressed {{ background: {t.accent_soft}; }}
QPushButton:default, QPushButton[primary="true"] {{ background: {t.accent}; color: {t.on_accent}; border: 1px solid {t.accent}; font-weight: 700; }}
QPushButton:default:hover, QPushButton[primary="true"]:hover {{ background: {t.accent_deep}; border-color: {t.accent_deep}; }}
QPushButton:disabled {{ color: {rgba('muted', 0.6)}; background: {t.raised}; border-color: {t.line}; }}

QToolButton {{ background: transparent; color: {t.ink}; border: 1px solid transparent; border-radius: 9px;
    padding: 5px 9px; }}
QToolButton:hover {{ background: {t.raised}; border-color: {t.line}; }}
QToolButton:pressed, QToolButton:checked {{ background: {t.accent_soft}; border-color: {t.accent}; }}
QToolButton:disabled {{ color: {rgba('muted', 0.55)}; }}
QToolButton::menu-indicator {{ image: url({ink_chev}); subcontrol-position: right center; right: 6px; }}
QToolButton[popupMode="2"] {{ padding-right: 22px; }}

QLineEdit, QSpinBox, QPlainTextEdit#plain {{ background: {t.surface}; color: {t.ink}; border: 1px solid {t.line};
    border-radius: 10px; padding: 7px 10px; selection-background-color: {t.accent_soft}; selection-color: {t.ink}; }}
QLineEdit:focus, QSpinBox:focus {{ border: 1px solid {t.accent}; }}
QComboBox {{ background: {t.surface}; color: {t.ink}; border: 1px solid {t.line}; border-radius: 10px;
    padding: 6px 30px 6px 11px; }}
QComboBox:hover {{ border-color: {t.accent}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: url({ink_chev}); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{ background: {t.surface}; color: {t.ink}; border: 1px solid {t.line};
    selection-background-color: {t.accent_soft}; selection-color: {t.ink}; padding: 4px; outline: none; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {t.line}; border-radius: 5px;
    background: {t.surface}; }}
QCheckBox::indicator:hover {{ border-color: {t.accent}; }}
QCheckBox::indicator:checked {{ background: {t.accent}; border-color: {t.accent};
    image: url({_glyph("check", t.on_accent)}); }}
QCheckBox::indicator:disabled {{ background: {t.raised}; border-color: {t.line}; }}
QSpinBox {{ padding-right: 26px; }}
QSpinBox::up-button, QSpinBox::down-button {{ subcontrol-origin: border; width: 22px; border: none;
    background: transparent; }}
QSpinBox::up-button {{ subcontrol-position: top right; margin-top: 3px; }}
QSpinBox::down-button {{ subcontrol-position: bottom right; margin-bottom: 3px; }}
QSpinBox::up-arrow {{ image: url({_glyph("chevron-up", t.muted)}); width: 10px; height: 10px; }}
QSpinBox::down-arrow {{ image: url({ink_chev}); width: 10px; height: 10px; }}

QProgressBar {{ background: {t.line}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }}
QProgressBar::chunk {{ border-radius: 3px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
    stop:0 {t.accent}, stop:1 {t.foam if t.dark else t.accent_deep}); }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {rgba('muted', 0.35)}; border-radius: 3px; min-height: 36px; }}
QScrollBar::handle:vertical:hover {{ background: {rgba('muted', 0.6)}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {rgba('muted', 0.35)}; border-radius: 3px; min-width: 36px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

*[dim="true"] {{ color: {t.muted}; }}
*[warn="true"] {{ color: {t.amber}; }}
*[eyebrow="true"] {{ color: {t.muted}; font-weight: 700; letter-spacing: 1.4px; }}

/* Cards on the canvas */
QWidget#card {{ background: {t.surface}; border: 1px solid {t.line}; border-radius: 16px; }}
QFrame#notice {{ background: {t.accent_soft}; border: none; border-radius: 10px; }}
QFrame#chip {{ background: {t.raised}; border: 1px solid {t.accent}; border-radius: 17px; }}
QLineEdit#markernote {{ background: {glass}; color: {t.on_deep}; border: 1px solid {t.foam}; border-radius: 10px; padding: 6px 8px; }}
QToolButton#tagchip {{ background: {glass}; color: {t.on_deep}; border: 1px solid {glass_line}; border-radius: 11px;
    padding: 2px 9px; }}
QToolButton#tagchip:hover {{ background: {glass_hover}; }}
QToolButton#tagchip:checked {{ background: {t.foam}; color: {t.deep_top}; border-color: {t.foam}; }}
QToolButton#tageditchip {{ background: {t.accent_soft}; color: {t.accent_deep}; border: none; border-radius: 11px;
    padding: 2px 9px; }}
QToolButton#tageditchip:hover {{ background: {t.coral}; color: #ffffff; }}
QLineEdit#tagentry {{ background: transparent; border: 1px dashed {t.line}; border-radius: 11px; padding: 2px 8px;
    color: {t.ink}; }}
QLineEdit#tagentry:focus {{ border: 1px solid {t.accent}; background: {t.raised}; }}
QPlainTextEdit#notes {{ background: transparent; border: 1px solid transparent; border-radius: 6px; color: {t.ink};
    padding: 0 2px; }}
QPlainTextEdit#notes:hover {{ border-color: {t.line}; }}
QPlainTextEdit#notes:focus {{ background: {t.raised}; border-color: {t.accent}; }}
QPlainTextEdit#editor {{ background: {t.surface}; color: {t.ink}; border: none;
    selection-background-color: {t.accent_soft}; selection-color: {t.ink}; }}
QLineEdit#title {{ background: transparent; border: 1px solid transparent; color: {t.ink}; padding: 2px 4px; }}
QLineEdit#title:hover {{ border-color: {t.line}; }}
QLineEdit#title:focus {{ background: {t.raised}; border-color: {t.accent}; }}
QLineEdit#context {{ background: transparent; border: 1px solid transparent; border-radius: 6px; color: {t.muted}; padding: 1px 4px; font-style: italic; }}
QLineEdit#context:hover {{ border-color: {t.line}; }}
QLineEdit#context:focus {{ background: {t.raised}; border-color: {t.accent}; color: {t.ink}; font-style: normal; }}
QToolButton#play {{ background: {t.accent}; border: none; border-radius: 21px; padding: 0; }}
QToolButton#play:hover {{ background: {t.accent_deep}; }}
QToolButton#play:disabled {{ background: {t.line}; }}

/* The deep sidebar */
QWidget#sidebar QLabel {{ color: {t.on_deep}; background: transparent; }}
QWidget#sidebar *[dim="true"] {{ color: {t.on_deep_muted}; }}
QWidget#sidebar *[eyebrow="true"] {{ color: {t.on_deep_muted}; }}
QWidget#sidebar *[warn="true"] {{ color: #ffc56b; }}
QWidget#sidebar QLineEdit, QWidget#sidebar QComboBox {{ background: {glass}; color: {t.on_deep};
    border: 1px solid {glass_line}; selection-background-color: {rgba('foam', 0.35)}; selection-color: {t.on_deep}; }}
QWidget#sidebar QLineEdit:focus, QWidget#sidebar QComboBox:hover {{ border-color: {t.foam}; background: {glass_hover}; }}
QWidget#sidebar QComboBox:disabled {{ color: {t.on_deep_muted}; }}
QWidget#sidebar QComboBox::down-arrow {{ image: url({deep_chev}); }}
QWidget#sidebar QComboBox QAbstractItemView {{ background: {t.surface}; color: {t.ink}; border: 1px solid {t.line};
    selection-background-color: {t.accent_soft}; selection-color: {t.ink}; }}
QComboBox QAbstractItemView::item {{ color: {t.ink}; padding: 5px 8px; min-height: 22px; }}
QComboBox QAbstractItemView::item:selected {{ background: {t.accent_soft}; color: {t.ink}; }}
QWidget#sidebar QLineEdit {{ border-radius: 12px; padding: 8px 10px; }}
QWidget#sidebar QToolButton {{ background: {glass}; color: {t.on_deep}; border: 1px solid {glass_line}; }}
QWidget#sidebar QToolButton:hover {{ background: {glass_hover}; border-color: {t.foam}; }}
QWidget#sidebar QToolButton:checked {{ background: {rgba('foam', 0.28)}; border-color: {t.foam}; }}
QWidget#sidebar QListView {{ background: transparent; border: none; }}
QWidget#sidebar QToolButton#record {{ color: white; border: none; border-radius: 23px; font-weight: 800; font-size: 12pt;
    padding: 0 18px; background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {t.coral}, stop:1 {t.coral_deep}); }}
QWidget#sidebar QToolButton#record:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ff7f7f, stop:1 #e11d48); }}
QWidget#sidebar QToolButton#record[recording="true"] {{ background: {t.on_deep}; color: {t.coral_deep}; }}
QWidget#sidebar QToolButton#record[recording="true"]:hover {{ background: #ffffff; }}
QWidget#sidebar QToolButton#record:disabled {{ background: {glass}; color: {t.on_deep_muted}; }}
QWidget#sidebar QToolButton#pause {{ border-radius: 23px; }}
QWidget#sidebar QFrame#banner {{ background: {rgba('foam', 0.16)}; border: 1px solid {rgba('foam', 0.45)};
    border-radius: 10px; }}
QWidget#sidebar QFrame#banner QLabel {{ color: {t.on_deep}; }}
QWidget#sidebar QFrame#banner QToolButton:!hover {{ background: transparent; border: none; }}
QWidget#sidebar QFrame#banner QToolButton#linkbtn {{ background: {t.foam}; }}
QWidget#sidebar QFrame#selectionbar {{ background: {rgba('foam', 0.16)}; border-top: 1px solid {glass_line}; }}
QWidget#sidebar QFrame#selectionbar QLabel {{ color: {t.on_deep}; }}
QWidget#sidebar QToolButton#linkbtn {{ background: {t.foam}; color: {t.deep_top}; border: none; border-radius: 8px;
    padding: 4px 10px; font-weight: 700; }}
QWidget#sidebar QToolButton#linkbtn:hover {{ background: #ffffff; }}
QWidget#sidebar QSlider::groove:horizontal {{ height: 4px; border-radius: 2px; background: {glass_line}; }}
QWidget#sidebar QSlider::sub-page:horizontal {{ height: 4px; border-radius: 2px; background: {t.foam}; }}
QWidget#sidebar QSlider::handle:horizontal {{ width: 14px; height: 14px; margin: -5px 0; border-radius: 7px;
    background: {t.on_deep}; border: 2px solid {t.foam}; }}
QWidget#sidebar QSlider::handle:horizontal:hover {{ background: #ffffff; }}
"""


# ---- applying -------------------------------------------------------------------------------------

def apply(mode_: str = LIGHT, app: QApplication | None = None) -> Tokens:
    """Apply a theme mode to the application and repaint every window."""
    global _current, _mode
    app = app or QApplication.instance()
    load_fonts()
    _mode = mode_ if mode_ in MODES else LIGHT
    _current = resolve(_mode)
    app.setStyle("Fusion")
    app.setFont(ui_font())
    app.setPalette(palette(_current))
    app.setStyleSheet(stylesheet(_current))
    for w in app.allWidgets():
        w.update()
    return _current


def set_role(widget: QWidget, **props) -> QWidget:
    """Tag a widget for the stylesheet (dim=True, warn=True, eyebrow=True) and re-polish it."""
    for k, v in props.items():
        widget.setProperty(k, "true" if v else "false")
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    return widget
