"""PFS122: flash (MTP), pdk14, 2 KW ROM, 128 B RAM, 12-bit ADC.

Source: PADAUK PFS122 datasheet (V002 2023-03-31 and V004 2025-09-02; the
register chapters are identical), chapters 2, 4, 5, 6, 8.

Not in the datasheet: the oscillator/bandgap trim registers and the
code-option registers (ROP, MISC2, MISCLVR). The datasheet says code options
are chosen in Padauk's IDE; these addresses and bits are the PFS172's (same
core and chip ID), documented by free-pdk. Marked source="free-pdk".
"""

from . import (Chip, Register, Package, PinInfo, bit_field, enum_field, clkmd_register,
               t16m_register, timer8_registers, comparator_registers, edge_values, std_clocks)

E = edge_values()
TM_CLK = {"OFF": 0, "SYSCLK": 1, "IHRC": 2, "EOSC": 3, "ILRC": 4, "COMP": 5,
          "PA0_RISE": 8, "PA0_FALL": 9, "PB0_RISE": 10, "PB0_FALL": 11, "PA4_RISE": 12, "PA4_FALL": 13}

ADC_CH = {"PB0": 0, "PB1": 1, "PB2": 2, "PB3": 3, "PB4": 4, "PB5": 5, "PB6": 6, "PB7": 7,
          "PA3": 8, "PA4": 9, "PA0": 10, "BANDGAP": 15}

REGISTERS = [
    Register("FLAG", 0x00, "ACC status flags", "6.1", fields=[
        bit_field("OV", 3), bit_field("AC", 2), bit_field("C", 1), bit_field("Z", 0)]),
    Register("SP", 0x02, "Stack pointer", "6.2"),
    clkmd_register(0x03, has_eosc=True),
    Register("INTEN", 0x04, "Interrupt enable", "6.4", fields=[
        bit_field("TM3", 7), bit_field("TM2", 6), bit_field("COMP", 4), bit_field("ADC", 3),
        bit_field("T16", 2), bit_field("INT1", 1, "PB0 or PA4 (code option)"),
        bit_field("INT0", 0, "PA0 or PB5 (code option)")]),
    Register("INTRQ", 0x05, "Interrupt request (write 0 to clear)", "6.5", fields=[
        bit_field("TM3", 7), bit_field("TM2", 6), bit_field("COMP", 4), bit_field("ADC", 3),
        bit_field("T16", 2), bit_field("INT1", 1), bit_field("INT0", 0)]),
    t16m_register(0x06, has_eosc=True),
    Register("EOSCR", 0x0A, "External crystal oscillator", "6.7", "wo", fields=[
        bit_field("EN", 7, "enable the crystal oscillator"),
        enum_field("DRIVE", 5, 2, {"LOW": 1, "MID": 2, "HIGH": 3}, "32 kHz / 1 MHz / 4 MHz crystals"),
    ]),
    Register("IHRCR", 0x0B, "IHRC trim (written by the calibration code)", source="free-pdk"),
    Register("INTEGS", 0x0C, "Interrupt edge select", "6.8", "wo", fields=[
        enum_field("T16", 4, 1, {"RISE": 0, "FALL": 1}, "Timer16 interrupt edge"),
        enum_field("INT1", 2, 2, E, "PB0/PA4 interrupt edge"),
        enum_field("INT0", 0, 2, E, "PA0/PB5 interrupt edge"),
    ]),
    Register("PADIER", 0x0D, "Port A digital input enable (bits 7..3, 0)", "6.9", "wo"),
    Register("PBDIER", 0x0E, "Port B digital input enable", "6.10", "wo"),
    Register("PA", 0x10, "Port A data", "6.11"),
    Register("PAC", 0x11, "Port A direction, 1 = output", "6.12"),
    Register("PAPH", 0x12, "Port A pull-high enable (input mode)", "6.13"),
    Register("PAPL", 0x13, "Port A pull-low enable", "6.14"),
    Register("PB", 0x15, "Port B data", "6.15"),
    Register("PBC", 0x16, "Port B direction, 1 = output", "6.16"),
    Register("PBPH", 0x17, "Port B pull-high enable (input mode)", "6.17"),
    Register("PBPL", 0x18, "Port B pull-low enable", "6.18"),
    Register("ADCC", 0x20, "ADC control", "6.19", fields=[
        bit_field("EN", 7, "enable the ADC"),
        bit_field("START", 6, "write 1: start a conversion; reads 1 when done"),
        enum_field("CH", 2, 4, ADC_CH, "input channel"),
    ]),
    Register("ADCM", 0x21, "ADC mode (clock)", "6.20", fields=[
        enum_field("CLK", 1, 3, {"DIV1": 0, "DIV2": 1, "DIV4": 2, "DIV8": 3, "DIV16": 4,
                                 "DIV32": 5, "DIV64": 6, "DIV128": 7}, "ADC clock = system clock / n"),
    ]),
    Register("ADCRH", 0x22, "ADC result bits 11..4", "6.21", "ro"),
    Register("ADCRL", 0x23, "ADC result bits 3..0 (in bits 7..4)", "6.22", "ro"),
    Register("MISC", 0x26, "Misc: wake-up, LVR, watchdog period", "6.23", "wo", fields=[
        bit_field("FAST_WAKEUP", 5, "fast wake-up (45 ILRC clocks)"),
        bit_field("LVR_DISABLE", 2, "disable the low-voltage reset"),
        enum_field("WDT", 0, 2, {"8K": 0, "16K": 1, "64K": 2, "256K": 3}, "watchdog period in ILRC clocks"),
    ]),
    Register("MISC2", 0x27, "Code option: comparator interrupt edge (Comparator Edge)", source="free-pdk",
             access="wo", fields=[enum_field("COMP_EDGE", 5, 2, E, "comparator interrupt edge")]),
    Register("MISCLVR", 0x28, "Code option: low-voltage reset level (LVR)", source="free-pdk", access="wo",
             fields=[enum_field("LVR", 4, 4, {"1V8": 0, "2V0": 2, "2V2": 4, "2V5": 7, "2V7": 8,
                                               "3V0": 9, "3V5": 12, "4V0": 14}, "LVR level"),
                     enum_field("BANDGAP", 0, 2, {"ON": 0, "DIV4": 1, "DIV32": 2, "AUTO": 3},
                                "bandgap mode")]),
    *comparator_registers(0x2B, 0x2C, ("6.24", "6.25"),
                          {"PA3": 0, "PA4": 1, "BANDGAP": 2, "VINTR": 3, "PB6": 4, "PB7": 5},
                          gpcs_bit6=True),
    *timer8_registers(2, (0x30, 0x31, 0x32, 0x33), ("6.26", "6.27", "6.28", "6.29"), TM_CLK,
                      {"NONE": 0, "PB2": 1, "PA3": 2, "PB4": 3}, "6-bit or 7-bit (code option)"),
    *timer8_registers(3, (0x34, 0x35, 0x36, 0x37), ("6.30", "6.31", "6.32", "6.33"), TM_CLK,
                      {"NONE": 0, "PB5": 1, "PB6": 2, "PB7": 3}, "6-bit or 7-bit (code option)"),
    Register("ILRCR", 0x3B, "ILRC trim (written by the calibration code)", source="free-pdk"),
    Register("BGTR", 0x3C, "Bandgap trim", source="free-pdk"),
    Register("ROP", 0x3D, "Code options: interrupt pins, timer PWM options", source="free-pdk", access="wo",
             fields=[
                 bit_field("GPC_PWM", 6, "comparator controls all PWM outputs"),
                 bit_field("TMX_32MHZ", 5, "TM2/TM3 IHRC clock is IHRC*2 (32 MHz)"),
                 bit_field("TMX_7BIT", 4, "TMxS.7 = 1 selects 7-bit PWM (else 6-bit)"),
                 bit_field("INT0_PB5", 1, "INT0 comes from PB5 (else PA0)"),
                 bit_field("INT1_PA4", 0, "INT1 comes from PA4 (else PB0)"),
             ]),
]

PINS = {
    "PA0": PinInfo("PA0", "A", 0, ["output", "input", "interrupt", "comp_out", "adc"],
                   "PA0 / AD10 / CO / INT0. External interrupt 0, comparator output, ADC channel 10."),
    "PA3": PinInfo("PA3", "A", 3, ["output", "input", "pwm", "comp_minus", "adc"],
                   "PA3 / AD8 / CIN0- / TM2PWM. Programming pin."),
    "PA4": PinInfo("PA4", "A", 4, ["output", "input", "interrupt", "comp_plus", "comp_minus", "adc"],
                   "PA4 / AD9 / CIN+ / CIN1- / INT1 (code option). Programming pin."),
    "PA5": PinInfo("PA5", "A", 5, ["output", "input", "reset"],
                   "PA5 / PRSTB. Programming pin (high voltage): put a 33 ohm resistor in series "
                   "if something else drives it."),
    "PA6": PinInfo("PA6", "A", 6, ["output", "input"], "PA6 / X2 (crystal). Programming pin."),
    "PA7": PinInfo("PA7", "A", 7, ["output", "input", "serial_tx"],
                   "PA7 / X1 (crystal). The programmer reads serial debug output on this pin."),
    "PB0": PinInfo("PB0", "B", 0, ["output", "input", "interrupt", "adc"], "PB0 / AD0 / INT1"),
    "PB1": PinInfo("PB1", "B", 1, ["output", "input", "adc"], "PB1 / AD1"),
    "PB2": PinInfo("PB2", "B", 2, ["output", "input", "pwm", "adc"], "PB2 / AD2 / TM2PWM"),
    "PB3": PinInfo("PB3", "B", 3, ["output", "input", "adc"], "PB3 / AD3"),
    "PB4": PinInfo("PB4", "B", 4, ["output", "input", "pwm", "adc"],
                   "PB4 / AD4 / TM2PWM. Strong drive option (PB4_PB7_Drive)."),
    "PB5": PinInfo("PB5", "B", 5, ["output", "input", "interrupt", "pwm", "adc"],
                   "PB5 / AD5 / INT0 (code option) / TM3PWM"),
    "PB6": PinInfo("PB6", "B", 6, ["output", "input", "pwm", "comp_minus", "adc"], "PB6 / AD6 / CIN4- / TM3PWM"),
    "PB7": PinInfo("PB7", "B", 7, ["output", "input", "pwm", "comp_minus", "adc"],
                   "PB7 / AD7 / CIN5- / TM3PWM. Strong drive option (PB4_PB7_Drive)."),
}

PACKAGES = [
    Package("S16", "SOP16 (PFS122-S16A)",
            ["VDD", "PA7", "PA6", "PA5", "PB7", "PB4", "PB5", "PB6",
             "PB2", "PB0", "PB1", "PB3", "PA3", "PA4", "PA0", "GND"]),
    Package("QFN16", "QFN 16-pin (PFS122-1J16A, -2J16A)",
            ["VDD", "PA7", "PA6", "PA5", "PB7", "PB4", "PB5", "PB6",
             "PB2", "PB0", "PB1", "PB3", "PA3", "PA4", "PA0", "GND"], quad=True),
    Package("S14", "SOP14 (PFS122-S14)",
            ["VDD", "PA7", "PA6", "PA5", "PB7", "PB4", "PB5", "PB0", "PB1", "PB3", "PA3", "PA4", "PA0", "GND"]),
    Package("M10", "MSOP10 / ESSOP10 / DFN10 (PFS122-M10, -EY10, -4N10)",
            ["VDD", "PA6", "PA5", "PB7", "PB4", "PB1", "PA3", "PA4", "PA0", "GND"]),
    Package("S08", "SOP8 (PFS122-S08)", ["VDD", "PA6", "PA5", "PB7", "PB1", "PA3", "PA4", "GND"]),
    Package("U06", "SOT23-6 (PFS122-U06)", ["PA4", "GND", "PA6", "PA5", "VDD", "PA3"]),
]

LVR = [("4V0", 4000), ("3V5", 3500), ("3V0", 3000), ("2V7", 2700),
       ("2V5", 2500), ("2V2", 2200), ("2V0", 2000), ("1V8", 1800)]

CHIP = Chip(
    name="PFS122",
    arch="pdk14",
    rom_words=2048,
    ram_bytes=128,
    otp=False,
    datasheet="PFS122 datasheet V004 (V002 has the same registers)",
    registers=REGISTERS,
    pins=PINS,
    packages=PACKAGES,
    # Datasheet 4.1: 8 MHz needs VDD >= 3.0 V, 4 MHz >= 2.2 V, 2 MHz >= 1.8 V
    clocks=std_clocks({2: 1800, 4: 2200, 8: 3000}, 56000),
    ilrc_hz=56000,
    vdd_range_mv=(1800, 5500),
    fuse_addr=0x7FF,
    fuse_reserved=0x017C,
    fuse_bits={
        "security": {"on": 0x0000, "off": 0x0001},
        "drive": {"normal": 0x0000, "strong": 1 << 7},   # PB4/PB7 drive (code option PB4_PB7_Drive)
        "bootup": {"slow": 0x0000, "fast": 3 << 12},
    },
    fuse_defaults={"security": "off", "drive": "normal", "bootup": "fast"},
    lvr_levels=LVR,
    lvr_in="register",
    timers=["T16", "TM2", "TM3"],
    pwm_outputs={
        "TM2": {"PB2": "TM2C_OUT_PB2", "PA3": "TM2C_OUT_PA3", "PB4": "TM2C_OUT_PB4"},
        "TM3": {"PB5": "TM3C_OUT_PB5", "PB6": "TM3C_OUT_PB6", "PB7": "TM3C_OUT_PB7"},
    },
    comparator={
        "minus": {"PA3": "GPCC_MINUS_PA3", "PA4": "GPCC_MINUS_PA4", "PB6": "GPCC_MINUS_PB6",
                  "PB7": "GPCC_MINUS_PB7", "BANDGAP": "GPCC_MINUS_BANDGAP", "VINTR": "GPCC_MINUS_VINTR"},
        "plus": {"PA4": "GPCC_PLUS_PA4", "VINTR": "GPCC_PLUS_VINTR"},
        "out_pin": "PA0",
        "edge": ("MISC2", "MISC2_COMP_EDGE"),
        "wakeup": True,
    },
    adc={
        "bits": 12,
        "channels": {k: f"ADCC_CH_{k}" for k in ADC_CH},
        "clock_target_hz": 500_000,   # datasheet 5.13: about 2 us per ADC clock
        "bandgap_mv": 1200,
    },
    interrupts={
        "PA0": {"line": "INT0", "inten": "INTEN_INT0", "intrq": "INTRQ_INT0", "edge": "INTEGS_INT0", "rop": 0},
        "PB5": {"line": "INT0", "inten": "INTEN_INT0", "intrq": "INTRQ_INT0", "edge": "INTEGS_INT0",
                "rop": "ROP_INT0_PB5"},
        "PB0": {"line": "INT1", "inten": "INTEN_INT1", "intrq": "INTRQ_INT1", "edge": "INTEGS_INT1", "rop": 0},
        "PA4": {"line": "INT1", "inten": "INTEN_INT1", "intrq": "INTRQ_INT1", "edge": "INTEGS_INT1",
                "rop": "ROP_INT1_PA4"},
    },
    has_pull_down=True,
    reserved_rom=(0x7E0, 0x7FF),
    factory_ihrcr=0x7ED,
    factory_bgtr=0x7EE,
    notes=[
        "Flash: rewrite it as often as you like (about 1000 cycles).",
        "Needs the PoGo430 easypdkprog fork with programmer firmware 1.4 (bundled).",
        "Written in the datasheet's limited-voltage programming mode (VDD 5 V).",
        "Code-option registers (interrupt pin choice, LVR, comparator edge) come from free-pdk's PFS172 "
        "documentation; the datasheet doesn't list them.",
    ],
    programming_note="Needs programmer firmware 1.4 (Programmer page).",
)
