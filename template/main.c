/*
 * main.c - Padauk MCU project template (SDCC + Easy PDK programmer)
 *
 * Builds for any chip listed by `make devices` (tested: PFS154, PFS122, PMS150C).
 * Project settings (DEVICE, F_CPU, TARGET_VDD_MV) live in the Makefile.
 *
 * Out of the box this blinks an LED on PA4. PA4 exists on every supported
 * chip, including the tiny 6-pin PMS150C.
 *
 *   PA4 ----[ 330R-1k ]----|>|---- GND     (LED, active high)
 *
 * START HERE (first steps):
 *  1. Pick your chip / clock / supply voltage: `pdk set device=PFS154 clock=8M vdd=5`
 *     (or the status bar buttons in VS Code, or the top of the Makefile).
 *  2. Change pin numbers in board.h if your LED/button sit elsewhere.
 *  3. Put one-time setup code in setup() and repeating code in loop() below.
 *  4. Build (Ctrl+Shift+B or `make`), then Flash (`make program`).
 *  Stuck? `pdk doctor` checks your tools and programmer, `make help` lists the rest.
 *
 * Things worth knowing about Padauk chips:
 *  - Registers are NOT reset to known values at power-up: set every register
 *    you rely on (direction, pull-ups, timers...) yourself.
 *  - RAM is tiny (64 bytes on PMS150C, 128 on PFS154/PFS122). Use uint8_t
 *    wherever you can, avoid deep call chains, printf and 32-bit math.
 *  - Inputs only work after enabling them in PxDIER (digital input enable).
 */

#include <stdint.h>
#include <pdk/device.h>       // registers for the DEVICE chosen in the Makefile
#include "auto_sysclock.h"    // picks the clock source from F_CPU
#include "startup.h"          // STARTUP_FUNCTION name for your SDCC version
#include "delay.h"            // _delay_us() / _delay_ms() busy-wait delays
#include "board.h"            // pin assignments + small pin helper macros

// ---------------------------------------------------------------------------
// Global state (keep it small, every byte of RAM counts)
// ---------------------------------------------------------------------------
// volatile uint8_t tick;     // use 'volatile' for anything shared with the ISR

// ---------------------------------------------------------------------------
// Interrupt service routine
// All interrupts share this single handler. Check INTRQ to see what fired,
// and clear the flag yourself. Enable sources in INTEN, then call __engint().
// ---------------------------------------------------------------------------
void interrupt(void) __interrupt(0)
{
  // Example (timer16):
  // if (INTRQ & INTRQ_T16) {
  //   INTRQ &= ~INTRQ_T16;
  //   tick++;
  // }
}

// ---------------------------------------------------------------------------
// setup(): runs once after reset
// ---------------------------------------------------------------------------
static void setup(void)
{
  // >>> Your one-time setup goes here (pin directions, timers, ...) <<<
  PIN_OUTPUT(A, LED_PIN);     // LED pin as output (pins start as inputs)
  PIN_LOW(A, LED_PIN);

  // Example input with pull-up (button to GND):
  // PIN_INPUT_PULLUP(A, BUTTON_PIN);

  // Enable interrupts only if you use them:
  // INTRQ = 0;
  // __engint();
}

// ---------------------------------------------------------------------------
// loop(): runs forever
// ---------------------------------------------------------------------------
static void loop(void)
{
  // >>> Your main code goes here (replace the blink) <<<
  PIN_TOGGLE(A, LED_PIN);
  _delay_ms(500);
}

void main(void)
{
  setup();
  for (;;) {
    loop();
  }
}

// ---------------------------------------------------------------------------
// Startup code: runs before main() and before global variables are set up.
// Sets the system clock and leaves a placeholder that easypdkprog fills in
// with the calibration value when you run `make program`.
// ---------------------------------------------------------------------------
unsigned char STARTUP_FUNCTION(void)
{
  // Optional: set fuses / code options. Names differ per chip, look in
  // include/pdk/device/<chip>.h for FUSE_... values. Only call this once.
  //   PFS154:          PDK_SET_FUSE(FUSE_SECURITY_OFF | FUSE_IO_DRV_NORMAL | FUSE_BOOTUP_FAST);
  //   PFS122 / PFS172: PDK_SET_FUSE(FUSE_SECURITY_OFF | FUSE_PB4_PB7_NORMAL | FUSE_BOOTUP_FAST);
  //   PMS150C:         PDK_SET_FUSE(FUSE_SECURITY_OFF | FUSE_IO_DRV_NORMAL | FUSE_LVR_2V5 | FUSE_BOOTUP_FAST);

  // Pick IHRC/ILRC and the divider that matches F_CPU.
  // For manual control use PDK_SET_SYSCLOCK(SYSCLOCK_IHRC_8MHZ) etc. (pdk/sysclock.h)
  AUTO_INIT_SYSCLOCK();

  // Placeholder that easypdkprog replaces with a calibration routine for
  // F_CPU at TARGET_VDD_MV. Without it the internal oscillator is uncalibrated.
  AUTO_CALIBRATE_SYSCLOCK(TARGET_VDD_MV);

  return 0;   // 0 = let SDCC continue with normal initialization
}
