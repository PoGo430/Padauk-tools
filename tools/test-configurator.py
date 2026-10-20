#!/usr/bin/env python3
"""Fuzz test for the Padauk Configurator: random valid pin setups for each chip,
generate pdk_init.c/h, hook main.c, and compile with SDCC.

  tools/test-configurator.py [runs-per-device]     (default 25)
"""
import os
import random
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "PadaukBuilder"))
import pdk_codegen as g  # noqa: E402

RESOURCE = {"tm2_pwm": "TM2", "serial_tx": "TM2", "tm3_pwm": "TM3", "pwmg0": "G0", "pwmg1": "G1",
            "pwmg2": "G2", "comp_minus": "CM"}


def random_config(device, rnd):
    cfg = g.default_config(device)
    pkg = rnd.choice(g.packages(device))
    cfg["package"] = pkg["parts"][0]
    cfg["pins"] = {}
    used = set()
    for pin in sorted(p for p in set(pkg["pins"]) if p.startswith("P")):
        if rnd.random() < 0.2:
            continue
        funcs = g.pin_functions(device, pin)
        rnd.shuffle(funcs)
        for fn in funcs:
            res = RESOURCE.get(fn)
            if fn == "int":
                res = g.chip(device)["ints"][pin][0]
            if res and res in used:
                continue
            if res:
                used.add(res)
            e = {"function": fn, "name": f"{fn.upper()}_{pin}"}
            if fn in ("gpio_out", "gpio_od"):
                e["init"] = rnd.choice(["low", "high"])
            if fn in ("gpio_in", "int"):
                opts = ["none", "up"] + (["down"] if pin in g.pin_info(device)["pull_down"] else [])
                e["pull"] = rnd.choice(opts)
            if fn == "int":
                e["edge"] = rnd.choice(["both", "rising", "falling"])
            cfg["pins"][pin] = e
            if fn in g.PWM_FUNCS:
                cfg["pwm"][fn] = {"freq": rnd.choice([50, 500, 1000, 4000, 20000, 62500]),
                                  "duty": rnd.randint(0, 100), "invert": rnd.random() < 0.5}
            break
    cfg["comp"]["enabled"] = rnd.random() < 0.3
    cfg["comp"]["minus"] = "bandgap"
    cfg["comp"]["interrupt"] = rnd.random() < 0.5
    cfg["comp"]["edge"] = rnd.choice(["both", "rising", "falling"])
    cfg["comp"]["range"] = rnd.randint(1, 4)
    cfg["comp"]["level"] = rnd.randint(0, 15)
    s = cfg["system"]
    s["unused_pins"] = rnd.choice(["pullup", "output_low", "float"])
    s["millis"] = rnd.random() < 0.4
    s["watchdog"] = rnd.choice(["off", "8k", "16k", "64k", "256k"])
    s["fuses"] = rnd.random() < 0.8
    s["bootup"] = rnd.choice(["slow", "fast"])
    s["drive"] = rnd.choice(g.chip(device)["drive_fuse"])[0]
    s["lvr"] = rnd.choice([None] + g.chip(device)["lvr"][1])
    return cfg


def main():
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    rnd = random.Random(1234)
    fails = 0
    with tempfile.TemporaryDirectory() as tmp:
        for device in g.SUPPORTED:
            proj = os.path.join(tmp, device)
            subprocess.run([os.path.join(ROOT, "pdk"), "new", proj, "-d", device, "--no-code"],
                           check=True, stdout=subprocess.DEVNULL)
            ok = 0
            for i in range(runs):
                cfg = random_config(device, rnd)
                f_cpu = rnd.choice([8_000_000, 4_000_000, 1_000_000])
                errors, _ = g.check(cfg, f_cpu, 5000)
                if errors:
                    print(f"  {device} #{i}: config rejected: {errors}")
                    fails += 1
                    continue
                g.write_generated(proj, cfg, f_cpu, 5000)
                g.hook_main(proj)
                r = subprocess.run(["make", "-s", "build", f"F_CPU={f_cpu}"], cwd=proj,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
                out = r.stdout.decode(errors="replace")
                warn = [l for l in out.splitlines() if "pdk_init" in l and "warning" in l]
                if r.returncode != 0 or warn:
                    fails += 1
                    print(f"  FAIL {device} #{i}  pins={ {p: e['function'] for p, e in cfg['pins'].items()} }")
                    print("    " + "\n    ".join(out.strip().splitlines()[-12:]))
                    src = open(os.path.join(proj, "pdk_init.c")).read().splitlines()
                    for w in warn:
                        line = int(w.split(":")[1])
                        print(f"    line {line}: {src[line - 1].strip()}")
                else:
                    ok += 1
            print(f"  {device}: {ok}/{runs} random configurations compiled")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
