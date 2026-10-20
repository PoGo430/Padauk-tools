#!/usr/bin/env python3
"""
Padauk Configurator - a small STM32CubeMX-style pin and peripheral setup tool
for the PFS154, PFS122 and PMS150C (and PFS172).

Click pins on the chip to give them a function, set PWM / comparator / ADC /
system options, then "Generate code" writes pdk_init.h + pdk_init.c into the
project and hooks them into main.c. Settings are saved in padauk.json.

  python3 pdk_configurator.py [project-folder]     (or: pdk configure)
"""
import importlib.machinery
import importlib.util
import os
import re
import sys

from PyQt5.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout, QGraphicsRectItem, QGraphicsScene, QGraphicsSimpleTextItem,
    QGraphicsView, QGroupBox, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
    QScrollArea, QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
    QWidget,
)

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)
import pdk_codegen as g  # noqa: E402


def _load_pdk():
    base = getattr(sys, "_MEIPASS", os.path.dirname(HERE))
    path = os.path.join(base, "pdk")
    loader = importlib.machinery.SourceFileLoader("pdk_cli", path)
    spec = importlib.util.spec_from_loader("pdk_cli", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    mod.COLOR = False
    return mod


pdk = _load_pdk()

GROUP_COLORS = {
    None: "#d9d9d9", "gpio": "#43a047", "int": "#8e24aa", "pwm": "#1e88e5",
    "analog": "#fb8c00", "serial": "#00897b", "system": "#e53935",
}
POWER_COLORS = {"VDD": "#c62828", "GND": "#424242"}
CLOCKS = [("16 MHz", 16_000_000), ("8 MHz", 8_000_000), ("4 MHz", 4_000_000), ("2 MHz", 2_000_000),
          ("1 MHz", 1_000_000), ("500 kHz", 500_000), ("250 kHz", 250_000)]
VOLTAGES = [("5.0 V", 5000), ("4.0 V", 4000), ("3.3 V", 3300), ("3.0 V", 3000), ("2.5 V", 2500)]


def text_color_for(bg):
    c = QColor(bg)
    return Qt.black if (c.red() * 299 + c.green() * 587 + c.blue() * 114) / 1000 > 150 else Qt.white


# ----------------------------------------------------------------------------
# Chip drawing
# ----------------------------------------------------------------------------
class PinItem(QGraphicsRectItem):
    def __init__(self, view, pin, number, rect):
        super().__init__(rect)
        self.view, self.pin, self.number = view, pin, number
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor if pin.startswith("P") else Qt.ArrowCursor)

    def mousePressEvent(self, event):
        if self.pin.startswith("P"):
            self.view.pinClicked.emit(self.pin, event.screenPos())

    def hoverEnterEvent(self, event):
        self.setPen(QPen(QColor("#000000"), 2))

    def hoverLeaveEvent(self, event):
        self.setPen(QPen(QColor("#555555"), 1))


class ChipView(QGraphicsView):
    pinClicked = pyqtSignal(str, object)

    PITCH = 38
    PIN_LEN = 46
    PIN_W = 26

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.Antialiasing)
        self.setMinimumSize(420, 380)
        self.setBackgroundBrush(QColor("#fafafa"))

    def draw(self, cfg):
        scene = self.scene()
        scene.clear()
        pkg = g.current_package(cfg)
        pins = pkg["pins"]
        n = len(pins)
        mono = QFont("Monospace", 9)
        mono.setStyleHint(QFont.TypeWriter)
        bold = QFont()
        bold.setBold(True)

        if pkg["quad"]:
            side = n // 4
            size = side * self.PITCH + 30
            body = QRectF(0, 0, size, size)
            sides = ["left", "bottom", "right", "top"]
            positions = []
            for i in range(n):
                s, k = divmod(i, side)
                off = 15 + k * self.PITCH + self.PITCH / 2
                if sides[s] == "left":
                    positions.append(("left", off))
                elif sides[s] == "bottom":
                    positions.append(("bottom", off))
                elif sides[s] == "right":
                    positions.append(("right", size - off))
                else:
                    positions.append(("top", size - off))
        else:
            half = n // 2
            h = half * self.PITCH + 20
            body = QRectF(0, 0, 150, h)
            positions = [("left", 10 + i * self.PITCH + self.PITCH / 2) for i in range(half)] + \
                        [("right", h - (10 + i * self.PITCH + self.PITCH / 2)) for i in range(half)]

        body_item = scene.addRect(body, QPen(QColor("#222222"), 2), QBrush(QColor("#2b2b2b")))
        body_item.setZValue(-1)
        scene.addEllipse(body.left() + 10, body.top() + 10, 9, 9, QPen(Qt.NoPen), QBrush(QColor("#888888")))
        title = scene.addSimpleText(cfg["device"], bold)
        title.setBrush(QColor("#ffffff"))
        title.setPos(body.center().x() - title.boundingRect().width() / 2, body.center().y() - 18)
        sub = scene.addSimpleText(cfg["package"], QFont("Sans", 7))
        sub.setBrush(QColor("#bbbbbb"))
        sub.setPos(body.center().x() - sub.boundingRect().width() / 2, body.center().y() + 2)

        for idx, ((side, off), pin) in enumerate(zip(positions, pins)):
            entry = cfg["pins"].get(pin)
            fn = entry["function"] if entry else None
            group = g.FUNCTIONS[fn][2] if fn else None
            color = POWER_COLORS.get(pin, GROUP_COLORS[group])
            L, W = self.PIN_LEN, self.PIN_W
            if side == "left":
                rect = QRectF(body.left() - L, off - W / 2, L, W)
            elif side == "right":
                rect = QRectF(body.right(), off - W / 2, L, W)
            elif side == "bottom":
                rect = QRectF(off - W / 2, body.bottom(), W, L)
            else:
                rect = QRectF(off - W / 2, body.top() - L, W, L)
            item = PinItem(self, pin, idx + 1, rect)
            item.setBrush(QBrush(QColor(color)))
            item.setPen(QPen(QColor("#555555"), 1))
            item.setToolTip(self.tooltip(cfg, pin, idx + 1))
            scene.addItem(item)

            # pin name on the pin, function/name outside
            label = QGraphicsSimpleTextItem(pin, item)
            label.setFont(mono)
            label.setBrush(QBrush(text_color_for(color)))
            br = label.boundingRect()
            if side in ("left", "right"):
                label.setPos(rect.center().x() - br.width() / 2, rect.center().y() - br.height() / 2)
            else:
                label.setRotation(-90)
                label.setPos(rect.center().x() - br.height() / 2, rect.center().y() + br.width() / 2)
            num = QGraphicsSimpleTextItem(str(idx + 1), body_item)
            num.setFont(QFont("Sans", 7))
            num.setBrush(QColor("#9e9e9e"))
            nb = num.boundingRect()
            if side == "left":
                num.setPos(body.left() + 4, off - nb.height() / 2)
            elif side == "right":
                num.setPos(body.right() - nb.width() - 4, off - nb.height() / 2)
            elif side == "bottom":
                num.setPos(off - nb.width() / 2, body.bottom() - nb.height() - 2)
            else:
                num.setPos(off - nb.width() / 2, body.top() + 2)

            if fn:
                text = f"{g.pin_name(cfg, pin)}  {g.FUNCTIONS[fn][1]}" if side == "left" else \
                    f"{g.FUNCTIONS[fn][1]}  {g.pin_name(cfg, pin)}"
                out = scene.addSimpleText(text, QFont("Sans", 9))
                out.setBrush(QColor(color).darker(140))
                ob = out.boundingRect()
                if side == "left":
                    out.setPos(rect.left() - ob.width() - 6, rect.center().y() - ob.height() / 2)
                elif side == "right":
                    out.setPos(rect.right() + 6, rect.center().y() - ob.height() / 2)
                elif side == "bottom":
                    out.setRotation(90)
                    out.setPos(rect.center().x() + ob.height() / 2, rect.bottom() + 6)
                else:
                    out.setRotation(-90)
                    out.setPos(rect.center().x() - ob.height() / 2, rect.top() - 6)
        for desc, pin in pkg["extra"]:
            t = scene.addSimpleText(f"{desc}: {pin}", QFont("Sans", 8))
            t.setPos(body.left(), body.bottom() + (self.PIN_LEN + 30 if pkg["quad"] else 10))
        self.setSceneRect(scene.itemsBoundingRect().adjusted(-20, -20, 20, 20))
        self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)

    @staticmethod
    def tooltip(cfg, pin, number):
        device = cfg["device"]
        lines = [f"<b>Pin {number}: {pin}</b>"]
        if pin in ("VDD", "GND"):
            lines.append("Power")
            return "<br>".join(lines)
        info = g.pin_info(device)
        cur = info["current"].get(pin)
        if cur:
            lines.append("Max current: " + ", ".join(cur))
        pulls = [p for p, lst in (("pull-up", info["pull_up"]), ("pull-down", info["pull_down"])) if pin in lst]
        if pulls:
            lines.append("Internal " + " and ".join(pulls))
        if pin in info["programming"]:
            lines.append(f"<i>Programming pin ({info['programming'][pin]}): keep it free of heavy loads "
                         "if you program in-circuit</i>")
        funcs = [g.FUNCTIONS[f][0] for f in g.pin_functions(device, pin)]
        lines.append("Can be: " + ", ".join(funcs))
        lines.append("<i>Click to change</i>")
        return "<br>".join(lines)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.scene().items():
            self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)


# ----------------------------------------------------------------------------
# Main window
# ----------------------------------------------------------------------------
class ConfiguratorWindow(QMainWindow):
    generated = pyqtSignal(str)

    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        settings = pdk.project_settings(project)
        device = settings["DEVICE"] if settings["DEVICE"] in g.CHIPS else "PFS154"
        self.cfg = g.load_config(project, device)
        if self.cfg["device"] != device and not os.path.isfile(os.path.join(project, g.CONFIG_FILE)):
            self.cfg = g.default_config(device)
        self.f_cpu = int(settings["F_CPU"])
        self.vdd = int(settings["TARGET_VDD_MV"])
        self.updating = False
        self.dirty = False

        self.setWindowTitle(f"Padauk Configurator - {os.path.basename(project)}")
        self.resize(1250, 800)

        root = QWidget()
        outer = QVBoxLayout(root)
        outer.addLayout(self.build_top_bar())

        split = QSplitter()
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        self.chip_view = ChipView()
        self.chip_view.pinClicked.connect(self.pin_menu)
        lv.addWidget(self.chip_view, 1)
        lv.addWidget(self.build_legend())
        split.addWidget(left)

        self.tabs = QTabWidget()
        self.tabs.addTab(self.build_pins_tab(), "Pins")
        self.tabs.addTab(self.build_pwm_tab(), "PWM")
        self.tabs.addTab(self.build_analog_tab(), "Analog")
        self.tabs.addTab(self.build_system_tab(), "System")
        self.tabs.addTab(self.build_code_tab(), "Code preview")
        split.addWidget(self.tabs)
        split.setSizes([560, 690])
        outer.addWidget(split, 1)

        bottom = QHBoxLayout()
        self.problems = QListWidget()
        self.problems.setMaximumHeight(96)
        bottom.addWidget(self.problems, 1)
        btns = QVBoxLayout()
        self.gen_btn = QPushButton("Generate code")
        self.gen_btn.setStyleSheet("font-weight: bold; padding: 8px 18px")
        self.gen_btn.clicked.connect(self.generate)
        btns.addWidget(self.gen_btn)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        btns.addWidget(close)
        btns.addStretch(1)
        bottom.addLayout(btns)
        outer.addLayout(bottom)
        self.setCentralWidget(root)
        self.refresh()

    # ----- top bar / legend ----------------------------------------------------
    def build_top_bar(self):
        row = QHBoxLayout()
        row.addWidget(QLabel("Chip:"))
        self.chip_combo = QComboBox()
        for d in g.SUPPORTED:
            self.chip_combo.addItem(d + ("  (OTP)" if g.chip(d)["otp"] else ""), d)
        self.chip_combo.currentIndexChanged.connect(self.change_chip)
        row.addWidget(self.chip_combo)
        row.addSpacing(12)
        row.addWidget(QLabel("Package:"))
        self.pkg_combo = QComboBox()
        self.pkg_combo.currentIndexChanged.connect(self.change_package)
        row.addWidget(self.pkg_combo, 1)
        row.addSpacing(12)
        path = QLabel(self.project)
        path.setStyleSheet("color: #777")
        row.addWidget(path)
        return row

    def build_legend(self):
        w = QWidget()
        row = QHBoxLayout(w)
        row.setContentsMargins(4, 0, 4, 0)
        for name, group in (("GPIO", "gpio"), ("Interrupt", "int"), ("PWM", "pwm"), ("Analog", "analog"),
                            ("Serial", "serial"), ("System", "system"), ("Unused", None)):
            sw = QLabel()
            sw.setFixedSize(12, 12)
            sw.setStyleSheet(f"background: {GROUP_COLORS[group]}; border: 1px solid #666")
            row.addWidget(sw)
            row.addWidget(QLabel(name))
            row.addSpacing(6)
        row.addStretch(1)
        hint = QLabel("Click a pin to assign it")
        hint.setStyleSheet("color: #777")
        row.addWidget(hint)
        return w

    # ----- tabs ----------------------------------------------------------------
    def build_pins_tab(self):
        self.pin_table = QTableWidget(0, 5)
        self.pin_table.setHorizontalHeaderLabels(["Pin", "Name (used in code)", "Function", "Option", "Edge"])
        self.pin_table.verticalHeader().setVisible(False)
        self.pin_table.setSelectionMode(QAbstractItemView.NoSelection)
        hdr = self.pin_table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        self.pin_table.itemChanged.connect(self.pin_name_edited)
        return self.pin_table

    def build_pwm_tab(self):
        self.pwm_area = QScrollArea()
        self.pwm_area.setWidgetResizable(True)
        return self.pwm_area

    def build_analog_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        box = QGroupBox("Comparator")
        f = QFormLayout(box)
        self.comp_enable = QCheckBox("Use the comparator (also on when a COMP pin is assigned)")
        f.addRow(self.comp_enable)
        self.comp_inputs = QLabel()
        self.comp_inputs.setWordWrap(True)
        f.addRow("Inputs:", self.comp_inputs)
        self.comp_minus = QComboBox()
        self.comp_minus.addItem("Bandgap 1.2 V", "bandgap")
        self.comp_minus.addItem("Internal reference (resistor ladder)", "internal")
        f.addRow("- input without a pin:", self.comp_minus)
        self.comp_range = QSpinBox()
        self.comp_range.setRange(1, 4)
        self.comp_level = QSpinBox()
        self.comp_level.setRange(0, 15)
        rr = QHBoxLayout()
        rr.addWidget(QLabel("range"))
        rr.addWidget(self.comp_range)
        rr.addWidget(QLabel("level"))
        rr.addWidget(self.comp_level)
        rr.addStretch(1)
        f.addRow("Internal reference:", rr)
        ref_note = QLabel("The reference voltage for each range/level is a fraction of VDD, "
                          "listed in the comparator chapter of the datasheet.")
        ref_note.setWordWrap(True)
        ref_note.setStyleSheet("color: #777")
        f.addRow(ref_note)
        self.comp_invert = QCheckBox("Invert output")
        f.addRow(self.comp_invert)
        self.comp_irq = QCheckBox("Interrupt (sets pdk_comp_flag)")
        self.comp_edge = QComboBox()
        for e in ("both", "rising", "falling"):
            self.comp_edge.addItem(e, e)
        ir = QHBoxLayout()
        ir.addWidget(self.comp_irq)
        ir.addWidget(self.comp_edge)
        ir.addStretch(1)
        f.addRow(ir)
        v.addWidget(box)
        for wdg in (self.comp_enable, self.comp_invert, self.comp_irq):
            wdg.toggled.connect(self.analog_changed)
        for wdg in (self.comp_minus, self.comp_edge):
            wdg.currentIndexChanged.connect(self.analog_changed)
        for wdg in (self.comp_range, self.comp_level):
            wdg.valueChanged.connect(self.analog_changed)

        self.adc_box = QGroupBox("ADC")
        af = QFormLayout(self.adc_box)
        self.adc_clock = QSpinBox()
        self.adc_clock.setRange(16, 2000)
        self.adc_clock.setSuffix(" kHz max")
        self.adc_clock.valueChanged.connect(self.analog_changed)
        af.addRow("ADC clock:", self.adc_clock)
        self.adc_note = QLabel()
        self.adc_note.setWordWrap(True)
        af.addRow(self.adc_note)
        v.addWidget(self.adc_box)
        v.addStretch(1)
        return w

    def build_system_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        box = QGroupBox("Clock and supply (saved in the Makefile)")
        f = QFormLayout(box)
        self.clock = QComboBox()
        for label, hz in CLOCKS:
            self.clock.addItem(label, hz)
        self.vdd_combo = QComboBox()
        for label, mv in VOLTAGES:
            self.vdd_combo.addItem(label, mv)
        f.addRow("System clock (F_CPU):", self.clock)
        f.addRow("Supply voltage:", self.vdd_combo)
        v.addWidget(box)

        box = QGroupBox("System")
        f = QFormLayout(box)
        self.unused = QComboBox()
        self.unused.addItem("Input with pull-up (low power, safe)", "pullup")
        self.unused.addItem("Output low", "output_low")
        self.unused.addItem("Leave floating", "float")
        f.addRow("Unused pins:", self.unused)
        self.millis = QCheckBox("millis() timebase (Timer16 interrupt)")
        f.addRow(self.millis)
        self.watchdog = QComboBox()
        for label, val in (("Off", "off"), ("8k ILRC clocks (~0.15 s)", "8k"), ("16k ILRC clocks (~0.3 s)", "16k"),
                           ("64k ILRC clocks (~1.2 s)", "64k"), ("256k ILRC clocks (~4.7 s)", "256k")):
            self.watchdog.addItem(label, val)
        f.addRow("Watchdog:", self.watchdog)
        v.addWidget(box)

        box = QGroupBox("Fuses and reset")
        f = QFormLayout(box)
        self.fuses = QCheckBox("Set fuses (recommended: factory defaults differ per chip)")
        f.addRow(self.fuses)
        self.security = QCheckBox("Code protection (security fuse) - chip can't be read back")
        f.addRow(self.security)
        self.drive = QComboBox()
        f.addRow("Pin drive:", self.drive)
        self.bootup = QComboBox()
        self.bootup.addItem("Slow (safer with slowly rising supply)", "slow")
        self.bootup.addItem("Fast", "fast")
        f.addRow("Boot-up time:", self.bootup)
        self.lvr = QComboBox()
        f.addRow("Low voltage reset:", self.lvr)
        v.addWidget(box)
        v.addStretch(1)

        for wdg in (self.clock, self.vdd_combo, self.unused, self.watchdog, self.drive, self.bootup, self.lvr):
            wdg.currentIndexChanged.connect(self.system_changed)
        for wdg in (self.millis, self.fuses, self.security):
            wdg.toggled.connect(self.system_changed)
        return w

    def build_code_tab(self):
        tabs = QTabWidget()
        font = QFont("Monospace", 9)
        font.setStyleHint(QFont.TypeWriter)
        self.code_h, self.code_c = QPlainTextEdit(), QPlainTextEdit()
        for ed, name in ((self.code_c, "pdk_init.c"), (self.code_h, "pdk_init.h")):
            ed.setReadOnly(True)
            ed.setFont(font)
            ed.setLineWrapMode(QPlainTextEdit.NoWrap)
            tabs.addTab(ed, name)
        return tabs

    # ----- refresh everything from self.cfg ------------------------------------
    def refresh(self):
        self.updating = True
        cfg = self.cfg
        c = g.chip(cfg["device"])
        self.chip_combo.setCurrentIndex(self.chip_combo.findData(cfg["device"]))
        self.pkg_combo.clear()
        for pkg in g.packages(cfg["device"]):
            self.pkg_combo.addItem(pkg["label"], pkg["parts"][0])
        self.pkg_combo.setCurrentIndex(max(0, self.pkg_combo.findData(g.current_package(cfg)["parts"][0])))

        self.fill_pin_table()
        self.fill_pwm_tab()

        cc = cfg["comp"]
        funcs = {e["function"]: p for p, e in cfg["pins"].items()}
        self.comp_enable.setChecked(cc["enabled"])
        plus = f"+ = {funcs['comp_plus']} (pin)" if "comp_plus" in funcs else "+ = internal reference"
        minus = f"- = {funcs['comp_minus']} (pin)" if "comp_minus" in funcs else "- = option below"
        out = ", output on PA0" if "comp_out" in funcs else ""
        self.comp_inputs.setText(f"{plus}, {minus}{out}.  Assign COMP+ (PA4), COMP- or COMP OUT (PA0) on the chip.")
        self.comp_minus.setCurrentIndex(self.comp_minus.findData(cc["minus"]))
        self.comp_minus.setEnabled("comp_minus" not in funcs)
        self.comp_range.setValue(int(cc["range"]))
        self.comp_level.setValue(int(cc["level"]))
        self.comp_invert.setChecked(cc["invert"])
        self.comp_irq.setChecked(cc["interrupt"])
        self.comp_edge.setCurrentIndex(self.comp_edge.findData(cc["edge"]))

        self.adc_box.setVisible(bool(c["adc"]))
        self.adc_clock.setValue(int(cfg["adc"].get("clock_khz", 500)))
        if c["adc"]:
            div = g.adc_divider(self.f_cpu, self.adc_clock.value())
            self.adc_note.setText(f"Uses SYSCLK/{div} = {g.human_freq(self.f_cpu / div)}. Read a pin with "
                                  "NAME_read() (8-bit result, reference = VDD)."
                                  + ("\nPFS122: uses the PFS172 ADC registers, not verified on the "
                                     "PFS122's 12-bit ADC." if c.get("adc_assumed") else ""))

        s = cfg["system"]
        self.select(self.clock, self.f_cpu, pdk.human_hz(self.f_cpu))
        self.select(self.vdd_combo, self.vdd, f"{self.vdd / 1000:.2f} V")
        self.unused.setCurrentIndex(self.unused.findData(s["unused_pins"]))
        self.millis.setChecked(s["millis"])
        self.watchdog.setCurrentIndex(self.watchdog.findData(s["watchdog"]))
        self.fuses.setChecked(s["fuses"])
        self.security.setChecked(s["security"])
        self.drive.clear()
        for label, macro in c["drive_fuse"]:
            self.drive.addItem(label, label)
        self.drive.setCurrentIndex(max(0, self.drive.findData(s["drive"])))
        self.bootup.setCurrentIndex(self.bootup.findData(s["bootup"]))
        self.lvr.clear()
        self.lvr.addItem(f"Auto ({g.default_lvr(cfg['device'], self.vdd).replace('V', '.').rstrip('.')} V)", None)
        for lv in c["lvr"][1]:
            self.lvr.addItem(lv.replace("V", ".").rstrip(".") + " V", lv)
        self.lvr.setCurrentIndex(max(0, self.lvr.findData(s["lvr"])) if s["lvr"] else 0)
        for wdg in (self.security, self.drive, self.bootup):
            wdg.setEnabled(s["fuses"])
        self.lvr.setEnabled(s["fuses"] or c["lvr"][0] != "fuse")
        self.updating = False
        self.update_outputs()

    @staticmethod
    def select(combo, value, label):
        i = combo.findData(value)
        if i < 0:
            combo.addItem(label, value)
            i = combo.count() - 1
        combo.setCurrentIndex(i)

    def update_outputs(self):
        """Chip drawing, problems and code preview."""
        self.chip_view.draw(self.cfg)
        errors, warnings = g.check(self.cfg, self.f_cpu, self.vdd)
        self.problems.clear()
        for e in errors:
            it = QListWidgetItem("Error: " + e)
            it.setForeground(QColor("#c62828"))
            self.problems.addItem(it)
        for w in warnings:
            it = QListWidgetItem("Note: " + w)
            it.setForeground(QColor("#9a6700"))
            self.problems.addItem(it)
        if not errors and not warnings:
            it = QListWidgetItem("No problems.")
            it.setForeground(QColor("#2e7d32"))
            self.problems.addItem(it)
        self.gen_btn.setEnabled(not errors)
        h, c = g.generate(self.cfg, self.f_cpu, self.vdd)
        for ed, text in ((self.code_h, h), (self.code_c, c)):
            bar = ed.verticalScrollBar().value()
            ed.setPlainText(text)
            ed.verticalScrollBar().setValue(bar)

    def changed(self):
        self.dirty = True
        self.refresh()

    # ----- pins ---------------------------------------------------------------
    def fill_pin_table(self):
        cfg = self.cfg
        rows = sorted(cfg["pins"].items())
        self.pin_table.blockSignals(True)
        # remove old cell widgets right away (Qt would otherwise delete them later)
        for r in range(self.pin_table.rowCount()):
            for col in range(self.pin_table.columnCount()):
                wdg = self.pin_table.cellWidget(r, col)
                if wdg:
                    wdg.hide()
                    self.pin_table.removeCellWidget(r, col)
        self.pin_table.setRowCount(0)
        self.pin_table.setRowCount(len(rows))
        info = g.pin_info(cfg["device"])
        for r, (pin, e) in enumerate(rows):
            fn = e["function"]
            item = QTableWidgetItem(pin)
            item.setFlags(Qt.ItemIsEnabled)
            item.setBackground(QColor(GROUP_COLORS[g.FUNCTIONS[fn][2]]).lighter(150))
            self.pin_table.setItem(r, 0, item)
            name = QTableWidgetItem(g.pin_name(cfg, pin))
            name.setData(Qt.UserRole, pin)
            self.pin_table.setItem(r, 1, name)

            func = QComboBox()
            for f in g.pin_functions(cfg["device"], pin):
                func.addItem(g.FUNCTIONS[f][0], f)
            func.addItem("(unused)", None)
            func.setCurrentIndex(func.findData(fn))
            func.currentIndexChanged.connect(lambda _, p=pin, w=func: self.set_function(p, w.currentData()))
            self.pin_table.setCellWidget(r, 2, func)

            opt = None
            if fn in ("gpio_out", "gpio_od"):
                opt = QComboBox()
                opt.addItem("starts low", "low")
                opt.addItem("starts high" if fn == "gpio_out" else "starts released", "high")
                opt.setCurrentIndex(opt.findData(e.get("init", "low")))
                opt.currentIndexChanged.connect(lambda _, p=pin, w=opt: self.set_pin_opt(p, "init", w.currentData()))
            elif fn in ("gpio_in", "int", "reset"):
                opt = QComboBox()
                opt.addItem("no pull", "none")
                if pin in info["pull_up"]:
                    opt.addItem("pull-up", "up")
                if pin in info["pull_down"]:
                    opt.addItem("pull-down", "down")
                default = "up" if fn in ("int", "reset") else "none"
                opt.setCurrentIndex(max(0, opt.findData(e.get("pull", default))))
                opt.currentIndexChanged.connect(lambda _, p=pin, w=opt: self.set_pin_opt(p, "pull", w.currentData()))
            self.pin_table.setCellWidget(r, 3, opt if opt else QLabel(""))

            if fn == "int":
                edge = QComboBox()
                for label, val in (("falling", "falling"), ("rising", "rising"), ("both", "both")):
                    edge.addItem(label, val)
                edge.setCurrentIndex(edge.findData(e.get("edge", "falling")))
                edge.currentIndexChanged.connect(lambda _, p=pin, w=edge: self.set_pin_opt(p, "edge", w.currentData()))
                self.pin_table.setCellWidget(r, 4, edge)
            else:
                self.pin_table.setCellWidget(r, 4, QLabel(""))
        self.pin_table.blockSignals(False)

    def pin_name_edited(self, item):
        if self.updating or item.column() != 1:
            return
        pin = item.data(Qt.UserRole)
        name = re.sub(r"\W", "_", item.text().strip())
        if pin in self.cfg["pins"]:
            self.cfg["pins"][pin]["name"] = name or pin
            self.changed()

    def set_function(self, pin, fn):
        if self.updating:
            return
        if fn is None:
            self.cfg["pins"].pop(pin, None)
        else:
            old = self.cfg["pins"].get(pin, {})
            self.cfg["pins"][pin] = {"function": fn, "name": old.get("name", pin)}
            if fn in g.PWM_FUNCS:
                self.cfg["pwm"].setdefault(fn, {"freq": 1000, "duty": 50, "invert": False})
            if fn in ("comp_plus", "comp_minus", "comp_out"):
                self.cfg["comp"]["enabled"] = True
        self.changed()

    def set_pin_opt(self, pin, key, value):
        if self.updating:
            return
        self.cfg["pins"][pin][key] = value
        self.changed()

    def resource_owner(self, fn, pin):
        """Which other pin already uses the hardware this function needs."""
        c = g.chip(self.cfg["device"])
        need = {"tm2_pwm": "TM2", "serial_tx": "TM2", "tm3_pwm": "TM3", "pwmg0": "G0", "pwmg1": "G1",
                "pwmg2": "G2", "comp_minus": "CM", "comp_plus": "CP", "comp_out": "CO"}.get(fn)
        if fn == "int":
            need = c["ints"][pin][0]
        if not need:
            return None
        for p, e in self.cfg["pins"].items():
            if p == pin:
                continue
            other = e["function"]
            o_need = {"tm2_pwm": "TM2", "serial_tx": "TM2", "tm3_pwm": "TM3", "pwmg0": "G0", "pwmg1": "G1",
                      "pwmg2": "G2", "comp_minus": "CM", "comp_plus": "CP", "comp_out": "CO"}.get(other)
            if other == "int":
                o_need = c["ints"][p][0]
            if o_need == need:
                return p
        return None

    def pin_menu(self, pin, pos):
        cfg = self.cfg
        menu = QMenu(self)
        cur = cfg["pins"].get(pin, {}).get("function")
        title = menu.addAction(f"{pin}" + (f"  ({g.pin_name(cfg, pin)})" if cur else ""))
        title.setEnabled(False)
        menu.addSeparator()
        for fn in g.pin_functions(cfg["device"], pin):
            label = g.FUNCTIONS[fn][0]
            if fn == "int":
                label += f" ({g.chip(cfg['device'])['ints'][pin][0]})"
            if fn == "adc":
                label += f" ({g.chip(cfg['device'])['adc'][pin].split('_')[2]})"
            owner = self.resource_owner(fn, pin)
            act = menu.addAction(label + (f"   - in use on {owner}" if owner else ""))
            act.setCheckable(True)
            act.setChecked(fn == cur)
            act.setEnabled(owner is None)
            act.triggered.connect(lambda _, f=fn: self.set_function(pin, f))
        menu.addSeparator()
        if cur:
            ren = menu.addAction("Rename...")
            ren.triggered.connect(lambda: self.rename(pin))
            clr = menu.addAction("Clear")
            clr.triggered.connect(lambda: self.set_function(pin, None))
        menu.exec_(pos)

    def rename(self, pin):
        name, ok = QInputDialog.getText(self, "Rename pin", f"Name for {pin} (used in code):",
                                        text=g.pin_name(self.cfg, pin))
        if ok and name.strip():
            self.cfg["pins"][pin]["name"] = re.sub(r"\W", "_", name.strip())
            self.changed()

    # ----- PWM tab ----------------------------------------------------------------
    def fill_pwm_tab(self):
        w = QWidget()
        v = QVBoxLayout(w)
        used = [(e["function"], p) for p, e in sorted(self.cfg["pins"].items()) if e["function"] in g.PWM_FUNCS]
        if not used:
            msg = QLabel("No PWM pins yet. Click a pin on the chip and choose a PWM function.\n\n"
                         + ("Timer2/Timer3: 8-bit PWM.  PWMG0-2: 11-bit PWM (PFS154)."
                            if self.cfg["device"] == "PFS154" else "Timer2/Timer3: 8-bit PWM."))
            msg.setWordWrap(True)
            v.addWidget(msg)
        for fn, pin in used:
            opts = self.cfg["pwm"].setdefault(fn, {"freq": 1000, "duty": 50, "invert": False})
            box = QGroupBox(f"{g.FUNCTIONS[fn][0]} on {pin} ({g.pin_name(self.cfg, pin)})")
            f = QFormLayout(box)
            freq = QSpinBox()
            freq.setRange(1, 500_000)
            freq.setSuffix(" Hz")
            freq.setValue(int(opts["freq"]))
            duty = QDoubleSpinBox()
            duty.setRange(0, 100)
            duty.setSuffix(" %")
            duty.setValue(float(opts["duty"]))
            inv = QCheckBox("Invert output (e.g. LED wired to VDD)")
            inv.setChecked(bool(opts.get("invert")))
            if fn.startswith("pwmg"):
                st = g.pwmg_settings(opts["freq"])
                res = f"~{g.human_freq(st['freq'])}, duty steps 0..{st['cub']}" if st else "frequency out of range"
            else:
                st = g.tm_pwm_settings(opts["freq"])
                res = f"{g.human_freq(st['freq'])}, {st['bits']}-bit"
            got = QLabel(res)
            got.setStyleSheet("color: #2e7d32")
            f.addRow("Frequency:", freq)
            f.addRow("Actual:", got)
            f.addRow("Start duty:", duty)
            f.addRow(inv)
            f.addRow(QLabel(f"Change it at runtime with {g.pin_name(self.cfg, pin)}_set_duty(x)"))
            freq.editingFinished.connect(lambda fn=fn, wdg=freq: self.set_pwm(fn, "freq", wdg.value()))
            duty.editingFinished.connect(lambda fn=fn, wdg=duty: self.set_pwm(fn, "duty", wdg.value()))
            inv.toggled.connect(lambda val, fn=fn: self.set_pwm(fn, "invert", val))
            v.addWidget(box)
        v.addStretch(1)
        self.pwm_area.setWidget(w)

    def set_pwm(self, fn, key, value):
        if self.updating or self.cfg["pwm"].get(fn, {}).get(key) == value:
            return
        self.cfg["pwm"].setdefault(fn, {})[key] = value
        self.changed()

    # ----- other handlers -----------------------------------------------------------
    def analog_changed(self):
        if self.updating:
            return
        cc = self.cfg["comp"]
        cc.update(enabled=self.comp_enable.isChecked(), minus=self.comp_minus.currentData(),
                  range=self.comp_range.value(), level=self.comp_level.value(),
                  invert=self.comp_invert.isChecked(), interrupt=self.comp_irq.isChecked(),
                  edge=self.comp_edge.currentData())
        self.cfg["adc"]["clock_khz"] = self.adc_clock.value()
        self.changed()

    def system_changed(self):
        if self.updating:
            return
        s = self.cfg["system"]
        self.f_cpu = self.clock.currentData()
        self.vdd = self.vdd_combo.currentData()
        s.update(unused_pins=self.unused.currentData(), millis=self.millis.isChecked(),
                 watchdog=self.watchdog.currentData(), fuses=self.fuses.isChecked(),
                 security=self.security.isChecked(), drive=self.drive.currentData(),
                 bootup=self.bootup.currentData(), lvr=self.lvr.currentData())
        self.changed()

    def change_chip(self):
        if self.updating:
            return
        device = self.chip_combo.currentData()
        old = self.cfg
        new = g.default_config(device)
        dropped = []
        for pin, e in old["pins"].items():
            if e["function"] in g.pin_functions(device, pin):
                new["pins"][pin] = e
            else:
                dropped.append(f"{pin} ({g.FUNCTIONS[e['function']][0]})")
        if "PA4" not in old["pins"]:
            new["pins"].pop("PA4", None)
        new["pwm"] = {k: v for k, v in old["pwm"].items()}
        for key in ("comp", "adc"):
            new[key].update(old[key])
        new["system"].update({k: v for k, v in old["system"].items() if k not in ("drive", "lvr")})
        # keep the same package type if the new chip has it
        old_type = g.current_package(old)["label"].split()[0]
        for pkg in g.packages(device):
            if pkg["label"].startswith(old_type):
                new["package"] = pkg["parts"][0]
        self.cfg = new
        if dropped:
            QMessageBox.information(self, "Chip changed", f"{device} can't do this, so these pins were cleared:\n"
                                    + "\n".join(dropped))
        self.changed()

    def change_package(self):
        if self.updating:
            return
        self.cfg["package"] = self.pkg_combo.currentData()
        self.changed()

    # ----- generate ---------------------------------------------------------------
    def generate(self):
        errors, _ = g.check(self.cfg, self.f_cpu, self.vdd)
        if errors:
            return
        p = self.project
        g.save_config(p, self.cfg)
        mk = os.path.join(p, "Makefile")
        with open(mk) as f:
            text = f.read()
        text = pdk.write_setting(text, "DEVICE", self.cfg["device"])
        text = pdk.write_setting(text, "F_CPU", str(self.f_cpu))
        text = pdk.write_setting(text, "TARGET_VDD_MV", str(self.vdd))
        with open(mk, "w") as f:
            f.write(text)
        pdk.write_intellisense(p, pdk.load_devices(mk))
        files = g.write_generated(p, self.cfg, self.f_cpu, self.vdd)
        hooked = g.hook_main(p)
        self.dirty = False
        msg = [f"Wrote {', '.join(files)} and padauk.json, updated the Makefile."]
        if hooked:
            msg.append("main.c: " + "; ".join(hooked) + " (backup: main.c.bak)")
        elif hooked is None:
            msg.append("No main.c found: call pdk_init() at startup and pdk_irq() in your interrupt handler.")
        self.statusBar().showMessage("  ".join(msg), 15000)
        self.generated.emit(" ".join(msg))
        QMessageBox.information(self, "Code generated", "\n\n".join(msg) +
                                "\n\nUse the pin names in your code, e.g. LED_high(), BUTTON_read().")

    def closeEvent(self, event):
        if self.dirty:
            r = QMessageBox.question(self, "Unsaved changes", "Generate code before closing?",
                                     QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            if r == QMessageBox.Cancel:
                event.ignore()
                return
            if r == QMessageBox.Yes:
                self.generate()
        event.accept()


def main():
    app = QApplication(sys.argv)
    project = pdk.find_project(sys.argv[1] if len(sys.argv) > 1 else None)
    if not project:
        QMessageBox.warning(None, "Padauk Configurator", "Run this inside a Padauk project (pdk new <name>).")
        return 1
    w = ConfiguratorWindow(project)
    w.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
