# Padauk Tools

Write, build and flash **Padauk microcontrollers** from **VS Code** (or the
terminal) with the open-source [free-pdk](https://free-pdk.github.io)
toolchain: [SDCC](https://sdcc.sourceforge.net) and the
[Easy PDK programmer](https://github.com/free-pdk/easy-pdk-programmer-software).

Made for the **PFS154**, **PFS122** and **PMS150C**. It also builds for the
other chips in the free-pdk headers (`pdk devices`).

## Setup (once)

1. Install SDCC, make and easypdkprog: see **[docs/setup.md](docs/setup.md)**.
   The **PFS122** needs the *development* version of easypdkprog and a
   programmer firmware update. `tools/build-easypdkprog-dev.sh` builds both.
2. Put the `pdk` command on your PATH and check everything:
   ```sh
   ./pdk install        # symlinks pdk into ~/.local/bin
   pdk doctor           # checks sdcc, make, easypdkprog, USB permissions, VS Code
   ```
3. In VS Code, install the **C/C++** extension (it's suggested automatically
   when you open a project).

## New project

```sh
pdk new blinky                              # PFS154, opens VS Code
pdk new adc-test -d PFS122
pdk new hello -d PMS150C -e serial_hello    # start from an example (pdk examples)
```

## In VS Code

| | |
|---|---|
| **Ctrl+Shift+B** | Build. Errors and warnings show up in the Problems panel, clickable |
| Status bar buttons | **Build**, **Flash**, **Monitor**, **Device** (with the suggested *Task Buttons* extension) |
| Ctrl+Shift+P > *Run Task* | all tasks: Flash, Flash + Monitor, Monitor, Probe, Erase, Clean, Select device / clock / voltage |

- **Select device** shows a list of chips. The choice is saved in the
  Makefile, and IntelliSense switches to that chip's registers, so `PBC` is
  flagged as an error on a PMS150C (it has no port B).
- **Monitor** powers the chip from the programmer and shows what it prints on
  PA7 (`include/serial.h`). Handy for printf-style debugging.
- SDCC-specific syntax (`__sfr`, `__at()`, `__interrupt()`, inline asm) is
  handled, so the headers don't light up red.

## Pin configurator (CubeMX-style)

```sh
pdk configure        # or "Configure pins..." in the GUI, or the Pins button in VS Code
```

Click pins on a drawing of your chip and package to make them outputs,
inputs, interrupts, PWM, comparator or ADC inputs, or the serial debug
output. It also covers clock, watchdog, fuses and low-voltage reset.
**Generate code** writes `pdk_init.c/h` with named helpers (`LED_toggle()`,
`BUTTON_read()`, `FAN_set_duty(x)`, ...) and hooks them into `main.c`.
Conflicts, such as two functions needing the same timer, are flagged
before you generate. See **[docs/configurator.md](docs/configurator.md)**.

## GUI

Prefer buttons? `pdk gui` (needs `pip install PyQt5`) opens the Padauk Tools
window on the current project:

- **New / Open** projects (pick the chip and a starting example)
- chip, clock and supply voltage dropdowns, saved straight to the Makefile
- **Build**, **Flash**, **Flash + Monitor**, **Monitor**, **Stop**, plus Probe, Erase, Clean
- ROM/RAM bars after each build, colored errors (double-click one to open the file)
- **Configure pins...** opens the pin configurator
- **Doctor** checks your setup, **Upgrade** refreshes the project from the template
- asks before writing a one-time-programmable chip
- shortcuts: Ctrl+B build, Ctrl+U flash, Ctrl+M monitor, Esc stop

It uses the same project files as VS Code and `pdk`, so you can mix them.
For a standalone executable: `python3 PadaukBuilder/build_executables.py`.

## In the terminal

Run these anywhere inside a project folder:

```sh
pdk build                     # compile + ROM/RAM usage
pdk flash                     # write the chip (asks first for OTP chips)
pdk flash -m                  # write, then monitor serial output
pdk monitor                   # power the chip, show serial output (Ctrl+C to stop)
pdk probe                     # what's in the programmer socket?
pdk set device=PMS150C clock=1M vdd=3.3
pdk device                    # show settings (pdk device PFS122 to change)
pdk erase | read | clean
pdk upgrade                   # pull template improvements into an existing project
pdk configure                 # pin configurator; pdk generate regenerates its code without the GUI
```

`pdk` only drives the project's Makefile, so plain `make`, `make program`,
`make run`, `make set DEVICE=PFS122` and so on work too (`make help`).

Example build output:

```
  PFS154 (pdk14)  F_CPU=8000000 Hz  VDD=5.00 V
  ROM:    81 /  2048 words  (  3%)
  RAM:    10 /   128 bytes  (  7%)  static data, stack uses the rest
```

## Project layout

```
main.c         setup(), loop(), interrupt handler, clock startup
board.h        pin assignments + PIN_OUTPUT / PIN_HIGH / PIN_READ helpers
src/           extra .c/.h files (built automatically)
Makefile       settings at the top: DEVICE, F_CPU, TARGET_VDD_MV
include/       free-pdk headers + delay.h, millis.h, serial.h
.vscode/       tasks, IntelliSense config (pdk_config.h is generated, don't edit)
```

| Setting | Default | |
|---|---|---|
| `DEVICE` | `PFS154` | chip; picks pdk13/14/15 and ROM/RAM size automatically |
| `F_CPU` | `8000000` | clock in Hz: 8M, 4M, 2M, 1M, 500k, 250k from the internal oscillator |
| `TARGET_VDD_MV` | `5000` | your circuit's supply voltage. The clock is calibrated for it, and Monitor powers the chip at it |
| `PROG_PORT` | auto | e.g. `/dev/ttyACM0` |
| `PROG_FLAGS` | | extra easypdkprog options, e.g. `--securefill` |
| `EASYPDKPROG` | `easypdkprog` | path to easypdkprog, e.g. a development build |

## This repo

```
pdk            the command-line tool (Python 3, no extra packages)
PadaukBuilder/ the GUI (pdk gui) and pin configurator (pdk configure)
template/      what `pdk new` copies
examples/      blink_irq, button_led, serial_hello, button_serial
docs/          setup.md (install), chips.md (chip notes), configurator.md
tools/         test-all.sh, test-configurator.py (compile-test random pin setups), build-easypdkprog-dev.sh
```

`tools/test-all.sh` builds the template and every example for the three
chips. GitHub Actions runs it, plus a `pdk` smoke test, on every push.

The template also contains a Code::Blocks project (`.cbp`) with Build /
Program / Run targets, if you prefer that editor.

## Credits

`include/pdk` is [pdk-includes](https://github.com/free-pdk/pdk-includes)
(commit `874918f`), `include/easy-pdk` is
[easy-pdk-includes](https://github.com/free-pdk/easy-pdk-includes), and
`delay.h`, `millis.h`, `serial.h`, `auto_sysclock.h`, `startup.h` come from
[free-pdk-examples](https://github.com/free-pdk/free-pdk-examples)
(`delay.h` has small guards added for editors). See the licenses in those
folders.
