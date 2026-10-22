"""PMS150C: OTP, pdk13, 1 KW ROM, 64 B RAM.

Source: PADAUK PMS150C datasheet (PDK-DS-PMS150C-EN V004), chapters 2, 4, 5, 6, 8.
"""

from . import (Chip, Register, Package, PinInfo, bit_field, enum_field, clkmd_register,
               t16m_register, timer8_registers, comparator_registers, edge_values, std_clocks)

E = edge_values()

REGISTERS = [
    Register("FLAG", 0x00, "ACC status flags", "6.1", fields=[
        bit_field("OV", 3), bit_field("AC", 2), bit_field("C", 1), bit_field("Z", 0)]),
    Register("SP", 0x02, "Stack pointer", "6.2"),
    clkmd_register(0x03, has_eosc=False),
    Register("INTEN", 0x04, "Interrupt enable", "6.4", fields=[
        bit_field("TM2", 6), bit_field("COMP", 4), bit_field("T16", 2), bit_field("PA0", 0)]),
    Register("INTRQ", 0x05, "Interrupt request (write 0 to clear)", "6.5", fields=[
        bit_field("TM2", 6), bit_field("COMP", 4), bit_field("T16", 2), bit_field("PA0", 0)]),
    t16m_register(0x06, has_eosc=False),
    Register("EOSCR", 0x0A, "LVR power-down", "6.7", "wo", fields=[
        bit_field("LVR_OFF", 0, "power down the LVR (bandgap) circuit")]),
    Register("IHRCR", 0x0B, "IHRC trim (written by the calibration code)", source="free-pdk"),
    Register("INTEGS", 0x0C, "Interrupt edge select", "6.8", "wo", fields=[
        enum_field("COMP", 6, 2, E, "comparator interrupt edge"),
        enum_field("T16", 4, 1, {"RISE": 0, "FALL": 1}, "Timer16 interrupt edge"),
        enum_field("PA0", 0, 2, E, "PA0 interrupt edge"),
    ]),
    Register("PADIER", 0x0D, "Port A digital input / wake-up enable (bits 7..3, 0)", "6.9", "wo"),
    Register("PA", 0x10, "Port A data", "6.10"),
    Register("PAC", 0x11, "Port A direction, 1 = output", "6.11"),
    Register("PAPH", 0x12, "Port A pull-high enable", "6.12"),
    *timer8_registers(2, (0x1C, 0x1D, 0x17, 0x09), ("6.16", "6.17", "6.19", "6.18"),
                      {"OFF": 0, "SYSCLK": 1, "IHRC": 2, "ILRC": 4, "COMP": 5,
                       "PA0_RISE": 8, "PA0_FALL": 9, "PA4_RISE": 12, "PA4_FALL": 13},
                      {"NONE": 0, "PA3": 2, "PA4": 3}),
    Register("BGTR", 0x19, "Bandgap trim", source="free-pdk"),
    *comparator_registers(0x1A, 0x1E, ("6.14", "6.15"),
                          {"PA3": 0, "PA4": 1, "BANDGAP": 2, "VINTR": 3, "PA6": 4, "PA7": 5},
                          gpcs_bit6=True),
    Register("MISC", 0x1B, "Misc: wake-up, LVR, watchdog period", "6.13", "wo", fields=[
        bit_field("FAST_WAKEUP", 5, "fast wake-up (32 ILRC clocks)"),
        bit_field("LVR_DISABLE", 2, "disable the low-voltage reset"),
        enum_field("WDT", 0, 2, {"8K": 0, "16K": 1, "64K": 2, "256K": 3}, "watchdog period in ILRC clocks"),
    ]),
    Register("ILRCR", 0x1F, "ILRC trim (written by the calibration code)", source="free-pdk"),
]
PINS = {
    "PA0": PinInfo("PA0", "A", 0, ["output", "input", "interrupt", "comp_out"],
                   "PA0 / INT0 / CO. External interrupt and comparator output."),
    "PA3": PinInfo("PA3", "A", 3, ["output", "input", "pwm", "comp_minus"],
                   "PA3 / TM2PWM / CIN0-. Programming pin."),
    "PA4": PinInfo("PA4", "A", 4, ["output", "input", "pwm", "comp_plus", "comp_minus"],
                   "PA4 / TM2PWM / CIN+ / CIN1-. Programming pin."),
    "PA5": PinInfo("PA5", "A", 5, ["output", "input", "reset"],
                   "PA5 / PRSTB. Input or open-drain output only (no push-pull). "
                   "Programming pin (high voltage): put a 33 ohm resistor in series if "
                   "something else drives it.", open_drain_only=True),
    "PA6": PinInfo("PA6", "A", 6, ["output", "input", "comp_minus"],
                   "PA6 / CIN2-. Programming pin."),
    "PA7": PinInfo("PA7", "A", 7, ["output", "input", "comp_minus", "serial_tx"],
                   "PA7 / CIN3-. The programmer reads serial debug output on this pin."),
}

PACKAGES = [
    Package("S08", "SOP8 / DIP8 (PMS150C-S08, -D08)",
            ["VDD", "PA7", "PA6", "PA5", "PA3", "PA4", "PA0", "GND"]),
    Package("U06", "SOT23-6 (PMS150C-U06)", ["PA4", "GND", "PA6", "PA5", "VDD", "PA3"]),
]

LVR = [("4V0", 4000), ("3V5", 3500), ("3V0", 3000), ("2V75", 2750),
       ("2V5", 2500), ("2V2", 2200), ("2V0", 2000), ("1V8", 1800)]

CHIP = Chip(
    name="PMS150C",
    arch="pdk13",
    rom_words=1024,
    ram_bytes=64,
    otp=True,
    datasheet="PMS150C datasheet V004",
    registers=REGISTERS,
    pins=PINS,
    packages=PACKAGES,
    # Datasheet 4.1: 8 MHz needs VDD >= 3.0 V, 4 MHz >= 2.2 V, 2 MHz >= 2.0 V
    clocks=std_clocks({2: 2000, 4: 2200, 8: 3000}, 62000),
    ilrc_hz=62000,
    vdd_range_mv=(2000, 5500),
    fuse_addr=0x3FF,
    fuse_reserved=0x0260,
    fuse_bits={
        "security": {"on": 0x0000, "off": 0x0001},
        "lvr": {"4V0": 0 << 2, "3V5": 1 << 2, "3V0": 2 << 2, "2V75": 3 << 2,
                "2V5": 4 << 2, "1V8": 5 << 2, "2V2": 6 << 2, "2V0": 7 << 2},
        "drive": {"low": 0x0000, "normal": 1 << 7},
        "bootup": {"slow": 0x0000, "fast": 3 << 10},
    },
    fuse_defaults={"security": "off", "drive": "normal", "bootup": "fast"},
    lvr_levels=LVR,
    lvr_in="fuse",
    timers=["T16", "TM2"],
    pwm_outputs={"TM2": {"PA3": "TM2C_OUT_PA3", "PA4": "TM2C_OUT_PA4"}},
    comparator={
        "minus": {"PA3": "GPCC_MINUS_PA3", "PA4": "GPCC_MINUS_PA4", "PA6": "GPCC_MINUS_PA6",
                  "PA7": "GPCC_MINUS_PA7", "BANDGAP": "GPCC_MINUS_BANDGAP", "VINTR": "GPCC_MINUS_VINTR"},
        "plus": {"PA4": "GPCC_PLUS_PA4", "VINTR": "GPCC_PLUS_VINTR"},
        "out_pin": "PA0",
        "edge": ("INTEGS", "INTEGS_COMP"),   # register holding the comparator interrupt edge
        "wakeup": True,
    },
    adc=None,
    interrupts={
        "PA0": {"line": "PA0", "inten": "INTEN_PA0", "intrq": "INTRQ_PA0", "edge": "INTEGS_PA0"},
    },
    has_pull_down=False,
    reserved_rom=(0x3F6, 0x3FF),
    factory_ihrcr=None,
    factory_bgtr=0x3F6,
    notes=[
        "One-time programmable: a chip can be written only once.",
        "pdk13 core: 64 bytes of RAM. Avoid 32-bit math and big local variables.",
        "PA5 is input or open-drain output only.",
    ],
    programming_note="OTP: each chip can be written once.",
)
