#!/usr/bin/env python3
"""Build a single-file 'Padauk Tools' GUI executable with PyInstaller.

pdk, template/ and examples/ are bundled, so the executable works on its own
(it still needs sdcc, make and easypdkprog installed). Output: PadaukBuilder/dist/
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def data(src, dest):
    return ["--add-data", os.path.join(REPO, src) + os.pathsep + dest]


def main():
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", os.path.join(HERE, "requirements.txt")], check=True)
    cmd = [sys.executable, "-m", "PyInstaller", "--onefile", "--windowed", "--noconfirm",
           "--name", "Padauk Tools",
           "--paths", HERE,
           "--hidden-import", "pdk_configurator", "--hidden-import", "pdk_codegen",
           "--hidden-import", "pdk_pinouts",
           *data("pdk", "."), *data("template", "template"), *data("examples", "examples"),
           os.path.join(HERE, "Padauk Tools.py")]
    subprocess.run(cmd, check=True, cwd=HERE)
    print("\nDone. Executable: " + os.path.join(HERE, "dist", "Padauk Tools"))


if __name__ == "__main__":
    main()
