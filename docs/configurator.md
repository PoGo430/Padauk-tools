# Pin configurator

A small STM32CubeMX-style tool for the **PFS154**, **PFS122** and **PMS150C**
(the PFS172 works too). Click pins on a drawing of the chip, choose what
they do, set up PWM, the comparator, the ADC and system options. It then
generates the init code for your project.

```sh
pdk configure                # in a project folder (needs: pip install PyQt5)
```

It's also in the GUI (**Configure pins...**) and in VS Code (**Pins**
status bar button, or the *Padauk: Pin configurator* task).

## What it does

- **Chip and package:** the drawing matches the real package (SOT23-6,
  SOP8, MSOP10, SOP14, SOP16/DIP16, QFN16, DFN10), with pin numbers.
  Hover a pin to see its max current, pull-ups and programming function.
- **Click a pin** to pick a function. Functions the hardware can't do on
  that pin aren't offered. Functions whose peripheral is already used
  elsewhere are greyed out, with the pin that uses it.
- **Pins tab:** name each pin (the name is used in the code), and set its
  initial level, pull-up/down and interrupt edge.
- **PWM tab:** type a frequency and it picks the timer settings, showing
  the frequency you'll actually get.
- **Analog tab:** comparator inputs, internal reference, interrupt; ADC clock.
- **System tab:** clock and supply voltage (saved in the Makefile),
  unused pins, `millis()` timebase, watchdog, fuses (code protection, drive
  strength, boot-up time) and the low-voltage reset level.
- **Code preview** updates as you click; problems (conflicts, pins not on
  the chosen package, OTP reminders) are listed at the bottom.
- **Generate code** writes `pdk_init.h` and `pdk_init.c`, saves your setup
  in `padauk.json`, and adds `#include "pdk_init.h"`, `pdk_init()` and
  `pdk_irq()` to `main.c` if they're missing (backup in `main.c.bak`).

| Function | PMS150C | PFS154 | PFS122 / PFS172 |
|---|---|---|---|
| Output / input, pull-up | all pins | all pins | all pins (+ pull-down) |
| External interrupt | PA0 | PA0 (INT0), PB0 (INT1) | INT0: PA0 or PB5, INT1: PB0 or PA4 |
| 8-bit PWM, Timer2 | PA3, PA4 | PA3, PB2, PB4 | PA3, PB2, PB4 |
| 8-bit PWM, Timer3 | - | PB5, PB6, PB7 | PB5, PB6, PB7 |
| 11-bit PWM, PWMG0/1/2 | - | PA0, PA3, PA4, PA5, PB2-PB7 | - |
| Comparator | + PA4, - PA3/PA4/PA6/PA7, out PA0 | + PA4, - PA3/PA4/PB6/PB7, out PA0 | same as PFS154 |
| ADC | - | - | PA0, PA3, PA4, PB0-PB7 |
| Serial TX (debug) | PA7 | PA7 | PA7 |

## Using the generated code

```c
#include "pdk_init.h"

void interrupt(void) __interrupt(0)
{
  pdk_irq();                       // added by the configurator
}

static void setup(void)
{
  pdk_init();                      // added by the configurator
}

static void loop(void)
{
  if (BUTTON_triggered()) {        // external interrupt on the pin named BUTTON
    pdk_int0_flag = 0;
    LED_toggle();
  }
  FAN_set_duty(128);               // PWM pin named FAN (Timer3 here: Serial TX uses Timer2)
  if (SWITCH_read()) { ... }       // input pin named SWITCH
  uint8_t v = POT_read();          // ADC pin named POT (PFS122/PFS172)
  serial_print_uint(v);            // with Serial TX on PA7; see it with `pdk monitor`
  serial_println("");              // (printf() needs more RAM than these chips have)
}
```

Each named pin gets `NAME_BIT` and, depending on its function, `NAME_high()`,
`NAME_low()`, `NAME_toggle()`, `NAME_read()`, `NAME_set_duty(x)` or
`NAME_triggered()`. The pin list at the top of `pdk_init.h` shows them all.

Don't edit `pdk_init.c/h` by hand: they're rewritten on every generate.
Change things in the configurator, or run `pdk generate` after editing
`padauk.json`.

## Where the data comes from, and what's unverified

The Padauk datasheet site couldn't be reached while building this, so the
tool uses the free-pdk project's data, which was compiled from those
datasheets:

- **Pinouts and pin functions:** the data behind the interactive pinout
  diagrams on free-pdk.github.io/chips
  ([@cmfcmf/pinout-diagrams](https://www.npmjs.com/package/@cmfcmf/pinout-diagrams), MIT).
- **Registers and bit values:** the free-pdk `pdk-includes` headers
  (`include/pdk/device/...`). The generated code only uses their macro names.

Check these against your datasheet:

- **PFS122:** free-pdk has no separate pinout for it, so the PFS172 pinout is
  used (same chip ID). The ADC code uses the PFS172's 8-bit ADC registers;
  the PFS122 has a 12-bit ADC.
- **PFS154 11-bit PWM frequency:** computed as
  16 MHz / (prescaler x scaler x (upper bound/2 + 1)). Measure it if the exact
  frequency matters.
- **Comparator internal reference:** you pick a range (1-4) and a level
  (0-15). The resulting voltage is listed in the comparator chapter of the
  datasheet.
- **Watchdog times** are approximate (they run from the ~55-60 kHz ILRC).

Every combination is compile-tested: `tools/test-configurator.py` generates
random valid setups for each chip and builds them with SDCC (also run in CI).
It hasn't been tested on real hardware yet.
