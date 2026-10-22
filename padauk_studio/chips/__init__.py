"""Chip database.

One module per chip (pms150c, pfs154, pfs122), written from the Padauk
datasheets. Everything else (the pin view, the code generator, the checks
and the generated register header) reads from here, so a chip fact lives in
exactly one place.

Registers that are not in a datasheet (oscillator trim, code-option
registers) are marked with ``source="free-pdk"`` and explained in their doc.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Field:
    """A bit field inside a register.

    1-bit fields become a mask macro ``REG_NAME``.  Wider fields get
    ``REG_NAME_POS`` / ``REG_NAME_MASK`` and one macro per entry in
    ``values``: ``REG_NAME_VALUENAME = (value << pos)``.
    """
    name: str
    pos: int
    width: int = 1
    values: Dict[str, int] = field(default_factory=dict)
    doc: str = ""


@dataclass
class Register:
    name: str
    addr: int
    doc: str
    section: str = ""            # datasheet section, e.g. "6.3"
    access: str = "rw"           # rw, wo (write only), ro
    fields: List[Field] = field(default_factory=list)
    consts: Dict[str, int] = field(default_factory=dict)  # extra named values (already shifted)
    source: str = "datasheet"    # or "free-pdk" for undocumented registers


@dataclass
class Package:
    key: str                     # short name used in project files, e.g. "S16"
    label: str                   # shown in the UI
    pins: List[str]              # pin 1..n
    quad: bool = False           # QFN: drawn with pins on 4 sides
    note: str = ""


@dataclass
class PinInfo:
    name: str                    # "PA4"
    port: str                    # "A"
    bit: int
    functions: List[str]         # function ids this pin can take (see FUNCTIONS)
    notes: str = ""              # shown in the side panel (datasheet pin description)
    open_drain_only: bool = False


@dataclass
class ClockOption:
    key: str                     # e.g. "IHRC_DIV2"
    label: str                   # "8 MHz (IHRC/2)"
    freq: int                    # Hz (nominal)
    source: str                  # "IHRC" or "ILRC"
    clkmd: str                   # macro name of the CLKMD value in the generated header
    min_vdd_mv: int              # datasheet minimum VDD for this clock
    undocumented: bool = False


@dataclass
class Chip:
    name: str
    arch: str                    # sdcc -m option: pdk13 / pdk14
    rom_words: int
    ram_bytes: int
    otp: bool
    datasheet: str
    registers: List[Register]
    pins: Dict[str, PinInfo]
    packages: List[Package]
    clocks: List[ClockOption]
    ilrc_hz: int
    vdd_range_mv: Tuple[int, int]
    fuse_addr: int
    fuse_reserved: int           # bits that must be 1 in the fuse word
    fuse_bits: Dict[str, Dict[str, int]]   # option -> {choice: bits}
    fuse_defaults: Dict[str, str]
    lvr_levels: List[Tuple[str, int]]      # [(key, millivolt)] in datasheet order
    lvr_in: str                  # "fuse" or "register"
    timers: List[str]            # ["T16", "TM2", ...]
    pwm_outputs: Dict[str, Dict[str, str]]  # periph -> {pin: macro of the output select value}
    comparator: dict
    adc: Optional[dict]
    interrupts: Dict[str, dict]  # "PA0": {"inten": "INTEN_PA0", ...}
    has_pull_down: bool
    reserved_rom: Tuple[int, int]  # first, last reserved word at the end of ROM
    factory_ihrcr: Optional[int]
    factory_bgtr: Optional[int]
    notes: List[str]
    programming_note: str = ""
    extra_header: str = ""       # extra C text appended to the generated header

    @property
    def reg_by_name(self) -> Dict[str, Register]:
        return {r.name: r for r in self.registers}

    def package(self, key: str) -> Package:
        for p in self.packages:
            if p.key == key:
                return p
        return self.packages[-1]

    def clock(self, key: str) -> ClockOption:
        for c in self.clocks:
            if c.key == key:
                return c
        raise KeyError(key)

    def io_pins(self, package_key: Optional[str] = None) -> List[str]:
        """Port pins (in PA0..PB7 order) available on a package (or on the die)."""
        names = list(self.pins)
        if package_key:
            on_pkg = set(self.package(package_key).pins)
            names = [n for n in names if n in on_pkg]
        return names


# Pin functions. The id is stored in project files; the label is what the UI shows.
FUNCTIONS = {
    "unused":     "Unused",
    "output":     "GPIO output",
    "input":      "GPIO input",
    "interrupt":  "External interrupt",
    "pwm":        "PWM output",
    "comp_minus": "Comparator - input",
    "comp_plus":  "Comparator + input",
    "comp_out":   "Comparator output",
    "adc":        "ADC input",
    "serial_tx":  "Serial TX (debug print)",
    "reset":      "Reset input (PRSTB)",
}


def bit_field(name, pos, doc=""):
    return Field(name, pos, 1, {}, doc)


def enum_field(name, pos, width, values, doc=""):
    return Field(name, pos, width, dict(values), doc)


def port_regs(port, base_addrs, sections, pull_down=None, extra_doc=""):
    """Data / control / pull-high (/ pull-low) registers of a port."""
    p = port.upper()
    regs = [
        Register(f"P{p}", base_addrs[0], f"Port {p} data", sections[0]),
        Register(f"P{p}C", base_addrs[1], f"Port {p} direction, 1 = output", sections[1]),
        Register(f"P{p}PH", base_addrs[2], f"Port {p} pull-high enable" + extra_doc, sections[2]),
    ]
    if pull_down:
        regs.append(Register(f"P{p}PL", pull_down[0], f"Port {p} pull-low enable", pull_down[1]))
    return regs


def clkmd_register(addr, has_eosc):
    """CLKMD is the same on all three chips (EOSC modes only where present)."""
    sysclk = {
        # value of bits 7..5 plus bit 3 (clock type), already shifted
        "CLKMD_SYSCLK_IHRC_DIV4": (0 << 5),
        "CLKMD_SYSCLK_IHRC_DIV2": (1 << 5),
        "CLKMD_SYSCLK_IHRC": (2 << 5),           # 16 MHz, reserved in the datasheet (undocumented)
        "CLKMD_SYSCLK_ILRC_DIV4": (6 << 5),
        "CLKMD_SYSCLK_ILRC": (7 << 5),
        "CLKMD_SYSCLK_IHRC_DIV16": (0 << 5) | 8,
        "CLKMD_SYSCLK_IHRC_DIV8": (1 << 5) | 8,
        "CLKMD_SYSCLK_ILRC_DIV16": (2 << 5) | 8,
        "CLKMD_SYSCLK_IHRC_DIV32": (3 << 5) | 8,
        "CLKMD_SYSCLK_IHRC_DIV64": (4 << 5) | 8,
    }
    if has_eosc:
        sysclk.update({
            "CLKMD_SYSCLK_EOSC_DIV4": (3 << 5),
            "CLKMD_SYSCLK_EOSC_DIV2": (4 << 5),
            "CLKMD_SYSCLK_EOSC": (5 << 5),
            "CLKMD_SYSCLK_EOSC_DIV8": (5 << 5) | 8,
        })
    return Register(
        "CLKMD", addr, "Clock mode", "6.3", fields=[
            Field("SYSCLK", 5, 3, {}, "system clock select, see CLKMD_SYSCLK_*"),
            bit_field("IHRC_EN", 4, "IHRC oscillator enable"),
            bit_field("TYPE1", 3, "clock type 1 (selects the second SYSCLK table)"),
            bit_field("ILRC_EN", 2, "ILRC enable (also needed by the watchdog)"),
            bit_field("WDT_EN", 1, "watchdog enable"),
            bit_field("PRSTB", 0, "PA5 is the reset pin PRSTB"),
        ], consts=sysclk)


def std_clocks(min_vdd, ilrc_hz):
    """IHRC is 16 MHz; min_vdd maps MHz -> mV from the datasheet operating table."""
    def need(f):
        for mhz, mv in sorted(min_vdd.items()):
            if f <= mhz * 1_000_000:
                return mv
        return 4500
    out = []
    for key, div, label in [
        ("IHRC", 1, "16 MHz (IHRC, undocumented)"),
        ("IHRC_DIV2", 2, "8 MHz (IHRC/2)"),
        ("IHRC_DIV4", 4, "4 MHz (IHRC/4)"),
        ("IHRC_DIV8", 8, "2 MHz (IHRC/8)"),
        ("IHRC_DIV16", 16, "1 MHz (IHRC/16)"),
        ("IHRC_DIV32", 32, "500 kHz (IHRC/32)"),
        ("IHRC_DIV64", 64, "250 kHz (IHRC/64)"),
    ]:
        f = 16_000_000 // div
        out.append(ClockOption(key, label, f, "IHRC", f"CLKMD_SYSCLK_{key}",
                               need(f) if div > 1 else 4500, undocumented=(div == 1)))
    for key, div in [("ILRC", 1), ("ILRC_DIV4", 4), ("ILRC_DIV16", 16)]:
        f = ilrc_hz // div
        khz = f / 1000
        label = f"~{khz:g} kHz (ILRC" + (f"/{div}" if div > 1 else "") + ", low power)"
        out.append(ClockOption(key, label, f, "ILRC", f"CLKMD_SYSCLK_{key}", need(f)))
    return out


T16_CLK = {"OFF": 0, "SYSCLK": 1, "PA4_FALL": 3, "IHRC": 4, "EOSC": 5, "ILRC": 6, "PA0_FALL": 7}
DIV4 = {"DIV1": 0, "DIV4": 1, "DIV16": 2, "DIV64": 3}


def t16m_register(addr, has_eosc):
    clk = dict(T16_CLK)
    if not has_eosc:
        clk.pop("EOSC")
    return Register("T16M", addr, "Timer16 mode", "6.6", fields=[
        enum_field("CLK", 5, 3, clk, "clock source"),
        enum_field("PRE", 3, 2, DIV4, "clock divider"),
        enum_field("INTSRC", 0, 3, {f"BIT{8 + i}": i for i in range(8)},
                   "interrupt when this counter bit changes (edge from INTEGS)"),
    ])


def timer8_registers(n, addrs, sections, clocks, outputs, six_bit_doc="6-bit"):
    """TM2 / TM3: control, counter, scalar, bound."""
    c, ct, s, b = addrs
    return [
        Register(f"TM{n}C", c, f"Timer{n} control", sections[0], fields=[
            enum_field("CLK", 4, 4, clocks, "clock source"),
            enum_field("OUT", 2, 2, outputs, "output pin"),
            bit_field("PWM", 1, "1 = PWM mode, 0 = period mode"),
            bit_field("INVERT", 0, "invert the output"),
        ]),
        Register(f"TM{n}CT", ct, f"Timer{n} counter", sections[1]),
        Register(f"TM{n}S", s, f"Timer{n} scalar", sections[2], "wo", fields=[
            bit_field("PWM6", 7, f"PWM resolution: 0 = 8-bit, 1 = {six_bit_doc}"),
            enum_field("PRE", 5, 2, DIV4, "prescaler"),
            Field("SCALE", 0, 5, {}, "clock divided by (SCALE + 1)"),
        ]),
        Register(f"TM{n}B", b, f"Timer{n} bound (period mode: top, PWM mode: duty)", sections[3], "wo"),
    ]


def comparator_registers(gpcc_addr, gpcs_addr, sections, minus_inputs, gpcs_bit6):
    gpcs_fields = [
        bit_field("OUT_PA0", 7, "comparator output on PA0"),
        bit_field("HIGH", 5, "high range of the internal reference"),
        bit_field("LOW", 4, "low range of the internal reference"),
        Field("LEVEL", 0, 4, {}, "internal reference level 0..15"),
    ]
    if gpcs_bit6:
        gpcs_fields.insert(1, bit_field("WAKEUP", 6, "wake up by comparator"))
    return [
        Register("GPCC", gpcc_addr, "Comparator control", sections[0], fields=[
            bit_field("EN", 7, "enable"),
            bit_field("RESULT", 6, "result (read only): 1 = plus > minus"),
            bit_field("TM2_SAMPLE", 5, "result sampled by TM2_CLK"),
            bit_field("INVERT", 4, "invert the result"),
            enum_field("MINUS", 1, 3, minus_inputs, "minus input"),
            enum_field("PLUS", 0, 1, {"VINTR": 0, "PA4": 1}, "plus input"),
        ]),
        Register("GPCS", gpcs_addr, "Comparator selection (internal reference)", sections[1], "wo",
                 fields=gpcs_fields),
    ]


def edge_values():
    return {"BOTH": 0, "RISE": 1, "FALL": 2}


def comparator_vintr(range_key, level, vdd):
    """Internal reference voltage (datasheet 5.x comparator chapter, same on all three)."""
    n = level
    if range_key == "R1":      # GPCS HIGH=0 LOW=0
        return vdd * (1 / 4 + (n + 1) / 32)
    if range_key == "R2":      # HIGH=0 LOW=1
        return vdd * (n + 1) / 24
    if range_key == "R3":      # HIGH=1 LOW=0
        return vdd * (1 / 5 + (n + 1) / 40)
    return vdd * (n + 1) / 32  # R4: HIGH=1 LOW=1


VINTR_RANGES = {
    # key: (HIGH bit, LOW bit, label)
    "R1": (0, 0, "VDD/4 + (n+1)*VDD/32"),
    "R2": (0, 1, "(n+1)*VDD/24"),
    "R3": (1, 0, "VDD/5 + (n+1)*VDD/40"),
    "R4": (1, 1, "(n+1)*VDD/32"),
}


def _load():
    from . import pms150c, pfs154, pfs122
    return {c.CHIP.name: c.CHIP for c in (pfs154, pfs122, pms150c)}


CHIPS: Dict[str, Chip] = {}


def get(name: str) -> Chip:
    if not CHIPS:
        CHIPS.update(_load())
    return CHIPS[name.upper()]


def names() -> List[str]:
    if not CHIPS:
        CHIPS.update(_load())
    return list(CHIPS)
