/*
 * blink_irq - blink the LED on PA4 from a timer interrupt (no busy-wait).
 * The main loop stays free for other work.
 *
 * Uses include/millis.h (timer16 / T16 interrupt, needs the IHRC running,
 * so keep F_CPU >= 250000).
 */

#include <stdint.h>
#include <pdk/device.h>
#include "auto_sysclock.h"
#include "startup.h"
#include "millis.h"
#include "board.h"

#define BLINK_INTERVAL_MS  500

static uint32_t last_toggle;

void interrupt(void) __interrupt(0)
{
  if (INTRQ & INTRQ_T16) {
    INTRQ &= ~INTRQ_T16;
    millis_irq_handler();
  }
}

void main(void)
{
  PIN_OUTPUT(A, LED_PIN);
  PIN_LOW(A, LED_PIN);

  millis_setup();
  INTRQ = 0;
  __engint();

  for (;;) {
    if (millis() - last_toggle >= BLINK_INTERVAL_MS) {
      last_toggle += BLINK_INTERVAL_MS;
      PIN_TOGGLE(A, LED_PIN);
    }
    // ... other work here ...
  }
}

// Startup: set + calibrate the system clock (see template/main.c for details)
unsigned char STARTUP_FUNCTION(void)
{
  AUTO_INIT_SYSCLOCK();
  AUTO_CALIBRATE_SYSCLOCK(TARGET_VDD_MV);
  return 0;
}
