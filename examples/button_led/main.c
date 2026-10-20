/*
 * button_led - LED on PA4 follows a push button on PA3.
 *
 *   PA3 ----[button]---- GND   (internal pull-up, so pressed = 0)
 *   PA4 ----[330R]--|>|-- GND
 */

#include <stdint.h>
#include <pdk/device.h>
#include "auto_sysclock.h"
#include "startup.h"
#include "delay.h"
#include "board.h"

#define button_pressed()  (!PIN_READ(A, BUTTON_PIN))

void interrupt(void) __interrupt(0)
{
}

void main(void)
{
  PIN_OUTPUT(A, LED_PIN);
  PIN_INPUT_PULLUP(A, BUTTON_PIN);

  for (;;) {
    if (button_pressed())
      PIN_HIGH(A, LED_PIN);
    else
      PIN_LOW(A, LED_PIN);
    _delay_ms(5);   // crude debounce
  }
}

// Startup: set + calibrate the system clock (see template/main.c for details)
unsigned char STARTUP_FUNCTION(void)
{
  AUTO_INIT_SYSCLOCK();
  AUTO_CALIBRATE_SYSCLOCK(TARGET_VDD_MV);
  return 0;
}
