# Padauk Tools

A project template and tools for programming **Padauk microcontrollers** with
the open-source [free-pdk](https://free-pdk.github.io) toolchain:
[SDCC](https://sdcc.sourceforge.net) and the
[Easy PDK programmer](https://github.com/free-pdk/easy-pdk-programmer-software).

Tested chips: **PFS154**, **PFS122**, **PMS150C**. It also builds for every
other chip in the free-pdk headers (`make devices`).

```
template/          copy this for every new project
  main.c             program skeleton: setup(), loop(), interrupt, clock startup
  board.h            pin assignments + PIN_OUTPUT/PIN_HIGH/PIN_READ helpers
  Makefile           all settings (DEVICE, F_CPU, TARGET_VDD_MV) + build/program targets
  padauk.cbp         Code::Blocks project (Build / Program / Run targets)
  include/           free-pdk headers (pdk/, easy-pdk/) + delay, millis, serial helpers
examples/          drop-in main.c files: blink_irq, button_led, serial_hello, button_serial
new-project.sh     create a project from the template
PadaukBuilder/     optional GUI (PyQt5)
tools/             test-all.sh, build-easypdkprog-dev.sh
docs/              setup.md (install), chips.md (PFS154 / PFS122 / PMS150C notes)
```

## Quick start

1. Install SDCC and easypdkprog: see **[docs/setup.md](docs/setup.md)**.
   **The PFS122 needs the development version of easypdkprog plus a firmware
   update on the programmer.** The setup guide covers it, and
   `tools/build-easypdkprog-dev.sh` builds both.
2. Create a project:
   ```sh
   ./new-project.sh ~/padauk/blinky PFS154
   ./new-project.sh ~/padauk/hello  PFS122 serial_hello    # start from an example
   ```
3. Build and program:
   ```sh
   cd ~/padauk/blinky
   make              # build + ROM/RAM usage
   make program      # write the chip in the programmer
   make run          # power it from the programmer and show serial output (PA7)
   ```

Typical output:

```
  PFS154 (pdk14)  F_CPU=8000000 Hz  VDD=5.00 V
  ROM:    81 /  2048 words  (  3%)
  RAM:    10 /   128 bytes  (  7%)  static data, stack uses the rest
```

## Makefile

Settings are at the top of the `Makefile`, or pass them on the command line:

| Variable | Default | Meaning |
|---|---|---|
| `DEVICE` | `PFS154` | chip; sets the SDCC architecture (pdk13/14/15), ROM and RAM size automatically |
| `F_CPU` | `8000000` | system clock in Hz (16M, 8M, 4M, 2M, 1M, 500k, 250k from IHRC; lower uses ILRC) |
| `TARGET_VDD_MV` | `5000` | your circuit's supply voltage; the clock is calibrated for it |
| `PROJECT_NAME` | `MyProject` | output file name |
| `SOURCES` | `*.c src/*.c` | extra `.c` files are picked up automatically |
| `EASYPDKPROG` | `easypdkprog` | path to the programmer tool |
| `PROG_PORT` | auto | e.g. `/dev/ttyACM0` |
| `PROG_FLAGS` | | extra easypdkprog options, e.g. `--securefill` |

```sh
make program DEVICE=PMS150C F_CPU=1000000 TARGET_VDD_MV=3300
```

| Target | |
|---|---|
| `make` | build and show ROM/RAM usage (fails if it doesn't fit) |
| `make program` / `flash` | build and write the chip |
| `make run` / `start` | power the chip at `TARGET_VDD_MV`, show its serial output |
| `make probe` | detect the chip in the socket |
| `make erase` | erase a flash chip (refuses on OTP chips) |
| `make read` | read the chip into `.output/` |
| `make list` | chips your easypdkprog supports |
| `make test` | programmer self test |
| `make devices` | chips this Makefile knows |
| `make config` | current settings and the exact program command |
| `make clean` | delete build output |

Build output goes to `.build/<DEVICE>/` and `.output/`, so switching `DEVICE`
never mixes object files.

## Code::Blocks

Open the `.cbp` in your project folder. Pick a target in the toolbar and
press Build:

- **Build**: `make`
- **Program**: `make program`
- **Run**: `make run`

All settings stay in the Makefile.

## GUI

`PadaukBuilder/Padauk Tools.py` is a small front end for the Makefile:

- open a project folder or create a new one (from the template or an example)
- set device, clock and voltage (shows ROM/RAM size and whether the chip is OTP)
- Build / Program / Run / Probe / Erase / Clean, with a Stop button
- asks for confirmation before writing an OTP chip

```sh
pip install PyQt5
python3 "PadaukBuilder/Padauk Tools.py"
python3 PadaukBuilder/build_executables.py      # optional: single-file executable
```

## Testing

`tools/test-all.sh` builds the template and every example for PFS154, PFS122
and PMS150C (or the chips you pass it). GitHub Actions runs it on every push.

## Credits

`include/pdk` is [pdk-includes](https://github.com/free-pdk/pdk-includes)
(commit `874918f`), `include/easy-pdk` is
[easy-pdk-includes](https://github.com/free-pdk/easy-pdk-includes), and
`delay.h`, `millis.h`, `serial.h`, `auto_sysclock.h`, `startup.h` come from
[free-pdk-examples](https://github.com/free-pdk/free-pdk-examples). See their
licenses in those folders.
