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
| ADC | no | 12-bit (see below) | no |
| free-pdk status | Supported | Supported (beta) | Supported |
| easypdkprog | 1.3 or dev | **dev branch only** | 1.3 or dev |

The architecture is picked automatically from `DEVICE` (`make config` shows it).

## PFS154

The easiest chip to start with: flash, so you can rewrite it as often as you
like, and well tested in the free-pdk community.

- Fuses: `FUSE_SECURITY_ON/OFF`, `FUSE_IO_DRV_LOW/NORMAL`, `FUSE_BOOTUP_SLOW/FAST`.
  `FUSE_IO_DRV_LOW` limits the pin drive strength.
- The 11-bit PWM generators (PWMG0..2) are in `include/pdk/device/periph/pwmg_*.h`.
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

**Headers:** `pdk/device.h` maps `PFS122` to `device/pfs172.h`. Everything
except the ADC should match.

- Fuses: `FUSE_SECURITY_ON/OFF`, `FUSE_PB4_PB7_NORMAL/STRONG`, `FUSE_BOOTUP_SLOW/FAST`.
- **ADC:** the header describes the PFS172's 8-bit ADC (`ADCC`, `ADCM`, `ADCR` at
  0x20-0x22). The PFS122's 12-bit result registers are not defined in
  pdk-includes yet. Before relying on the ADC, compare the register table in
  the PFS122 datasheet with `device/pfs172.h` and add the missing registers
  (for example `ADCRH`/`ADCRL`) in your project.

## PMS150C

Very cheap, tiny (SOT23-6 / SOP8), and **one-time programmable**: once written,
it can't be erased or rewritten. `make program` prints a reminder, and the GUI
asks before writing.

- pdk13 core: smaller instruction set, 64 bytes RAM. Keep code simple, avoid
  32-bit math and big local arrays.
- Pins: PA0, PA3, PA4, PA5, PA6, PA7 (SOP8). PA5 is the reset/programming pin
  (input or open-drain output only).
- No port B, no PWMG, no ADC. Timer2 can do 8-bit PWM.
- Fuses: `FUSE_SECURITY_ON/OFF`, `FUSE_LVR_*` (low-voltage reset level),
  `FUSE_IO_DRV_LOW/NORMAL`, `FUSE_BOOTUP_SLOW/FAST`.
- The PMS15A is the same silicon; use `DEVICE = PMS15A` if that's what's printed on it.

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
