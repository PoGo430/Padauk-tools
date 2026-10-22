"""The chip database against the datasheets.

The tables below were typed again from the datasheets' register chapters
(chapter 6 "IO Registers"), separately from padauk_studio/chips, so a typo in
one place shows up here.
"""
import re

import pytest

from padauk_studio import chips
from padauk_studio.gen_header import generate_header

DATASHEET_ADDR = {
    "PMS150C": {  # PMS150C datasheet V004, 6.1 - 6.19
        "FLAG": 0x00, "SP": 0x02, "CLKMD": 0x03, "INTEN": 0x04, "INTRQ": 0x05, "T16M": 0x06,
        "EOSCR": 0x0A, "INTEGS": 0x0C, "PADIER": 0x0D, "PA": 0x10, "PAC": 0x11, "PAPH": 0x12,
        "MISC": 0x1B, "GPCC": 0x1A, "GPCS": 0x1E, "TM2C": 0x1C, "TM2CT": 0x1D, "TM2B": 0x09, "TM2S": 0x17,
    },
    "PFS154": {  # PFS154 datasheet V107, 6.1 - 6.45
        "FLAG": 0x00, "SP": 0x02, "CLKMD": 0x03, "INTEN": 0x04, "INTRQ": 0x05, "T16M": 0x06,
        "EOSCR": 0x0A, "INTEGS": 0x0C, "PADIER": 0x0D, "PBDIER": 0x0E, "PA": 0x10, "PAC": 0x11,
        "PAPH": 0x12, "PB": 0x14, "PBC": 0x15, "PBPH": 0x16, "MISC": 0x08, "TM2C": 0x1C, "TM2CT": 0x1D,
        "TM2S": 0x17, "TM2B": 0x09, "TM3C": 0x32, "TM3CT": 0x33, "TM3S": 0x34, "TM3B": 0x35,
        "GPCC": 0x18, "GPCS": 0x19,
        "PWMG0C": 0x20, "PWMG0S": 0x21, "PWMG0CUBH": 0x24, "PWMG0CUBL": 0x25, "PWMG0DTH": 0x22, "PWMG0DTL": 0x23,
        "PWMG1C": 0x26, "PWMG1S": 0x27, "PWMG1CUBH": 0x2A, "PWMG1CUBL": 0x2B, "PWMG1DTH": 0x28, "PWMG1DTL": 0x29,
        "PWMG2C": 0x2C, "PWMG2S": 0x2D, "PWMG2CUBH": 0x30, "PWMG2CUBL": 0x31, "PWMG2DTH": 0x2E, "PWMG2DTL": 0x2F,
    },
    "PFS122": {  # PFS122 datasheet V004 (= V002), 6.1 - 6.33
        "FLAG": 0x00, "SP": 0x02, "CLKMD": 0x03, "INTEN": 0x04, "INTRQ": 0x05, "T16M": 0x06,
        "EOSCR": 0x0A, "INTEGS": 0x0C, "PADIER": 0x0D, "PBDIER": 0x0E, "PA": 0x10, "PAC": 0x11,
        "PAPH": 0x12, "PAPL": 0x13, "PB": 0x15, "PBC": 0x16, "PBPH": 0x17, "PBPL": 0x18,
        "ADCC": 0x20, "ADCM": 0x21, "ADCRH": 0x22, "ADCRL": 0x23, "MISC": 0x26, "GPCC": 0x2B, "GPCS": 0x2C,
        "TM2C": 0x30, "TM2CT": 0x31, "TM2S": 0x32, "TM2B": 0x33, "TM3C": 0x34, "TM3CT": 0x35, "TM3S": 0x36,
        "TM3B": 0x37,
    },
}

# (register, field, value name) -> shifted value, from the datasheet bit tables
DATASHEET_FIELDS = {
    "PMS150C": {
        ("TM2C", "CLK", "IHRC"): 0x20, ("TM2C", "CLK", "PA4_FALL"): 0xD0, ("TM2C", "OUT", "PA3"): 0x08,
        ("TM2C", "OUT", "PA4"): 0x0C, ("GPCC", "MINUS", "PA6"): 0x08, ("GPCC", "MINUS", "BANDGAP"): 0x04,
        ("T16M", "CLK", "PA0_FALL"): 0xE0, ("MISC", "WDT", "256K"): 0x03, ("INTEGS", "COMP", "FALL"): 0x80,
    },
    "PFS154": {
        ("TM2C", "OUT", "PB2"): 0x04, ("TM2C", "OUT", "PB4"): 0x0C, ("TM3C", "OUT", "PB7"): 0x0C,
        ("TM2C", "CLK", "PB0_FALL"): 0xB0, ("PWMG0C", "OUT", "PA0"): 0x06, ("PWMG0C", "OUT", "PB4"): 0x08,
        ("PWMG1C", "OUT", "PA4"): 0x06, ("PWMG2C", "OUT", "PA5"): 0x0A, ("PWMG2C", "OUT", "PB3"): 0x02,
        ("PWMG0C", "CLK", "IHRC"): 0x01, ("GPCC", "MINUS", "PB7"): 0x0A, ("INTEGS", "PB0", "FALL"): 0x08,
        ("EOSCR", "DRIVE", "HIGH"): 0x60,
    },
    "PFS122": {
        ("ADCC", "CH", "PA0"): 0x28, ("ADCC", "CH", "BANDGAP"): 0x3C, ("ADCC", "CH", "PB7"): 0x1C,
        ("ADCM", "CLK", "DIV16"): 0x08, ("ADCM", "CLK", "DIV128"): 0x0E, ("TM3C", "OUT", "PB5"): 0x04,
        ("TM2C", "OUT", "PA3"): 0x08, ("GPCC", "MINUS", "PB6"): 0x08, ("INTEGS", "INT1", "RISE"): 0x04,
    },
}

# single-bit fields: (register, field) -> bit
DATASHEET_BITS = {
    "PMS150C": {("INTEN", "TM2"): 6, ("INTEN", "COMP"): 4, ("INTEN", "T16"): 2, ("INTEN", "PA0"): 0,
                ("MISC", "LVR_DISABLE"): 2, ("MISC", "FAST_WAKEUP"): 5, ("GPCS", "OUT_PA0"): 7},
    "PFS154": {("INTEN", "TM3"): 7, ("INTEN", "PWMG"): 5, ("INTEN", "PB0"): 1, ("PWMG0C", "EN"): 7,
               ("PWMG0C", "INVERT"): 5, ("MISC", "LCD_BIAS"): 4, ("TM2S", "PWM6"): 7},
    "PFS122": {("INTEN", "ADC"): 3, ("INTEN", "INT1"): 1, ("ADCC", "EN"): 7, ("ADCC", "START"): 6,
               ("GPCS", "WAKEUP"): 6},
}

PACKAGE_PINS = {  # pin count per package, datasheet chapter 2
    "PMS150C": {"S08": 8, "U06": 6},
    "PFS154": {"S16": 16, "QFN16": 16, "S14": 14, "M10": 10, "S08": 8, "U06": 6},
    "PFS122": {"S16": 16, "QFN16": 16, "S14": 14, "M10": 10, "S08": 8, "U06": 6},
}


@pytest.mark.parametrize("name", list(DATASHEET_ADDR))
def test_register_addresses(name):
    chip = chips.get(name)
    regs = chip.reg_by_name
    for reg, addr in DATASHEET_ADDR[name].items():
        assert reg in regs, f"{name}: {reg} missing"
        assert regs[reg].addr == addr, f"{name}: {reg} at {regs[reg].addr:#x}, datasheet {addr:#x}"
        assert regs[reg].source == "datasheet"
    # every other register is marked as not from the datasheet
    for r in chip.registers:
        if r.name not in DATASHEET_ADDR[name]:
            assert r.source == "free-pdk", f"{name}: {r.name} isn't in the datasheet table"
    addrs = [r.addr for r in chip.registers]
    assert len(addrs) == len(set(addrs)), "two registers at one address"


@pytest.mark.parametrize("name", list(DATASHEET_FIELDS))
def test_field_values(name):
    chip = chips.get(name)
    regs = chip.reg_by_name
    for (reg, fld, val), want in DATASHEET_FIELDS[name].items():
        f = next(f for f in regs[reg].fields if f.name == fld)
        assert f.values[val] << f.pos == want, f"{name} {reg}_{fld}_{val}"
    for (reg, fld), bit in DATASHEET_BITS[name].items():
        f = next(f for f in regs[reg].fields if f.name == fld)
        assert (f.pos, f.width) == (bit, 1), f"{name} {reg}_{fld}"


@pytest.mark.parametrize("name", list(PACKAGE_PINS))
def test_packages(name):
    chip = chips.get(name)
    for key, n in PACKAGE_PINS[name].items():
        pk = chip.package(key)
        assert pk.key == key and len(pk.pins) == n
        assert pk.pins.count("VDD") == 1 and pk.pins.count("GND") == 1
        for pin in pk.pins:
            assert pin in ("VDD", "GND") or pin in chip.pins, f"{name} {key}: {pin}"
        assert len(set(pk.pins)) == n


@pytest.mark.parametrize("name", list(PACKAGE_PINS))
def test_macros_used_by_codegen_exist(name):
    """Every macro name the database hands to the code generator is in the header."""
    chip = chips.get(name)
    header = generate_header(chip)
    defined = set(re.findall(r"#define (\w+)", header))
    used = [c.clkmd for c in chip.clocks]
    for outs in chip.pwm_outputs.values():
        used += list(outs.values())
    used += list(chip.comparator["minus"].values()) + list(chip.comparator["plus"].values())
    for irq in chip.interrupts.values():
        used += [irq["inten"], irq["intrq"], irq["edge"] + "_FALL"]
        if irq.get("rop"):
            used.append(irq["rop"])
    if chip.adc:
        used += list(chip.adc["channels"].values())
    for opt, choices in chip.fuse_bits.items():
        used += [f"FUSE_{opt.upper()}_{c.upper()}" for c in choices]
    missing = [m for m in used if m not in defined]
    assert not missing, missing


def test_clock_limits():
    """Datasheet 4.1: minimum VDD for 8 / 4 / 2 MHz."""
    want = {"PMS150C": (3000, 2200, 2000), "PFS154": (3500, 2500, 2000), "PFS122": (3000, 2200, 1800)}
    for name, (v8, v4, v2) in want.items():
        c = chips.get(name)
        assert c.clock("IHRC_DIV2").min_vdd_mv == v8
        assert c.clock("IHRC_DIV4").min_vdd_mv == v4
        assert c.clock("IHRC_DIV8").min_vdd_mv == v2
