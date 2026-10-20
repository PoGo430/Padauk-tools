/*
 * button_serial - report button presses on PA3 over serial (PA7, ~115200 baud).
 * Run `make run` with the chip in the programmer to see the output.
 *
 *   PA3 ----[button]---- GND   (internal pull-up, so pressed = 0)
 */

#include <stdint.h>
#include <pdk/device.h>
#include "auto_sysclock.h"
#include "startup.h"
#include "serial.h"
#include "delay.h"
#include "board.h"

#define button_pressed()  (!PIN_READ(A, BUTTON_PIN))

static uint8_t was_pressed;

void interrupt(void) __interrupt(0)
{
  if (INTRQ & INTRQ_TM2) {
    INTRQ &= ~INTRQ_TM2;
    serial_irq_handler();
  }
}

void main(void)
{
  PIN_INPUT_PULLUP(A, BUTTON_PIN);

  serial_setup();
  INTRQ = 0;
  __engint();

  for (;;) {
    uint8_t pressed = button_pressed() ? 1 : 0;
    if (pressed != was_pressed) {
      serial_println(pressed ? "Button down" : "Button up");
      was_pressed = pressed;
    }
    _delay_ms(5);
  }
}

// Startup: set + calibrate the system clock (see template/main.c for details)
unsigned char STARTUP_FUNCTION(void)
{
  AUTO_INIT_SYSCLOCK();
  AUTO_CALIBRATE_SYSCLOCK(TARGET_VDD_MV);
  return 0;
}
