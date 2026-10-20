/*
 * board.h - pin assignments and small pin helpers for this project.
 *
 * Change the pin numbers here instead of scattering them through the code.
 * Port A pins available per chip/package (check the datasheet pinout):
 *   PMS150C (SOT23-6 / SOP8): PA0, PA3, PA4, PA5, PA6, PA7
 *   PFS154 / PFS122:          PA0, PA3..PA7 and PB0..PB7 (package dependent)
 *
 * PA5 is the reset/programming pin: input or open-drain output only.
 * PA7 is the serial TX pin used by serial.h (shown by `make run`).
 */

#ifndef BOARD_H
#define BOARD_H

#define LED_PIN       4     // PA4
#define BUTTON_PIN    3     // PA3 (to GND, uses internal pull-up)

// ---------------------------------------------------------------------------
// Pin helpers. 'port' is the letter (A, B, C), 'pin' is 0..7.
//   PIN_OUTPUT(A, 4);  PIN_HIGH(A, 4);  if (PIN_READ(A, 3)) { ... }
// ---------------------------------------------------------------------------
#define PIN_MASK(pin)               ((uint8_t)(1u << (pin)))

#define PIN_OUTPUT(port, pin)       (P##port##C |= PIN_MASK(pin))
#define PIN_HIGH(port, pin)         (P##port    |= PIN_MASK(pin))
#define PIN_LOW(port, pin)          (P##port    &= (uint8_t)~PIN_MASK(pin))
#define PIN_TOGGLE(port, pin)       (P##port    ^= PIN_MASK(pin))

// Inputs must be enabled in PxDIER or they always read as 0.
#define PIN_INPUT(port, pin)        do { P##port##C &= (uint8_t)~PIN_MASK(pin); \
                                         P##port##DIER |= PIN_MASK(pin); } while (0)
#define PIN_INPUT_PULLUP(port, pin) do { PIN_INPUT(port, pin); \
                                         P##port##PH |= PIN_MASK(pin); } while (0)
#define PIN_READ(port, pin)         (P##port & PIN_MASK(pin))

#endif // BOARD_H
