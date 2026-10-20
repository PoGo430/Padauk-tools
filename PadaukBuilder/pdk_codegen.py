"""
Padauk Configurator core: chip capabilities, project configuration, checks and
C code generation. No GUI code here, so it can be used from `pdk generate` too.

Register names and bit values come from the free-pdk pdk-includes headers
(include/pdk/device/...), pin functions from pdk_pinouts.py.
The configuration lives in <project>/padauk.json; the generated code goes to
<project>/pdk_init.h and pdk_init.c (overwritten on every generate).
"""
import copy
import json
import os
import re

try:
    from pdk_pinouts import PACKAGES, PIN_INFO
except ImportError:  # imported as part of a package
    from .pdk_pinouts import PACKAGES, PIN_INFO

CONFIG_FILE = "padauk.json"
IHRC_HZ = 16_000_000

# ----------------------------------------------------------------------------
# What each chip can do, mapped to pdk-includes macro names
# ----------------------------------------------------------------------------
CHIPS = {
    "PMS150C": {
        "pinout": "PMS150C",
        "otp": True,
        "ports": ["A"],
        "pull_down_reg": False,
        "tm2_out": {"PA3": "TM2C_OUT_PA3", "PA4": "TM2C_OUT_PA4"},
        "tm3_out": {},
        "pwmg_out": {},
        "ints": {  # pin: (interrupt, INTEN/INTRQ suffix, INTEGS prefix, ROP value or None)
            "PA0": ("INT0", "PA0", "INTEGS_PA0", None),
        },
        "comp_minus": {"PA3": "GPCC_COMP_MINUS_PA3", "PA4": "GPCC_COMP_MINUS_PA4",
                       "PA6": "GPCC_COMP_MINUS_PA6", "PA7": "GPCC_COMP_MINUS_PA7"},
        "comp_edge": "INTEGS_COMP",
        "adc": {},
        "lvr": ("fuse", ["4V", "3V5", "3V", "2V75", "2V5", "2V2", "2V", "1V8"]),
        "drive_fuse": [("normal", "FUSE_IO_DRV_NORMAL"), ("low", "FUSE_IO_DRV_LOW")],
        "has_rop": False,
        "misc2": False,
    },
    "PFS154": {
        "pinout": "PFS154",
        "otp": False,
        "ports": ["A", "B"],
        "pull_down_reg": False,
        "tm2_out": {"PB2": "TM2C_OUT_PB2", "PA3": "TM2C_OUT_PA3", "PB4": "TM2C_OUT_PB4"},
        "tm3_out": {"PB5": "TM3C_OUT_PB5", "PB6": "TM3C_OUT_PB6", "PB7": "TM3C_OUT_PB7"},
        "pwmg_out": {
            0: {"PB5": "PWMG0C_OUT_PB5", "PA0": "PWMG0C_OUT_PA0", "PB4": "PWMG0C_OUT_PB4"},
            1: {"PB6": "PWMG1C_OUT_PB6", "PA4": "PWMG1C_OUT_PA4", "PB7": "PWMG1C_OUT_PB7"},
            2: {"PB3": "PWMG2C_OUT_PB3", "PA3": "PWMG2C_OUT_PA3", "PB2": "PWMG2C_OUT_PB2", "PA5": "PWMG2C_OUT_PA5"},
        },
        "ints": {
            "PA0": ("INT0", "PA0", "INTEGS_PA0", None),
            "PB0": ("INT1", "PB0", "INTEGS_PB0", None),
        },
        "comp_minus": {"PA3": "GPCC_COMP_MINUS_PA3", "PA4": "GPCC_COMP_MINUS_PA4",
                       "PB6": "GPCC_COMP_MINUS_PB6", "PB7": "GPCC_COMP_MINUS_PB7"},
        "comp_edge": "MISC2_COMP_EDGE_INT",
        "adc": {},
        "lvr": ("MISCLVR", ["4V", "3V5", "3V", "2V75", "2V5", "2V2", "2V", "1V8"]),
        "drive_fuse": [("normal", "FUSE_IO_DRV_NORMAL"), ("low", "FUSE_IO_DRV_LOW")],
        "has_rop": False,
        "misc2": True,
    },
    "PFS172": {
        "pinout": "PFS172",
        "otp": False,
        "ports": ["A", "B"],
        "pull_down_reg": True,
        "tm2_out": {"PB2": "TM2C_OUT_PB2", "PA3": "TM2C_OUT_PA3", "PB4": "TM2C_OUT_PB4"},
        "tm3_out": {"PB5": "TM3C_OUT_PB5", "PB6": "TM3C_OUT_PB6", "PB7": "TM3C_OUT_PB7"},
        "pwmg_out": {},
        "ints": {
            "PA0": ("INT0", "PA0", "INTEGS_PA0", "ROP_INT_SRC_PA0"),
            "PB5": ("INT0", "PB5", "INTEGS_PB5", "ROP_INT_SRC_PB5"),
            "PB0": ("INT1", "PB0", "INTEGS_PB0", "ROP_INT_SRC_PB0"),
            "PA4": ("INT1", "PA4", "INTEGS_PA4", "ROP_INT_SRC_PA4"),
        },
        "comp_minus": {"PA3": "GPCC_COMP_MINUS_PA3", "PA4": "GPCC_COMP_MINUS_PA4",
                       "PB6": "GPCC_COMP_MINUS_PB6", "PB7": "GPCC_COMP_MINUS_PB7"},
        "comp_edge": "MISC2_COMP_EDGE_INT",
        "adc": {"PB0": "ADCC_CH_AD0_PB0", "PB1": "ADCC_CH_AD1_PB1", "PB2": "ADCC_CH_AD2_PB2",
                "PB3": "ADCC_CH_AD3_PB3", "PB4": "ADCC_CH_AD4_PB4", "PB5": "ADCC_CH_AD5_PB5",
                "PB6": "ADCC_CH_AD6_PB6", "PB7": "ADCC_CH_AD7_PB7", "PA3": "ADCC_CH_AD8_PA3",
                "PA4": "ADCC_CH_AD9_PA4", "PA0": "ADCC_CH_AD10_PA0"},
        "lvr": ("MISCLVR_FULL", ["4V5", "4V", "3V75", "3V5", "3V3", "3V15", "3V", "2V7", "2V5",
                                 "2V4", "2V3", "2V2", "2V1", "2V", "1V9", "1V8"]),
        "drive_fuse": [("normal", "FUSE_PB4_PB7_NORMAL"), ("strong (PB4, PB7)", "FUSE_PB4_PB7_STRONG")],
        "has_rop": True,
        "misc2": True,
    },
}
# PFS122: checked against its datasheet (V004, 2025-09-02). Same registers and pins as the PFS172,
# except a 12-bit ADC (ADCRH 0x22 = bits 11..4, ADCRL 0x23 bits 7..4 = bits 3..0) and 8 LVR levels.
# Interrupt pin choice, LVR and comparator edge are "code options" there; like on the PFS172 they are
# written to the undocumented ROP / MISCLVR / MISC2 registers (free-pdk), which the datasheet doesn't list.
CHIPS["PFS122"] = dict(CHIPS["PFS172"], pinout="PFS122", adc_bits=12, hidden_code_option_regs=True,
                       lvr=("MISCLVR_FULL", ["4V", "3V5", "3V", "2V7", "2V5", "2V2", "2V", "1V8"]),
                       max_clock=[(8_000_000, 3000), (4_000_000, 2200), (2_000_000, 1800)])

SUPPORTED = ["PFS154", "PFS122", "PMS150C", "PFS172"]

# Pin functions: id -> (menu label, short label for the chip view, colour group)
FUNCTIONS = {
    "gpio_out":   ("Output", "OUT", "gpio"),
    "gpio_od":    ("Output (open-drain)", "OUT-OD", "gpio"),
    "gpio_in":    ("Input", "IN", "gpio"),
    "int":        ("External interrupt", "INT", "int"),
    "tm2_pwm":    ("PWM - Timer2 (8-bit)", "TM2 PWM", "pwm"),
    "tm3_pwm":    ("PWM - Timer3 (8-bit)", "TM3 PWM", "pwm"),
    "pwmg0":      ("PWM - PWMG0 (11-bit)", "PWMG0", "pwm"),
    "pwmg1":      ("PWM - PWMG1 (11-bit)", "PWMG1", "pwm"),
    "pwmg2":      ("PWM - PWMG2 (11-bit)", "PWMG2", "pwm"),
    "adc":        ("Analog input (ADC)", "ADC", "analog"),
    "comp_plus":  ("Comparator + input", "COMP+", "analog"),
    "comp_minus": ("Comparator - input", "COMP-", "analog"),
    "comp_out":   ("Comparator output", "COMP OUT", "analog"),
    "serial_tx":  ("Serial TX (debug, ~115200 baud)", "TX", "serial"),
    "reset":      ("Reset input (PRSTB)", "RESET", "system"),
}

PWM_FUNCS = ("tm2_pwm", "tm3_pwm", "pwmg0", "pwmg1", "pwmg2")


def chip(device):
    return CHIPS[device]


def packages(device):
    return PACKAGES[chip(device)["pinout"]]


def pin_info(device):
    return PIN_INFO[chip(device)["pinout"]]


def all_io_pins(device):
    """Every I/O pin on the die (largest package), e.g. ['PA0', 'PA3', ..., 'PB7']."""
    pins = set()
    for pkg in packages(device):
        pins.update(p for p in pkg["pins"] if re.fullmatch(r"P[A-C]\d", p))
    return sorted(pins)


def open_drain_only(device, pin):
    return "drive: 0mA" in pin_info(device)["current"].get(pin, [])


def pin_functions(device, pin):
    """Functions available on a pin, in menu order."""
    c = chip(device)
    if not re.fullmatch(r"P[A-C]\d", pin) or pin not in all_io_pins(device):
        return []       # not an I/O pin, or not on this chip at all (e.g. PB0 on the PMS150C)
    funcs = ["gpio_od" if open_drain_only(device, pin) else "gpio_out", "gpio_in"]
    if pin in c["ints"]:
        funcs.append("int")
    if pin in c["tm2_out"]:
        funcs.append("tm2_pwm")
    if pin in c["tm3_out"]:
        funcs.append("tm3_pwm")
    for n, outs in c["pwmg_out"].items():
        if pin in outs:
            funcs.append(f"pwmg{n}")
    if pin in c["adc"]:
        funcs.append("adc")
    if pin == "PA4":
        funcs.append("comp_plus")
    if pin in c["comp_minus"]:
        funcs.append("comp_minus")
    if pin == "PA0":
        funcs.append("comp_out")
    if pin == "PA7":
        funcs.append("serial_tx")
    if pin == "PA5":
        funcs.append("reset")
    return funcs


# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------
def default_config(device="PFS154"):
    c = chip(device)
    pkgs = packages(device)
    # default package: SOP8 if available (common, breadboard friendly with an adapter)
    pkg = next((p for p in pkgs if "SOP8" in p["label"]), pkgs[0])
    return {
        "version": 1,
        "device": device,
        "package": pkg["parts"][0],
        "pins": {"PA4": {"function": "gpio_out", "name": "LED", "init": "low"}},
        "pwm": {},          # per function id: {"freq": Hz, "duty": %, "invert": bool}
        "comp": {"enabled": False, "plus": "internal", "minus": "bandgap", "range": 1, "level": 8,
                 "invert": False, "interrupt": False, "edge": "both"},
        "adc": {"clock_khz": 500},
        "system": {
            "unused_pins": "pullup",       # pullup | output_low | float
            "millis": False,
            "watchdog": "off",             # off | 8k | 16k | 64k | 256k (ILRC clocks)
            "fuses": True,
            "security": False,
            "drive": c["drive_fuse"][0][0],
            "bootup": "slow",
            "lvr": None,                   # None = pick from VDD
        },
    }


def load_config(project, device=None):
    path = os.path.join(project, CONFIG_FILE)
    if os.path.isfile(path):
        with open(path) as f:
            cfg = json.load(f)
        if cfg.get("device") == "PFS122" and str(cfg.get("package", "")).startswith("PFS172-"):
            cfg["package"] = "PFS122-" + cfg["package"][len("PFS172-"):]
        base = default_config(cfg.get("device", device or "PFS154"))
        for key, val in cfg.items():          # merge, so new options get defaults
            if isinstance(val, dict) and isinstance(base.get(key), dict) and key not in ("pins", "pwm"):
                base[key].update(val)
            else:
                base[key] = val
        return base
    return default_config(device or "PFS154")


def save_config(project, cfg):
    with open(os.path.join(project, CONFIG_FILE), "w") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")


def current_package(cfg):
    for pkg in packages(cfg["device"]):
        if cfg["package"] in pkg["parts"]:
            return pkg
    return packages(cfg["device"])[0]


def pin_name(cfg, pin):
    entry = cfg["pins"].get(pin, {})
    return entry.get("name") or pin


# Suggested names for a newly assigned pin (made unique with 2, 3, ...); the user can rename them
DEFAULT_NAMES = {"gpio_out": "LED", "gpio_od": "OUT", "gpio_in": "BUTTON", "int": "BUTTON",
                 "tm2_pwm": "PWM", "tm3_pwm": "PWM", "pwmg0": "PWM", "pwmg1": "PWM", "pwmg2": "PWM",
                 "adc": "ANALOG", "comp_plus": "COMP_PLUS", "comp_minus": "COMP_MINUS", "comp_out": "COMP_OUT",
                 "serial_tx": "TX"}


def is_default_name(pin, name):
    """True if a name is the bare pin or one of our suggestions (so it's fine to replace it)."""
    bases = "|".join(sorted(set(DEFAULT_NAMES.values())))
    return not name or name == pin or re.fullmatch(rf"(?:{bases})\d*", name) is not None


def suggest_name(cfg, pin, fn):
    """A short, unique, function-based name for a pin, e.g. 'LED', 'BUTTON2'; the bare pin if none fits."""
    base = DEFAULT_NAMES.get(fn)
    if not base:
        return pin
    taken = {pin_name(cfg, p) for p in cfg["pins"] if p != pin}
    name, i = base, 2
    while name in taken:
        name, i = f"{base}{i}", i + 1
    return name


def pin_number(cfg, pin):
    """Physical pin number on the selected package, or None if the pin isn't bonded out."""
    pins = current_package(cfg)["pins"]
    return pins.index(pin) + 1 if pin in pins else None


def pin_usage(cfg, pin):
    """What the generated code gives you for one configured pin, e.g. 'LED_high(), LED_low(), LED_toggle()'."""
    e = cfg["pins"].get(pin)
    if not e:
        return ""
    fn, n = e["function"], pin_name(cfg, pin)
    if fn == "gpio_out":
        return f"{n}_high(), {n}_low(), {n}_toggle()"
    if fn == "gpio_od":
        return f"{n}_low(), {n}_high() (= release), {n}_toggle()"
    if fn == "gpio_in":
        return f"{n}_read()"
    if fn == "int":
        irq = chip(cfg["device"])["ints"].get(pin, ("int?",))[0].lower()
        return f"{n}_read(), {n}_triggered() (clear with pdk_{irq}_flag = 0)"
    if fn in PWM_FUNCS:
        return f"{n}_set_duty(0..{n}_PWM_MAX)"
    if fn == "adc":
        return f"{n}_read() (0..{adc_max(cfg['device'])})"
    if fn == "serial_tx":
        return 'serial_println("text"), serial_print_uint(n), putchar(c)'
    return ""


def usage(cfg):
    """One line per pin/feature: what to call in your code after generating."""
    lines = []
    for pin in sorted(cfg["pins"]):
        text = pin_usage(cfg, pin)
        if text:
            lines.append(text)
    funcs = {e["function"] for e in cfg["pins"].values()}
    if cfg["comp"]["enabled"] or funcs & {"comp_plus", "comp_minus", "comp_out"}:
        lines.append("COMP_read()" + (", pdk_comp_flag" if cfg["comp"]["interrupt"] else ""))
    if cfg["system"]["millis"]:
        lines.append("millis()")
    if cfg["system"]["watchdog"] != "off":
        lines.append("pdk_watchdog_feed()")
    return lines


def resources(cfg):
    """Shared hardware blocks and who uses them: [(name, user or None), ...] for this chip."""
    c = chip(cfg["device"])
    pins = cfg["pins"]

    def label(p):
        return p if pin_name(cfg, p) == p else f"{pin_name(cfg, p)} ({p})"

    def users(*funcs):
        return ", ".join(label(p) for p, e in sorted(pins.items()) if e["function"] in funcs) or None

    out = [("Timer2", users("tm2_pwm", "serial_tx"))]
    if c["tm3_out"]:
        out.append(("Timer3", users("tm3_pwm")))
    for n in sorted(c["pwmg_out"]):
        out.append((f"PWMG{n}", users(f"pwmg{n}")))
    for irq in sorted({v[0] for v in c["ints"].values()}):
        out.append((irq, ", ".join(label(p) for p, e in sorted(pins.items())
                                   if e["function"] == "int" and c["ints"].get(p, ("",))[0] == irq) or None))
    comp = users("comp_plus", "comp_minus", "comp_out")
    out.append(("Comparator", comp or ("on" if cfg["comp"]["enabled"] else None)))
    if c["adc"]:
        out.append(("ADC", users("adc")))
    out.append(("Timer16", "millis()" if cfg["system"]["millis"] else None))
    return out


def default_lvr(device, vdd_mv):
    """Highest LVR level at or below ~80% of VDD."""
    levels = chip(device)["lvr"][1]

    def mv(level):
        v, _, frac = level.partition("V")
        return int(v) * 1000 + (int(frac.ljust(2, "0")) * 10 if frac else 0)

    ok = [lv for lv in levels if mv(lv) <= vdd_mv * 0.8]
    return max(ok, key=mv) if ok else min(levels, key=mv)


# ----------------------------------------------------------------------------
# Checks
# ----------------------------------------------------------------------------
def check(cfg, f_cpu, vdd_mv):
    """Return (errors, warnings) as lists of strings."""
    errors, warnings = [], []
    device = cfg["device"]
    c = chip(device)
    pkg_pins = set(current_package(cfg)["pins"])
    used_by = {}
    names = {}

    for pin, entry in sorted(cfg["pins"].items()):
        fn = entry.get("function")
        if fn not in pin_functions(device, pin):
            if pin not in all_io_pins(device):
                errors.append(f"{pin} doesn't exist on the {device}: set it to (unused)")
                continue
            errors.append(f"{pin}: '{FUNCTIONS.get(fn, (fn,))[0]}' is not available on this pin")
            continue
        if pin not in pkg_pins:
            warnings.append(f"{pin} is configured but not on the {cfg['package']} package")
        name = pin_name(cfg, pin)
        if not re.fullmatch(r"[A-Za-z_]\w*", name):
            errors.append(f"{pin}: name '{name}' is not a valid C identifier")
        elif name in names:
            errors.append(f"{pin} and {names[name]} have the same name '{name}'")
        names[name] = pin
        resource = {"int": c["ints"].get(pin, ("",))[0], "tm2_pwm": "Timer2", "tm3_pwm": "Timer3",
                    "pwmg0": "PWMG0", "pwmg1": "PWMG1", "pwmg2": "PWMG2", "comp_minus": "Comparator - input",
                    "serial_tx": "Timer2"}.get(fn)
        if resource:
            if resource in used_by:
                errors.append(f"{pin} and {used_by[resource]} both need {resource}")
            used_by[resource] = pin
        if pin in pin_info(device)["programming"] and fn in ("gpio_out", "gpio_od", "tm2_pwm", "tm3_pwm",
                                                             "pwmg0", "pwmg1", "pwmg2", "comp_out", "serial_tx"):
            pass  # fine; noted in the pin tooltip

    funcs = {e.get("function") for e in cfg["pins"].values()}
    comp_pins = funcs & {"comp_plus", "comp_minus", "comp_out"}
    comp_on = cfg["comp"]["enabled"] or bool(comp_pins)
    if comp_on and "comp_plus" not in funcs and "comp_minus" not in funcs \
            and cfg["comp"]["minus"] == "internal":
        errors.append("Comparator: + and - can't both be the internal reference (use bandgap or a pin for -)")
    if "serial_tx" in funcs and f_cpu < 250_000:
        warnings.append("Serial TX needs the IHRC running; use F_CPU >= 250 kHz")
    if cfg["system"]["millis"] and f_cpu < 250_000:
        warnings.append("millis() needs the IHRC running; use F_CPU >= 250 kHz")
    for hz, min_mv in c.get("max_clock", []):        # highest clock first
        if f_cpu >= hz:
            if vdd_mv < min_mv:
                warnings.append(f"Datasheet: {human_freq(hz)} needs VDD >= {min_mv / 1000:.1f} V "
                                f"(you have {vdd_mv / 1000:.1f} V); lower the clock")
            break
    if c.get("hidden_code_option_regs") and ("int" in funcs or cfg["system"]["fuses"] or comp_on):
        warnings.append("PFS122: interrupt pin choice, LVR level and comparator edge use registers that are "
                        "documented for the PFS172 but not in the PFS122 datasheet (same chip ID)")
    if c["otp"]:
        warnings.append(f"{device} is OTP: test on a PFS154 first if you can")
    if f_cpu > 8_000_000:
        warnings.append("F_CPU above 8 MHz is beyond the usual datasheet rating")
    if cfg["system"]["security"]:
        warnings.append("Security fuse ON: the chip can't be read back (easypdkprog needs --allowsecfuse)")
    return errors, warnings


# ----------------------------------------------------------------------------
# Timer maths
# ----------------------------------------------------------------------------
TM_PRESCALE = [(1, "NONE"), (4, "DIV4"), (16, "DIV16"), (64, "DIV64")]


def tm_pwm_settings(freq):
    """Timer2/3 PWM from the 16 MHz IHRC: f = 16M / (2^bits * prescale * (scale+1))."""
    best = None
    for bits, res in ((8, "8BIT"), (6, "6BIT")):
        for pre, pre_name in TM_PRESCALE:
            for scale in range(32):
                f = IHRC_HZ / ((1 << bits) * pre * (scale + 1))
                err = abs(f - freq) / freq
                # prefer 8-bit resolution unless 6-bit is clearly closer
                score = err + (0 if bits == 8 else 0.02)
                if best is None or score < best[0]:
                    best = (score, bits, res, pre_name, scale, f)
    _, bits, res, pre_name, scale, f = best
    return {"bits": bits, "res": res, "prescale": pre_name, "scale": scale, "freq": f}


def pwmg_settings(freq):
    """PFS154 11-bit PWMG from IHRC: f = 16M / (prescale * (scale+1) * (CUB/2 + 1)), as many steps as possible."""
    best = None
    for pre, pre_name in TM_PRESCALE:
        for scale in range(32):
            counts = round(IHRC_HZ / (pre * (scale + 1) * freq))
            if not 2 <= counts <= 1024:
                continue
            f = IHRC_HZ / (pre * (scale + 1) * counts)
            err = abs(f - freq) / freq
            score = err - counts * 1e-6        # tie-break: more resolution
            if best is None or score < best[0]:
                best = (score, pre_name, scale, counts, f)
    if best is None:
        return None
    _, pre_name, scale, counts, f = best
    return {"prescale": pre_name, "scale": scale, "cub": 2 * counts - 1, "freq": f}


def adc_max(device):
    return (1 << chip(device).get("adc_bits", 8)) - 1


def comp_reference(rng, level, vdd_mv):
    """Internal comparator reference in mV (PFS122 datasheet 5.5.1; same ladder on the other chips)."""
    n = int(level) + 1
    frac = {1: 1 / 4 + n / 32, 2: n / 24, 3: 1 / 5 + n / 40, 4: n / 32}[int(rng)]
    return frac * vdd_mv


def adc_divider(f_cpu, max_khz):
    for div in (1, 2, 4, 8, 16, 32, 64, 128):
        if f_cpu / div <= max_khz * 1000:
            return div
    return 128


def human_freq(f):
    if f >= 1e6:
        return f"{f / 1e6:.3g} MHz"
    if f >= 1e3:
        return f"{f / 1e3:.3g} kHz"
    return f"{f:.3g} Hz"


# ----------------------------------------------------------------------------
# Code generation
# ----------------------------------------------------------------------------
def generate(cfg, f_cpu, vdd_mv):
    """Return (pdk_init_h, pdk_init_c) source text."""
    device = cfg["device"]
    c = chip(device)
    pins = cfg["pins"]
    sysc = cfg["system"]
    by_func = {}
    for pin, e in pins.items():
        by_func.setdefault(e["function"], []).append(pin)

    def bit(pin):
        return int(pin[2])

    def port(pin):
        return pin[1]

    h, s = [], []           # header lines, source lines
    hdr = [
        "// Generated by Padauk Configurator from padauk.json. Don't edit:",
        "// this file is overwritten every time you generate code.",
        f"// Chip: {device}, package {cfg['package']}, F_CPU {human_freq(f_cpu)}, VDD {vdd_mv / 1000:.2f} V",
    ]
    h += hdr + ["", "#ifndef PDK_INIT_H", "#define PDK_INIT_H", "", "#include <stdint.h>", "#include <pdk/device.h>", ""]

    # ---- pin table comment
    h.append(f"// Pins (pin numbers for the {cfg['package']} package)")
    for pin in sorted(pins):
        e = pins[pin]
        num = pin_number(cfg, pin)
        h.append(f"//   {pin}  {'pin ' + str(num) if num else '(n/a)':<7} {pin_name(cfg, pin):<14} "
                 f"{FUNCTIONS[e['function']][0]}")
    h.append("")

    # ---- per-pin macros
    for pin in sorted(pins):
        e = pins[pin]
        fn, name, b, P = e["function"], pin_name(cfg, pin), bit(pin), f"P{port(pin)}"
        if fn in ("gpio_out", "gpio_od", "gpio_in", "int", "reset"):
            h.append(f"#define {name}_BIT          {b}")
        if fn in ("gpio_out", "gpio_od"):
            h += [f"#define {name}_high()       ({P} |= (uint8_t)(1 << {b}))" +
                  ("   // released (open-drain)" if fn == "gpio_od" else ""),
                  f"#define {name}_low()        ({P} &= (uint8_t)~(1 << {b}))",
                  f"#define {name}_toggle()     ({P} ^= (uint8_t)(1 << {b}))"]
        if fn in ("gpio_in", "int"):
            h.append(f"#define {name}_read()       ({P} & (uint8_t)(1 << {b}))")
        if fn == "int":
            irq = c["ints"][pin][0]
            h.append(f"#define {name}_triggered()  (pdk_{irq.lower()}_flag)   // set by pdk_irq(), clear it yourself")
        if fn in ("tm2_pwm", "tm3_pwm"):
            reg = "TM2B" if fn == "tm2_pwm" else "TM3B"
            st = tm_pwm_settings(cfg["pwm"].get(fn, {}).get("freq", 1000))
            top = (1 << st["bits"]) - 1
            h.append(f"#define {name}_PWM_MAX      {top}")
            h.append(f"#define {name}_set_duty(d)  ({reg} = (uint8_t)(d))   // 0..{top}, duty = (d+1)/{top + 1}")
        if fn.startswith("pwmg"):
            n = fn[-1]
            st = pwmg_settings(cfg["pwm"].get(fn, {}).get("freq", 1000))
            cub = st["cub"] if st else 255
            h.append(f"#define {name}_PWM_MAX      {cub}")
            h.append(f"#define {name}_set_duty(d)  do {{ PWMG{n}DTL = (uint8_t)((d) << 5); "
                     f"PWMG{n}DTH = (uint8_t)((d) >> 3); }} while (0)   // 0..{cub}")
        if fn == "adc":
            h.append(f"#define {name}_ADC          {c['adc'][pin]}")
            h.append(f"#define {name}_read()       adc_read({c['adc'][pin]})")
        if fn == "serial_tx":
            h.append("// Serial TX on PA7: serial_println(\"text\"), putchar(c), serial_print_uint(n).")
            h.append("// (printf() needs more RAM than these chips have.)")
        h.append("")

    comp_funcs = {f for f in by_func if f.startswith("comp_")}
    comp_on = cfg["comp"]["enabled"] or bool(comp_funcs)
    if comp_on:
        h += ["#define COMP_read()          (GPCC & GPCC_COMP_RESULT_POSITIVE)   // + input higher than - input", ""]

    uses_irq = {k for k in ("int", "serial_tx") if k in by_func}
    if sysc["millis"]:
        uses_irq.add("millis")
    if comp_on and cfg["comp"]["interrupt"]:
        uses_irq.add("comp")

    h += ["void pdk_init(void);   // call once at the start of main()/setup()",
          "void pdk_irq(void);    // call at the start of your interrupt(void) __interrupt(0) handler", ""]
    for irq in sorted({c["ints"][p][0] for p in by_func.get("int", [])}):
        h.append(f"extern volatile uint8_t pdk_{irq.lower()}_flag;")
    if "comp" in uses_irq:
        h.append("extern volatile uint8_t pdk_comp_flag;")
    if "adc" in by_func:
        if c.get("adc_bits", 8) == 12:
            h.append("uint16_t adc_read(uint8_t channel);  // 12-bit result 0..4095 (VDD = 4096), channel = <NAME>_ADC")
            h.append("#define ADC_MAX  4095")
        else:
            h.append("uint8_t adc_read(uint8_t channel);   // 8-bit result 0..255, channel = <NAME>_ADC")
            h.append("#define ADC_MAX  255")
    if sysc["millis"]:
        h.append("uint32_t millis(void);   // milliseconds since start (Timer16)")
    if "serial_tx" in by_func:
        h += ["#include <stdio.h>", "void serial_println(char *str);",
              "void serial_print_uint(uint16_t n);   // decimal, no newline"]
    if sysc["watchdog"] != "off":
        h.append("#define pdk_watchdog_feed()  __wdreset()   // call more often than the watchdog timeout")
    h += ["", "#endif // PDK_INIT_H", ""]

    # ======================= source =======================
    s += hdr + ["", '#include "pdk_init.h"']
    if "serial_tx" in by_func:
        s.append('#include "serial.h"     // don\'t include serial.h anywhere else')
    if sysc["millis"]:
        s.append('#include "millis.h"     // don\'t include millis.h anywhere else')
    s.append("")
    for irq in sorted({c["ints"][p][0] for p in by_func.get("int", [])}):
        s.append(f"volatile uint8_t pdk_{irq.lower()}_flag;")
    if "comp" in uses_irq:
        s.append("volatile uint8_t pdk_comp_flag;")
    s.append("")

    s += ["void pdk_init(void)", "{"]

    # ---- fuses
    if sysc["fuses"]:
        parts = ["FUSE_SECURITY_ON" if sysc["security"] else "FUSE_SECURITY_OFF",
                 dict(c["drive_fuse"]).get(sysc["drive"], c["drive_fuse"][0][1]),
                 "FUSE_BOOTUP_FAST" if sysc["bootup"] == "fast" else "FUSE_BOOTUP_SLOW"]
        lvr = sysc["lvr"] or default_lvr(device, vdd_mv)
        if c["lvr"][0] == "fuse":
            parts.append(f"FUSE_LVR_{lvr}")
        s += ["  // Fuses (stored in the last ROM word when the chip is written)",
              f"  PDK_SET_FUSE({' | '.join(parts)});", ""]

    # ---- system
    s.append("  // System")
    if c["lvr"][0] == "MISCLVR":
        lvr = sysc["lvr"] or default_lvr(device, vdd_mv)
        s.append(f"  MISCLVR = MISCLVR_{lvr};                 // low voltage reset level")
    elif c["lvr"][0] == "MISCLVR_FULL":
        lvr = sysc["lvr"] or default_lvr(device, vdd_mv)
        s.append(f"  MISCLVR = (uint8_t)(MISCLVR_BANDGAP_ON | MISCLVR_{lvr});   // low voltage reset level")
    wdt = sysc["watchdog"]
    if wdt == "off":
        s += ["  MISC = 0;                                // watchdog timeout default, LVR enabled",
              "  CLKMD &= (uint8_t)~CLKMD_ENABLE_WATCHDOG; // watchdog off"]
    else:
        s += [f"  MISC = MISC_WATCHDOG_{wdt.upper()}_ILRC;   // watchdog timeout",
              "  __wdreset();",
              "  CLKMD |= CLKMD_ENABLE_WATCHDOG;         // watchdog on: call pdk_watchdog_feed() regularly"]
    if "reset" in by_func:
        s.append("  CLKMD |= CLKMD_ENABLE_PRSTB;            // PA5 is the reset pin")
    if c["has_rop"]:
        rop = []
        for p in by_func.get("int", []):
            rop.append(c["ints"][p][3])
        s.append(f"  ROP = (uint8_t)({' | '.join(sorted(set(rop))) if rop else '0'});"
                 "   // interrupt pin selection, timer/PWM options default")
    s.append("")

    # ---- ports
    adc_pins = set(by_func.get("adc", []))
    analog = adc_pins | set(by_func.get("comp_plus", [])) | set(by_func.get("comp_minus", []))
    io = all_io_pins(device)
    for P in c["ports"]:
        port_pins = [p for p in io if p[1] == P]
        if not port_pins:
            continue
        out = init_hi = pu = pd = dier = 0
        notes = []
        for p in port_pins:
            m = 1 << bit(p)
            e = pins.get(p)
            fn = e["function"] if e else None
            if fn is None:
                if sysc["unused_pins"] == "pullup" and p in pin_info(device)["pull_up"]:
                    pu |= m
                    dier |= m
                elif sysc["unused_pins"] == "output_low" and not open_drain_only(device, p):
                    out |= m
                elif sysc["unused_pins"] == "output_low":
                    out |= m      # open-drain pin driven low
                continue
            if fn in ("gpio_out", "gpio_od", "tm2_pwm", "tm3_pwm", "pwmg0", "pwmg1", "pwmg2",
                      "comp_out", "serial_tx"):
                out |= m
                if fn in ("gpio_out", "gpio_od") and e.get("init", "low") == "high":
                    init_hi |= m
                if fn == "serial_tx":
                    init_hi |= m      # UART idle level
            if fn in ("gpio_in", "int", "reset"):
                dier |= m
                pull = e.get("pull", "up" if fn in ("int", "reset") else "none")
                if pull == "up":
                    pu |= m
                elif pull == "down":
                    pd |= m
            if p in analog:
                notes.append(f"{p} analog")
        s.append(f"  // Port {P}" + (f" ({', '.join(notes)}: digital input off)" if notes else ""))
        s.append(f"  P{P} = 0x{init_hi:02X};           // initial output levels")
        s.append(f"  P{P}C = 0x{out:02X};          // 1 = output")
        s.append(f"  P{P}PH = 0x{pu:02X};         // pull-ups")
        if c["pull_down_reg"]:
            s.append(f"  P{P}PL = 0x{pd:02X};         // pull-downs")
        s.append(f"  P{P}DIER = 0x{dier:02X};       // digital input enable (inputs, interrupts)")
        s.append("")

    # ---- timers / PWM
    for fn, reg in (("tm2_pwm", "TM2"), ("tm3_pwm", "TM3")):
        if fn not in by_func:
            continue
        pin = by_func[fn][0]
        opts = cfg["pwm"].get(fn, {})
        st = tm_pwm_settings(opts.get("freq", 1000))
        top = (1 << st["bits"])
        duty = max(0, min(top - 1, round(opts.get("duty", 50) / 100 * top) - 1))
        out_macro = c["tm2_out"][pin] if fn == "tm2_pwm" else c["tm3_out"][pin]
        ctl = [f"{reg}C_CLK_IHRC", f"{reg}C_MODE_PWM", out_macro]
        if opts.get("invert"):
            ctl.append(f"{reg}C_INVERT_OUT")
        s += [f"  // {reg} PWM on {pin} ({pin_name(cfg, pin)}): {human_freq(st['freq'])}, {st['bits']}-bit",
              f"  {reg}CT = 0;",
              f"  {reg}B = {duty};                       // duty {(duty + 1) * 100 / top:.1f}%",
              f"  {reg}S = (uint8_t)({reg}S_PWM_RES_{st['res']} | {reg}S_PRESCALE_{st['prescale']} | "
              f"{reg}S_SCALE_{'NONE' if st['scale'] == 0 else 'DIV' + str(st['scale'] + 1)});",
              f"  {reg}C = (uint8_t)({' | '.join(ctl)});", ""]
    if "serial_tx" in by_func:
        s += ["  // Serial TX on PA7 (Timer2 interrupt)", "  serial_setup();", ""]

    for n in (0, 1, 2):
        fn = f"pwmg{n}"
        if fn not in by_func:
            continue
        pin = by_func[fn][0]
        opts = cfg["pwm"].get(fn, {})
        st = pwmg_settings(opts.get("freq", 1000))
        cub = st["cub"]
        duty = max(0, min(cub, round(opts.get("duty", 50) / 100 * (cub + 1)) - 1))
        ctl = [f"PWMG{n}C_ENABLE", f"PWMG{n}C_CLK_IHRC", c["pwmg_out"][n][pin]]
        if opts.get("invert"):
            ctl.append(f"PWMG{n}C_INVERT_OUT")
        s += [f"  // PWMG{n} on {pin} ({pin_name(cfg, pin)}): ~{human_freq(st['freq'])}, 0..{cub}",
              f"  PWMG{n}CUBH = (uint8_t)({cub} >> 3);",
              f"  PWMG{n}CUBL = (uint8_t)({cub} << 5);",
              f"  PWMG{n}DTH = (uint8_t)({duty} >> 3);",
              f"  PWMG{n}DTL = (uint8_t)({duty} << 5);     // duty ~{(duty + 1) * 100 / (cub + 1):.0f}%",
              f"  PWMG{n}S = (uint8_t)(PWMG{n}S_PRESCALE_{st['prescale']} | "
              f"PWMG{n}S_SCALE_{'NONE' if st['scale'] == 0 else 'DIV' + str(st['scale'] + 1)});",
              f"  PWMG{n}C = (uint8_t)({' | '.join(ctl)});", ""]

    # ---- comparator
    if comp_on:
        cc = cfg["comp"]
        plus = "GPCC_COMP_PLUS_PA4" if "comp_plus" in by_func else "GPCC_COMP_PLUS_VINT_R"
        if "comp_minus" in by_func:
            minus = c["comp_minus"][by_func["comp_minus"][0]]
        else:
            minus = "GPCC_COMP_MINUS_BANDGAP_1V2" if cc["minus"] == "bandgap" else "GPCC_COMP_MINUS_VINT_R"
        ctl = ["GPCC_COMP_ENABLE", plus, minus] + (["GPCC_COMP_OUT_INVERT"] if cc["invert"] else [])
        sel = [f"GPCS_COMP_RANGE{int(cc['range'])}", str(int(cc["level"]))]
        if "comp_out" in by_func:
            sel.insert(0, "GPCS_COMP_OUTPUT_PA0")
        s += ["  // Comparator (internal reference: range/level, see the datasheet for the voltage)",
              f"  GPCS = (uint8_t)({' | '.join(sel)});",
              f"  GPCC = (uint8_t)({' | '.join(ctl)});"]
        if c["misc2"]:
            edge = {"both": "BOTH", "rising": "RISE", "falling": "FALL"}[cc["edge"]]
            s.append(f"  MISC2 = MISC2_COMP_EDGE_INT_{edge};   // comparator interrupt edge")
        s.append("")
    else:
        s += ["  GPCC = 0;                                // comparator off", ""]

    # ---- ADC
    if "adc" in by_func:
        div = adc_divider(f_cpu, cfg["adc"].get("clock_khz", 500))
        name = "SYSCLK" if div == 1 else f"SYSCLK_DIV{div}"
        s += [f"  // ADC: clock {human_freq(f_cpu / div)}, reference VDD",
              f"  ADCM = ADCM_CLK_{name};",
              "  ADCC = ADCC_ADC_ENABLE;", ""]

    # ---- millis
    if sysc["millis"]:
        s += ["  // millis() timebase (Timer16)", "  millis_setup();", ""]

    # ---- interrupts
    inten, integs = [], []
    for p in by_func.get("int", []):
        irq, suffix, edge_prefix, _ = c["ints"][p]
        inten.append(f"INTEN_{suffix}")
        edge = {"both": "BOTH", "rising": "RISING", "falling": "FALLING"}[pins[p].get("edge", "falling")]
        integs.append(f"{edge_prefix}_{edge}")
    if "comp" in uses_irq:
        inten.append("INTEN_COMP")
        if c["comp_edge"] == "INTEGS_COMP":
            edge = {"both": "BOTH", "rising": "RISING", "falling": "FALLING"}[cfg["comp"]["edge"]]
            integs.append(f"INTEGS_COMP_{edge}")
    if "serial_tx" in by_func:
        inten.append("INTEN_TM2")
    if sysc["millis"]:
        inten.append("INTEN_T16")
    s += ["  // Interrupts",
          f"  INTEGS = (uint8_t)({' | '.join(integs) if integs else '0'});",
          f"  INTEN = (uint8_t)({' | '.join(inten) if inten else '0'});",
          "  INTRQ = 0;"]
    if inten:
        s.append("  __engint();                              // enable interrupts")
    s += ["}", ""]

    # ---- pdk_irq
    s += ["void pdk_irq(void)", "{"]
    for p in by_func.get("int", []):
        irq, suffix, _, _ = c["ints"][p]
        s += [f"  if ((INTEN & INTEN_{suffix}) && (INTRQ & INTRQ_{suffix})) {{",
              f"    INTRQ &= (uint8_t)~INTRQ_{suffix};",
              f"    pdk_{irq.lower()}_flag = 1;              // {pin_name(cfg, p)}",
              "  }"]
    if "comp" in uses_irq:
        s += ["  if ((INTEN & INTEN_COMP) && (INTRQ & INTRQ_COMP)) {",
              "    INTRQ &= (uint8_t)~INTRQ_COMP;", "    pdk_comp_flag = 1;", "  }"]
    if "serial_tx" in by_func:
        s += ["  if (INTRQ & INTRQ_TM2) {", "    INTRQ &= (uint8_t)~INTRQ_TM2;", "    serial_irq_handler();", "  }"]
    if sysc["millis"]:
        s += ["  if (INTRQ & INTRQ_T16) {", "    INTRQ &= (uint8_t)~INTRQ_T16;", "    millis_irq_handler();", "  }"]
    s += ["}", ""]

    if "serial_tx" in by_func:
        s += ["void serial_print_uint(uint16_t n)", "{",
              "  char buf[6];",
              "  uint8_t i = 0;",
              "  do {",
              "    buf[i++] = (char)('0' + n % 10);",
              "    n /= 10;",
              "  } while (n);",
              "  while (i)",
              "    putchar(buf[--i]);",
              "}", ""]
    if "adc" in by_func and c.get("adc_bits", 8) == 12:
        s += ["// PFS122 12-bit ADC: ADCRH (0x22) = result bits 11..4, ADCRL (0x23) bits 7..4 = result bits 3..0",
              "__sfr __at(0x23) _pdk_adcrl;",
              "",
              "uint16_t adc_read(uint8_t channel)", "{",
              "  ADCC = (uint8_t)(ADCC_ADC_ENABLE | channel);",
              "  ADCC |= ADCC_START_ADC_CONV;",
              "  while (!(ADCC & ADCC_IS_ADC_CONV_READY))",
              "    ;",
              "  return (uint16_t)((uint16_t)ADCR << 4) | (_pdk_adcrl >> 4);   // ADCR = ADCRH", "}", ""]
    elif "adc" in by_func:
        s += ["uint8_t adc_read(uint8_t channel)", "{",
              "  ADCC = (uint8_t)(ADCC_ADC_ENABLE | channel);",
              "  ADCC |= ADCC_START_ADC_CONV;",
              "  while (!(ADCC & ADCC_IS_ADC_CONV_READY))",
              "    ;",
              "  return ADCR;", "}", ""]
    # Cast every register assignment: SDCC warns when a macro >= 0x80 is assigned to an 8-bit SFR
    reg_assign = re.compile(r"^(\s*[A-Z][A-Z0-9_]* = )(?!\(uint8_t\)|0x|0;|\d+;)([^;]+);")
    s = [reg_assign.sub(lambda m: f"{m.group(1)}(uint8_t)({m.group(2)});", line) for line in s]
    return "\n".join(h), "\n".join(s)


# ----------------------------------------------------------------------------
# Writing files / hooking into main.c
# ----------------------------------------------------------------------------
def write_generated(project, cfg, f_cpu, vdd_mv):
    header, source = generate(cfg, f_cpu, vdd_mv)
    for name, text in (("pdk_init.h", header), ("pdk_init.c", source)):
        with open(os.path.join(project, name), "w") as f:
            f.write(text)
    return ["pdk_init.h", "pdk_init.c"]


def hook_main(project):
    """Add #include "pdk_init.h", pdk_init() and pdk_irq() to main.c if missing.
    Returns a list of changes made (empty if nothing to do), or None if main.c is missing."""
    path = os.path.join(project, "main.c")
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        text = f.read()
    orig = text
    changes = []
    if '"pdk_init.h"' not in text:
        m = re.search(r'^#include\s+"board\.h".*$', text, re.M) or \
            re.search(r'^#include\s+<pdk/device\.h>.*$', text, re.M)
        if m:
            text = text[:m.end()] + '\n#include "pdk_init.h"     // generated by Padauk Configurator' + text[m.end():]
            changes.append('added #include "pdk_init.h"')
    if "pdk_irq()" not in text:
        m = re.search(r"__interrupt\s*\(\s*0\s*\)\s*\{", text)
        if m:
            text = text[:m.end()] + "\n  pdk_irq();                  // generated interrupts (flags, serial, millis)" + text[m.end():]
            changes.append("added pdk_irq() to the interrupt handler")
    if "pdk_init()" not in text:
        m = re.search(r"static\s+void\s+setup\s*\(\s*void\s*\)\s*\{", text) or \
            re.search(r"void\s+main\s*\(\s*void\s*\)\s*\{", text)
        if m:
            text = text[:m.end()] + "\n  pdk_init();                 // pins and peripherals from Padauk Configurator" + text[m.end():]
            changes.append("added pdk_init() to " + ("setup()" if "setup" in m.group(0) else "main()"))
    if text != orig:
        with open(path + ".bak", "w") as f:
            f.write(orig)
        with open(path, "w") as f:
            f.write(text)
    return changes


def copy_config(cfg):
    return copy.deepcopy(cfg)
