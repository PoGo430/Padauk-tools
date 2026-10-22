"""PFS154: flash (MTP), pdk14, 2 KW ROM, 128 B RAM.

Source: PADAUK PFS154 datasheet (PDK-DS-PFS154 V107, 2024-09-12), chapters 2, 4, 5, 6, 8.
Registers marked source="free-pdk" are not in the datasheet; they come from
the free-pdk project (pdk-includes / undocumented-features page).
"""

from . import (Chip, Register, Package, PinInfo, Field, bit_field, enum_field, clkmd_register,
               t16m_register, timer8_registers, comparator_registers, edge_values, std_clocks)

E = edge_values()
TM_CLK = {"OFF": 0, "SYSCLK": 1, "IHRC": 2, "EOSC": 3, "ILRC": 4, "COMP": 5,
          "PA0_RISE": 8, "PA0_FALL": 9, "PB0_RISE": 10, "PB0_FALL": 11, "PA4_RISE": 12, "PA4_FALL": 13}


def pwmg_registers(n, base, sections, outputs):
    """11-bit PWM generator n. Datasheet 6.28-6.45."""
    c, s, dth, dtl, cubh, cubl = base, base + 1, base + 2, base + 3, base + 4, base + 5
    return [
        Register(f"PWMG{n}C", c, f"PWMG{n} control", sections[0], fields=[
            bit_field("EN", 7, "enable"),
            bit_field("STATUS", 6, "output status (read only)"),
            bit_field("INVERT", 5, "invert the output"),
            bit_field("RESET", 4, "write 1 to clear the counter"),
            enum_field("OUT", 1, 3, outputs, "output pin"),
            enum_field("CLK", 0, 1, {"SYSCLK": 0, "IHRC": 1}, "clock source"),
        ]),
        Register(f"PWMG{n}S", s, f"PWMG{n} scalar", sections[1], "wo", fields=[
            bit_field("INT_AT_ZERO", 7, "interrupt when the counter is 0 (else on duty match)"),
            enum_field("PRE", 5, 2, {"DIV1": 0, "DIV4": 1, "DIV16": 2, "DIV64": 3}, "prescaler"),
            Field("SCALE", 0, 5, {}, "clock divided by (SCALE + 1)"),
        ]),
        Register(f"PWMG{n}DTH", dth, f"PWMG{n} duty bits 10..3 (write after DTL)", sections[4], "wo"),
        Register(f"PWMG{n}DTL", dtl, f"PWMG{n} duty bits 2..0 in bits 7..5 (write first)", sections[5], "wo"),
        Register(f"PWMG{n}CUBH", cubh, f"PWMG{n} counter upper bound bits 10..3", sections[2], "wo"),
        Register(f"PWMG{n}CUBL", cubl, f"PWMG{n} counter upper bound bits 2..1 in bits 7..6", sections[3], "wo"),
    ]


REGISTERS = [
    Register("FLAG", 0x00, "ACC status flags", "6.1", fields=[
        bit_field("OV", 3), bit_field("AC", 2), bit_field("C", 1), bit_field("Z", 0)]),
    Register("SP", 0x02, "Stack pointer", "6.2"),
    clkmd_register(0x03, has_eosc=True),
    Register("INTEN", 0x04, "Interrupt enable", "6.4", fields=[
        bit_field("TM3", 7), bit_field("TM2", 6), bit_field("PWMG", 5), bit_field("COMP", 4),
        bit_field("T16", 2), bit_field("PB0", 1), bit_field("PA0", 0)]),
    Register("INTRQ", 0x05, "Interrupt request (write 0 to clear)", "6.5", fields=[
        bit_field("TM3", 7), bit_field("TM2", 6), bit_field("PWMG", 5), bit_field("COMP", 4),
        bit_field("T16", 2), bit_field("PB0", 1), bit_field("PA0", 0)]),
    t16m_register(0x06, has_eosc=True),
    Register("MISC", 0x08, "Misc: wake-up, LCD bias, LVR, watchdog period", "6.17", "wo", fields=[
        bit_field("FAST_WAKEUP", 5, "fast wake-up (45 ILRC clocks)"),
        bit_field("LCD_BIAS", 4, "VDD/2 bias generator for LCD"),
        bit_field("LVR_DISABLE", 2, "disable the low-voltage reset"),
        enum_field("WDT", 0, 2, {"8K": 0, "16K": 1, "64K": 2, "256K": 3}, "watchdog period in ILRC clocks"),
    ]),
    Register("EOSCR", 0x0A, "External crystal oscillator", "6.7", "wo", fields=[
        bit_field("EN", 7, "enable the crystal oscillator"),
        enum_field("DRIVE", 5, 2, {"LOW": 1, "MID": 2, "HIGH": 3}, "32 kHz / 1 MHz / 4 MHz crystals"),
    ]),
    Register("IHRCR", 0x0B, "IHRC trim (written by the calibration code)", source="free-pdk"),
    Register("INTEGS", 0x0C, "Interrupt edge select", "6.8", "wo", fields=[
        enum_field("T16", 4, 1, {"RISE": 0, "FALL": 1}, "Timer16 interrupt edge"),
        enum_field("PB0", 2, 2, E, "PB0 interrupt edge"),
        enum_field("PA0", 0, 2, E, "PA0 interrupt edge"),
    ]),
    Register("PADIER", 0x0D, "Port A digital input enable (bits 7..3, 0)", "6.9", "wo"),
    Register("PBDIER", 0x0E, "Port B digital input enable", "6.10", "wo"),
    Register("MISC2", 0x0F, "Code option: comparator interrupt edge (Comparator_Edge)", source="free-pdk",
             access="wo", fields=[
                 enum_field("COMP_EDGE", 5, 2, E, "comparator interrupt edge"),
             ]),
    Register("PA", 0x10, "Port A data", "6.11"),
    Register("PAC", 0x11, "Port A direction, 1 = output", "6.12"),
    Register("PAPH", 0x12, "Port A pull-high enable", "6.13"),
    Register("PB", 0x14, "Port B data", "6.14"),
    Register("PBC", 0x15, "Port B direction, 1 = output", "6.15"),
    Register("PBPH", 0x16, "Port B pull-high enable", "6.16"),
    *comparator_registers(0x18, 0x19, ("6.26", "6.27"),
                          {"PA3": 0, "PA4": 1, "BANDGAP": 2, "VINTR": 3, "PB6": 4, "PB7": 5},
                          gpcs_bit6=False),
    Register("BGTR", 0x1A, "Bandgap trim", source="free-pdk"),
    Register("MISCLVR", 0x1B, "Code option: low-voltage reset level (LVR)", source="free-pdk", access="wo",
             fields=[enum_field("LVR", 5, 3, {"4V0": 0, "3V5": 1, "3V0": 2, "2V75": 3, "2V5": 4,
                                               "1V8": 5, "2V2": 6, "2V0": 7}, "LVR level")]),
    *timer8_registers(2, (0x1C, 0x1D, 0x17, 0x09), ("6.18", "6.19", "6.20", "6.21"), TM_CLK,
                      {"NONE": 0, "PB2": 1, "PA3": 2, "PB4": 3}),
    *pwmg_registers(0, 0x20, ("6.28", "6.29", "6.30", "6.31", "6.32", "6.33"),
                    {"NONE": 0, "PB5": 1, "PA0": 3, "PB4": 4}),
    *pwmg_registers(1, 0x26, ("6.34", "6.35", "6.36", "6.37", "6.38", "6.39"),
                    {"NONE": 0, "PB6": 1, "PA4": 3, "PB7": 4}),
    *pwmg_registers(2, 0x2C, ("6.40", "6.41", "6.42", "6.43", "6.44", "6.45"),
                    {"NONE": 0, "PB3": 1, "PA3": 3, "PB2": 4, "PA5": 5}),
    *timer8_registers(3, (0x32, 0x33, 0x34, 0x35), ("6.22", "6.23", "6.24", "6.25"), TM_CLK,
                      {"NONE": 0, "PB5": 1, "PB6": 2, "PB7": 3}),
    Register("RFCC", 0x36, "RC-to-frequency converter control (undocumented)", source="free-pdk", fields=[
        enum_field("CH", 5, 3, {"PA4": 0, "PA0": 1, "PA3": 4, "PB7": 5, "PB6": 6, "NONE": 7},
                   "input pin (PB0..PB4 need CH_EXT)"),
        bit_field("START", 4, "start counting"),
        bit_field("C_TYPE", 3, "1 = C type, 0 = R type"),
        bit_field("OVERFLOW", 2, "counter overflow"),
        bit_field("OUT", 1, "output enable"),
        bit_field("CH_EXT", 0, "second pin table (PB4, PB3, PB2, PB1, PB0)"),
    ]),
    Register("RFCCRH", 0x37, "RFC count high byte", source="free-pdk"),
    Register("RFCCRL", 0x38, "RFC count low byte", source="free-pdk"),
    Register("ILRCR", 0x39, "ILRC trim (written by the calibration code)", source="free-pdk"),
]

PINS = {
    "PA0": PinInfo("PA0", "A", 0, ["output", "input", "interrupt", "comp_out", "pwm"],
                   "PA0 / INT0 / CO / PG0PWM. External interrupt, comparator output, PWMG0 output."),
    "PA3": PinInfo("PA3", "A", 3, ["output", "input", "pwm", "comp_minus"],
                   "PA3 / TM2PWM / PG2PWM / CIN0-. Programming pin."),
    "PA4": PinInfo("PA4", "A", 4, ["output", "input", "pwm", "comp_plus", "comp_minus"],
                   "PA4 / PG1PWM / CIN+ / CIN1-. Programming pin."),
    "PA5": PinInfo("PA5", "A", 5, ["output", "input", "pwm", "reset"],
                   "PA5 / PRSTB / PG2PWM. Input or open-drain output only. Programming pin "
                   "(high voltage): put a 33 ohm resistor in series if something else drives it.",
                   open_drain_only=True),
    "PA6": PinInfo("PA6", "A", 6, ["output", "input"], "PA6 / X2 (crystal). Programming pin."),
    "PA7": PinInfo("PA7", "A", 7, ["output", "input", "serial_tx"],
                   "PA7 / X1 (crystal). The programmer reads serial debug output on this pin."),
    "PB0": PinInfo("PB0", "B", 0, ["output", "input", "interrupt"], "PB0 / INT1. External interrupt."),
    "PB1": PinInfo("PB1", "B", 1, ["output", "input"], "PB1"),
    "PB2": PinInfo("PB2", "B", 2, ["output", "input", "pwm"], "PB2 / TM2PWM / PG2PWM"),
    "PB3": PinInfo("PB3", "B", 3, ["output", "input", "pwm"], "PB3 / PG2PWM"),
    "PB4": PinInfo("PB4", "B", 4, ["output", "input", "pwm"], "PB4 / TM2PWM / PG0PWM"),
    "PB5": PinInfo("PB5", "B", 5, ["output", "input", "pwm"], "PB5 / TM3PWM / PG0PWM"),
    "PB6": PinInfo("PB6", "B", 6, ["output", "input", "pwm", "comp_minus"], "PB6 / TM3PWM / PG1PWM / CIN4-"),
    "PB7": PinInfo("PB7", "B", 7, ["output", "input", "pwm", "comp_minus"], "PB7 / TM3PWM / PG1PWM / CIN5-"),
}

PACKAGES = [
    Package("S16", "SOP16 / DIP16 (PFS154-S16, -D16)",
            ["PB4", "PB5", "PB6", "PB7", "VDD", "PA7", "PA6", "PA5",
             "PA3", "PA4", "PA0", "GND", "PB0", "PB1", "PB2", "PB3"]),
    Package("QFN16", "QFN3x3 16-pin (PFS154-1J16A)",
            ["PA0", "GND", "PB0", "PB1", "PB2", "PB3", "PB4", "PB5",
             "PB6", "PB7", "VDD", "PA7", "PA6", "PA5", "PA3", "PA4"], quad=True,
            note="Bottom pad: GND"),
    Package("S14", "SOP14 (PFS154-S14)",
            ["PB5", "PB6", "PB7", "VDD", "PA7", "PA6", "PA5", "PA3", "PA4", "PA0", "GND", "PB0", "PB1", "PB2"]),
    Package("M10", "MSOP10 (PFS154-M10)",
            ["PB7", "VDD", "PA7", "PA6", "PA5", "PA3", "PA4", "PA0", "GND", "PB0"]),
    Package("S08", "SOP8 (PFS154-S08)", ["VDD", "PA7", "PA6", "PA5", "PA3", "PA4", "PA0", "GND"]),
    Package("U06", "SOT23-6 (PFS154-U06)", ["PA4", "GND", "PA5", "PA6", "VDD", "PA3"]),
]

LVR = [("4V0", 4000), ("3V5", 3500), ("3V0", 3000), ("2V75", 2750),
       ("2V5", 2500), ("2V2", 2200), ("2V0", 2000), ("1V8", 1800)]

CHIP = Chip(
    name="PFS154",
    arch="pdk14",
    rom_words=2048,
    ram_bytes=128,
    otp=False,
    datasheet="PFS154 datasheet V107",
    registers=REGISTERS,
    pins=PINS,
    packages=PACKAGES,
    # Datasheet 4.1: 8 MHz needs VDD >= 3.5 V, 4 MHz >= 2.5 V, 2 MHz >= 2.0 V
    clocks=std_clocks({2: 2000, 4: 2500, 8: 3500}, 55000),
    ilrc_hz=55000,
    vdd_range_mv=(2000, 5500),
    fuse_addr=0x7FF,
    fuse_reserved=0x30FC,
    fuse_bits={
        "security": {"on": 0x0000, "off": 0x0001},
        "drive": {"low": 0x0000, "normal": 1 << 8},
        "bootup": {"slow": 0x0000, "fast": 3 << 10},
    },
    fuse_defaults={"security": "off", "drive": "normal", "bootup": "fast"},
    lvr_levels=LVR,
    lvr_in="register",
    timers=["T16", "TM2", "TM3", "PWMG0", "PWMG1", "PWMG2"],
    pwm_outputs={
        "TM2": {"PB2": "TM2C_OUT_PB2", "PA3": "TM2C_OUT_PA3", "PB4": "TM2C_OUT_PB4"},
        "TM3": {"PB5": "TM3C_OUT_PB5", "PB6": "TM3C_OUT_PB6", "PB7": "TM3C_OUT_PB7"},
        "PWMG0": {"PB5": "PWMG0C_OUT_PB5", "PA0": "PWMG0C_OUT_PA0", "PB4": "PWMG0C_OUT_PB4"},
        "PWMG1": {"PB6": "PWMG1C_OUT_PB6", "PA4": "PWMG1C_OUT_PA4", "PB7": "PWMG1C_OUT_PB7"},
        "PWMG2": {"PB3": "PWMG2C_OUT_PB3", "PA3": "PWMG2C_OUT_PA3", "PB2": "PWMG2C_OUT_PB2",
                  "PA5": "PWMG2C_OUT_PA5"},
    },
    comparator={
        "minus": {"PA3": "GPCC_MINUS_PA3", "PA4": "GPCC_MINUS_PA4", "PB6": "GPCC_MINUS_PB6",
                  "PB7": "GPCC_MINUS_PB7", "BANDGAP": "GPCC_MINUS_BANDGAP", "VINTR": "GPCC_MINUS_VINTR"},
        "plus": {"PA4": "GPCC_PLUS_PA4", "VINTR": "GPCC_PLUS_VINTR"},
        "out_pin": "PA0",
        "edge": ("MISC2", "MISC2_COMP_EDGE"),
        "wakeup": False,
    },
    adc=None,
    interrupts={
        "PA0": {"line": "PA0", "inten": "INTEN_PA0", "intrq": "INTRQ_PA0", "edge": "INTEGS_PA0"},
        "PB0": {"line": "PB0", "inten": "INTEN_PB0", "intrq": "INTRQ_PB0", "edge": "INTEGS_PB0"},
    },
    has_pull_down=False,
    reserved_rom=(0x7E0, 0x7FF),
    factory_ihrcr=0x7ED,
    factory_bgtr=0x7EE,
    notes=[
        "Flash: rewrite it as often as you like (about 1000 cycles).",
        "PA5 is input or open-drain output only.",
        "The three 11-bit PWM generators (PWMG0..2) share one interrupt.",
    ],
)
