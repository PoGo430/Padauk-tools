"""Padauk Studio.

    padauk-studio [FOLDER]                      open the GUI (on a project folder)
    padauk-studio new FOLDER [-c CHIP] [-e EXAMPLE]
    padauk-studio generate [FOLDER]             write pdk_init.c/h and main.c
    padauk-studio build [FOLDER]                generate + compile
    padauk-studio write [FOLDER]                build + write the chip
    padauk-studio monitor [FOLDER]              run the chip, print its serial output
    padauk-studio examples                      list the examples
    padauk-studio check                         show which tools were found
"""

import argparse
import os
import subprocess
import sys


def _project(folder):
    from .project import Project
    return Project.load(os.path.abspath(folder or "."))


def cli(argv):
    from . import __version__, checks, codegen, examples, toolchain
    from .project import Project, default_project

    ap = argparse.ArgumentParser(prog="padauk-studio", description="Padauk Studio " + __version__)
    sub = ap.add_subparsers(dest="cmd")
    n = sub.add_parser("new")
    n.add_argument("folder")
    n.add_argument("-c", "--chip", default="PFS154")
    n.add_argument("-e", "--example", default="")
    for c in ("generate", "build", "write", "monitor"):
        s = sub.add_parser(c)
        s.add_argument("folder", nargs="?", default=".")
    sub.add_parser("examples")
    sub.add_parser("check")
    a = ap.parse_args(argv)

    if a.cmd == "examples":
        for e in examples.EXAMPLES:
            print(f"{e['key']:18} {', '.join(e['chips']):24} {e['title']}")
        return 0
    if a.cmd == "check":
        for t in ("sdcc", "easypdkprog", "dfu-util"):
            path, where = toolchain.find_tool(t)
            print(f"{t:12} {path or 'NOT FOUND'} {f'({where})' if path else ''}")
        print(f"{'firmware':12} {toolchain.firmware_file() or 'NOT FOUND'}")
        return 0
    if a.cmd == "new":
        folder = os.path.abspath(a.folder)
        name = os.path.basename(folder)
        if a.example:
            p, code = examples.make_project(a.example, a.chip.upper(), name)
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, "main.c"), "w", encoding="utf-8") as f:
                f.write(examples.main_with_code(code))
        else:
            p = Project(default_project(a.chip.upper(), name))
        codegen.write_project(p, folder)
        print(f"Created {folder}")
        return 0

    p = _project(a.folder)
    found = checks.check(p)
    for lvl, text, where in found:
        if lvl != "info":
            print(f"{lvl}: {text}", file=sys.stderr)
    if any(f[0] == "error" for f in found):
        return 1
    if a.cmd == "generate":
        print("Generated:", ", ".join(codegen.write_project(p)) or "no changes")
        return 0
    if a.cmd in ("build", "write"):
        codegen.write_project(p)
        res = toolchain.build(p, log=print)
        for m in res.messages:
            loc = f"{m.file}:{m.line}: " if m.file else ""
            print(f"{loc}{m.kind}: {m.text}", file=sys.stderr)
        if not res.ok:
            return 1
        print(f"ROM {res.rom_words}/{res.rom_total} words, RAM {res.ram_bytes}/{res.ram_total} bytes")
        if a.cmd == "build":
            return 0
        if p.chip.otp and input(f"{p.chip.name} is one-time programmable. Write? [y/N] ").lower() != "y":
            return 1
        cmd = toolchain.cmd_write(p, res.ihx)
        return subprocess.call(cmd, env=toolchain.tool_env()) if cmd else 1
    if a.cmd == "monitor":
        cmd = toolchain.cmd_start(p)
        return subprocess.call(cmd, env=toolchain.tool_env()) if cmd else 1
    return 0


def _attach_console():
    """The Windows build is a GUI program: give command-line use the console it was started from."""
    if os.name == "nt" and getattr(sys, "frozen", False):
        import ctypes
        if ctypes.windll.kernel32.AttachConsole(-1):
            sys.stdout = open("CONOUT$", "w")
            sys.stderr = open("CONOUT$", "w")
            sys.stdin = open("CONIN$", "r")


def main():
    argv = sys.argv[1:]
    commands = {"new", "generate", "build", "write", "monitor", "examples", "check", "-h", "--help"}
    if argv and argv[0] in commands:
        _attach_console()
        sys.exit(cli(argv))
    from .ui.main_window import run
    sys.exit(run(argv[0] if argv else None))


if __name__ == "__main__":
    main()
