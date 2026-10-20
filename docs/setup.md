# Setting up the toolchain

You need: **SDCC** (the C compiler), **easypdkprog** (talks to the Easy PDK
programmer), **make**, and **Python 3** for the `pdk` helper. VS Code is
optional but recommended.

## 1. SDCC

SDCC 4.2.0 or newer (the template is tested with 4.2.0).

| OS | Install |
|----|---------|
| Debian / Ubuntu / Mint | `sudo apt install sdcc make gawk` |
| Arch | `sudo pacman -S sdcc make` |
| macOS | `brew install sdcc make` |
| Windows | installer from <https://sdcc.sourceforge.net>, plus MSYS2 for `make` / `awk` |

Check it: `sdcc --version` should list `pdk13/pdk14/pdk15`.

SDCC 4.2.11+ renamed the startup function (`_sdcc_external_startup` became
`__sdcc_external_startup`). `include/startup.h` handles that, so always write
`STARTUP_FUNCTION` like the template does.

## 2. easypdkprog

### Which version do I need?

| Chip | easypdkprog 1.3 (latest release) | development branch |
|------|------|------|
| PFS154 | yes | yes |
| PMS150C | yes | yes |
| **PFS122** | **no** (unknown IC name) | **yes** |

The PFS122 (and PFS121, PFS172B, PFS123, PFS173B) were added to easypdkprog
after the 1.3 release and only exist on the
[development branch](https://github.com/free-pdk/easy-pdk-programmer-software/tree/development).
The development branch also uses a newer programmer protocol (1.5 instead of
1.3), so **the programmer firmware has to be updated too**. The software
refuses to talk to firmware that doesn't match.

The development build still supports the PFS154 and PMS150C, so you can use it
for everything.

### Option A: release 1.3 (PFS154, PMS150C only)

Download from
<https://github.com/free-pdk/easy-pdk-programmer-software/releases>, unzip,
and put `easypdkprog` on your PATH.

### Option B: development branch (needed for PFS122)

On Linux, the script in this repo builds both the software and the firmware:

```sh
sudo apt install build-essential git gcc-arm-none-eabi libnewlib-arm-none-eabi dfu-util
tools/build-easypdkprog-dev.sh            # builds into ~/easy-pdk-dev
sudo cp ~/easy-pdk-dev/easypdkprog /usr/local/bin/
```

Then flash the new firmware onto the programmer (one time):

1. Unplug the programmer.
2. Hold its button, plug in USB, then let go of the button.
3. Run:
   ```sh
   dfu-util -d 0483:df11 -a "@Internal Flash  /0x08000000/064*0002Kg" \
            --dfuse-address 0x08000000 -D ~/easy-pdk-dev/Firmware/source/build/EASYPDKPROG.dfu
   ```
4. Unplug, plug back in, and check with `easypdkprog probe`.

If you want to go back to 1.3 later, flash the firmware from the 1.3 release
zip the same way.

(macOS: the same steps work with `brew install arm-none-eabi-gcc dfu-util`.
Windows: build in MSYS2, see the `INSTALL` file in that repo.)

### Linux: USB permissions

The programmer shows up as `/dev/ttyACM0`. If you get "permission denied":

```sh
sudo usermod -aG dialout $USER     # then log out and back in
```

If it takes a long time to be detected after plugging in, ModemManager is
probing it. Install the udev rule from the easypdkprog repo:

```sh
sudo cp ~/easy-pdk-dev/Linux_udevrules/70-stm32vcp.rules /etc/udev/rules.d/
sudo udevadm control --reload
```

## 3. pdk and VS Code

```sh
./pdk install          # links pdk into ~/.local/bin (add that to PATH if pdk doctor says so)
pdk doctor             # checks everything below
pdk doctor --probe     # ...and talks to the programmer
```

VS Code: install the **C/C++** extension (`ms-vscode.cpptools`). Opening a
project suggests it, plus **Task Buttons** for the Build/Flash/Monitor
buttons in the status bar. For `pdk new` to open VS Code by itself, run
*Shell Command: Install 'code' command in PATH* from the command palette
(macOS); on Linux and Windows the installer does this.

GUI (optional): `pip install PyQt5`, then `pdk gui`.

### Windows

The tasks and `pdk` call `make`, so install [MSYS2](https://www.msys2.org)
and in its terminal run `pacman -S make gawk`. Add `C:\msys64\usr\bin` and
SDCC's `bin` folder to your PATH. Run pdk as `py pdk <command>`.

## 4. Check the programmer by hand

```sh
easypdkprog test      # programmer self test (no chip in the socket)
easypdkprog probe     # with a chip in the socket
easypdkprog list      # chips this easypdkprog version supports
```
