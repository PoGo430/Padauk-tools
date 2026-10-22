#!/usr/bin/env python3
"""Build the one-file Padauk Studio executable for this OS (Linux or Windows).

    python packaging/build.py            # tools + executable -> dist/
    python packaging/build.py --tools    # only fetch/build the tools

Steps:
 1. SDCC 4.6.0 (official binaries), trimmed to what pdk13/pdk14 need (~14 MB)
 2. easypdkprog from the PoGo430 fork (stable 1.3 + native PFS122), built from source
 3. dfu-util (programmer firmware updates)
 4. PyInstaller one-file executable with the tools, firmware and examples inside

Needs: Python 3.9+, pip install pyside6 pyinstaller, git, make and a C compiler
(Linux: build-essential; Windows: MSYS2 MinGW64 gcc + make on the PATH), and
on Linux the dfu-util and libusb-1.0 packages.
"""

import argparse
import glob
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WIN = os.name == "nt"
PLAT = "windows" if WIN else "linux"
TOOLS = os.path.join(HERE, f"tools-{PLAT}")
WORK = os.path.join(HERE, "work")

SDCC_VERSION = "4.6.0"
SDCC_URL = {
    "linux": f"https://downloads.sourceforge.net/project/sdcc/sdcc-linux-amd64/{SDCC_VERSION}/"
             f"sdcc-{SDCC_VERSION}-amd64-unknown-linux2.5.tar.bz2",
    "windows": f"https://downloads.sourceforge.net/project/sdcc/sdcc-win64/{SDCC_VERSION}/"
               f"sdcc-{SDCC_VERSION}-x64-setup.exe",
}
EASYPDK_REPO = "https://github.com/PoGo430/easy-pdk-programmer-software.git"
EASYPDK_COMMIT = "c24616d"     # master: "Native PFS122 support (firmware + software 1.4)"
DFU_UTIL_WIN = "https://downloads.sourceforge.net/project/dfu-util/dfu-util-0.11-binaries.tar.xz"

SDCC_BINS = ["sdcc", "sdcpp", "sdaspdk13", "sdaspdk14", "sdaspdk15", "sdldpdk", "makebin", "ucsim_pdk"]


def sh(cmd, cwd=None, env=None):
    print("+", " ".join(cmd) if isinstance(cmd, list) else cmd, flush=True)
    subprocess.check_call(cmd, cwd=cwd, env=env, shell=isinstance(cmd, str))


def download(url, dest):
    if os.path.exists(dest):
        return dest
    print("downloading", url, flush=True)
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Wget/1.21"})
            with urllib.request.urlopen(req, timeout=120) as r, open(dest + ".part", "wb") as f:
                shutil.copyfileobj(r, f)
            os.replace(dest + ".part", dest)
            return dest
        except OSError as e:
            print("  retry:", e, flush=True)
    raise SystemExit(f"download failed: {url}")


def sdcc():
    out = os.path.join(TOOLS, "sdcc")
    if os.path.exists(os.path.join(out, "bin", "sdcc" + (".exe" if WIN else ""))):
        return
    os.makedirs(WORK, exist_ok=True)
    if WIN:
        setup = download(SDCC_URL["windows"], os.path.join(WORK, "sdcc-setup.exe"))
        full = os.path.join(WORK, "sdcc-win")
        if not os.path.exists(full):
            sh([setup, "/S", f"/D={full}"])      # NSIS: silent install into this folder
        os.makedirs(os.path.join(out, "bin"), exist_ok=True)
        for b in SDCC_BINS:
            f = os.path.join(full, "bin", b + ".exe")
            if os.path.exists(f) or b in ("sdcc", "sdcpp", "sdaspdk13", "sdaspdk14", "sdldpdk"):
                shutil.copy2(f, os.path.join(out, "bin"))
        for dll in glob.glob(os.path.join(full, "bin", "*.dll")):
            shutil.copy2(dll, os.path.join(out, "bin"))
        shutil.copytree(os.path.join(full, "include"), os.path.join(out, "include"))
        for arch in ("pdk13", "pdk14", "pdk15"):
            shutil.copytree(os.path.join(full, "lib", arch), os.path.join(out, "lib", arch))
    else:
        tb = download(SDCC_URL["linux"], os.path.join(WORK, "sdcc.tar.bz2"))
        full = os.path.join(WORK, "sdcc-linux")
        if not os.path.exists(full):
            with tarfile.open(tb) as t:
                t.extractall(full)  # noqa: S202 (official SDCC archive)
        src = glob.glob(os.path.join(full, "sdcc-*"))[0]
        os.makedirs(os.path.join(out, "bin"), exist_ok=True)
        for b in SDCC_BINS:
            shutil.copy2(os.path.join(src, "bin", b), os.path.join(out, "bin"))
        if os.path.isdir(os.path.join(src, "libexec")):
            shutil.copytree(os.path.join(src, "libexec"), os.path.join(out, "libexec"))
        shutil.copytree(os.path.join(src, "share", "sdcc", "include"), os.path.join(out, "share", "sdcc", "include"))
        for arch in ("pdk13", "pdk14", "pdk15"):
            shutil.copytree(os.path.join(src, "share", "sdcc", "lib", arch),
                            os.path.join(out, "share", "sdcc", "lib", arch))
    with open(os.path.join(out, "README.txt"), "w") as f:
        f.write(f"SDCC {SDCC_VERSION} (https://sdcc.sourceforge.net), trimmed to the Padauk (pdk) parts.\n"
                "SDCC is free software (GPL); its source code is on SourceForge.\n")


def easypdkprog():
    exe = os.path.join(TOOLS, "easypdkprog" + (".exe" if WIN else ""))
    if os.path.exists(exe):
        return
    src = os.path.join(WORK, "easy-pdk-programmer-software")
    if not os.path.exists(src):
        sh(["git", "clone", EASYPDK_REPO, src])
    sh(["git", "checkout", "-q", EASYPDK_COMMIT], cwd=src)
    env = dict(os.environ)
    make = ["make", "easypdkprog"]
    if WIN:
        make.append("LDFLAGS=-static")       # no MinGW DLLs needed next to it
    sh(make, cwd=src, env=env)
    shutil.copy2(os.path.join(src, "easypdkprog" + (".exe" if WIN else "")), exe)
    shutil.copy2(os.path.join(src, "LICENSE"), os.path.join(TOOLS, "easypdkprog-LICENSE.txt"))
    # the prebuilt programmer firmware in the fork must be the one we ship
    fw_src = os.path.join(src, "Firmware", "EASYPDKPROG_1.4.dfu")
    fw_ours = os.path.join(ROOT, "padauk_studio", "firmware", "EASYPDKPROG_1.4.dfu")
    if open(fw_src, "rb").read() != open(fw_ours, "rb").read():
        raise SystemExit("padauk_studio/firmware/EASYPDKPROG_1.4.dfu differs from the fork's firmware")


def dfu_util():
    if WIN:
        exe = os.path.join(TOOLS, "dfu-util.exe")
        if os.path.exists(exe):
            return
        tx = download(DFU_UTIL_WIN, os.path.join(WORK, "dfu-util.tar.xz"))
        d = os.path.join(WORK, "dfu-util")
        if not os.path.exists(d):
            with tarfile.open(tx) as t:
                t.extractall(d)
        win64 = glob.glob(os.path.join(d, "*", "win64"))[0]
        for f in os.listdir(win64):
            if f.endswith((".exe", ".dll")):
                shutil.copy2(os.path.join(win64, f), TOOLS)
    else:
        exe = os.path.join(TOOLS, "dfu-util")
        if os.path.exists(exe):
            return
        sysexe = shutil.which("dfu-util")
        if not sysexe:
            print("WARNING: dfu-util not installed (sudo apt install dfu-util): firmware updates will need "
                  "a system dfu-util", flush=True)
            return
        shutil.copy2(sysexe, exe)
        # libusb is the one library dfu-util needs that a desktop may not have
        os.makedirs(os.path.join(TOOLS, "lib"), exist_ok=True)
        out = subprocess.check_output(["ldd", sysexe], text=True)
        for line in out.splitlines():
            if "libusb-1.0" in line and "=>" in line:
                lib = line.split("=>")[1].split()[0]
                shutil.copy2(lib, os.path.join(TOOLS, "lib", os.path.basename(lib)))


def pyinstaller():
    sep = ";" if WIN else ":"
    name = "padauk-studio"
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed", "--name", name,
            "--distpath", os.path.join(ROOT, "dist"), "--workpath", os.path.join(WORK, "pyinstaller"),
            "--specpath", WORK,
            "--add-data", f"{TOOLS}{sep}tools",
            "--add-data", f"{os.path.join(ROOT, 'padauk_studio', 'firmware')}{sep}firmware",
            "--exclude-module", "tkinter",
            ]
    for mod in ("QtWebEngineCore", "QtWebEngineWidgets", "QtQml", "QtQuick", "QtPdf", "Qt3DCore",
                "QtMultimedia", "QtCharts", "QtDataVisualization", "QtNetwork", "QtSql", "QtBluetooth",
                "QtPositioning", "QtSensors", "QtSerialPort", "QtWebChannel", "QtWebSockets", "QtOpenGL"):
        args += ["--exclude-module", f"PySide6.{mod}"]
    args.append(os.path.join(HERE, "launcher.py"))
    sh(args, cwd=ROOT)
    print("built", os.path.join(ROOT, "dist", name + (".exe" if WIN else "")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tools", action="store_true", help="only fetch/build the tools")
    a = ap.parse_args()
    os.makedirs(TOOLS, exist_ok=True)
    sdcc()
    easypdkprog()
    dfu_util()
    if not a.tools:
        pyinstaller()


if __name__ == "__main__":
    main()
