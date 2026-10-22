"""Checks that run before generating code. Each finding is (level, text, where).

level: "error" blocks Generate/Build, "warning" and "info" don't.
where: a pin name, "clock", "TM2", ... so the GUI can point at it.
"""

from typing import List, Tuple

from . import codegen
from .project import Project, valid_label

Finding = Tuple[str, str, str]


def check(project: Project) -> List[Finding]:
    p, chip = project, project.chip
    out: List[Finding] = []
    add = lambda lvl, text, where="": out.append((lvl, text, where))   # noqa: E731

    vdd = int(p.data.get("vdd_mv", 5000))
    clk = p.clock
    lo, hi = chip.vdd_range_mv
    if not lo <= vdd <= hi:
        add("error", f"VDD {vdd / 1000:g} V is outside the {chip.name}'s {lo / 1000:g}-{hi / 1000:g} V range.", "clock")
    if vdd < clk.min_vdd_mv:
        add("error", f"{clk.label} needs VDD of at least {clk.min_vdd_mv / 1000:g} V (datasheet 4.1). "
                     f"Pick a slower clock or a higher VDD.", "clock")
    if clk.undocumented:
        add("warning", "16 MHz isn't in the datasheet: it only runs reliably near 5 V.", "clock")

    # LVR
    lvr = codegen.lvr_choice(p)
    if lvr:
        if lvr[1] >= vdd:
            add("error", f"Low-voltage reset at {lvr[1] / 1000:g} V is not below VDD {vdd / 1000:g} V: "
                         "the chip would stay in reset.", "system")
        elif lvr[1] < clk.min_vdd_mv and p.data["system"].get("lvr") != "auto":
            add("warning", f"Low-voltage reset at {lvr[1] / 1000:g} V is below the {clk.min_vdd_mv / 1000:g} V "
                           f"this clock needs: brown-outs can crash the program.", "system")
    else:
        add("info", "Low-voltage reset is off.", "system")

    # labels
    seen = {}
    for pin, cfg in p.pins.items():
        lab = cfg.get("label")
        if not lab:
            continue
        if not valid_label(lab):
            add("error", f"{pin}: '{lab}' isn't a valid C name (letters, digits, _; not starting with a digit).", pin)
        elif lab.upper() in seen:
            add("error", f"{pin} and {seen[lab.upper()]} have the same name '{lab}'.", pin)
        elif lab.upper() in {r.name for r in chip.registers} or lab.upper() in chip.pins:
            add("error", f"{pin}: '{lab}' is a register or pin name, pick another name.", pin)
        seen[lab.upper()] = pin

    # pins on this package
    bonded = set(chip.package(p.data["package"]).pins)
    for pin in p.pins:
        if pin not in bonded:
            add("warning", f"{pin} is set up but isn't a pin of the {chip.package(p.data['package']).label} package.", pin)

    # PWM
    users = {}
    for pin, cfg in p.pins.items():
        if cfg.get("fn") != "pwm":
            continue
        per = cfg.get("periph")
        if not per:
            add("error", f"{pin}: no PWM generator left that can drive this pin.", pin)
            continue
        if pin not in chip.pwm_outputs.get(per, {}):
            add("error", f"{pin}: {per} can't output on this pin.", pin)
        if per in users:
            add("error", f"{per} drives only one pin, but {users[per]} and {pin} both use it.", pin)
        users[per] = pin
    if p.serial_enabled():
        st = p.data["serial"].get("timer")
        if st in users:
            add("error", f"{st} can't do serial output and PWM ({users[st]}) at the same time.", st)

    # interrupts sharing one line (PFS122: PA0/PB5, PB0/PA4)
    lines = {}
    for pin in p.pins_with("interrupt"):
        irq = chip.interrupts.get(pin)
        if not irq:
            add("error", f"{pin} has no external interrupt.", pin)
            continue
        if irq["line"] in lines:
            add("error", f"{lines[irq['line']]} and {pin} share interrupt {irq['line']}: only one can use it.", pin)
        lines[irq["line"]] = pin

    # serial
    if p.serial_enabled():
        baud = int(p.data["serial"].get("baud", 115200))
        if "PA7" not in bonded:
            add("error", "Serial output uses PA7, which this package doesn't have.", "PA7")
        if clk.source != "IHRC" and chip.factory_ihrcr is None:
            add("error", "Serial output needs the calibrated 16 MHz IHRC: pick an IHRC system clock.", "clock")
        elif clk.source != "IHRC":
            add("warning", "Serial output uses the IHRC with its factory trim (not calibrated): "
                           "the baud rate may be a few % off.", "clock")
        if p.f_cpu / baud < 60:
            add("error", f"{baud} baud is too fast for a {p.clock.label} system clock: the interrupt can't keep up. "
                         f"Use at most {int(p.f_cpu / 60)} baud.", "serial")

    # timers
    plan = codegen.timer_plan(p)
    for name in chip.timers:
        cfg = p.timer(name)
        mode = cfg.get("mode", "off")
        if mode == "off":
            continue
        s = plan.get(name)
        if mode == "pwm":
            want = float(cfg.get("freq_hz", 1000))
        elif mode == "serial":
            want = float(p.data["serial"].get("baud", 115200))
        elif mode == "millis":
            want = 1000
        else:
            want = float(cfg.get("tick_hz", 1000))
        if not s:
            add("error", f"{name}: can't make {want:g} Hz with this clock.", name)
            continue
        err = s.error(want)
        if mode == "millis" or (name == "T16" and mode == "tick"):
            continue      # Timer16 steps are powers of two; millis() corrects for it
        if err > 0.05:
            add("warning", f"{name}: closest is {s.actual_hz:.6g} Hz instead of {want:g} Hz.", name)
        if mode == "serial" and err > 0.03:
            add("error", f"{name}: serial would be {err * 100:.1f} % off; pick another baud rate.", name)

    # comparator
    comp = p.data["comparator"]
    if comp.get("enabled"):
        if comp.get("plus") == "VINTR" and comp.get("minus") == "VINTR":
            add("error", "Comparator: both inputs are the internal reference.", "comparator")
        if comp.get("minus") not in chip.comparator["minus"]:
            add("error", f"Comparator: {comp.get('minus')} can't be the minus input.", "comparator")
        if comp.get("plus") not in chip.comparator["plus"]:
            add("error", f"Comparator: {comp.get('plus')} can't be the plus input.", "comparator")
        for key, fn in (("plus", "comp_plus"), ("minus", "comp_minus")):
            src = comp.get(key)
            if src in chip.pins and p.fn(src) != fn:
                add("error", f"Comparator {key} input is {src}, but {src} isn't set up as a comparator input.",
                    src)

    # pins with notes
    for pin in p.pins:
        info = chip.pins[pin]
        if info.open_drain_only and p.fn(pin) == "output":
            add("info", f"{pin} can only pull low (open drain): use a pull-up to get a high level.", pin)

    if chip.otp:
        add("info", f"The {chip.name} is one-time programmable: test on a PFS154 first if you can.", "")
    return out


def errors(project: Project) -> List[Finding]:
    return [f for f in check(project) if f[0] == "error"]
