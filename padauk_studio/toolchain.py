"""Find and run the bundled tools: SDCC, easypdkprog, dfu-util.

Search order for each tool: the path set in Settings, the copy bundled with
Padauk Studio (tools/ next to the app, or inside the one-file executable),
then the system PATH.
"""

import glob
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Tuple

from .project import Project

EXE = ".exe" if os.name == "nt" else ""
CONFIG_DIR = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~/.config"), "padauk-studio")
CONFIG_FILE = os.path.join(CONFIG_DIR, "settings.json")


def app_dir() -> str:
    """Folder with the bundled resources (tools/, firmware/, examples/)."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def bundled_tools_dir() -> Optional[str]:
    cands = [os.path.join(app_dir(), "tools")]
    if not getattr(sys, "frozen", False):
        # development checkout: packaging/fetch_tools.py puts them here
        root = os.path.dirname(app_dir())
        plat = "windows" if os.name == "nt" else "linux"
        cands.append(os.path.join(root, "packaging", f"tools-{plat}"))
    for c in cands:
        if os.path.isdir(c):
            return c
    return None


def firmware_file() -> Optional[str]:
    files = sorted(glob.glob(os.path.join(app_dir(), "firmware", "*.dfu")))
    return files[-1] if files else None


def load_settings() -> dict:
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_settings(data: dict):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def find_tool(name: str) -> Tuple[Optional[str], str]:
    """(path, where) for sdcc / easypdkprog / dfu-util. where: settings, bundled or PATH."""
    s = load_settings().get("paths", {}).get(name)
    if s and os.path.isfile(s):
        return s, "settings"
    tdir = bundled_tools_dir()
    if tdir:
        for rel in (f"sdcc/bin/{name}{EXE}", f"{name}{EXE}", f"bin/{name}{EXE}"):
            cand = os.path.join(tdir, rel)
            if os.path.isfile(cand):
                return cand, "bundled"
    p = shutil.which(name)
    if p:
        return p, "PATH"
    if os.name == "nt" and name == "sdcc":
        for base in (os.environ.get("ProgramFiles", r"C:\Program Files"), r"C:\Program Files (x86)"):
            cand = os.path.join(base, "SDCC", "bin", "sdcc.exe")
            if os.path.isfile(cand):
                return cand, "installed"
    return None, ""


def _popen_kwargs():
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = 0x08000000   # CREATE_NO_WINDOW
    return kw


def run(cmd: List[str], cwd=None, timeout=120) -> Tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, **_popen_kwargs())
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except FileNotFoundError:
        return 127, f"not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"timed out: {' '.join(cmd)}"


def tool_version(name: str) -> str:
    path, _ = find_tool(name)
    if not path:
        return ""
    flag = {"sdcc": "--version", "easypdkprog": "--version", "dfu-util": "--version"}[name]
    code, out = run([path, flag], timeout=15)
    line = out.strip().splitlines()[0] if out.strip() else ""
    return line


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

MSG_RE = re.compile(r"^(?P<file>[^:\n]+?\.[ch]):(?P<line>\d+):\s*(?:(?P<kind>error|warning)\s*\d*:?|(?P<syntax>syntax error:))\s*(?P<text>.*)$")


@dataclass
class Message:
    kind: str          # error / warning
    file: str
    line: int
    text: str


@dataclass
class BuildResult:
    ok: bool
    ihx: Optional[str] = None
    log: str = ""
    messages: List[Message] = field(default_factory=list)
    rom_words: int = 0
    rom_total: int = 0
    ram_bytes: int = 0
    ram_total: int = 0


def parse_messages(text: str, folder: str) -> List[Message]:
    out = []
    for line in text.splitlines():
        m = MSG_RE.match(line.strip())
        if not m:
            continue
        kind = "error" if (m.group("kind") == "error" or m.group("syntax")) else "warning"
        f = m.group("file")
        if not os.path.isabs(f):
            f = os.path.join(folder, f)
        txt = m.group("text")
        if m.group("syntax"):
            txt = "syntax error: " + txt
        out.append(Message(kind, os.path.normpath(f), int(m.group("line")), txt))
    return out


def ihx_addresses(path: str) -> List[int]:
    addrs = []
    base = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line.startswith(":"):
                continue
            n = int(line[1:3], 16)
            a = int(line[3:7], 16)
            t = int(line[7:9], 16)
            if t == 0:
                addrs.extend(range(base + a, base + a + n))
            elif t == 4:
                base = int(line[9:13], 16) << 16
    return addrs


def sizes(project: Project, ihx: str, mapfile: str) -> Tuple[int, int]:
    chip = project.chip
    words = {a // 2 for a in ihx_addresses(ihx) if a // 2 != chip.fuse_addr}
    rom = (max(words) + 1) if words else 0
    ram = 0
    try:
        with open(mapfile) as f:
            m = re.search(r"([0-9A-Fa-f]{8})\s+s_SSEG\b", f.read())
            if m:
                ram = int(m.group(1), 16)
    except OSError:
        pass
    return rom, ram


def sources(folder: str) -> List[str]:
    files = sorted(glob.glob(os.path.join(folder, "*.c")) + glob.glob(os.path.join(folder, "src", "*.c")))
    # main.c first, so its symbols lead the map file
    files.sort(key=lambda f: (os.path.basename(f) != "main.c", f))
    return files


def build(project: Project, log: Callable[[str], None] = lambda s: None) -> BuildResult:
    folder = project.path
    chip = project.chip
    sdcc, where = find_tool("sdcc")
    res = BuildResult(False, rom_total=chip.reserved_rom[0], ram_total=chip.ram_bytes)
    if not sdcc:
        res.log = "SDCC not found. Set its path in Settings, or install SDCC 4.2 or newer."
        log(res.log)
        return res
    out = os.path.join(folder, "build")
    os.makedirs(out, exist_ok=True)
    for f in glob.glob(os.path.join(out, "*.rel")):
        os.remove(f)
    rels = []
    alltext = ""
    base = ["-m" + chip.arch, "--std-sdcc11", "--opt-code-size", "--fverbose-asm", "-I", folder]
    srcs = sources(folder)
    if not srcs:
        res.log = "No .c files in the project folder."
        log(res.log)
        return res
    for src in srcs:
        rel = os.path.join(out, os.path.splitext(os.path.basename(src))[0] + ".rel")
        rel_name = os.path.relpath(src, folder)
        log(f"Compiling {rel_name}")
        code, text = run([sdcc] + base + ["-c", "-o", rel, rel_name], cwd=folder)
        text = "\n".join(l for l in text.splitlines() if l.strip())
        if text:
            log(text)
        alltext += text + "\n"
        if code != 0:
            res.log = alltext
            res.messages = parse_messages(alltext, folder)
            if not any(m.kind == "error" for m in res.messages):
                res.messages.append(Message("error", src, 1, f"sdcc failed (exit {code})"))
            return res
        rels.append(rel)
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", project.name) or "firmware"
    ihx = os.path.join(out, name + ".ihx")
    log("Linking")
    code, text = run([sdcc, "-m" + chip.arch, "--out-fmt-ihx", "-o", ihx] + rels, cwd=folder)
    text = "\n".join(l for l in text.splitlines() if l.strip())
    if text:
        log(text)
    alltext += text + "\n"
    res.messages = parse_messages(alltext, folder)
    if code != 0 or not os.path.exists(ihx):
        res.log = alltext
        if "overlap" in text.lower() or "too big" in text.lower() or "overflow" in text.lower():
            res.messages.append(Message("error", "", 0, "The program doesn't fit in the chip's memory."))
        else:
            res.messages.append(Message("error", "", 0, f"Linking failed (exit {code})"))
        return res
    rom, ram = sizes(project, ihx, os.path.splitext(ihx)[0] + ".map")
    res.rom_words, res.ram_bytes = rom, ram
    res.ihx = ihx
    res.log = alltext
    if rom > chip.reserved_rom[0]:
        res.messages.append(Message("error", "", 0,
                                    f"Program is {rom} words; the {chip.name} has {chip.reserved_rom[0]} "
                                    "(the rest holds calibration data)."))
        return res
    free_stack = chip.ram_bytes - ram
    if free_stack < 12:
        res.messages.append(Message("warning", "", 0,
                                    f"Only {free_stack} bytes of RAM left for the stack: "
                                    "deep calls or interrupts may crash."))
    res.ok = True
    return res


# ---------------------------------------------------------------------------
# Programmer
# ---------------------------------------------------------------------------

def prog_base(project: Optional[Project] = None) -> Optional[List[str]]:
    exe, _ = find_tool("easypdkprog")
    if not exe:
        return None
    cmd = [exe]
    port = load_settings().get("port", "")
    if port:
        cmd += ["-p", port]
    if project is not None:
        cmd += ["-n", project.chip.name]
    return cmd


def cmd_probe() -> Optional[List[str]]:
    b = prog_base()
    return b + ["-v", "probe"] if b else None


def cmd_write(project: Project, ihx: str) -> Optional[List[str]]:
    b = prog_base(project)
    return b + ["write", ihx] if b else None


def cmd_erase(project: Project) -> Optional[List[str]]:
    b = prog_base(project)
    return b + ["erase"] if b else None


def cmd_start(project: Project) -> Optional[List[str]]:
    b = prog_base(project)
    vdd = int(project.data.get("vdd_mv", 5000)) / 1000
    return b + ["-r", f"{vdd:.2f}", "start"] if b else None


def parse_probe(text: str) -> dict:
    info = {}
    m = re.search(r"Hardware:(\d+\.\d+)\s+Firmware:(\d+\.\d+)\s+Protocol:(\d+\.\d+)", text)
    if m:
        info["hardware"], info["firmware"], info["protocol"] = m.groups()
    m = re.search(r"IC is supported: ([A-Z0-9]+)", text)
    if m:
        info["ic"] = m.group(1)
    if "Unsupported IC" in text:
        info["ic"] = "unsupported"
    if "Nothing found" in text:
        info["ic"] = ""
    if "No programmer found" in text:
        info["error"] = "No programmer found. Is it plugged in? (Linux: are you in the dialout group?)"
    return info


def cmd_dfu(dfu_file: str) -> Optional[List[str]]:
    exe, _ = find_tool("dfu-util")
    if not exe:
        return None
    # the command from the easy-pdk-programmer-software README
    return [exe, "-d", "0483:df11", "-a", "@Internal Flash  /0x08000000/064*0002Kg",
            "--dfuse-address", "0x08000000", "-D", dfu_file]
