#!/usr/bin/env python3
"""Build a single-file 'Padauk Tools' executable with PyInstaller.

The template/ and examples/ folders are bundled, so "New project..." works
from the executable too. Output goes to PadaukBuilder/dist/.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


def main():
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", os.path.join(HERE, "requirements.txt")], check=True)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",
        "--noconfirm",
        "--name", "Padauk Tools",
        "--add-data", os.path.join(REPO, "template") + os.pathsep + "template",
        "--add-data", os.path.join(REPO, "examples") + os.pathsep + "examples",
        os.path.join(HERE, "Padauk Tools.py"),
    ]
    subprocess.run(cmd, check=True, cwd=HERE)
    print("\nDone. Executable: " + os.path.join(HERE, "dist", "Padauk Tools"))


if __name__ == "__main__":
    main()
