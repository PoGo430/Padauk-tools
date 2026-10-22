"""Project settings (saved as project.pdkstudio, JSON) and the rules for changing them.

The GUI, the code generator and the tests all go through this module, so a pin
assignment means the same thing everywhere.
"""

import copy
import json
import os
import re
from typing import Dict, List, Optional

from . import chips
from .chips import Chip

PROJECT_FILE = "project.pdkstudio"
FORMAT = 1

TIMER_DEFAULTS = {
    "T16": {"mode": "off", "tick_hz": 1000},                 # off / millis / tick
    "TM2": {"mode": "off", "freq_hz": 1000, "duty": 50, "tick_hz": 1000},   # off / pwm / tick / serial
    "TM3": {"mode": "off", "freq_hz": 1000, "duty": 50, "tick_hz": 1000},
    "PWMG0": {"mode": "off", "freq_hz": 1000, "duty": 50},   # off / pwm
    "PWMG1": {"mode": "off", "freq_hz": 1000, "duty": 50},
    "PWMG2": {"mode": "off", "freq_hz": 1000, "duty": 50},
}


def default_project(chip_name="PFS154", name="project") -> dict:
    chip = chips.get(chip_name)
    return {
        "format": FORMAT,
        "name": name,
        "chip": chip.name,
        "package": chip.packages[0].key,
        "clock": "IHRC_DIV2",
        "vdd_mv": 5000,
        "pins": {},
        "timers": {t: copy.deepcopy(TIMER_DEFAULTS[t]) for t in chip.timers},
        "comparator": {"enabled": False, "plus": "VINTR", "minus": "BANDGAP", "range": "R1",
                       "level": 8, "invert": False, "irq": "off", "wakeup": False},
        "adc": {"enabled": False},
        "serial": {"baud": 115200, "timer": "TM2"},
        "system": {"watchdog": "off", "lvr": "auto", "security": "off", "bootup": "fast",
                   "drive": chip.fuse_defaults.get("drive", "normal"), "fast_wakeup": False},
        "unused_pins": "pullup",   # pullup / output_low
    }


def pin_defaults(fn: str) -> dict:
    return {
        "output": {"initial": 0},
        "input": {"pull": "up"},
        "interrupt": {"pull": "up", "edge": "fall"},
        "pwm": {"periph": ""},
    }.get(fn, {})


class Project:
    def __init__(self, data: Optional[dict] = None, path: Optional[str] = None):
        self.data = data or default_project()
        self.path = path        # project folder
        self.upgrade()

    # ---- file IO -------------------------------------------------------------
    @classmethod
    def load(cls, folder: str) -> "Project":
        with open(os.path.join(folder, PROJECT_FILE), encoding="utf-8") as f:
            return cls(json.load(f), folder)

    def save(self, folder: Optional[str] = None):
        folder = folder or self.path
        os.makedirs(folder, exist_ok=True)
        self.path = folder
        with open(os.path.join(folder, PROJECT_FILE), "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, sort_keys=False)
            f.write("\n")

    def to_json(self) -> str:
        return json.dumps(self.data, indent=2)

    def upgrade(self):
        """Fill in missing keys (older project files, hand edits)."""
        d = self.data
        base = default_project(d.get("chip", "PFS154"), d.get("name", "project"))
        for k, v in base.items():
            if k not in d:
                d[k] = v
            elif isinstance(v, dict) and k not in ("pins", "timers"):
                for kk, vv in v.items():
                    d[k].setdefault(kk, vv)
        chip = self.chip
        timers = d.setdefault("timers", {})
        for t in chip.timers:
            timers.setdefault(t, copy.deepcopy(TIMER_DEFAULTS[t]))
            for kk, vv in TIMER_DEFAULTS[t].items():
                timers[t].setdefault(kk, vv)
        for t in list(timers):
            if t not in chip.timers:
                del timers[t]
        if d["package"] not in [p.key for p in chip.packages]:
            d["package"] = chip.packages[0].key
        if d["clock"] not in [c.key for c in chip.clocks]:
            d["clock"] = "IHRC_DIV2"

    # ---- convenience ---------------------------------------------------------
    @property
    def chip(self) -> Chip:
        return chips.get(self.data["chip"])

    @property
    def name(self) -> str:
        return self.data.get("name", "project")

    @property
    def clock(self):
        return self.chip.clock(self.data["clock"])

    @property
    def f_cpu(self) -> int:
        return self.clock.freq

    @property
    def pins(self) -> Dict[str, dict]:
        return self.data["pins"]

    def fn(self, pin: str) -> str:
        return self.pins.get(pin, {}).get("fn", "unused")

    def pins_with(self, fn: str) -> List[str]:
        return [p for p in self.chip.pins if self.fn(p) == fn]

    def label(self, pin: str) -> str:
        return self.pins.get(pin, {}).get("label", "") or pin

    def timer(self, name: str) -> dict:
        return self.data["timers"].get(name, {"mode": "off"})

    def serial_enabled(self) -> bool:
        return bool(self.pins_with("serial_tx"))

    def uses_ihrc(self) -> bool:
        """Whether anything needs the 16 MHz IHRC running."""
        if self.clock.source == "IHRC":
            return True
        return self.serial_enabled()

    # ---- changes (used by the GUI) -------------------------------------------
    def set_chip(self, chip_name: str):
        """Switch chip, keeping pin settings that still make sense."""
        old = self.data
        new = default_project(chip_name, old.get("name", "project"))
        chip = chips.get(chip_name)
        for key in ("vdd_mv", "comparator", "serial", "name"):
            if key in old:
                new[key] = copy.deepcopy(old[key])
        if old.get("clock") in [c.key for c in chip.clocks]:
            new["clock"] = old["clock"]
        if old.get("package") in [p.key for p in chip.packages]:
            new["package"] = old["package"]
        for k in ("watchdog", "lvr", "security", "bootup", "fast_wakeup"):
            new["system"][k] = old.get("system", {}).get(k, new["system"][k])
        if new["system"]["lvr"] not in ["auto", "off"] + [k for k, _ in chip.lvr_levels]:
            new["system"]["lvr"] = "auto"
        for t, cfg in old.get("timers", {}).items():
            if t in new["timers"]:
                new["timers"][t] = copy.deepcopy(cfg)
        self.data = new
        for pin, cfg in old.get("pins", {}).items():
            if pin in chip.pins and cfg.get("fn") in chip.pins[pin].functions:
                self.data["pins"][pin] = copy.deepcopy(cfg)
        self._sync_timers()
        self.upgrade()

    def set_package(self, key: str):
        self.data["package"] = key

    def set_pin(self, pin: str, fn: str, **opts):
        """Give a pin a function ("unused" clears it). Keeps peripherals in sync."""
        chip = self.chip
        if fn != "unused" and fn not in chip.pins[pin].functions:
            raise ValueError(f"{pin} can't be {fn}")
        old = self.pins.get(pin, {})
        if fn == "unused":
            self.pins.pop(pin, None)
        else:
            cfg = {"fn": fn}
            if old.get("label") and old.get("fn") != "serial_tx":
                cfg["label"] = old["label"]
            cfg.update(pin_defaults(fn))
            if fn == old.get("fn"):
                cfg.update({k: v for k, v in old.items() if k != "fn"})
            cfg.update(opts)
            if fn == "pwm" and not cfg.get("periph"):
                cfg["periph"] = self.free_pwm_periph(pin) or ""
            if fn in ("comp_minus", "comp_plus"):
                # only one pin can be each comparator input
                for other in self.pins_with(fn):
                    if other != pin:
                        self.pins.pop(other, None)
                self.data["comparator"]["enabled"] = True
                self.data["comparator"]["minus" if fn == "comp_minus" else "plus"] = pin
            if fn == "comp_out":
                self.data["comparator"]["enabled"] = True
            if fn == "adc":
                self.data["adc"]["enabled"] = True
            if fn == "serial_tx":
                self._claim_serial_timer()
            self.pins[pin] = cfg
        # undo what the old function set up
        if old.get("fn") == "comp_minus" and self.fn(pin) != "comp_minus":
            if self.data["comparator"].get("minus") == pin:
                self.data["comparator"]["minus"] = "BANDGAP"
        if old.get("fn") == "comp_plus" and self.fn(pin) != "comp_plus":
            if self.data["comparator"].get("plus") == pin:
                self.data["comparator"]["plus"] = "VINTR"
        if old.get("fn") == "adc" and not self.pins_with("adc"):
            self.data["adc"]["enabled"] = False
        self._sync_timers()

    def set_pin_option(self, pin: str, key: str, value):
        if pin not in self.pins:
            return
        if value in (None, ""):
            self.pins[pin].pop(key, None)
        else:
            self.pins[pin][key] = value
        self._sync_timers()

    def free_pwm_periph(self, pin: str) -> Optional[str]:
        """A PWM peripheral that can drive this pin and isn't used yet."""
        chip = self.chip
        used = {cfg.get("periph") for p, cfg in self.pins.items() if cfg.get("fn") == "pwm" and p != pin}
        options = [per for per, outs in chip.pwm_outputs.items() if pin in outs]
        for per in options:
            if per not in used and self.timer(per).get("mode") in ("off", "pwm"):
                return per
        for per in options:
            if per not in used:
                return per
        return options[0] if options else None

    def pwm_periphs_for(self, pin: str) -> List[str]:
        return [per for per, outs in self.chip.pwm_outputs.items() if pin in outs]

    def _claim_serial_timer(self):
        t = self.data["serial"].get("timer", "TM2")
        if t not in self.chip.timers:
            t = "TM2"
        # prefer a timer that isn't doing PWM
        busy = {cfg.get("periph") for cfg in self.pins.values() if cfg.get("fn") == "pwm"}
        if t in busy:
            for alt in ("TM2", "TM3"):
                if alt in self.chip.timers and alt not in busy:
                    t = alt
                    break
        self.data["serial"]["timer"] = t

    def _sync_timers(self):
        """Timer modes follow the pin assignments (PWM pins, serial)."""
        timers = self.data["timers"]
        pwm_users = {}
        for pin, cfg in self.pins.items():
            if cfg.get("fn") == "pwm" and cfg.get("periph"):
                pwm_users.setdefault(cfg["periph"], pin)
        serial_t = self.data["serial"].get("timer") if self.serial_enabled() else None
        for t, cfg in timers.items():
            if t in pwm_users:
                cfg["mode"] = "pwm"
            elif t == serial_t:
                cfg["mode"] = "serial"
            elif cfg.get("mode") in ("pwm", "serial"):
                cfg["mode"] = "off"


# ---- names -------------------------------------------------------------------
C_KEYWORDS = {
    "auto", "break", "case", "char", "const", "continue", "default", "do", "double", "else", "enum",
    "extern", "float", "for", "goto", "if", "int", "long", "register", "return", "short", "signed",
    "sizeof", "static", "struct", "switch", "typedef", "union", "unsigned", "void", "volatile", "while",
    "main", "interrupt",
}


def valid_label(label: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,23}", label)) and label.lower() not in C_KEYWORDS


def clean_label(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_]", "_", text.strip())
    if s and s[0].isdigit():
        s = "_" + s
    return s[:24]
