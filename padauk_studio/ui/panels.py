"""The settings pages on the right: Pin, Clock & power, Timers, Comparator, ADC, Serial."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton,
                               QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from .. import codegen, timing
from ..chips import FUNCTIONS, VINTR_RANGES, comparator_vintr
from ..project import clean_label, valid_label


def combo(items, current=None):
    """items: [(value, text)]"""
    c = QComboBox()
    for v, t in items:
        c.addItem(t, v)
    if current is not None:
        set_combo(c, current)
    return c


def set_combo(c, value):
    i = c.findData(value)
    if i >= 0:
        c.blockSignals(True)
        c.setCurrentIndex(i)
        c.blockSignals(False)


def note(text):
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setStyleSheet("color: #666;")
    lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lab


class Page(QScrollArea):
    changed = Signal()
    title = ""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.project = None
        self.inner = QWidget()
        self.lay = QVBoxLayout(self.inner)
        self.lay.setAlignment(Qt.AlignTop)
        self.setWidget(self.inner)
        self._loading = False

    def set_project(self, project):
        self.project = project
        self.rebuild()
        self.load()

    def rebuild(self):
        pass

    def load(self):
        pass

    def emit_changed(self):
        if not self._loading:
            self.changed.emit()

    def clear(self):
        """Start with a fresh, empty page (the scroll area deletes the old one)."""
        self.inner = QWidget()
        self.lay = QVBoxLayout(self.inner)
        self.lay.setAlignment(Qt.AlignTop)
        self.setWidget(self.inner)


# ---------------------------------------------------------------------------
class PinPage(Page):
    title = "Pin"
    jump = Signal(str)        # page title to show (e.g. "Comparator")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pin = None

    def show_pin(self, pin):
        self.pin = pin
        self.rebuild()
        self.load()

    def rebuild(self):
        self.clear()
        p = self.project
        if not p:
            return
        if self.pin not in p.chip.pins:
            self.pin = None
        if not self.pin:
            self.lay.addWidget(QLabel("<b>No pin selected</b>"))
            self.lay.addWidget(note("Click a pin on the chip to set it up. Right-click a pin for a quick menu; "
                                    "Delete resets the selected pin to Unused."))
            self.lay.addWidget(self._summary())
            return
        chip = p.chip
        info = chip.pins[self.pin]
        pkg = chip.package(p.data["package"])
        num = pkg.pins.index(self.pin) + 1 if self.pin in pkg.pins else None
        head = QLabel(f"<span style='font-size:16pt'><b>{self.pin}</b></span>"
                      + (f"&nbsp;&nbsp;pin {num}" if num else "&nbsp;&nbsp;<i>(not on this package)</i>"))
        self.lay.addWidget(head)
        self.lay.addWidget(note(info.notes))

        box = QGroupBox("Function")
        bl = QVBoxLayout(box)
        self.group = QButtonGroup(self)
        self.buttons = {}
        for fn in ["unused"] + info.functions:
            rb = QRadioButton(FUNCTIONS[fn] if fn != "unused" else "Unused")
            self.group.addButton(rb)
            self.buttons[fn] = rb
            bl.addWidget(rb)
            rb.toggled.connect(lambda on, f=fn: on and self._set_fn(f))
        self.lay.addWidget(box)

        self.opts_box = QGroupBox("Settings")
        self.opts = QFormLayout(self.opts_box)
        self.lay.addWidget(self.opts_box)
        self._build_options()

    def _summary(self):
        p = self.project
        box = QGroupBox("Pins in use")
        lay = QVBoxLayout(box)
        if not p.pins:
            lay.addWidget(note("None yet."))
        for pin, cfg in p.pins.items():
            txt = f"{pin}: {FUNCTIONS[cfg['fn']]}"
            if cfg.get("label"):
                txt += f" &mdash; <b>{cfg['label']}</b>"
            if cfg["fn"] == "pwm":
                txt += f" ({cfg.get('periph')})"
            lay.addWidget(QLabel(txt))
        return box

    def _build_options(self):
        p, pin = self.project, self.pin
        cfg = p.pins.get(pin, {})
        fn = cfg.get("fn", "unused")
        f = self.opts
        if fn == "unused":
            self.opts_box.setVisible(False)
            return
        self.opts_box.setVisible(True)
        chip = p.chip
        if fn in ("output", "input", "interrupt", "pwm", "adc", "comp_plus", "comp_minus"):
            self.name_edit = QLineEdit(cfg.get("label", ""))
            self.name_edit.setPlaceholderText(f"{pin} (a name for your code, like LED)")
            self.name_edit.editingFinished.connect(self._set_label)
            f.addRow("Name", self.name_edit)
            self.name_hint = note("")
            f.addRow("", self.name_hint)
            self._label_hint()
        if fn == "output":
            c = combo([(0, "Low"), (1, "High")], cfg.get("initial", 0))
            c.currentIndexChanged.connect(lambda: self._opt("initial", c.currentData()))
            f.addRow("Start level", c)
            if chip.pins[pin].open_drain_only:
                f.addRow("", note("Open drain: it can pull low, or let go (needs a pull-up for high)."))
            lab = cfg.get("label") or pin
            f.addRow("", note(f"In code: {lab}_high(), {lab}_low(), {lab}_toggle(), {lab}_set(x), {lab}_read()"))
        if fn in ("input", "interrupt"):
            pulls = [("none", "None"), ("up", "Pull-up")]
            if chip.has_pull_down:
                pulls.append(("down", "Pull-down"))
            c = combo(pulls, cfg.get("pull", "none"))
            c.currentIndexChanged.connect(lambda: self._opt("pull", c.currentData()))
            f.addRow("Pull resistor", c)
        if fn == "interrupt":
            c2 = combo([("fall", "Falling edge"), ("rise", "Rising edge"), ("both", "Both edges")],
                       cfg.get("edge", "fall"))
            c2.currentIndexChanged.connect(lambda: self._opt("edge", c2.currentData()))
            f.addRow("Trigger on", c2)
            irq = chip.interrupts.get(pin, {})
            f.addRow("", note(f"Your code goes in main.c, section irq_{irq.get('line', pin)}."))
        if fn in ("input", "interrupt"):
            lab = cfg.get("label") or pin
            f.addRow("", note(f"In code: {lab}_read()"))
        if fn == "pwm":
            pers = p.pwm_periphs_for(pin)
            used = {c.get("periph"): pp for pp, c in p.pins.items() if c.get("fn") == "pwm" and pp != pin}
            items = []
            for per in pers:
                t = per
                if per in used:
                    t += f" (used by {used[per]})"
                elif p.serial_enabled() and p.data["serial"].get("timer") == per:
                    t += " (used by serial)"
                items.append((per, t))
            c = combo(items, cfg.get("periph"))
            c.currentIndexChanged.connect(lambda: self._opt("periph", c.currentData()))
            f.addRow("Generator", c)
            per = cfg.get("periph")
            if per:
                tcfg = p.timer(per)
                fr = QDoubleSpinBox()
                fr.setRange(1, 1_000_000)
                fr.setDecimals(1)
                fr.setSuffix(" Hz")
                fr.setValue(float(tcfg.get("freq_hz", 1000)))
                fr.editingFinished.connect(lambda: self._timer_opt(per, "freq_hz", fr.value()))
                f.addRow("Frequency", fr)
                du = QDoubleSpinBox()
                du.setRange(0, 100)
                du.setDecimals(1)
                du.setSuffix(" %")
                du.setValue(float(tcfg.get("duty", 50)))
                du.editingFinished.connect(lambda: self._timer_opt(per, "duty", du.value()))
                f.addRow("Start duty", du)
                plan = codegen.timer_plan(p)
                if per in plan:
                    f.addRow("Result", QLabel(codegen.describe_timer(per, plan[per], "pwm")))
                lab = cfg.get("label") or pin
                f.addRow("", note(f"In code: {lab}_set_duty(0 .. {lab}_DUTY_MAX), {lab}_off(), {lab}_on()"))
        if fn == "adc":
            lab = cfg.get("label") or pin
            f.addRow("", note(f"Analog input, channel {chip.adc['channels'][pin]}. In code: {lab}_read() "
                              f"returns 0..4095 (4095 = VDD)."))
        if fn in ("comp_plus", "comp_minus", "comp_out"):
            b = QPushButton("Comparator settings...")
            b.clicked.connect(lambda: self.jump.emit("Comparator"))
            f.addRow("", b)
        if fn == "serial_tx":
            f.addRow("", note("Text from serial_print() goes out here. Press Monitor to read it while the "
                              "chip is in the programmer."))
            b = QPushButton("Serial settings...")
            b.clicked.connect(lambda: self.jump.emit("Serial"))
            f.addRow("", b)
        if fn == "reset":
            f.addRow("", note("A low level on this pin resets the chip."))

    def _label_hint(self):
        txt = self.name_edit.text().strip()
        if txt and not valid_label(txt):
            self.name_hint.setText("Use letters, digits and _ (not starting with a digit).")
            self.name_edit.setStyleSheet("border: 1px solid #d33;")
        else:
            self.name_hint.setText("")
            self.name_edit.setStyleSheet("")

    def load(self):
        if not self.project or not self.pin:
            return
        self._loading = True
        fn = self.project.fn(self.pin)
        if fn in self.buttons:
            self.buttons[fn].setChecked(True)
        self._loading = False

    def _set_fn(self, fn):
        if self._loading or not self.pin:
            return
        if self.project.fn(self.pin) == fn:
            return
        self.project.set_pin(self.pin, fn)
        self.emit_changed()

    def _set_label(self):
        txt = clean_label(self.name_edit.text()) if self.name_edit.text().strip() else ""
        if txt != self.name_edit.text():
            self.name_edit.setText(txt)
        self._label_hint()
        if self.project.pins.get(self.pin, {}).get("label", "") == txt:
            return
        self.project.set_pin_option(self.pin, "label", txt)
        self.emit_changed()

    def _opt(self, key, value):
        if self._loading:
            return
        self.project.set_pin_option(self.pin, key, value)
        self.emit_changed()

    def _timer_opt(self, timer, key, value):
        cfg = self.project.data["timers"][timer]
        if cfg.get(key) == value:
            return
        cfg[key] = value
        self.emit_changed()


# ---------------------------------------------------------------------------
class ClockPage(Page):
    title = "Clock & power"

    def rebuild(self):
        self.clear()
        p = self.project
        chip = p.chip
        box = QGroupBox("System clock")
        f = QFormLayout(box)
        self.clock = combo([(c.key, f"{c.label}  (VDD >= {c.min_vdd_mv / 1000:g} V)") for c in chip.clocks])
        self.clock.currentIndexChanged.connect(lambda: self._set("clock", self.clock.currentData()))
        f.addRow("Clock", self.clock)
        self.vdd = QDoubleSpinBox()
        self.vdd.setRange(1.8, 5.5)
        self.vdd.setSingleStep(0.1)
        self.vdd.setDecimals(2)
        self.vdd.setSuffix(" V")
        self.vdd.editingFinished.connect(lambda: self._set("vdd_mv", int(round(self.vdd.value() * 1000))))
        f.addRow("Supply (VDD)", self.vdd)
        f.addRow("", note("The clock is calibrated at this voltage when the chip is written, and Monitor "
                          "powers the chip with it. Use your circuit's real supply voltage."))
        self.lay.addWidget(box)

        box2 = QGroupBox("Power and reset")
        f2 = QFormLayout(box2)
        lv = [("auto", "Automatic"), ("off", "Off")] + [(k, f"{mv / 1000:g} V") for k, mv in chip.lvr_levels]
        self.lvr = combo(lv)
        self.lvr.currentIndexChanged.connect(lambda: self._sys("lvr", self.lvr.currentData()))
        f2.addRow("Low-voltage reset", self.lvr)
        self.lvr_note = note("")
        f2.addRow("", self.lvr_note)
        wd = [("off", "Off")] + [(k, f"{k} ILRC clocks (~{int(k[:-1]) * 1024 / chip.ilrc_hz:.2g} s)")
                                 for k in ("8K", "16K", "64K", "256K")]
        self.wdt = combo(wd)
        self.wdt.currentIndexChanged.connect(lambda: self._sys("watchdog", self.wdt.currentData()))
        f2.addRow("Watchdog", self.wdt)
        self.fast = QCheckBox("Fast wake-up from sleep")
        self.fast.toggled.connect(lambda v: self._sys("fast_wakeup", v))
        f2.addRow("", self.fast)
        self.unused = combo([("pullup", "Input with pull-up"), ("output_low", "Output low")])
        self.unused.currentIndexChanged.connect(lambda: self._set("unused_pins", self.unused.currentData()))
        f2.addRow("Unused pins", self.unused)
        self.lay.addWidget(box2)

        box3 = QGroupBox("Fuses (written with the program)")
        f3 = QFormLayout(box3)
        self.fuses = {}
        labels = {"security": "Read protection", "bootup": "Boot-up time",
                  "drive": "Pin drive" if chip.name != "PFS122" else "PB4/PB7 drive"}
        names = {"on": "On (can't be read back)", "off": "Off", "slow": "Slow", "fast": "Fast",
                 "low": "Low", "normal": "Normal", "strong": "Strong"}
        for opt in ("security", "bootup", "drive"):
            if opt not in chip.fuse_bits:
                continue
            c = combo([(k, names.get(k, k)) for k in chip.fuse_bits[opt]])
            c.currentIndexChanged.connect(lambda _=0, o=opt, cc=c: self._sys(o, cc.currentData()))
            f3.addRow(labels[opt], c)
            self.fuses[opt] = c
        self.lay.addWidget(box3)

        box4 = QGroupBox(f"About the {chip.name}")
        l4 = QVBoxLayout(box4)
        facts = (f"{'OTP (write once)' if chip.otp else 'Flash'}, {chip.arch}, {chip.rom_words} words ROM, "
                 f"{chip.ram_bytes} bytes RAM, {chip.vdd_range_mv[0] / 1000:g}-{chip.vdd_range_mv[1] / 1000:g} V")
        l4.addWidget(note(facts))
        for n in chip.notes:
            l4.addWidget(note("• " + n))
        self.lay.addWidget(box4)

    def load(self):
        p = self.project
        self._loading = True
        set_combo(self.clock, p.data["clock"])
        self.vdd.setValue(p.data["vdd_mv"] / 1000)
        s = p.data["system"]
        set_combo(self.lvr, s.get("lvr", "auto"))
        lvr = codegen.lvr_choice(p)
        self.lvr_note.setText("Resets the chip when VDD drops below "
                              f"{lvr[1] / 1000:g} V." if lvr else "No reset on low voltage.")
        set_combo(self.wdt, s.get("watchdog", "off"))
        self.fast.setChecked(bool(s.get("fast_wakeup")))
        set_combo(self.unused, p.data.get("unused_pins", "pullup"))
        for opt, c in self.fuses.items():
            set_combo(c, s.get(opt, p.chip.fuse_defaults.get(opt)))
        self._loading = False

    def _set(self, key, value):
        if self._loading or self.project.data.get(key) == value:
            return
        self.project.data[key] = value
        self.emit_changed()

    def _sys(self, key, value):
        if self._loading or self.project.data["system"].get(key) == value:
            return
        self.project.data["system"][key] = value
        self.emit_changed()


# ---------------------------------------------------------------------------
class TimersPage(Page):
    title = "Timers"

    def rebuild(self):
        self.clear()
        p = self.project
        self.rows = {}
        self.lay.addWidget(note("PWM timers are set up from the pins: give a pin the function \"PWM output\". "
                                "Timers not used for PWM can make a periodic interrupt."))
        for t in p.chip.timers:
            box = QGroupBox({"T16": "Timer16", "TM2": "Timer2 (8-bit)", "TM3": "Timer3 (8-bit)"}.get(
                t, f"{t} (11-bit PWM)"))
            f = QFormLayout(box)
            if t == "T16":
                modes = [("off", "Off"), ("millis", "millis() clock"), ("tick", "Periodic interrupt")]
            elif t.startswith("TM"):
                modes = [("off", "Off"), ("tick", "Periodic interrupt"), ("pwm", "PWM (set on a pin)"),
                         ("serial", "Serial (set on the Serial page)")]
            else:
                modes = [("off", "Off"), ("pwm", "PWM (set on a pin)")]
            mc = combo(modes)
            mc.currentIndexChanged.connect(lambda _=0, tt=t, c=mc: self._mode(tt, c.currentData()))
            f.addRow("Use", mc)
            tick = QDoubleSpinBox()
            tick.setRange(0.1, 500000)
            tick.setDecimals(1)
            tick.setSuffix(" Hz")
            tick.editingFinished.connect(lambda tt=t, s=tick: self._val(tt, "tick_hz", s.value()))
            f.addRow("Interrupt rate", tick)
            result = QLabel("")
            f.addRow("Result", result)
            info = note("")
            f.addRow("", info)
            self.rows[t] = (mc, tick, result, info, f)
            self.lay.addWidget(box)

    def load(self):
        p = self.project
        self._loading = True
        plan = codegen.timer_plan(p)
        for t, (mc, tick, result, info, f) in self.rows.items():
            cfg = p.timer(t)
            mode = cfg.get("mode", "off")
            set_combo(mc, mode)
            # PWM and serial are owned by pins / the serial page
            for i in range(mc.count()):
                v = mc.itemData(i)
                item = mc.model().item(i)
                item.setEnabled(v not in ("pwm", "serial") or v == mode)
            tick.setValue(float(cfg.get("tick_hz", 1000)))
            tick.setVisible(mode == "tick")
            f.labelForField(tick).setVisible(mode == "tick")
            s = plan.get(t)
            result.setText(codegen.describe_timer(t, s, mode) if s else "")
            result.setVisible(bool(s))
            f.labelForField(result).setVisible(bool(s))
            txt = ""
            if mode == "pwm":
                pin = next((pp for pp, c in p.pins.items() if c.get("periph") == t), "?")
                txt = f"PWM on {pin}. Change frequency and duty on the pin."
            elif mode == "tick":
                txt = f"Your code goes in main.c, section irq_{t}."
            elif mode == "millis":
                txt = "millis() returns milliseconds since start (uses the Timer16 interrupt)."
            elif mode == "serial":
                txt = "Bit clock for the serial output."
            info.setText(txt)
            info.setVisible(bool(txt))
        self._loading = False

    def _mode(self, t, mode):
        if self._loading:
            return
        self.project.data["timers"][t]["mode"] = mode
        self.emit_changed()

    def _val(self, t, key, v):
        if self.project.data["timers"][t].get(key) == v:
            return
        self.project.data["timers"][t][key] = v
        self.emit_changed()


# ---------------------------------------------------------------------------
class ComparatorPage(Page):
    title = "Comparator"

    def rebuild(self):
        self.clear()
        p = self.project
        chip = p.chip
        self.en = QCheckBox("Use the comparator")
        self.en.toggled.connect(self._enable)
        self.lay.addWidget(self.en)
        box = QGroupBox("Inputs")
        f = QFormLayout(box)
        names = {"VINTR": "Internal reference (adjustable)", "BANDGAP": "Bandgap 1.20 V"}
        self.plus = combo([(k, names.get(k, k)) for k in chip.comparator["plus"]])
        self.plus.currentIndexChanged.connect(lambda: self._input("plus", self.plus.currentData()))
        f.addRow("Plus (+)", self.plus)
        self.minus = combo([(k, names.get(k, k)) for k in chip.comparator["minus"]])
        self.minus.currentIndexChanged.connect(lambda: self._input("minus", self.minus.currentData()))
        f.addRow("Minus (-)", self.minus)
        f.addRow("", note("Choosing a pin here sets that pin up as a comparator input."))
        self.lay.addWidget(box)
        box2 = QGroupBox("Internal reference")
        f2 = QFormLayout(box2)
        self.range = combo([(k, f"{k}: {v[2]}") for k, v in VINTR_RANGES.items()])
        self.range.currentIndexChanged.connect(lambda: self._set("range", self.range.currentData()))
        f2.addRow("Range", self.range)
        self.level = QSpinBox()
        self.level.setRange(0, 15)
        self.level.valueChanged.connect(lambda v: self._set("level", v))
        f2.addRow("Level n", self.level)
        self.vref = QLabel("")
        f2.addRow("Voltage", self.vref)
        self.lay.addWidget(box2)
        box3 = QGroupBox("Output")
        f3 = QFormLayout(box3)
        self.inv = QCheckBox("Invert the result")
        self.inv.toggled.connect(lambda v: self._set("invert", v))
        f3.addRow("", self.inv)
        self.irq = combo([("off", "No interrupt"), ("both", "Interrupt on both edges"),
                          ("rise", "Interrupt on rising edge"), ("fall", "Interrupt on falling edge")])
        self.irq.currentIndexChanged.connect(lambda: self._set("irq", self.irq.currentData()))
        f3.addRow("Interrupt", self.irq)
        self.wake = QCheckBox("Wake up from sleep on a change")
        self.wake.toggled.connect(lambda v: self._set("wakeup", v))
        if chip.comparator.get("wakeup"):
            f3.addRow("", self.wake)
        self.outpin = QCheckBox(f"Output on {chip.comparator['out_pin']}")
        self.outpin.toggled.connect(self._outpin)
        f3.addRow("", self.outpin)
        f3.addRow("", note("In code: comparator_read() is 1 when plus > minus."))
        self.lay.addWidget(box3)

    def load(self):
        p = self.project
        c = p.data["comparator"]
        self._loading = True
        self.en.setChecked(bool(c.get("enabled")))
        set_combo(self.plus, c.get("plus", "VINTR"))
        set_combo(self.minus, c.get("minus", "BANDGAP"))
        set_combo(self.range, c.get("range", "R1"))
        self.level.setValue(int(c.get("level", 8)))
        v = comparator_vintr(c.get("range", "R1"), int(c.get("level", 8)), p.data["vdd_mv"] / 1000)
        self.vref.setText(f"{v:.3f} V at VDD {p.data['vdd_mv'] / 1000:g} V  ({v / (p.data['vdd_mv'] / 1000) * 100:.1f} % of VDD)")
        self.inv.setChecked(bool(c.get("invert")))
        set_combo(self.irq, c.get("irq", "off"))
        self.wake.setChecked(bool(c.get("wakeup")))
        self.outpin.setChecked(p.fn(p.chip.comparator["out_pin"]) == "comp_out")
        for w in (self.plus, self.minus, self.range, self.level, self.inv, self.irq, self.wake, self.outpin):
            w.setEnabled(bool(c.get("enabled")))
        self._loading = False

    def _enable(self, on):
        if self._loading:
            return
        p = self.project
        p.data["comparator"]["enabled"] = on
        if not on:
            for fn in ("comp_plus", "comp_minus", "comp_out"):
                for pin in p.pins_with(fn):
                    p.set_pin(pin, "unused")
            p.data["comparator"]["enabled"] = False
        self.emit_changed()

    def _input(self, which, value):
        if self._loading:
            return
        p = self.project
        fn = "comp_plus" if which == "plus" else "comp_minus"
        for pin in p.pins_with(fn):
            if pin != value:
                p.set_pin(pin, "unused")
        if value in p.chip.pins:
            p.set_pin(value, fn)
        p.data["comparator"][which] = value
        self.emit_changed()

    def _outpin(self, on):
        if self._loading:
            return
        pin = self.project.chip.comparator["out_pin"]
        self.project.set_pin(pin, "comp_out" if on else "unused")
        self.emit_changed()

    def _set(self, key, value):
        if self._loading or self.project.data["comparator"].get(key) == value:
            return
        self.project.data["comparator"][key] = value
        self.emit_changed()


# ---------------------------------------------------------------------------
class AdcPage(Page):
    title = "ADC"

    def rebuild(self):
        self.clear()
        chip = self.project.chip
        if not chip.adc:
            self.lay.addWidget(note(f"The {chip.name} has no ADC."))
            return
        self.lay.addWidget(note(f"{chip.adc['bits']}-bit ADC, reference = VDD. Give pins the function "
                                "\"ADC input\" to use them; vdd_read_mv() measures VDD with the bandgap."))
        self.list = QLabel("")
        self.list.setWordWrap(True)
        self.lay.addWidget(self.list)
        self.clk = note("")
        self.lay.addWidget(self.clk)

    def load(self):
        p = self.project
        if not p.chip.adc:
            return
        pins = p.pins_with("adc")
        rows = [f"{pin}: {p.chip.adc['channels'][pin]} — {p.label(pin)}_read()" for pin in pins]
        self.list.setText("<br>".join(rows) if rows else "No ADC pins yet.")
        div = 1
        while div < 128 and p.f_cpu / div > p.chip.adc["clock_target_hz"]:
            div *= 2
        self.clk.setText(f"ADC clock: system clock / {div} = {timing.fmt_hz(p.f_cpu / div)} "
                         "(datasheet recommends about 500 kHz)." if pins else "")


# ---------------------------------------------------------------------------
class SerialPage(Page):
    title = "Serial"

    def rebuild(self):
        self.clear()
        p = self.project
        self.en = QCheckBox("Serial output on PA7 (for serial_print and Monitor)")
        self.en.toggled.connect(self._enable)
        self.lay.addWidget(self.en)
        box = QGroupBox("Settings")
        f = QFormLayout(box)
        self.baud = combo([(b, str(b)) for b in (115200, 57600, 38400, 19200, 9600)])
        self.baud.currentIndexChanged.connect(lambda: self._set("baud", self.baud.currentData()))
        f.addRow("Baud rate", self.baud)
        self.timer = combo([(t, t) for t in p.chip.timers if t in ("TM2", "TM3")])
        self.timer.currentIndexChanged.connect(lambda: self._set("timer", self.timer.currentData()))
        f.addRow("Timer", self.timer)
        self.lay.addWidget(box)
        self.lay.addWidget(note("TX only, 8N1. The programmer detects the baud rate by itself from the first "
                                "character, so Monitor works with any of these. Leave the chip in the "
                                "programmer's socket and press Monitor."))
        self.lay.addWidget(note("In code: serial_print(\"text\"), serial_println(\"text\"), "
                                "serial_print_uint(1234), serial_print_hex(0x5A), serial_putc('x')."))

    def load(self):
        p = self.project
        self._loading = True
        on = p.serial_enabled()
        self.en.setChecked(on)
        set_combo(self.baud, p.data["serial"].get("baud", 115200))
        set_combo(self.timer, p.data["serial"].get("timer", "TM2"))
        self.baud.setEnabled(on)
        self.timer.setEnabled(on)
        self.en.setEnabled("serial_tx" in p.chip.pins.get("PA7").functions)
        self._loading = False

    def _enable(self, on):
        if self._loading:
            return
        self.project.set_pin("PA7", "serial_tx" if on else "unused")
        self.emit_changed()

    def _set(self, key, value):
        if self._loading or self.project.data["serial"].get(key) == value:
            return
        self.project.data["serial"][key] = value
        self.project._sync_timers()
        self.emit_changed()
