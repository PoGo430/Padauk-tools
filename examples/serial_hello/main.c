/*
 * serial_hello - print "Hello World!" once a second on PA7 (~115200 baud).
 *
 * The Easy PDK programmer can show this directly: leave the chip in the
 * programmer and run `make run`. Great for debugging (printf-style).
 *
 * Uses include/serial.h (TX only, timer2 / TM2 interrupt, needs the IHRC
 * running, so keep F_CPU >= 250000).
 */

#include <stdint.h>
#include <pdk/device.h>
#include "auto_sysclock.h"
#include "startup.h"
#include "serial.h"
#include "delay.h"

void interrupt(void) __interrupt(0)
{
  if (INTRQ & INTRQ_TM2) {
    INTRQ &= ~INTRQ_TM2;
    serial_irq_handler();
  }
}

void main(void)
{
  serial_setup();
  INTRQ = 0;
  __engint();

  for (;;) {
    serial_println("Hello World!");
    _delay_ms(1000);
  }
}

// Startup: set + calibrate the system clock (see template/main.c for details)
unsigned char STARTUP_FUNCTION(void)
{
  AUTO_INIT_SYSCLOCK();
  AUTO_CALIBRATE_SYSCLOCK(TARGET_VDD_MV);
  return 0;
}
