"""Drawing of the chip package with clickable pins.

Click a pin to select it (the side panel shows its settings). Right-click for
a menu of functions, with "Unused" at the top. Delete / Backspace resets the
selected pin. Click the background to deselect.
"""

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QGraphicsItem, QGraphicsRectItem, QGraphicsScene, QGraphicsSimpleTextItem,
                               QGraphicsView, QMenu)

from ..chips import FUNCTIONS

COLORS = {
    "unused": "#d9dde3",
    "output": "#8fd18f",
    "input": "#8fbfe8",
    "interrupt": "#6fa0f0",
    "pwm": "#f2b35e",
    "comp_minus": "#c99be6",
    "comp_plus": "#c99be6",
    "comp_out": "#b07fd6",
    "adc": "#e6d36e",
    "serial_tx": "#ef8f8f",
    "reset": "#a0a0a0",
    "power": "#55595f",
}

PIN_W, PIN_H, GAP = 34, 22, 8
LABEL_W = 150


def short_function(fn, cfg):
    if fn == "pwm":
        per = cfg.get("periph", "")
        return per if per.startswith("PWM") else f"PWM {per}"
    return {
        "output": "Output", "input": "Input", "interrupt": "Interrupt", "comp_minus": "Comp -",
        "comp_plus": "Comp +", "comp_out": "Comp out", "adc": "ADC", "serial_tx": "Serial TX",
        "reset": "Reset",
    }.get(fn, "")


class PinItem(QGraphicsRectItem):
    def __init__(self, view, name, number, w, h):
        super().__init__(0, 0, w, h)
        self.view = view
        self.name = name
        self.number = number
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor if name not in ("VDD", "GND") else Qt.ArrowCursor)
        self.num_text = QGraphicsSimpleTextItem(str(number), self)
        f = QFont()
        f.setPointSize(7)
        self.num_text.setFont(f)
        self.num_text.setBrush(QBrush(QColor("#333")))
        self.hover = False

    def hoverEnterEvent(self, e):
        self.hover = True
        self.update()

    def hoverLeaveEvent(self, e):
        self.hover = False
        self.update()

    def mousePressEvent(self, e):
        if self.name in ("VDD", "GND"):
            self.view.select_pin(None)
            return
        if e.button() == Qt.LeftButton:
            self.view.select_pin(self.name)
        elif e.button() == Qt.RightButton:
            self.view.select_pin(self.name)
            self.view.pin_menu(self.name, e.screenPos())
        e.accept()

    def paint(self, painter, option, widget=None):
        brush = self.brush().color()
        if self.hover and self.name not in ("VDD", "GND"):
            brush = brush.lighter(115)
        painter.setBrush(brush)
        sel = self.view.selected == self.name
        painter.setPen(QPen(QColor("#1a73e8") if sel else QColor("#666"), 3 if sel else 1))
        painter.drawRoundedRect(self.rect(), 3, 3)


class ChipView(QGraphicsView):
    pinSelected = Signal(object)            # pin name or None
    pinFunctionChosen = Signal(str, str)    # pin, function id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.TextAntialiasing)
        self.setFocusPolicy(Qt.StrongFocus)
        self.project = None
        self.selected = None
        self.items = {}

    # ---- drawing --------------------------------------------------------------
    def set_project(self, project):
        self.project = project
        if self.selected and self.selected not in project.chip.pins:
            self.selected = None
        self.redraw()

    def request_redraw(self):
        """Redraw after the current event: the pin items may still be handling a click."""
        if not getattr(self, "_redraw_pending", False):
            self._redraw_pending = True
            QTimer.singleShot(0, self.redraw)

    def redraw(self):
        self._redraw_pending = False
        sc = self.scene()
        sc.clear()
        self.items = {}
        if not self.project:
            return
        chip = self.project.chip
        pkg = chip.package(self.project.data["package"])
        n = len(pkg.pins)
        if pkg.quad:
            self._draw_quad(pkg, n)
        else:
            self._draw_dual(pkg, n)
        sc.setSceneRect(sc.itemsBoundingRect().adjusted(-20, -20, 20, 20))
        self.fit()

    def _body(self, x, y, w, h, title, sub):
        body = self.scene().addRect(x, y, w, h, QPen(QColor("#222"), 1.5), QBrush(QColor("#2f3237")))
        body.setZValue(-1)
        t = self.scene().addSimpleText(title)
        f = QFont()
        f.setPointSize(13)
        f.setBold(True)
        t.setFont(f)
        t.setBrush(QBrush(QColor("#f0f0f0")))
        br = t.boundingRect()
        t.setPos(x + (w - br.width()) / 2, y + h / 2 - br.height())
        s = self.scene().addSimpleText(sub)
        f2 = QFont()
        f2.setPointSize(8)
        s.setFont(f2)
        s.setBrush(QBrush(QColor("#c0c0c0")))
        br2 = s.boundingRect()
        s.setPos(x + (w - br2.width()) / 2, y + h / 2 + 2)
        # notch at the top marks the pin-1 end
        notch = self.scene().addEllipse(x + w / 2 - 12, y - 12, 24, 24, QPen(QColor("#222"), 1.5),
                                        QBrush(QColor("#45494f")))
        notch.setSpanAngle(-180 * 16)
        notch.setStartAngle(0)
        notch.setZValue(0)

    def _pin(self, name, number, x, y, w, h, side):
        item = PinItem(self, name, number, w, h)
        item.setPos(x, y)
        fn = "power" if name in ("VDD", "GND") else self.project.fn(name)
        item.setBrush(QBrush(QColor(COLORS.get(fn, "#ddd"))))
        self.scene().addItem(item)
        nb = item.num_text.boundingRect()
        item.num_text.setPos((w - nb.width()) / 2, (h - nb.height()) / 2)
        # pin name + assignment as text outside the body
        cfg = self.project.pins.get(name, {}) if name not in ("VDD", "GND") else {}
        label = name
        extra = ""
        if cfg:
            extra = cfg.get("label") or ""
            fn_txt = short_function(cfg["fn"], cfg)
            extra = f"{extra}  ({fn_txt})" if extra else fn_txt
        bonded_text = QGraphicsSimpleTextItem(label)
        f = QFont()
        f.setBold(True)
        f.setPointSize(9)
        bonded_text.setFont(f)
        bonded_text.setBrush(QBrush(QColor("#ffffff" if name in ("VDD", "GND") else "#ffffff")))
        sub = QGraphicsSimpleTextItem(extra)
        f2 = QFont()
        f2.setPointSize(8)
        sub.setFont(f2)
        sub.setBrush(QBrush(QColor("#2a6f2a" if cfg else "#666")))
        self.scene().addItem(bonded_text)
        self.scene().addItem(sub)
        bt, st = bonded_text.boundingRect(), sub.boundingRect()
        # pin name inside the body, assignment outside
        if side == "left":
            bonded_text.setPos(x + w + 6, y + (h - bt.height()) / 2)
            sub.setPos(x - st.width() - 6, y + (h - st.height()) / 2)
        elif side == "right":
            bonded_text.setPos(x - bt.width() - 6, y + (h - bt.height()) / 2)
            sub.setPos(x + w + 6, y + (h - st.height()) / 2)
        elif side == "top":
            bonded_text.setPos(x + (w - bt.width()) / 2, y + h + 4)
            sub.setRotation(-45)
            sub.setPos(x + w / 2 - 2, y - 2)
        else:
            bonded_text.setPos(x + (w - bt.width()) / 2, y - bt.height() - 4)
            sub.setRotation(45)
            sub.setPos(x + w / 2 - 6, y + h + 2)
        if name in ("VDD", "GND"):
            bonded_text.setBrush(QBrush(QColor("#f0f0f0")))
        self.items[name] = item

    def _draw_dual(self, pkg, n):
        half = n // 2
        h_body = half * (PIN_H + GAP) + GAP
        w_body = 170
        x0, y0 = 0, 0
        chip = self.project.chip
        self._body(x0, y0, w_body, h_body, chip.name, pkg.key)
        for i in range(half):
            y = y0 + GAP + i * (PIN_H + GAP)
            self._pin(pkg.pins[i], i + 1, x0 - PIN_W, y, PIN_W, PIN_H, "left")
        for i in range(half):
            idx = n - 1 - i     # right side counts upwards from the bottom
            y = y0 + GAP + i * (PIN_H + GAP)
            self._pin(pkg.pins[idx], idx + 1, x0 + w_body, y, PIN_W, PIN_H, "right")

    def _draw_quad(self, pkg, n):
        side = n // 4
        size = side * (PIN_H + GAP) + 3 * GAP + 40
        chip = self.project.chip
        self._body(0, 0, size, size, chip.name, pkg.key)
        off = (size - (side * (PIN_H + GAP) - GAP)) / 2
        for i in range(n):
            s, k = divmod(i, side)
            if s == 0:      # left, top to bottom
                self._pin(pkg.pins[i], i + 1, -PIN_W, off + k * (PIN_H + GAP), PIN_W, PIN_H, "left")
            elif s == 1:    # bottom, left to right
                self._pin(pkg.pins[i], i + 1, off + k * (PIN_H + GAP), size, PIN_H, PIN_W, "bottom")
            elif s == 2:    # right, bottom to top
                self._pin(pkg.pins[i], i + 1, size, size - off - PIN_H - k * (PIN_H + GAP), PIN_W, PIN_H, "right")
            else:           # top, right to left
                self._pin(pkg.pins[i], i + 1, size - off - PIN_H - k * (PIN_H + GAP), -PIN_W, PIN_H, PIN_W, "top")
        if pkg.note:
            t = self.scene().addSimpleText(pkg.note)
            t.setBrush(QBrush(QColor("#c0c0c0")))
            t.setPos(10, size - 22)

    def fit(self):
        r = self.scene().sceneRect()
        if r.isEmpty():
            return
        self.fitInView(r, Qt.KeepAspectRatio)
        # don't blow small packages up too much
        if self.transform().m11() > 1.6:
            self.resetTransform()
            self.scale(1.6, 1.6)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.fit()

    # ---- interaction ------------------------------------------------------------
    def select_pin(self, name):
        if name == self.selected:
            self.pinSelected.emit(name)
            return
        self.selected = name
        for it in self.items.values():
            it.update()
        self.pinSelected.emit(name)

    def mousePressEvent(self, e):
        item = self.itemAt(e.position().toPoint())
        while item is not None and not isinstance(item, PinItem):
            item = item.parentItem()
        if item is None:
            self.select_pin(None)
        super().mousePressEvent(e)

    def keyPressEvent(self, e):
        if self.selected and e.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.pinFunctionChosen.emit(self.selected, "unused")
            return
        if e.key() == Qt.Key_Escape:
            self.select_pin(None)
            return
        super().keyPressEvent(e)

    def pin_menu(self, name, screen_pos):
        if not self.project:
            return
        info = self.project.chip.pins[name]
        current = self.project.fn(name)
        menu = QMenu(self)
        act = menu.addAction("Unused (reset pin)")
        act.setCheckable(True)
        act.setChecked(current == "unused")
        act.triggered.connect(lambda: self.pinFunctionChosen.emit(name, "unused"))
        menu.addSeparator()
        for fn in info.functions:
            a = menu.addAction(FUNCTIONS[fn])
            a.setCheckable(True)
            a.setChecked(current == fn)
            a.triggered.connect(lambda checked=False, f=fn: self.pinFunctionChosen.emit(name, f))
        menu.exec(screen_pos)
