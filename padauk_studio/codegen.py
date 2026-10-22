"""Turn a Project into C files: <chip>.h, pdk_init.h, pdk_init.c and main.c.

main.c keeps everything between /* USER CODE BEGIN x */ and /* USER CODE END x */
when it is generated again. Sections that no longer exist (say you removed the
Timer16 interrupt) are moved to an `#if 0` block at the end of main.c instead
of being thrown away.
"""

import os
import re
from typing import Dict, List, Optional, Tuple

from . import timing
from .chips import Chip, VINTR_RANGES, comparator_vintr
from .gen_header import generate_header, header_name
from .project import Project

USER_RE = re.compile(r"/\*\s*USER CODE BEGIN (\w+)\s*\*/\n?(.*?)[ \t]*/\*\s*USER CODE END \1\s*\*/", re.S)

PORT_A_DIER_BITS = 0xF9     # PA0, PA3..PA7 exist (bits 2..1 reserved: keep 0)


def hx(v: int) -> str:
    return f"0x{v:02x}"


def bitlist(bits: int) -> str:
    return " ".join(str(i) for i in range(8) if bits & (1 << i)) or "-"


class GenError(Exception):
    pass


class Context:
    """Derived facts the generators share."""

    def __init__(self, project: Project):
        self.p = project
        self.chip: Chip = project.chip
        self.clk = project.clock
        self.f_cpu = project.f_cpu
        self.vdd = int(project.data.get("vdd_mv", 5000))
        self.bonded = set(self.chip.package(project.data["package"]).pins)
        self.notes: List[str] = []      # explanations shown in the GUI ("TM2: 976.6 Hz, 8-bit")
        # clock sources a timer may use
        self.sources: Dict[str, float] = {"SYSCLK": float(self.f_cpu)}
        if project.uses_ihrc() or self.clk.source == "IHRC":
            self.sources["IHRC"] = 16_000_000.0

    def label(self, pin):
        return self.p.label(pin)

    def timer_sources(self, prefer_ihrc=True):
        if prefer_ihrc and "IHRC" in self.sources:
            return {"IHRC": self.sources["IHRC"]}
        return dict(self.sources)


# ---------------------------------------------------------------------------
# Peripheral settings (also used by the GUI to show the actual frequencies)
# ---------------------------------------------------------------------------

def lvr_choice(project: Project) -> Optional[Tuple[str, int]]:
    """(key, mV) of the LVR level to use, or None for "off"."""
    chip = project.chip
    sel = project.data["system"].get("lvr", "auto")
    if sel == "off":
        return None
    levels = dict(chip.lvr_levels)
    if sel in levels:
        return sel, levels[sel]
    need = project.clock.min_vdd_mv
    vdd = int(project.data.get("vdd_mv", 5000))
    ok = sorted((mv, k) for k, mv in chip.lvr_levels if mv >= need and mv <= vdd * 0.9)
    if ok:
        mv, k = ok[0]
        return k, mv
    below = sorted((mv, k) for k, mv in chip.lvr_levels if mv <= vdd * 0.9)
    if below:
        mv, k = below[-1]
        return k, mv
    mv, k = min((mv, k) for k, mv in chip.lvr_levels)
    return k, mv


def timer_plan(project: Project) -> Dict[str, timing.TimerSetting]:
    """The register settings for every timer in use."""
    ctx = Context(project)
    out = {}
    for name in project.chip.timers:
        cfg = project.timer(name)
        mode = cfg.get("mode", "off")
        if mode == "off":
            continue
        if name == "T16":
            hz = 1000 if mode == "millis" else float(cfg.get("tick_hz", 1000))
            s = timing.t16_tick(ctx.sources, hz)
        elif name.startswith("TM"):
            if mode == "pwm":
                s = timing.tm8_pwm(ctx.timer_sources(), float(cfg.get("freq_hz", 1000)))
                if s and s.error(float(cfg.get("freq_hz", 1000))) > 0.02:
                    s = timing.tm8_pwm(ctx.sources, float(cfg.get("freq_hz", 1000)))
            elif mode == "serial":
                s = timing.tm8_period(ctx.timer_sources(), float(project.data["serial"].get("baud", 115200)))
            else:
                s = timing.tm8_period(ctx.sources, float(cfg.get("tick_hz", 1000)))
        else:   # PWMG
            s = timing.pwmg(ctx.timer_sources(), float(cfg.get("freq_hz", 1000)))
        if s:
            out[name] = s
    return out


def describe_timer(name: str, s: timing.TimerSetting, mode: str) -> str:
    src = {"IHRC": "16 MHz IHRC", "SYSCLK": "system clock", "ILRC": "ILRC"}[s.source]
    if name.startswith("PWMG"):
        return f"{timing.fmt_hz(s.actual_hz)} from {src}, {2 * (s.bound + 1)} duty steps"
    if mode == "pwm":
        return f"{timing.fmt_hz(s.actual_hz)} from {src}, {s.res}-bit duty"
    if name == "T16":
        return f"interrupt every {1000 / s.actual_hz:.4g} ms ({timing.fmt_hz(s.actual_hz)}) from {src}"
    return f"interrupt rate {timing.fmt_hz(s.actual_hz)} from {src}"


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------

def port_values(ctx: Context):
    """Register values for each port: dict port -> dict(reg -> value, comments)."""
    chip, p = ctx.chip, ctx.p
    ports = sorted({info.port for info in chip.pins.values()})
    res = {}
    unused_mode = p.data.get("unused_pins", "pullup")
    for port in ports:
        v = {"data": 0, "dir": 0, "ph": 0, "pl": 0, "dier": 0, "who": {}}
        for name, info in chip.pins.items():
            if info.port != port:
                continue
            b = 1 << info.bit
            cfg = p.pins.get(name, {})
            fn = cfg.get("fn", "unused")
            if fn == "unused":
                if name not in ctx.bonded:
                    v["dir"] |= b                   # not on this package: drive low
                    v["who"][name] = "not bonded: output low"
                elif unused_mode == "output_low":
                    v["dir"] |= b
                    v["who"][name] = "unused: output low"
                else:
                    v["ph"] |= b
                    v["dier"] |= b
                    v["who"][name] = "unused: input, pull-up"
                continue
            lab = ctx.label(name)
            if fn == "output":
                v["dir"] |= b
                v["dier"] |= b                      # so PA ^= x reads the pin back
                if cfg.get("initial"):
                    v["data"] |= b
                v["who"][name] = f"{lab}: output"
            elif fn in ("input", "interrupt"):
                v["dier"] |= b
                pull = cfg.get("pull", "none")
                if pull == "up":
                    v["ph"] |= b
                elif pull == "down" and chip.has_pull_down:
                    v["pl"] |= b
                v["who"][name] = f"{lab}: input" + (f", pull-{pull}" if pull in ("up", "down") else "")
            elif fn in ("pwm", "comp_out"):
                v["dir"] |= b
                v["who"][name] = f"{lab}: {'PWM' if fn == 'pwm' else 'comparator'} output"
            elif fn in ("adc", "comp_minus", "comp_plus"):
                v["who"][name] = f"{lab}: analog input (digital input off)"
            elif fn == "serial_tx":
                v["dir"] |= b
                v["data"] |= b
                v["dier"] |= b
                v["who"][name] = "serial TX (idle high)"
            elif fn == "reset":
                v["ph"] |= b
                v["dier"] |= b
                v["who"][name] = "reset input PRSTB, pull-up"
        if port == "A":
            v["dier"] &= PORT_A_DIER_BITS
        res[port] = v
    return res


# ---------------------------------------------------------------------------
# User code sections
# ---------------------------------------------------------------------------

def extract_user_code(text: str) -> Dict[str, str]:
    return {m.group(1): m.group(2) for m in USER_RE.finditer(text)}


def merge_user_code(template: str, old: Dict[str, str]) -> str:
    used = set()

    def fill(m):
        name, default = m.group(1), m.group(2)
        used.add(name)
        body = old.get(name, default)
        indent = re.match(r"[ \t]*", template[template.rfind("\n", 0, m.start()) + 1:m.start()]).group(0)
        return f"/* USER CODE BEGIN {name} */\n{body}{indent}/* USER CODE END {name} */"

    out = USER_RE.sub(fill, template)
    orphans = [(n, b) for n, b in old.items() if n not in used and b.strip()]
    if orphans:
        out += ("\n/* Code from sections that no longer exist (for example a removed interrupt).\n"
                " * Kept here so nothing is lost: move what you need, then delete it. */\n#if 0\n")
        for n, b in orphans:
            name = n if n.startswith("removed_") else f"removed_{n}"
            out += f"/* USER CODE BEGIN {name} */\n{b}/* USER CODE END {name} */\n"
        out += "#endif\n"
    return out


# ---------------------------------------------------------------------------
# File generators
# ---------------------------------------------------------------------------

def interrupt_sources(ctx: Context, plan) -> List[dict]:
    """[{"name": "T16", "intrq": "INTRQ_T16", "inten": ..., "comment": ...}]"""
    chip, p = ctx.chip, ctx.p
    out = []
    seen_lines = set()
    for pin in chip.pins:
        if p.fn(pin) != "interrupt":
            continue
        irq = chip.interrupts.get(pin)
        if not irq or irq["line"] in seen_lines:
            continue
        seen_lines.add(irq["line"])
        line = irq["line"]
        out.append({"name": line if line == pin else f"{line}", "pin": pin, "intrq": irq["intrq"],
                    "inten": irq["inten"], "comment": f"{ctx.label(pin)} ({pin}) changed",
                    "call": None})
    t16 = p.timer("T16").get("mode")
    if t16 in ("millis", "tick") and "T16" in plan:
        out.append({"name": "T16", "intrq": "INTRQ_T16", "inten": "INTEN_T16",
                    "comment": "Timer16 tick" + (" (millis)" if t16 == "millis" else ""),
                    "call": "pdk_millis_tick();" if t16 == "millis" else None})
    for t in ("TM2", "TM3"):
        if t not in chip.timers or t not in plan:
            continue
        mode = p.timer(t).get("mode")
        if mode == "tick":
            out.append({"name": t, "intrq": f"INTRQ_{t}", "inten": f"INTEN_{t}",
                        "comment": f"Timer{t[2]} period", "call": None})
        elif mode == "serial":
            out.append({"name": t, "intrq": f"INTRQ_{t}", "inten": f"INTEN_{t}",
                        "comment": f"Timer{t[2]}: serial bit clock", "call": "pdk_serial_isr();",
                        "no_user": True})
    comp = p.data["comparator"]
    if comp.get("enabled") and comp.get("irq", "off") != "off":
        out.append({"name": "COMP", "intrq": "INTRQ_COMP", "inten": "INTEN_COMP",
                    "comment": "comparator output changed", "call": None})
    return out


def generate_main(ctx: Context, plan, old_text: str = "") -> str:
    p, chip = ctx.p, ctx.chip
    srcs = interrupt_sources(ctx, plan)
    wdt = p.data["system"].get("watchdog", "off") != "off"
    L = []
    w = L.append
    w(f"/* main.c: {p.name} ({chip.name})")
    w(" *")
    w(" * Padauk Studio generates this file. Write your code between the")
    w(" * USER CODE BEGIN and USER CODE END lines: that code is kept when you")
    w(" * press Generate again. Everything else is rewritten.")
    w(" */")
    w('#include "pdk_init.h"')
    w("")
    w("/* USER CODE BEGIN includes */")
    w("/* USER CODE END includes */")
    w("")
    w("/* USER CODE BEGIN globals */")
    w("/* USER CODE END globals */")
    w("")
    w("void main(void)")
    w("{")
    w("  pdk_init();    /* pins, timers and interrupts as set up in Padauk Studio */")
    w("")
    w("  /* USER CODE BEGIN setup */")
    w("  /* USER CODE END setup */")
    w("")
    w("  for (;;) {")
    if wdt:
        w("    wdt_reset();   /* watchdog is on: reset it at least every period */")
    w("    /* USER CODE BEGIN loop */")
    w("    /* USER CODE END loop */")
    w("  }")
    w("}")
    w("")
    w("/* USER CODE BEGIN functions */")
    w("/* USER CODE END functions */")
    w("")
    w("/* All interrupts share this one handler. Check INTRQ to see which one it was. */")
    w("void interrupt(void) __interrupt(0)")
    w("{")
    for s in srcs:
        w(f"  if (INTRQ & {s['intrq']}) {{          /* {s['comment']} */")
        w(f"    INTRQ &= (uint8_t)~{s['intrq']};")
        if s.get("call"):
            w(f"    {s['call']}")
        if not s.get("no_user"):
            w(f"    /* USER CODE BEGIN irq_{s['name']} */")
            w(f"    /* USER CODE END irq_{s['name']} */")
        w("  }")
    w("  /* USER CODE BEGIN irq_other */")
    w("  /* USER CODE END irq_other */")
    w("}")
    template = "\n".join(L) + "\n"
    return merge_user_code(template, extract_user_code(old_text))


def generate_init_h(ctx: Context, plan) -> str:
    p, chip = ctx.p, ctx.chip
    L = []
    w = L.append
    w(f"/* pdk_init.h: settings and helpers for {p.name} ({chip.name}, {chip.package(p.data['package']).label}).")
    w(" * Generated by Padauk Studio: don't edit, it's rewritten when you press Generate. */")
    w("#ifndef PDK_INIT_H")
    w("#define PDK_INIT_H")
    w("")
    w(f'#include "{header_name(chip)}"')
    w("")
    w(f"#define F_CPU        {ctx.f_cpu}UL    /* system clock: {ctx.clk.label} */")
    w(f"#define VDD_MV       {ctx.vdd}         /* supply voltage the clock is calibrated at */")
    w("")
    w("void pdk_init(void);")
    w("")
    # pins
    pin_lines = []
    for name, info in chip.pins.items():
        cfg = p.pins.get(name)
        if not cfg:
            continue
        fn = cfg["fn"]
        lab = ctx.label(name)
        port, bit = "P" + info.port, info.bit
        if fn in ("output", "input", "interrupt"):
            pin_lines.append(f"/* {lab}: {name}, {fn} */")
            pin_lines.append(f"#define {lab}_PIN          {bit}")
            if fn == "output":
                pin_lines.append(f"#define {lab}_high()       ({port} |= (1 << {bit}))")
                pin_lines.append(f"#define {lab}_low()        ({port} &= (uint8_t)~(1 << {bit}))")
                pin_lines.append(f"#define {lab}_toggle()     ({port} ^= (1 << {bit}))")
                pin_lines.append(f"#define {lab}_set(on)      do {{ if (on) {lab}_high(); else {lab}_low(); }} while (0)")
            pin_lines.append(f"#define {lab}_read()       (({port} & (1 << {bit})) != 0)")
        elif fn == "pwm":
            per = cfg.get("periph", "")
            s = plan.get(per)
            if not s:
                continue
            pin_lines.append(f"/* {lab}: {name}, PWM from {per}: {describe_timer(per, s, 'pwm')} */")
            if per.startswith("TM"):
                steps = 256 if s.res == 8 else 64
                pin_lines.append(f"#define {lab}_DUTY_MAX     {steps - 1}   /* duty = (value + 1) / {steps} */")
                pin_lines.append(f"#define {lab}_set_duty(v)  ({per}B = (uint8_t)(v))")
                pin_lines.append(f"#define {lab}_off()        ({per}C &= (uint8_t)~{per}C_OUT_MASK)")
                pin_lines.append(f"#define {lab}_on()         ({per}C |= {chip.pwm_outputs[per][name]})")
            else:
                pin_lines.append(f"#define {lab}_DUTY_MAX     {2 * s.bound + 1}   /* duty = (value + 1) / {2 * (s.bound + 1)} */")
                pin_lines.append(f"void {lab}_set_duty(uint16_t value);")
                pin_lines.append(f"#define {lab}_off()        ({per}C &= (uint8_t)~{per}C_EN)")
                pin_lines.append(f"#define {lab}_on()         ({per}C |= {per}C_EN)")
        elif fn == "adc":
            pin_lines.append(f"/* {lab}: {name}, ADC input */")
            pin_lines.append(f"#define {lab}_read()       adc_read({chip.adc['channels'][name]})")
        elif fn == "serial_tx":
            pin_lines.append(f"/* {name}: serial TX, read it with Monitor */")
    if pin_lines:
        w("/* ---- Pins ---- */")
        L.extend(pin_lines)
        w("")
    comp = p.data["comparator"]
    if comp.get("enabled"):
        w("/* ---- Comparator ---- */")
        w("#define comparator_read()  ((GPCC & GPCC_RESULT) != 0)   /* 1: plus input > minus input */")
        w("#define comparator_on()    (GPCC |= GPCC_EN)")
        w("#define comparator_off()   (GPCC &= (uint8_t)~GPCC_EN)")
        w("")
    if p.data["adc"].get("enabled") and chip.adc:
        w(f"/* ---- ADC ({chip.adc['bits']}-bit, reference = VDD) ---- */")
        w("uint16_t adc_read(uint8_t channel);   /* channel: ADCC_CH_PB0 ... returns 0..4095 */")
        w("uint16_t vdd_read_mv(void);           /* measures VDD with the 1.2 V bandgap */")
        w("")
    if p.timer("T16").get("mode") == "millis":
        w("/* ---- millis ---- */")
        w("uint32_t millis(void);                /* milliseconds since start */")
        w("void pdk_millis_tick(void);           /* called by the interrupt */")
        w("")
    if p.serial_enabled():
        w(f"/* ---- Serial debug output on PA7 ({p.data['serial'].get('baud', 115200)} baud, 8N1) ---- */")
        w("void serial_putc(char c);")
        w("void serial_print(const char *s);")
        w("void serial_println(const char *s);")
        w("void serial_print_uint(uint16_t value);")
        w("void serial_print_hex(uint8_t value);")
        w("void pdk_serial_isr(void);            /* called by the interrupt */")
        w("")
    w("/* ---- Delays (busy wait, interrupts make them longer) ---- */")
    w("void pdk_delay_loop(uint16_t loops);      /* 8 cycles per loop */")
    w("void delay_ms(uint16_t ms);")
    w("#define delay_us(us)  pdk_delay_loop((uint16_t)(((uint32_t)(us) * (F_CPU / 1000UL)) / 8000UL + 1))"
      "   /* use a constant */")
    w("")
    w("#endif")
    return "\n".join(L) + "\n"


def generate_init_c(ctx: Context, plan) -> str:
    p, chip = ctx.p, ctx.chip
    sysd = p.data["system"]
    L = []
    w = L.append
    w(f"/* pdk_init.c: start-up code for {p.name} ({chip.name}).")
    w(" * Generated by Padauk Studio: don't edit, it's rewritten when you press Generate.")
    w(" * Put your own code in main.c (or in other .c files in the project folder). */")
    w('#include "pdk_init.h"')
    w("")
    # --- startup -----------------------------------------------------------------
    clk = ctx.clk
    clkmd = [clk.clkmd, "CLKMD_ILRC_EN"]
    ihrc_needed = clk.source == "IHRC" or "IHRC" in ctx.sources
    if ihrc_needed:
        clkmd.append("CLKMD_IHRC_EN")
    if sysd.get("watchdog", "off") != "off":
        clkmd.append("CLKMD_WDT_EN")
    if p.pins_with("reset"):
        clkmd.append("CLKMD_PRSTB")
    w("/* Runs before main() and before variables are set up. */")
    w("#if defined(__SDCC_REVISION) && __SDCC_REVISION < 13762")
    w("unsigned char _sdcc_external_startup(void)")
    w("#else")
    w("unsigned char __sdcc_external_startup(void)")
    w("#endif")
    w("{")
    w("  CLKMD |= CLKMD_IHRC_EN;     /* datasheet 5.4.6: start the new oscillator before switching */")
    w(f"  CLKMD = (uint8_t)({' | '.join(clkmd)});   /* {clk.label} */")
    if clk.source == "IHRC":
        w(f"  PDK_CALIBRATE_IHRC({ctx.f_cpu}, {ctx.vdd});   /* easypdkprog tunes the IHRC here when writing */")
    else:
        if any(r.name == "ILRCR" for r in chip.registers):
            w(f"  PDK_CALIBRATE_ILRC({ctx.f_cpu}, {ctx.vdd});   /* easypdkprog tunes the ILRC here when writing */")
        if ihrc_needed and chip.factory_ihrcr is not None:
            w("  IHRCR = FACTORY_IHRCR();    /* IHRC for the timers: factory trim */")
    fuse = []
    for opt in ("security", "drive", "bootup"):
        if opt in chip.fuse_bits:
            fuse.append(f"FUSE_{opt.upper()}_{sysd.get(opt, chip.fuse_defaults.get(opt)).upper()}")
    if chip.lvr_in == "fuse":
        lvr = lvr_choice(p)
        fuse.append(f"FUSE_LVR_{(lvr or ('2V0', 0))[0]}")
    w(f"  PDK_FUSE({' | '.join(fuse)});")
    w("  return 0;                   /* 0: let SDCC initialise the variables */")
    w("}")
    w("")
    # --- delays ------------------------------------------------------------------
    w("void pdk_delay_loop(uint16_t loops)")
    w("{")
    w("  loops;   /* used by the assembler code below */")
    w("__asm")
    w("00001$:")
    w("  nop")
    w("  dec  _pdk_delay_loop_PARM_1+0")
    w("  subc _pdk_delay_loop_PARM_1+1")
    w("  mov  a, _pdk_delay_loop_PARM_1+0")
    w("  or   a, _pdk_delay_loop_PARM_1+1")
    w("  t1sn.io f, z")
    w("  goto 00001$")
    w("__endasm;")
    w("}")
    w("")
    # 8 cycles per loop plus 14 cycles of call and loop overhead per ms (measured in ucsim)
    loops = max(1, round((ctx.f_cpu / 1000 - 14) / 8))
    w("void delay_ms(uint16_t ms)")
    w("{")
    w("  while (ms--)")
    note = "" if ctx.f_cpu >= 50_000 else " (clock too slow for exact ms: longer)"
    w(f"    pdk_delay_loop({loops});   /* 1 ms at {timing.fmt_hz(ctx.f_cpu)}{note} */")
    w("}")
    w("")
    # --- serial ------------------------------------------------------------------
    if p.serial_enabled():
        t = p.data["serial"].get("timer", "TM2")
        w("/* ---- Serial TX on PA7, bit-banged from the timer interrupt ---- */")
        w("static volatile uint16_t serial_bits;")
        w("")
        w("void pdk_serial_isr(void)")
        w("{")
        w("  if (!serial_bits)")
        w("    return;")
        w("  if (serial_bits & 1)")
        w("    PA |= (1 << 7);")
        w("  else")
        w("    PA &= (uint8_t)~(1 << 7);")
        w("  serial_bits >>= 1;")
        w("  if (!serial_bits)")
        w(f"    INTEN &= (uint8_t)~INTEN_{t};     /* sent: no more interrupts until the next character */")
        w("}")
        w("")
        w("void serial_putc(char c)")
        w("{")
        w("  while (serial_bits)")
        w("    ;")
        w("  serial_bits = ((uint16_t)(uint8_t)c << 1) | 0x200;   /* start bit, 8 data bits, stop bit */")
        w(f"  INTRQ &= (uint8_t)~INTRQ_{t};       /* the start bit begins at the next timer period */")
        w(f"  INTEN |= INTEN_{t};")
        w("}")
        w("")
        w("void serial_print(const char *s)")
        w("{")
        w("  while (*s)")
        w("    serial_putc(*s++);")
        w("}")
        w("")
        w("void serial_println(const char *s)")
        w("{")
        w("  serial_print(s);")
        w("  serial_putc('\\r');")
        w("  serial_putc('\\n');")
        w("}")
        w("")
        w("void serial_print_uint(uint16_t value)")
        w("{")
        w("  static const uint16_t tens[] = {10000, 1000, 100, 10};")
        w("  uint8_t i, started = 0;")
        w("  for (i = 0; i < 4; i++) {")
        w("    char d = '0';")
        w("    while (value >= tens[i]) {")
        w("      value -= tens[i];")
        w("      d++;")
        w("    }")
        w("    if (d != '0' || started) {")
        w("      serial_putc(d);")
        w("      started = 1;")
        w("    }")
        w("  }")
        w("  serial_putc('0' + (uint8_t)value);")
        w("}")
        w("")
        w("void serial_print_hex(uint8_t value)")
        w("{")
        w("  uint8_t n = value >> 4;")
        w("  serial_putc(n < 10 ? '0' + n : 'A' - 10 + n);")
        w("  n = value & 0x0f;")
        w("  serial_putc(n < 10 ? '0' + n : 'A' - 10 + n);")
        w("}")
        w("")
    # --- millis --------------------------------------------------------------------
    if p.timer("T16").get("mode") == "millis" and "T16" in plan:
        s = plan["T16"]
        tick_us = round(1_000_000 / s.actual_hz)
        w(f"/* ---- millis: Timer16 interrupt every {tick_us} us ---- */")
        w("static volatile uint32_t millis_count;")
        w("static volatile uint16_t millis_frac;")
        w("")
        w("void pdk_millis_tick(void)")
        w("{")
        w(f"  millis_frac += {tick_us};")
        w("  while (millis_frac >= 1000) {")
        w("    millis_frac -= 1000;")
        w("    millis_count++;")
        w("  }")
        w("}")
        w("")
        w("uint32_t millis(void)")
        w("{")
        w("  uint32_t now;")
        w("  INTEN &= (uint8_t)~INTEN_T16;   /* a 32-bit read isn't atomic */")
        w("  now = millis_count;")
        w("  INTEN |= INTEN_T16;")
        w("  return now;")
        w("}")
        w("")
    # --- adc ---------------------------------------------------------------------
    if p.data["adc"].get("enabled") and chip.adc:
        w("/* ---- ADC (datasheet 5.13) ---- */")
        w("uint16_t adc_read(uint8_t channel)")
        w("{")
        w("  ADCC = (uint8_t)(ADCC_EN | channel);")
        w("  ADCC = (uint8_t)(ADCC_EN | ADCC_START | channel);")
        w("  while (!(ADCC & ADCC_START))      /* reads 1 when the conversion is done */")
        w("    ;")
        w("  return (((uint16_t)ADCRH << 8) | ADCRL) >> 4;")
        w("}")
        w("")
        w("uint16_t vdd_read_mv(void)")
        w("{")
        w("  uint16_t bg = adc_read(ADCC_CH_BANDGAP);   /* 1.2 V as a fraction of VDD */")
        w("  if (!bg)")
        w("    return 0;")
        w(f"  return (uint16_t)({chip.adc['bandgap_mv']}UL * 4096UL / bg);")
        w("}")
        w("")
    # --- PWMG duty functions -------------------------------------------------------
    for pin, cfg in p.pins.items():
        if cfg.get("fn") == "pwm" and cfg.get("periph", "").startswith("PWMG") and cfg["periph"] in plan:
            per = cfg["periph"]
            lab = ctx.label(pin)
            w(f"void {lab}_set_duty(uint16_t value)")
            w("{")
            w(f"  {per}DTL = (uint8_t)(value << 5);   /* datasheet: write the low byte first */")
            w(f"  {per}DTH = (uint8_t)(value >> 3);")
            w("}")
            w("")
    # --- pdk_init ------------------------------------------------------------------
    w("void pdk_init(void)")
    w("{")
    # system
    misc = []
    if sysd.get("fast_wakeup"):
        misc.append("MISC_FAST_WAKEUP")
    lvr = lvr_choice(p)
    if lvr is None:
        misc.append("MISC_LVR_DISABLE")
    wd = sysd.get("watchdog", "off")
    if wd != "off":
        misc.append(f"MISC_WDT_{wd}")
    w(f"  MISC = (uint8_t)({' | '.join(misc) if misc else '0'});")
    if chip.lvr_in == "register" and lvr is not None:
        extra = " | MISCLVR_BANDGAP_ON" if chip.name == "PFS122" else ""
        w(f"  MISCLVR = (uint8_t)(MISCLVR_LVR_{lvr[0]}{extra});   /* low-voltage reset at {lvr[1] / 1000:g} V */")
    # code option registers
    comp = p.data["comparator"]
    edge_key = {"both": "BOTH", "rise": "RISE", "fall": "FALL"}
    comp_edge = edge_key.get(comp.get("irq", "off"), "BOTH")
    if chip.comparator["edge"][0] == "MISC2":
        w(f"  MISC2 = (uint8_t)(MISC2_COMP_EDGE_{comp_edge});")
    if chip.name == "PFS122":
        rop = []
        for pin in p.pins_with("interrupt"):
            r = chip.interrupts[pin].get("rop")
            if r:
                rop.append(r)
        w(f"  ROP = (uint8_t)({' | '.join(rop) if rop else '0'});   /* interrupt pins (code options Interrupt Src0/Src1) */")
    w("")
    # ports
    pv = port_values(ctx)
    for port, v in pv.items():
        P = "P" + port
        w(f"  /* Port {port}: " + "; ".join(f"{n} {d}" for n, d in v['who'].items() if p.fn(n) != 'unused' or True) + " */")
        w(f"  {P} = {hx(v['data'])};")
        w(f"  {P}C = {hx(v['dir'])};      /* 1 = output (bits {bitlist(v['dir'])}) */")
        w(f"  {P}PH = {hx(v['ph'])};     /* pull-up (bits {bitlist(v['ph'])}) */")
        if chip.has_pull_down:
            w(f"  {P}PL = {hx(v['pl'])};     /* pull-down (bits {bitlist(v['pl'])}) */")
        w(f"  {P}DIER = {hx(v['dier'])};   /* digital input on (bits {bitlist(v['dier'])}) */")
    w("")
    if ctx.chip.factory_bgtr is not None and (comp.get("enabled") or p.data["adc"].get("enabled")):
        w("  BGTR = FACTORY_BGTR();   /* bandgap: factory trim */")
    # Registers aren't reliably reset at power-up (free-pdk): switch off what isn't used
    off = []
    for name in chip.timers:
        if name not in plan:
            off.append("T16M = 0;" if name == "T16" else f"{name}C = 0;")
    if not comp.get("enabled"):
        off += ["GPCC = 0;", "GPCS = 0;"]
    if chip.adc and not p.data["adc"].get("enabled"):
        off.append("ADCC = 0;")
    if "EOSCR" in chip.reg_by_name:
        off.append("EOSCR = 0;")
    w("  " + " ".join(off) + "   /* unused: off */")
    # timers
    for name in chip.timers:
        if name not in plan:
            continue
        s = plan[name]
        mode = p.timer(name)["mode"]
        cfg = p.timer(name)
        w(f"  /* {name}: {mode}, {describe_timer(name, s, mode)} */")
        if name == "T16":
            w(f"  T16M = (uint8_t)(T16M_CLK_{s.source if s.source != 'SYSCLK' else 'SYSCLK'} | T16M_PRE_{s.pre} | T16M_INTSRC_BIT{s.bound});")
            w("  T16C = 0;")
        elif name.startswith("TM"):
            if mode == "pwm":
                pin = next((pp for pp, c in p.pins.items() if c.get("fn") == "pwm" and c.get("periph") == name), None)
                steps = 256 if s.res == 8 else 64
                k = min(steps - 1, max(0, round(float(cfg.get("duty", 50)) / 100 * steps) - 1))
                out = chip.pwm_outputs[name][pin]
                w(f"  {name}CT = 0;")
                w(f"  {name}B = {k};          /* duty ({k} + 1) / {steps} = {(k + 1) * 100 / steps:.1f} % */")
                w(f"  {name}S = (uint8_t)({'' if s.res == 8 else f'{name}S_PWM6 | '}{name}S_PRE_{s.pre} | {s.scale});")
                w(f"  {name}C = (uint8_t)({name}C_CLK_{s.source} | {out} | {name}C_PWM);")
            else:
                w(f"  {name}CT = 0;")
                w(f"  {name}B = {s.bound};")
                w(f"  {name}S = (uint8_t)({name}S_PRE_{s.pre} | {s.scale});")
                w(f"  {name}C = (uint8_t)({name}C_CLK_{s.source});   /* period mode, no output pin */")
        else:
            pin = next((pp for pp, c in p.pins.items() if c.get("fn") == "pwm" and c.get("periph") == name), None)
            b = s.bound
            d = min(2 * b + 1, max(0, round(float(cfg.get("duty", 50)) / 100 * 2 * (b + 1)) - 1))
            out = chip.pwm_outputs[name][pin]
            w(f"  {name}CUBH = {b >> 2};       /* counter bound {b} */")
            w(f"  {name}CUBL = {(b & 3) << 6};")
            w(f"  {name}DTL = {(d & 7) << 5};        /* duty {d}: ({d} + 1) / {2 * (b + 1)} = {(d + 1) * 100 / (2 * (b + 1)):.1f} %, low byte first */")
            w(f"  {name}DTH = {d >> 3};")
            w(f"  {name}S = (uint8_t)({name}S_PRE_{s.pre} | {s.scale});")
            w(f"  {name}C = (uint8_t)({name}C_EN | {out} | {name}C_CLK_{s.source});")
    # comparator
    if comp.get("enabled"):
        hi, lo, _ = VINTR_RANGES[comp.get("range", "R1")]
        level = int(comp.get("level", 8))
        vref = comparator_vintr(comp.get("range", "R1"), level, ctx.vdd / 1000)
        gpcs = []
        if p.pins_with("comp_out"):
            gpcs.append("GPCS_OUT_PA0")
        if comp.get("wakeup") and chip.comparator.get("wakeup"):
            gpcs.append("GPCS_WAKEUP")
        if hi:
            gpcs.append("GPCS_HIGH")
        if lo:
            gpcs.append("GPCS_LOW")
        gpcs.append(str(level))
        plus = comp.get("plus", "VINTR")
        minus = comp.get("minus", "BANDGAP")
        gpcc = ["GPCC_EN", chip.comparator["minus"][minus], chip.comparator["plus"][plus]]
        if comp.get("invert"):
            gpcc.append("GPCC_INVERT")
        w(f"  /* Comparator: {plus} vs {minus}; internal reference {vref:.3f} V at VDD {ctx.vdd / 1000:g} V */")
        w(f"  GPCS = (uint8_t)({' | '.join(gpcs)});")
        w(f"  GPCC = (uint8_t)({' | '.join(gpcc)});")
    # adc
    if p.data["adc"].get("enabled") and chip.adc:
        target = chip.adc["clock_target_hz"]
        div = 1
        while div < 128 and ctx.f_cpu / div > target:
            div *= 2
        w(f"  ADCM = (uint8_t)(ADCM_CLK_DIV{div});   /* ADC clock {timing.fmt_hz(ctx.f_cpu / div)} (datasheet: about 500 kHz) */")
        w("  ADCC = (uint8_t)(ADCC_EN);")
    # interrupts
    srcs = interrupt_sources(ctx, plan)
    integs = []
    for pin in p.pins_with("interrupt"):
        irq = chip.interrupts.get(pin)
        if irq:
            integs.append(f"{irq['edge']}_{edge_key.get(p.pins[pin].get('edge', 'fall'), 'FALL')}")
    if chip.comparator["edge"][0] == "INTEGS" and comp.get("enabled") and comp.get("irq", "off") != "off":
        integs.append(f"INTEGS_COMP_{comp_edge}")
    w(f"  INTEGS = {'(uint8_t)(' + ' | '.join(integs) + ')' if integs else '0'};   /* interrupt edges */")
    enabled = [s["inten"] for s in srcs if not s.get("no_user")]   # serial turns its own on
    if srcs:
        w("")
        w("  INTRQ = 0;")
        w(f"  INTEN = (uint8_t)({' | '.join(dict.fromkeys(enabled)) or '0'});")
        w("  interrupts_on();")
    else:
        w("  INTEN = 0;")
    if p.serial_enabled():
        w("")
        w("  serial_putc(0x55);   /* sync character: lets the programmer measure the baud rate */")
    w("}")
    return "\n".join(L) + "\n"


def generate(project: Project, old_main: str = "") -> Dict[str, str]:
    """All generated files: {filename: text}."""
    ctx = Context(project)
    plan = timer_plan(project)
    return {
        header_name(project.chip): generate_header(project.chip),
        "pdk_init.h": generate_init_h(ctx, plan),
        "pdk_init.c": generate_init_c(ctx, plan),
        "main.c": generate_main(ctx, plan, old_main),
    }


def write_project(project: Project, folder: Optional[str] = None) -> List[str]:
    """Generate into the project folder. Returns the files written."""
    folder = folder or project.path
    os.makedirs(folder, exist_ok=True)
    main_path = os.path.join(folder, "main.c")
    old = ""
    if os.path.exists(main_path):
        with open(main_path, encoding="utf-8") as f:
            old = f.read()
    files = generate(project, old)
    # remove a header from another chip (the chip was changed)
    from . import chips
    for other in chips.names():
        hn = other.lower() + ".h"
        if hn not in files and os.path.exists(os.path.join(folder, hn)):
            os.remove(os.path.join(folder, hn))
    written = []
    for name, text in files.items():
        path = os.path.join(folder, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                if f.read() == text:
                    continue
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        written.append(name)
    if write_vscode_config(project, folder):
        written.append(".vscode/c_cpp_properties.json")
    project.save(folder)
    return written


def write_vscode_config(project: Project, folder: str) -> bool:
    """IntelliSense settings for VS Code, so SDCC's keywords don't show as errors.
    Kept up to date while it's ours; if you edit it (rename the configuration), it's left alone."""
    import json
    path = os.path.join(folder, ".vscode", "c_cpp_properties.json")
    arch = project.chip.arch
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                old = json.load(f)
            name = old["configurations"][0]["name"]
        except (OSError, ValueError, KeyError, IndexError):
            return False
        if not name.startswith("SDCC ") or name == "SDCC " + arch:
            return False
    cfg = {"configurations": [{
        "name": "SDCC " + arch,
        "includePath": ["${workspaceFolder}/**"],
        "defines": [f"__SDCC_{arch}", "__SDCC", "__sfr=volatile unsigned char",
                    "__sfr16=volatile unsigned short", "__at(x)=", "__interrupt(x)=", "__asm__(x)=",
                    "__asm=", "__endasm="],
        "compilerPath": "",
        "cStandard": "c11",
        "intelliSenseMode": "gcc-x86",
    }], "version": 4}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    return True
