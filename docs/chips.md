# Chip notes: PFS154, PFS122, PMS150C

Sources: the [free-pdk chip list](https://free-pdk.github.io/chips),
[pdk-includes](https://github.com/free-pdk/pdk-includes) and the easypdkprog IC
table. Always check the Padauk datasheet for your exact chip and package.

| | PFS154 | PFS122 | PMS150C |
|---|---|---|---|
| Set in Makefile | `DEVICE = PFS154` | `DEVICE = PFS122` | `DEVICE = PMS150C` |
| SDCC architecture | pdk14 | pdk14 | pdk13 |
| ROM | 2048 words | 2048 words | 1024 words |
| RAM | 128 bytes | 128 bytes | 64 bytes |
| Memory | Flash (rewritable) | Flash (rewritable) | **OTP (write once)** |
| I/O pins (max) | 14 (PA, PB) | 14 (PA, PB) | 6 (PA only) |
| Timers | T16, TM2, TM3 | T16, TM2, TM3 | T16, TM2 |
| PWM | 2x 8-bit, 3x 11-bit | 2x 8-bit | 1x 8-bit |
| Comparator | yes | yes | yes |
| ADC | no | 12-bit, 11 channels | no |
| free-pdk status | Supported | Supported (beta) | Supported |
| easypdkprog | 1.3 or dev | **dev branch only** | 1.3 or dev |

The architecture is picked automatically from `DEVICE` (`make config` shows it).

## PFS154

The easiest chip to start with: flash, so you can rewrite it as often as you
like, and well tested in the free-pdk community.

- Fuses: `FUSE_SECURITY_ON/OFF`, `FUSE_IO_DRV_LOW/NORMAL`, `FUSE_BOOTUP_SLOW/FAST`.
  `FUSE_IO_DRV_LOW` limits the pin drive strength.
- The 11-bit PWM generators (PWMG0..2) are in `include/pdk/device/periph/pwmg_*.h`.
- **Undocumented RFC** (resistance/capacitance-to-frequency converter, see
  [free-pdk undocumented features](https://free-pdk.github.io/undocumented-features)):
  counts RC oscillations on a pin, useful for touch or resistive sensors. In
  the configurator pick "RC sensor input (RFC)", then `NAME_start()`, wait a
  fixed time, and `rfc_stop()` returns the count.
- Tip: develop and debug on a PFS154, then switch `DEVICE` to `PMS150C` for the
  final OTP version (watch the smaller RAM/ROM and fewer pins).

## PFS122

The PFS122 is the PFS172 core with a 12-bit ADC (the PFS172 has an 8-bit one).
free-pdk lists it as **beta**: it works with the open tools, but it has been
tested less than the others.

**Programming:** needs easypdkprog from the development branch plus matching
programmer firmware. See [setup.md](setup.md#option-b-development-branch-needed-for-pfs122).
With release 1.3 you'll get an "unknown IC" error for `-n PFS122`.

Untested shortcut: in the development branch, PFS122 is only an alias for the
PFS172 entry (same chip ID). Release 1.3 knows the PFS172, so you could try
`make probe` and then `make program PROG_ICNAME=PFS172` with 1.3. The dev
branch is the supported route, though.

**Checked against the PFS122 datasheet** (V004, 2025-09-02):

- **Pinout:** identical to the PFS172 in every shared package (SOT23-6, SOP8,
  MSOP10/ESSOP10/DFN10, SOP14, SOP16), plus QFN16 (PFS122-1J16A / -2J16A). The
  configurator has all of them.
- **Registers:** same addresses and bits as `device/pfs172.h` (which
  `pdk/device.h` uses for `PFS122`), except the ADC result.
- **12-bit ADC:** `ADCRH` (0x22) holds result bits 11..4, `ADCRL` (0x23) bits
  7..4 hold bits 3..0. The configurator's `adc_read()` returns the full 0..4095
  value on the PFS122. The reference is always VDD; to measure VDD itself, read
  the 1.20 V bandgap channel (`ADCC_CH_AD16_BANDGAP`). The datasheet recommends
  an ADC clock of about 500 kHz (e.g. SYSCLK/16 at 8 MHz).
- **Clock limits:** 8 MHz needs VDD >= 3.0 V, 4 MHz >= 2.2 V, 2 MHz >= 1.8 V.
- **Code options:** interrupt pin choice (PA0/PB5, PB0/PA4), LVR level (8
  levels, 1.8-4.0 V), comparator interrupt edge and PWM options are listed as
  "code options". Like on the PFS172, free-pdk sets these through registers
  (`ROP`, `MISCLVR`, `MISC2`) that the datasheet doesn't document; the
  generated code uses them the same way. This is the one part that's still
  unverified.
- Fuses: `FUSE_SECURITY_ON/OFF`, `FUSE_PB4_PB7_NORMAL/STRONG`, `FUSE_BOOTUP_SLOW/FAST`.

## PMS150C

Very cheap, tiny (SOT23-6 / SOP8), and **one-time programmable**: once written,
it can't be erased or rewritten. Flashing (VS Code task, `pdk flash` or
`make program`) asks for confirmation first.

- pdk13 core: smaller instruction set, 64 bytes RAM. Keep code simple, avoid
  32-bit math and big local arrays.
- Pins: PA0, PA3, PA4, PA5, PA6, PA7 (SOP8). PA5 is the reset/programming pin
  (input or open-drain output only).
- No port B, no PWMG, no ADC. Timer2 can do 8-bit PWM.
- Fuses: `FUSE_SECURITY_ON/OFF`, `FUSE_LVR_*` (low-voltage reset level),
  `FUSE_IO_DRV_LOW/NORMAL`, `FUSE_BOOTUP_SLOW/FAST`.
- The PMS15A is the same silicon; use `DEVICE = PMS15A` if that's what's printed on it.

## 16 MHz (undocumented, all three chips)

`F_CPU = 16000000` works but isn't in the datasheets: it's only stable with VDD
close to 5 V. The startup code turns on the 4 V low-voltage reset before
switching to 16 MHz (PFS154/PFS122; on the PMS150C use the `FUSE_LVR_4V` fuse,
which the configurator picks automatically at 16 MHz).

## Things that apply to all of them

- **Registers are not reset.** At power-up, registers hold random values, and
  the "reset value" column in the datasheet is wrong. Set every register you use.
- **Inputs need PxDIER.** A pin only reads digital input if its bit in
  `PADIER`/`PBDIER` is set (`PIN_INPUT()` in `board.h` does this).
- **Clock calibration.** The internal oscillator is calibrated by easypdkprog
  while writing, for the `F_CPU` and `TARGET_VDD_MV` in your Makefile. Set
  `TARGET_VDD_MV` to the voltage your circuit actually runs at. Datasheets
  typically rate 8 MHz only at higher supply voltages; use a lower `F_CPU`
  (for example 4 MHz or 1 MHz) for 3.3 V or battery circuits. The build warns
  above 8 MHz.
- **Serial debugging.** `include/serial.h` sends text on PA7. Leave the chip in
  the programmer and run `make run`: easypdkprog powers it and prints the
  output. See `examples/serial_hello`.
- **Single interrupt vector.** All interrupts go to one ISR
  (`__interrupt(0)`); check and clear the `INTRQ` bits yourself.
