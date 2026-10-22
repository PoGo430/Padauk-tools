"""Example projects shown in File > New from example.

Each example is a list of pin/peripheral settings plus the code that goes in
main.c's USER CODE sections. Most use pins that every chip has in its SOP8
package (PA0, PA3, PA4, PA7), so they work on all three chips. Several are
ports of https://github.com/free-pdk/free-pdk-examples.

User code keys: "includes", "globals", "setup", "loop", "functions",
"irq_T16", "irq_TM2", "irq_COMP", and "irq_pin:PA0" for the interrupt of pin
PA0 (its section name differs per chip).
"""

from .project import Project, default_project

WIRING_LED = "LED with a 1 k resistor from {pin} to GND."
WIRING_BUTTON = "Push button from {pin} to GND (the internal pull-up keeps it high)."

EXAMPLES = [
    {
        "key": "blink",
        "title": "Blink",
        "chips": ["PFS154", "PFS122", "PMS150C"],
        "text": "Blinks an LED on PA4 with delay_ms(). The classic first program.",
        "wiring": [WIRING_LED.format(pin="PA4")],
        "pins": {"PA4": ("output", {"label": "LED"})},
        "code": {
            "loop": "    LED_toggle();\n    delay_ms(500);\n",
        },
    },
    {
        "key": "blink_millis",
        "title": "Blink with millis()",
        "chips": ["PFS154", "PFS122", "PMS150C"],
        "text": "Blinks without blocking: Timer16 counts milliseconds and the loop checks millis(). "
                "The loop stays free for other work.",
        "wiring": [WIRING_LED.format(pin="PA4")],
        "pins": {"PA4": ("output", {"label": "LED"})},
        "timers": {"T16": {"mode": "millis"}},
        "code": {
            "globals": "static uint32_t last;\n",
            "loop": "    if (millis() - last >= 500) {\n      last += 500;\n      LED_toggle();\n    }\n",
        },
    },
    {
        "key": "button_led",
        "title": "Button controls LED",
        "chips": ["PFS154", "PFS122", "PMS150C"],
        "text": "The LED is on while the button is pressed.",
        "wiring": [WIRING_LED.format(pin="PA4"), WIRING_BUTTON.format(pin="PA0")],
        "pins": {"PA4": ("output", {"label": "LED"}), "PA0": ("input", {"label": "BUTTON", "pull": "up"})},
        "code": {
            "loop": "    LED_set(!BUTTON_read());   /* pressed = low */\n",
        },
    },
    {
        "key": "button_interrupt",
        "title": "Button interrupt",
        "chips": ["PFS154", "PFS122", "PMS150C"],
        "text": "Each press toggles the LED from the pin interrupt. The main loop does nothing.",
        "wiring": [WIRING_LED.format(pin="PA4"), WIRING_BUTTON.format(pin="PA0")],
        "pins": {"PA4": ("output", {"label": "LED"}),
                 "PA0": ("interrupt", {"label": "BUTTON", "pull": "up", "edge": "fall"})},
        "code": {
            "irq_pin:PA0": "    LED_toggle();   /* no debouncing: a bouncy button may toggle twice */\n",
        },
    },
    {
        "key": "sleep_wake",
        "title": "Sleep and wake up",
        "chips": ["PFS154", "PFS122", "PMS150C"],
        "text": "Blinks 3 times, then powers down (stopsys, under 1 uA). Any change on the button pin "
                "wakes it up again. Port of free-pdk's SleepWake.",
        "wiring": [WIRING_LED.format(pin="PA4"), WIRING_BUTTON.format(pin="PA0")],
        "pins": {"PA4": ("output", {"label": "LED"}), "PA0": ("input", {"label": "BUTTON", "pull": "up"})},
        "code": {
            "loop": ("    uint8_t i;\n    for (i = 0; i < 3; i++) {\n      LED_high();\n      delay_ms(200);\n"
                     "      LED_low();\n      delay_ms(200);\n    }\n"
                     "    stopsys();   /* wakes up when a pin with digital input on changes */\n"),
        },
    },
    {
        "key": "serial_hello",
        "title": "Serial: Hello World",
        "chips": ["PFS154", "PFS122", "PMS150C"],
        "text": "Prints a line with a counter every second on PA7. Leave the chip in the programmer and "
                "press Monitor to see it.",
        "wiring": ["Nothing: the programmer reads PA7 while the chip sits in its socket."],
        "pins": {"PA7": ("serial_tx", {})},
        "code": {
            "globals": "static uint16_t count;\n",
            "setup": "  serial_println(\"Hello from \" CHIP_NAME \"!\");\n",
            "loop": "    serial_print(\"count = \");\n    serial_print_uint(count++);\n"
                    "    serial_println(\"\");\n    delay_ms(1000);\n",
        },
    },
    {
        "key": "button_serial",
        "title": "Serial: button presses",
        "chips": ["PFS154", "PFS122", "PMS150C"],
        "text": "Counts button presses and prints them. Port of free-pdk's ReadButton_WriteSerial.",
        "wiring": [WIRING_BUTTON.format(pin="PA0")],
        "pins": {"PA7": ("serial_tx", {}), "PA0": ("input", {"label": "BUTTON", "pull": "up"})},
        "code": {
            "globals": "static uint8_t was_pressed;\nstatic uint16_t presses;\n",
            "loop": ("    uint8_t pressed = !BUTTON_read();\n    if (pressed && !was_pressed) {\n"
                     "      serial_print(\"pressed \");\n      serial_print_uint(++presses);\n"
                     "      serial_println(\" times\");\n      delay_ms(20);   /* debounce */\n    }\n"
                     "    was_pressed = pressed;\n"),
        },
    },
    {
        "key": "pwm_fade",
        "title": "PWM: fade an LED (Timer2)",
        "chips": ["PFS154", "PFS122", "PMS150C"],
        "text": "Fades an LED on PA3 in and out with Timer2's 8-bit PWM. Port of free-pdk's FadeLED.",
        "wiring": [WIRING_LED.format(pin="PA3")],
        "pins": {"PA3": ("pwm", {"label": "LED", "periph": "TM2"})},
        "timers": {"TM2": {"freq_hz": 1000, "duty": 1}},
        "code": {
            "loop": ("    uint8_t v;\n    for (v = 0; v < LED_DUTY_MAX; v++) {\n      LED_set_duty(v);\n"
                     "      delay_ms(4);\n    }\n    for (v = LED_DUTY_MAX; v > 0; v--) {\n      LED_set_duty(v);\n"
                     "      delay_ms(4);\n    }\n"),
        },
    },
    {
        "key": "pwmg_11bit",
        "title": "PWM: 11-bit generator (PWMG1)",
        "chips": ["PFS154"],
        "text": "Fades an LED on PA4 with the PFS154's 11-bit PWM generator: 2000 duty steps at 1 kHz, "
                "much smoother at low brightness than 8-bit PWM.",
        "wiring": [WIRING_LED.format(pin="PA4")],
        "pins": {"PA4": ("pwm", {"label": "LED", "periph": "PWMG1"})},
        "timers": {"PWMG1": {"freq_hz": 1000, "duty": 1}},
        "code": {
            "loop": ("    uint16_t v;\n    for (v = 0; v < LED_DUTY_MAX; v += 4) {\n      LED_set_duty(v);\n"
                     "      delay_ms(1);\n    }\n    for (v = LED_DUTY_MAX; v >= 4; v -= 4) {\n      LED_set_duty(v);\n"
                     "      delay_ms(1);\n    }\n"),
        },
    },
    {
        "key": "two_pwm",
        "title": "PWM: two channels (Timer2 + Timer3)",
        "chips": ["PFS154", "PFS122"],
        "text": "Two LEDs fading in opposite directions: Timer2 on PA3 and Timer3 on PB7.",
        "wiring": [WIRING_LED.format(pin="PA3"), WIRING_LED.format(pin="PB7")],
        "pins": {"PA3": ("pwm", {"label": "LED_A", "periph": "TM2"}),
                 "PB7": ("pwm", {"label": "LED_B", "periph": "TM3"})},
        "timers": {"TM2": {"freq_hz": 1000, "duty": 1}, "TM3": {"freq_hz": 1000, "duty": 99}},
        "code": {
            "loop": ("    uint8_t v;\n    for (v = 0; v < 255; v++) {\n      LED_A_set_duty(v);\n"
                     "      LED_B_set_duty(255 - v);\n      delay_ms(4);\n    }\n"
                     "    for (v = 255; v > 0; v--) {\n      LED_A_set_duty(v);\n"
                     "      LED_B_set_duty(255 - v);\n      delay_ms(4);\n    }\n"),
        },
    },
    {
        "key": "timer_tick",
        "title": "Timer2 periodic interrupt",
        "chips": ["PFS154", "PFS122", "PMS150C"],
        "text": "Timer2 interrupts 1000 times a second; the interrupt blinks the LED every 250 ticks.",
        "wiring": [WIRING_LED.format(pin="PA4")],
        "pins": {"PA4": ("output", {"label": "LED"})},
        "timers": {"TM2": {"mode": "tick", "tick_hz": 1000}},
        "code": {
            "globals": "static volatile uint8_t ticks;\n",
            "irq_TM2": "    if (++ticks >= 250) {\n      ticks = 0;\n      LED_toggle();\n    }\n",
        },
    },
    {
        "key": "comparator",
        "title": "Comparator: light sensor / threshold",
        "chips": ["PFS154", "PFS122", "PMS150C"],
        "text": "Compares the voltage on PA4 (for example a light sensor divider) with an internal "
                "reference of about half VDD and lights the LED on PA3 when it's higher.",
        "wiring": [WIRING_LED.format(pin="PA3"), "Voltage divider or potentiometer output to PA4."],
        "pins": {"PA3": ("output", {"label": "LED"}), "PA4": ("comp_plus", {"label": "SENSOR"})},
        "comparator": {"minus": "VINTR", "range": "R2", "level": 11},
        "code": {
            "loop": "    LED_set(comparator_read());\n",
        },
    },
    {
        "key": "low_battery",
        "title": "Comparator: low battery warning",
        "chips": ["PFS154", "PFS122", "PMS150C"],
        "text": "Uses the comparator to compare the 1.2 V bandgap with a fraction of VDD. The LED turns "
                "on when VDD drops below about 3.2 V. No external parts besides the LED.",
        "wiring": [WIRING_LED.format(pin="PA4")],
        "pins": {"PA4": ("output", {"label": "LED"})},
        "comparator": {"enabled": True, "plus": "VINTR", "minus": "BANDGAP", "range": "R4", "level": 11},
        "clock": "IHRC_DIV8",
        "code": {
            "setup": "  /* VINTR = (11 + 1) / 32 * VDD: above 1.2 V while VDD > 3.2 V */\n",
            "loop": "    LED_set(!comparator_read());\n    delay_ms(100);\n",
        },
    },
    {
        "key": "adc_serial",
        "title": "ADC: read a potentiometer",
        "chips": ["PFS122"],
        "text": "Reads the 12-bit ADC on PB1 and the supply voltage (with the bandgap), and prints both "
                "twice a second.",
        "wiring": ["Potentiometer: ends to VDD and GND, wiper to PB1."],
        "pins": {"PA7": ("serial_tx", {}), "PB1": ("adc", {"label": "POT"})},
        "code": {
            "loop": ("    serial_print(\"POT = \");\n    serial_print_uint(POT_read());\n"
                     "    serial_print(\"  VDD = \");\n    serial_print_uint(vdd_read_mv());\n"
                     "    serial_println(\" mV\");\n    delay_ms(500);\n"),
        },
    },
    {
        "key": "watchdog",
        "title": "Watchdog",
        "chips": ["PFS154", "PFS122", "PMS150C"],
        "text": "The watchdog resets the chip if the loop hangs. Hold the button to stop resetting "
                "the watchdog: the LED blinks fast after each reset.",
        "wiring": [WIRING_LED.format(pin="PA4"), WIRING_BUTTON.format(pin="PA0")],
        "pins": {"PA4": ("output", {"label": "LED"}), "PA0": ("input", {"label": "BUTTON", "pull": "up"})},
        "system": {"watchdog": "64K"},
        "code": {
            "setup": ("  {\n    uint8_t i;\n    for (i = 0; i < 6; i++) {   /* fast blink: we just started */\n"
                      "      LED_toggle();\n      delay_ms(50);\n      wdt_reset();\n    }\n  }\n"),
            "loop": ("    LED_toggle();\n    delay_ms(300);\n"
                     "    while (!BUTTON_read())\n      ;   /* stuck: the watchdog resets the chip after ~1 s */\n"),
        },
    },
]


def available(chip_name: str):
    return [e for e in EXAMPLES if chip_name in e["chips"]]


def by_key(key: str) -> dict:
    for e in EXAMPLES:
        if e["key"] == key:
            return e
    raise KeyError(key)


def make_project(key: str, chip_name: str, name: str = "") -> (Project, dict):
    """A Project with the example's settings, and its USER CODE sections."""
    ex = by_key(key)
    p = Project(default_project(chip_name, name or ex["key"]))
    if ex.get("clock") and ex["clock"] in [c.key for c in p.chip.clocks]:
        p.data["clock"] = ex["clock"]
    for t, cfg in ex.get("timers", {}).items():
        if t in p.data["timers"]:
            p.data["timers"][t].update(cfg)
    for pin, (fn, opts) in ex.get("pins", {}).items():
        p.set_pin(pin, fn, **opts)
    if "comparator" in ex:
        p.data["comparator"].update(ex["comparator"])
        p.data["comparator"]["enabled"] = True
    for k, v in ex.get("system", {}).items():
        p.data["system"][k] = v
    p._sync_timers()
    code = {}
    for k, v in ex.get("code", {}).items():
        if k.startswith("irq_pin:"):
            pin = k.split(":", 1)[1]
            k = "irq_" + p.chip.interrupts[pin]["line"]
        code[k] = v
    return p, code


def main_with_code(code: dict) -> str:
    """A fake old main.c so codegen.merge_user_code puts the example code in."""
    return "".join(f"/* USER CODE BEGIN {k} */\n{v}/* USER CODE END {k} */\n" for k, v in code.items())
