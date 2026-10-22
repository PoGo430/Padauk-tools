"""Run the generated start-up code in ucsim_pdk (SDCC's simulator) and check the
registers it leaves behind, for every example on every chip.

The expected values are computed here from the chip database's field values,
independently of the C text the generator writes. So this checks the whole
chain: generator -> header macros -> SDCC -> start-up code actually running.
"""
import os
import re
import subprocess

import pytest

from padauk_studio import codegen, examples, toolchain

UCSIM = os.path.join(os.path.dirname(toolchain.find_tool("sdcc")[0] or ""), "ucsim_pdk" + toolchain.EXE)
pytestmark = pytest.mark.skipif(not os.path.isfile(UCSIM), reason="ucsim_pdk not found")
CASES = [(e["key"], c) for e in examples.EXAMPLES for c in e["chips"]]


def field(chip, reg, name, value=None):
    """Shifted value of a field from the database (independent of the C header)."""
    r = chip.reg_by_name[reg]
    for f in r.fields:
        if f.name == name:
            if value is None:
                return 1 << f.pos
            return f.values[value] << f.pos
    if name in r.consts:
        return r.consts[name]
    raise KeyError(f"{reg}.{name}")


def expected(p):
    chip = p.chip
    ctx = codegen.Context(p)
    plan = codegen.timer_plan(p)
    exp = {}
    clk = chip.reg_by_name["CLKMD"].consts[p.clock.clkmd] | field(chip, "CLKMD", "ILRC_EN")
    if "IHRC" in ctx.sources:
        clk |= field(chip, "CLKMD", "IHRC_EN")
    if p.data["system"]["watchdog"] != "off":
        clk |= field(chip, "CLKMD", "WDT_EN")
    exp["CLKMD"] = clk
    for port, v in codegen.port_values(ctx).items():
        P = "P" + port
        exp[P] = v["data"]
        exp[P + "C"] = v["dir"]
        exp[P + "PH"] = v["ph"]
        exp[P + "DIER"] = v["dier"]
        if chip.has_pull_down:
            exp[P + "PL"] = v["pl"]
    inten = 0
    for s in codegen.interrupt_sources(ctx, plan):
        reg, name = s["inten"].split("_", 1)
        inten |= field(chip, "INTEN", name)
    if p.serial_enabled():
        # pdk_init sends a sync character: the serial timer interrupt is on until it's out
        inten |= field(chip, "INTEN", p.data["serial"]["timer"])
    exp["INTEN"] = inten
    for name, s in plan.items():
        mode = p.timer(name)["mode"]
        if name.startswith("TM"):
            c = field(chip, f"{name}C", "CLK", s.source)
            if mode == "pwm":
                pin = next(pp for pp, cfg in p.pins.items() if cfg.get("periph") == name)
                c |= field(chip, f"{name}C", "OUT", pin) | field(chip, f"{name}C", "PWM")
            exp[f"{name}C"] = c
            exp[f"{name}S"] = field(chip, f"{name}S", "PRE", s.pre) | s.scale | (
                field(chip, f"{name}S", "PWM6") if s.res == 6 else 0)
            if mode != "pwm":
                exp[f"{name}B"] = s.bound
        elif name.startswith("PWMG"):
            pin = next(pp for pp, cfg in p.pins.items() if cfg.get("periph") == name)
            exp[f"{name}C"] = (field(chip, f"{name}C", "EN") | field(chip, f"{name}C", "OUT", pin)
                               | field(chip, f"{name}C", "CLK", s.source))
            exp[f"{name}CUBH"] = s.bound >> 2
            exp[f"{name}CUBL"] = (s.bound & 3) << 6
    return exp


def break_address(build_dir):
    """Word address right after main() calls pdk_init()."""
    with open(os.path.join(build_dir, "main.rst")) as f:
        for line in f:
            if re.search(r"\bcall\s+_pdk_init\b", line):
                return int(line.split()[0], 16) // 2 + 1
    raise AssertionError("call _pdk_init not found")


@pytest.mark.parametrize("key,chip", CASES)
def test_init_registers(tmp_path, key, chip):
    p, code = examples.make_project(key, chip)
    folder = str(tmp_path / "proj")
    os.makedirs(folder)
    with open(os.path.join(folder, "main.c"), "w") as f:
        f.write(examples.main_with_code(code))
    codegen.write_project(p, folder)
    res = toolchain.build(p)
    assert res.ok, res.log
    exp = expected(p)
    regs = p.chip.reg_by_name
    # ucsim's generic pdk models have a multiplier at 0x08/0x09, where these chips have MISC / TM2B
    names = [n for n in exp if n in regs and regs[n].addr not in (0x08, 0x09)]
    # factory calibration values are RET k instructions in the reserved ROM area
    ret = 0x0100 if p.chip.arch == "pdk13" else 0x0200
    patches = [f"set memory rom 0x{a:x} 0x{ret | 0x80:04x}"
               for a in (p.chip.factory_bgtr, p.chip.factory_ihrcr) if a is not None]
    cmds = patches + [f"break 0x{break_address(os.path.join(folder, 'build')):x}", "run",
            "dump regs8 0 0x3f 1", "quit"]
    out = subprocess.run([UCSIM, "-t", p.chip.arch, res.ihx], input="\n".join(cmds) + "\n",
                         capture_output=True, text=True, timeout=30).stdout
    assert "Breakpoint" in out, out[-2000:]
    mem, addr = {}, None
    for line in out.split("Host usage", 1)[1].splitlines():
        m = re.match(r"^(?:0x([0-9a-f]+))?\s*(?:\w+:)?\s*([0-9a-f]{2})?\s", line + " ")
        if not m:
            continue
        if m.group(1):
            addr = int(m.group(1), 16)
        if m.group(2) and addr is not None:
            mem[addr] = int(m.group(2), 16)
    got = {n: mem[regs[n].addr] for n in names}
    bad = {n: (hex(got[n]), hex(exp[n])) for n in names if got[n] != exp[n]}
    assert not bad, f"register (got, expected): {bad}"


def test_clkmd_matches_datasheet_examples():
    """Datasheet 5.4.6 (PFS154): 0x34 = IHRC/2 with IHRC+ILRC on, 0xF4 = ILRC with both on."""
    from padauk_studio import chips
    c = chips.get("PFS154")
    on = field(c, "CLKMD", "IHRC_EN") | field(c, "CLKMD", "ILRC_EN")
    assert c.reg_by_name["CLKMD"].consts["CLKMD_SYSCLK_IHRC_DIV2"] | on == 0x34
    assert c.reg_by_name["CLKMD"].consts["CLKMD_SYSCLK_ILRC"] | on == 0xF4


@pytest.mark.parametrize("chip,clock", [("PFS154", "IHRC_DIV2"), ("PFS154", "IHRC_DIV16"),
                                        ("PMS150C", "IHRC_DIV4"), ("PFS122", "ILRC")])
def test_delay_ms(tmp_path, chip, clock):
    """delay_ms(500) in the blink example takes 500 ms of simulated cycles (within 2 %; 6 % on the
    ~56 kHz ILRC, where a millisecond is only 56 cycles)."""
    p, code = examples.make_project("blink", chip)
    p.data["clock"] = clock
    folder = str(tmp_path / "proj")
    os.makedirs(folder)
    with open(os.path.join(folder, "main.c"), "w") as f:
        f.write(examples.main_with_code(code))
    codegen.write_project(p, folder)
    res = toolchain.build(p)
    assert res.ok, res.log
    with open(os.path.join(folder, "build", "main.rst")) as f:
        call = [int(line.split()[0], 16) // 2 for line in f if re.search(r"call\s+_delay_ms\b", line)][0]
    cmds = f"break 0x{call:x}\nbreak 0x{call + 1:x}\nrun\nrun\nquit\n"
    out = subprocess.run([UCSIM, "-t", p.chip.arch, res.ihx], input=cmds,
                         capture_output=True, text=True, timeout=60).stdout
    ticks = [int(t) for t in re.findall(r"Simulated (\d+) ticks", out)]
    assert len(ticks) >= 2, out[-1500:]
    want = 0.5 * p.f_cpu
    tol = 0.06 if p.clock.source == "ILRC" else 0.02
    assert abs(ticks[-1] - want) / want < tol, (ticks[-1], want)
