#!/usr/bin/env python3
"""
Padauk Tools - GUI for Padauk projects (SDCC + Easy PDK programmer).

Works on the same project folders as VS Code and the `pdk` command, so you
can switch between them freely. Start it with `pdk gui` or run this file.

  Ctrl+B  build        Ctrl+U  flash        Ctrl+M  monitor        Esc  stop
"""
import argparse
import contextlib
import importlib.machinery
import importlib.util
import io
import os
import re
import shutil
import signal
import subprocess
import sys

from PyQt5.QtCore import QProcess, QSettings, Qt, QTimer
from PyQt5.QtGui import QColor, QFont, QKeySequence, QTextCharFormat, QTextCursor
from PyQt5.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QShortcut,
    QVBoxLayout, QWidget,
)

APP_NAME = "Padauk Tools"


# ----------------------------------------------------------------------------
# Load the `pdk` script as a module, so the GUI and the CLI share one implementation
# ----------------------------------------------------------------------------
def resource_dir():
    if getattr(sys, "frozen", False):                      # PyInstaller bundle
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


def load_pdk():
    path = os.path.join(resource_dir(), "pdk")
    loader = importlib.machinery.SourceFileLoader("pdk", path)
    spec = importlib.util.spec_from_loader("pdk", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    module.COLOR = False
    return module


pdk = load_pdk()

CLOCKS = [("8 MHz", "8000000"), ("4 MHz", "4000000"), ("2 MHz", "2000000"), ("1 MHz", "1000000"),
          ("500 kHz", "500000"), ("250 kHz", "250000"), ("16 MHz (overclocked)", "16000000")]
VOLTAGES = [("5.0 V", "5000"), ("4.0 V", "4000"), ("3.3 V", "3300"), ("3.0 V", "3000"), ("2.5 V", "2500")]

USE_SETSID = os.name == "posix" and shutil.which("setsid") is not None
ERROR_LINE = re.compile(r"^([^:\s][^:]*):(\d+):\s+(error|warning)")


def call_pdk(func, **kwargs):
    """Run a pdk command function, return (ok, printed output)."""
    out = io.StringIO()
    ok = True
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        try:
            func(argparse.Namespace(**kwargs))
        except SystemExit as e:
            ok = not e.code
    return ok, out.getvalue()


def device_label(name, info):
    arch, rom, ram, mem = info
    kind = "flash" if mem == "mtp" else "OTP"
    return f"{name}   ({kind}, {rom // 1024 if rom % 1024 == 0 else rom / 1024:g}K ROM, {ram} B RAM)"


# ----------------------------------------------------------------------------
class NewProjectDialog(QDialog):
    def __init__(self, parent, devices):
        super().__init__(parent)
        self.setWindowTitle("New project")
        form = QFormLayout(self)

        self.name = QLineEdit("MyProject")
        form.addRow("Name:", self.name)

        loc_row = QHBoxLayout()
        self.location = QLineEdit(QSettings("Padauk-tools", APP_NAME).value(
            "new_project_parent", os.path.expanduser("~")))
        browse = QPushButton("...")
        browse.setFixedWidth(32)
        browse.clicked.connect(self.browse)
        loc_row.addWidget(self.location, 1)
        loc_row.addWidget(browse)
        form.addRow("Create in:", loc_row)

        self.device = QComboBox()
        for name in sorted(devices, key=lambda n: (n not in pdk.MAIN_CHIPS, n)):
            self.device.addItem(device_label(name, devices[name]), name)
        form.addRow("Chip:", self.device)

        self.example = QComboBox()
        self.example.addItem("Blink (template)", "")
        for name in sorted(os.listdir(pdk.EXAMPLES)):
            if os.path.isfile(os.path.join(pdk.EXAMPLES, name, "main.c")):
                self.example.addItem(name, name)
        form.addRow("Start from:", self.example)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)
        self.resize(480, 0)

    def browse(self):
        path = QFileDialog.getExistingDirectory(self, "Create the project in...", self.location.text())
        if path:
            self.location.setText(path)

    def values(self):
        return (self.name.text().strip(), self.location.text().strip(),
                self.device.currentData(), self.example.currentData())


# ----------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self, start_dir=None):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(940, 700)
        self.settings = QSettings("Padauk-tools", APP_NAME)
        self.project = None
        self.devices = pdk.load_devices()
        self.loading = False
        self.output_buffer = ""

        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.on_output)
        self.process.finished.connect(self.on_finished)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(self.build_project_box())
        top = QHBoxLayout()
        top.addWidget(self.build_settings_box(), 3)
        top.addWidget(self.build_memory_box(), 2)
        layout.addLayout(top)
        layout.addWidget(self.build_actions_box())

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(5000)
        font = QFont("Monospace")
        font.setStyleHint(QFont.TypeWriter)
        self.output.setFont(font)
        self.output.mouseDoubleClickEvent = self.on_output_double_click
        self.output.setToolTip("Double-click an error line to open the file")
        layout.addWidget(self.output, 1)
        self.setCentralWidget(root)

        for keys, slot in [("Ctrl+B", lambda: self.run_make("all")), ("Ctrl+U", self.flash),
                           ("Ctrl+M", lambda: self.run_make("run")), ("Esc", self.stop_process)]:
            QShortcut(QKeySequence(keys), self, activated=slot)

        start = start_dir or self.settings.value("project_dir", "")
        self.set_project(pdk.find_project(start) if start else pdk.find_project())
        if not self.project:
            self.log("Open a project folder, or create a new one.\n", "dim")

    # ----- UI -----------------------------------------------------------------
    def build_project_box(self):
        box = QGroupBox("Project")
        row = QHBoxLayout(box)
        self.project_label = QLabel()
        self.project_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(self.project_label, 1)
        for text, slot in [("Open...", self.open_project), ("New...", self.new_project)]:
            btn = QPushButton(text)
            btn.clicked.connect(slot)
            row.addWidget(btn)
        self.config_btn = QPushButton("Configure pins...")
        self.config_btn.setToolTip("Pin and peripheral configurator: click pins, generate init code")
        self.config_btn.clicked.connect(self.open_configurator)
        row.addWidget(self.config_btn)
        self.code_btn = QPushButton("Open in VS Code")
        self.code_btn.clicked.connect(self.open_in_code)
        self.code_btn.setVisible(shutil.which("code") is not None)
        row.addWidget(self.code_btn)
        return box

    def build_settings_box(self):
        box = QGroupBox("Settings (saved to the Makefile)")
        form = QFormLayout(box)
        self.device = QComboBox()
        for name in sorted(self.devices, key=lambda n: (n not in pdk.MAIN_CHIPS, n)):
            self.device.addItem(device_label(name, self.devices[name]), name)
        self.device_note = QLabel()
        self.device_note.setStyleSheet("color: #b36b00")
        dev_col = QVBoxLayout()
        dev_col.addWidget(self.device)
        dev_col.addWidget(self.device_note)
        form.addRow("Chip:", dev_col)

        self.clock = QComboBox()
        for label, value in CLOCKS:
            self.clock.addItem(label, value)
        form.addRow("Clock:", self.clock)

        self.vdd = QComboBox()
        for label, value in VOLTAGES:
            self.vdd.addItem(label, value)
        self.vdd.setToolTip("Supply voltage of your circuit. The clock is calibrated for it,\n"
                            "and Monitor powers the chip at this voltage.")
        form.addRow("Supply:", self.vdd)

        for combo in (self.device, self.clock, self.vdd):
            combo.currentIndexChanged.connect(self.save_settings)
        self.settings_widgets = [self.device, self.clock, self.vdd]
        return box

    def build_memory_box(self):
        box = QGroupBox("Memory (last build)")
        grid = QGridLayout(box)
        self.rom_bar, self.ram_bar = QProgressBar(), QProgressBar()
        for row, (label, bar) in enumerate([("ROM", self.rom_bar), ("RAM", self.ram_bar)]):
            bar.setFormat("not built yet")
            bar.setValue(0)
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(bar, row, 1)
        return box

    def build_actions_box(self):
        box = QGroupBox()
        row = QHBoxLayout(box)
        self.action_buttons = []

        def add(text, slot, tip, primary=False):
            btn = QPushButton(text)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)
            if primary:
                btn.setStyleSheet("font-weight: bold")
            row.addWidget(btn)
            self.action_buttons.append(btn)
            return btn

        add("Build", lambda: self.run_make("all"), "Compile and show ROM/RAM usage (Ctrl+B)", True)
        add("Flash", self.flash, "Build and write the chip (Ctrl+U)", True)
        add("Flash + Monitor", lambda: self.flash(monitor=True), "Write the chip, then show its serial output")
        add("Monitor", lambda: self.run_make("run"), "Power the chip and show its serial output on PA7 (Ctrl+M)")
        row.addSpacing(12)
        add("Probe", lambda: self.run_make("probe"), "What chip is in the programmer?")
        add("Erase", self.erase, "Erase a flash chip")
        add("Clean", lambda: self.run_make("clean"), "Delete build output")
        row.addSpacing(12)
        self.doctor_btn = add("Doctor", self.doctor, "Check SDCC, make, easypdkprog and the programmer")
        add("Upgrade", self.upgrade, "Refresh include/, .vscode/ and the Makefile from the template")
        row.addStretch(1)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setToolTip("Stop the running command (Esc)")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_process)
        row.addWidget(self.stop_btn)
        return box

    # ----- Project --------------------------------------------------------------
    def set_project(self, path):
        self.project = path
        has = bool(path)
        self.project_label.setText(path or "(no project open)")
        for w in [b for b in self.action_buttons if b is not self.doctor_btn] + self.settings_widgets + \
                [self.code_btn, self.config_btn]:
            w.setEnabled(has)
        if not has:
            return
        self.settings.setValue("project_dir", path)
        self.setWindowTitle(f"{os.path.basename(path)} - {APP_NAME}")
        self.devices = pdk.load_devices(os.path.join(path, "Makefile")) or self.devices
        s = pdk.project_settings(path)
        self.loading = True
        self.select(self.device, s["DEVICE"], s["DEVICE"])
        self.select(self.clock, s["F_CPU"], f"{pdk.human_hz(int(s['F_CPU']))}")
        self.select(self.vdd, s["TARGET_VDD_MV"], f"{int(s['TARGET_VDD_MV']) / 1000:.2f} V")
        self.loading = False
        self.update_device_note()
        for bar in (self.rom_bar, self.ram_bar):
            bar.setValue(0)
            bar.setFormat("not built yet")

    @staticmethod
    def select(combo, value, label):
        i = combo.findData(value)
        if i < 0:
            combo.addItem(label, value)
            i = combo.count() - 1
        combo.setCurrentIndex(i)

    def open_project(self):
        path = QFileDialog.getExistingDirectory(self, "Open project folder", self.project or os.path.expanduser("~"))
        if not path:
            return
        project = pdk.find_project(path)
        if not project:
            QMessageBox.warning(self, APP_NAME, "That folder is not a Padauk project.\nUse New... to create one.")
            return
        self.set_project(project)
        self.output.clear()

    def new_project(self):
        dlg = NewProjectDialog(self, self.devices)
        if dlg.exec_() != QDialog.Accepted:
            return
        name, parent, device, example = dlg.values()
        if not name:
            return
        self.settings.setValue("new_project_parent", parent)
        dest = os.path.join(parent, name)
        ok, text = call_pdk(pdk.cmd_new, name=dest, device=device, example=example or None, no_code=True)
        self.output.clear()
        self.log(text.replace("pdk build", "press Build"), None if ok else "error")
        if ok:
            self.set_project(dest)

    def open_configurator(self):
        if not self.project:
            return
        sys.path.insert(0, os.path.join(resource_dir(), "PadaukBuilder"))
        sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
        import pdk_configurator
        self.configurator = pdk_configurator.ConfiguratorWindow(self.project, self)
        self.configurator.setWindowModality(Qt.WindowModal)
        self.configurator.generated.connect(self.on_generated)
        self.configurator.show()

    def on_generated(self, message):
        self.set_project(self.project)        # chip/clock may have changed
        self.output.clear()
        self.log(message + "\n", "good")

    def open_in_code(self):
        if self.project:
            subprocess.Popen(["code", self.project])

    def update_device_note(self):
        name = self.device.currentData()
        notes = []
        if name in pdk.DEV_BRANCH_ONLY:
            notes.append("needs development easypdkprog (docs/setup.md)")
        if self.devices.get(name, ("", 0, 0, ""))[3] == "otp":
            notes.append("one-time programmable")
        self.device_note.setText(", ".join(notes))
        self.device_note.setVisible(bool(notes))

    def save_settings(self):
        self.update_device_note()
        if self.loading or not self.project:
            return
        mk = os.path.join(self.project, "Makefile")
        with open(mk) as f:
            text = f.read()
        text = pdk.write_setting(text, "DEVICE", self.device.currentData())
        text = pdk.write_setting(text, "F_CPU", self.clock.currentData())
        text = pdk.write_setting(text, "TARGET_VDD_MV", self.vdd.currentData())
        with open(mk, "w") as f:
            f.write(text)
        pdk.write_intellisense(self.project, self.devices)
        self.statusBar().showMessage("Settings saved to the Makefile", 3000)

    # ----- Commands ---------------------------------------------------------------
    def flash(self, monitor=False):
        if not self.project:
            return
        device = self.device.currentData()
        if self.devices.get(device, ("", 0, 0, ""))[3] == "otp":
            answer = QMessageBox.question(
                self, "One-time programmable chip",
                f"The {device} can only be written ONCE.\n\nWrite it now?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        self.run_make(*(["program", "run"] if monitor else ["program"]), "OTP_OK=1")

    def erase(self):
        device = self.device.currentData()
        if QMessageBox.question(self, "Erase", f"Erase the {device} in the programmer?") == QMessageBox.Yes:
            self.run_make("erase")

    def doctor(self):
        self.output.clear()
        self.log("Checking your setup...\n\n", "dim")
        QApplication.processEvents()
        ok, text = call_pdk(pdk.cmd_doctor, probe=True, project=self.project)
        self.log(text)

    def upgrade(self):
        if QMessageBox.question(
                self, "Upgrade project",
                "Refresh include/, .vscode/ and the Makefile from the template?\n\n"
                "Your settings and code are kept, and a backup is made.") != QMessageBox.Yes:
            return
        ok, text = call_pdk(pdk.cmd_upgrade, project=self.project)
        self.output.clear()
        self.log(text, None if ok else "error")
        self.set_project(self.project)

    def run_make(self, *args):
        if not self.project or self.process.state() != QProcess.NotRunning:
            return
        if not shutil.which("make"):
            QMessageBox.warning(self, APP_NAME, "'make' was not found. Click Doctor for help.")
            return
        self.output.clear()
        self.output_buffer = ""
        self.log("$ make " + " ".join(a for a in args if a != "OTP_OK=1") + "\n", "dim")
        self.process.setWorkingDirectory(self.project)
        cmd = ["make", "--no-print-directory", *args]
        # Own process group, so Stop also ends easypdkprog (e.g. Monitor)
        if USE_SETSID:
            self.process.start("setsid", cmd)
        else:
            self.process.start(cmd[0], cmd[1:])
        if not self.process.waitForStarted(3000):
            self.log("Could not start make.\n", "error")
            return
        self.set_running(True)

    def stop_process(self):
        if self.process.state() == QProcess.NotRunning:
            return
        pid = self.process.processId()
        if USE_SETSID and pid:
            try:
                os.killpg(pid, signal.SIGINT)
                QTimer.singleShot(2000, self.force_kill)
                return
            except (ProcessLookupError, PermissionError):
                pass
        self.process.kill()

    def force_kill(self):
        if self.process.state() == QProcess.NotRunning:
            return
        try:
            os.killpg(self.process.processId(), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            self.process.kill()

    def set_running(self, running):
        for btn in self.action_buttons:
            btn.setEnabled(not running and (bool(self.project) or btn is self.doctor_btn))
        for w in self.settings_widgets:
            w.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.statusBar().showMessage("Running... (Esc to stop)" if running else "")

    # ----- Output ---------------------------------------------------------------
    def on_output(self):
        self.output_buffer += self.process.readAllStandardOutput().data().decode(errors="replace")
        *lines, self.output_buffer = self.output_buffer.split("\n")
        for line in lines:
            self.log_line(line)

    def log_line(self, line):
        style = None
        low = line.lower()
        if ERROR_LINE.match(line) and " error" in line or low.startswith(("error", "make: ***")) or " error:" in low:
            style = "error"
        elif ERROR_LINE.match(line) or "warning" in low:
            style = "warning"
        elif line.lstrip().startswith(("rom:", "ram:", "ROM:", "RAM:")):
            style = "good"
        self.log(line + "\n", style)
        for bar, key in ((self.rom_bar, "ROM"), (self.ram_bar, "RAM")):
            m = re.search(rf"{key}:\s+(\d+)\s*/\s*(\d+)\s+(\w+)", line)
            if m:
                used, total, unit = int(m.group(1)), int(m.group(2)), m.group(3)
                bar.setMaximum(total)
                bar.setValue(min(used, total))
                bar.setFormat(f"{used} / {total} {unit}  (%p%)")
                pct = used * 100 // max(total, 1)
                color = "#c62828" if pct >= 90 else "#ef8f00" if pct >= 75 else "#2e7d32"
                bar.setStyleSheet(f"QProgressBar::chunk {{ background: {color}; }}")

    def on_finished(self, code, status):
        if self.output_buffer:
            self.log_line(self.output_buffer)
            self.output_buffer = ""
        if status == QProcess.CrashExit or code in (130, -signal.SIGINT):
            self.log("\n[stopped]\n", "dim")
        elif code == 0:
            self.log("\n[done]\n", "good")
        else:
            self.log(f"\n[failed, exit code {code}]  Double-click an error to open the file.\n", "error")
        self.set_running(False)

    COLORS = {"error": "#c62828", "warning": "#b36b00", "good": "#2e7d32", "dim": "#777777"}

    def log(self, text, style=None):
        cursor = self.output.textCursor()
        cursor.movePosition(QTextCursor.End)
        fmt = QTextCharFormat()
        if style:
            fmt.setForeground(QColor(self.COLORS[style]))
        cursor.insertText(text, fmt)
        self.output.setTextCursor(cursor)
        self.output.ensureCursorVisible()

    def on_output_double_click(self, event):
        cursor = self.output.cursorForPosition(event.pos())
        line = cursor.block().text()
        m = ERROR_LINE.match(line)
        if not (m and self.project):
            return
        path = os.path.join(self.project, m.group(1))
        if not os.path.isfile(path):
            return
        if shutil.which("code"):
            subprocess.Popen(["code", "--goto", f"{path}:{m.group(2)}", self.project])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        elif os.name == "nt":
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path])

    def closeEvent(self, event):
        if self.process.state() != QProcess.NotRunning:
            self.stop_process()
            self.process.waitForFinished(3000)
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = MainWindow(sys.argv[1] if len(sys.argv) > 1 else None)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
