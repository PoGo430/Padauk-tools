"""Code generator: user code is kept, random setups compile."""
import os
import random

import pytest

from padauk_studio import checks, codegen, toolchain
from padauk_studio.project import Project, default_project

SDCC, _ = toolchain.find_tool("sdcc")


def test_user_code_kept_and_orphans_saved(tmp_path):
    p = Project(default_project("PFS154", "keep"))
    p.set_pin("PA0", "interrupt", label="BTN")
    folder = str(tmp_path)
    codegen.write_project(p, folder)
    path = os.path.join(folder, "main.c")
    text = open(path).read()
    text = text.replace("/* USER CODE BEGIN loop */\n", "/* USER CODE BEGIN loop */\n    my_loop();\n")
    text = text.replace("/* USER CODE BEGIN irq_PA0 */\n", "/* USER CODE BEGIN irq_PA0 */\n    pressed = 1;\n")
    open(path, "w").write(text)
    # regenerate unchanged: both kept
    codegen.write_project(p, folder)
    text = open(path).read()
    assert "    my_loop();\n    /* USER CODE END loop */" in text
    assert "pressed = 1;" in text and "#if 0" not in text
    # remove the interrupt: its code moves to the #if 0 block
    p.set_pin("PA0", "unused")
    codegen.write_project(p, folder)
    text = open(path).read()
    assert "my_loop();" in text
    assert "#if 0" in text and "USER CODE BEGIN removed_irq_PA0" in text and "pressed = 1;" in text
    # and stays there on the next generate
    codegen.write_project(p, folder)
    assert open(path).read().count("pressed = 1;") == 1
    # adding the interrupt back doesn't lose it either
    p.set_pin("PA0", "interrupt", label="BTN")
    codegen.write_project(p, folder)
    assert open(path).read().count("pressed = 1;") == 1


def test_pin_unassign_frees_peripherals():
    p = Project(default_project("PFS154"))
    p.set_pin("PA3", "pwm", periph="TM2")
    assert p.timer("TM2")["mode"] == "pwm"
    p.set_pin("PA3", "unused")
    assert p.timer("TM2")["mode"] == "off"
    assert "PA3" not in p.pins
    p.set_pin("PA4", "comp_plus")
    assert p.data["comparator"]["plus"] == "PA4" and p.data["comparator"]["enabled"]
    p.set_pin("PA4", "output")
    assert p.data["comparator"]["plus"] == "VINTR"


def test_chip_switch_keeps_what_fits():
    p = Project(default_project("PFS154"))
    p.set_pin("PA4", "output", label="LED")
    p.set_pin("PB3", "output", label="AUX")
    p.set_chip("PMS150C")
    assert p.pins == {"PA4": {"fn": "output", "initial": 0, "label": "LED"}}
    assert set(p.data["timers"]) == {"T16", "TM2"}


def random_project(rng, chip_name):
    p = Project(default_project(chip_name, "rnd"))
    chip = p.chip
    p.data["package"] = rng.choice(chip.packages).key
    for pin, info in chip.pins.items():
        if rng.random() < 0.5:
            continue
        fn = rng.choice(info.functions)
        opts = {}
        if fn in ("output", "input", "interrupt") and rng.random() < 0.7:
            opts["label"] = f"P_{pin}"
        if fn == "interrupt":
            opts["edge"] = rng.choice(["rise", "fall", "both"])
        try:
            p.set_pin(pin, fn, **opts)
        except ValueError:
            pass
    for t in chip.timers:
        cfg = p.data["timers"][t]
        if cfg["mode"] == "off" and t in ("T16", "TM2", "TM3") and rng.random() < 0.3:
            cfg["mode"] = "millis" if t == "T16" else "tick"
        cfg["freq_hz"] = rng.choice([50, 500, 1000, 4000, 20000])
        cfg["tick_hz"] = rng.choice([100, 1000, 8000])
        cfg["duty"] = rng.choice([0, 10, 50, 100])
    p.data["clock"] = rng.choice(["IHRC_DIV2", "IHRC_DIV4", "IHRC_DIV16", "ILRC"])
    p.data["vdd_mv"] = rng.choice([3300, 5000])
    p.data["system"]["watchdog"] = rng.choice(["off", "16K"])
    p.data["system"]["lvr"] = rng.choice(["auto", "off", chip.lvr_levels[-1][0]])
    comp = p.data["comparator"]
    comp["irq"] = rng.choice(["off", "rise", "both"])
    comp["range"] = rng.choice(["R1", "R2", "R3", "R4"])
    return p


@pytest.mark.skipif(not SDCC, reason="sdcc not found")
@pytest.mark.parametrize("chip", ["PFS154", "PFS122", "PMS150C"])
def test_random_setups_compile(tmp_path, chip):
    rng = random.Random(1234 + len(chip))
    built = 0
    for i in range(25):
        p = random_project(rng, chip)
        if checks.errors(p):
            continue
        folder = str(tmp_path / f"r{i}")
        codegen.write_project(p, folder)
        res = toolchain.build(p)
        msgs = "\n".join(f"{m.file}:{m.line}: {m.text}" for m in res.messages)
        assert res.ok, f"{p.to_json()}\n{res.log}\n{msgs}"
        assert not [m for m in res.messages if m.kind == "warning"], f"{p.to_json()}\n{msgs}"
        built += 1
    assert built >= 5
