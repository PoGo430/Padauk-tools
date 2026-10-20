#!/usr/bin/env python3
"""
Padauk Tools - small GUI around the project Makefile (SDCC + easypdkprog).

  * Pick a project folder (any folder made from template/).
  * Edit DEVICE / F_CPU / TARGET_VDD_MV / PROJECT_NAME in its Makefile.
  * Build, program, run, probe, erase and clean with one click.
  * Create new projects from the bundled template (optionally from an example).
"""
import os
import re
import shutil
import signal
import sys

from PyQt5.QtCore import QProcess, QSettings, QTimer
from PyQt5.QtGui import QFont, QTextCursor
from PyQt5.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox, QPlainTextEdit,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

APP_NAME = "Padauk Tools"

# Fallback if `make devices` cannot be run: name -> (arch, rom words, ram bytes, mtp/otp)
FALLBACK_DEVICES = {
    "PFS154": ("pdk14", 2048, 128, "mtp"),
    "PFS122": ("pdk14", 2048, 128, "mtp"),
    "PMS150C": ("pdk13", 1024, 64, "otp"),
}

F_CPU_CHOICES = ["16000000", "8000000", "4000000", "2000000", "1000000", "500000", "250000"]

USE_SETSID = os.name == "posix" and shutil.which("setsid") is not None

# Makefile variables the GUI edits. Matches "NAME ?= value" and "NAME = value".
SETTING_RE = r"^({name}[ \t]*[?:]?=[ \t]*)([^#\s]*)"


def resource_dir():
    """Folder that holds template/ and examples/ (repo root, or the PyInstaller bundle)."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read_setting(text, name):
    m = re.search(SETTING_RE.format(name=name), text, re.M)
    return m.group(2) if m else None


def write_setting(text, name, value):
    pattern = re.compile(SETTING_RE.format(name=name), re.M)
    if pattern.search(text):
        return pattern.sub(lambda m: m.group(1) + value, text, count=1)
    return f"{name} ?= {value}\n" + text


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(860, 640)
        self.settings = QSettings("Padauk-tools", APP_NAME)
        self.devices = dict(FALLBACK_DEVICES)
        self.process = QProcess(self)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self.on_output)
        self.process.finished.connect(self.on_finished)

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.addWidget(self.build_project_box())
        layout.addWidget(self.build_settings_box())
        layout.addLayout(self.build_action_row())

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        font = QFont("Monospace")
        font.setStyleHint(QFont.TypeWriter)
        self.output.setFont(font)
        layout.addWidget(self.output, 1)
        self.setCentralWidget(root)

        start_dir = self.settings.value("project_dir", "")
        if not start_dir or not os.path.isfile(os.path.join(start_dir, "Makefile")):
            start_dir = os.getcwd() if os.path.isfile("Makefile") else ""
        self.set_project_dir(start_dir)

    # ----- UI construction --------------------------------------------------
    def build_project_box(self):
        box = QGroupBox("Project folder")
        row = QHBoxLayout(box)
        self.dir_edit = QLineEdit()
        self.dir_edit.setReadOnly(True)
        open_btn = QPushButton("Open...")
        open_btn.clicked.connect(self.choose_project_dir)
        new_btn = QPushButton("New project...")
        new_btn.clicked.connect(self.new_project)
        new_btn.setEnabled(os.path.isdir(os.path.join(resource_dir(), "template")))
        row.addWidget(self.dir_edit, 1)
        row.addWidget(open_btn)
        row.addWidget(new_btn)
        return box

    def build_settings_box(self):
        box = QGroupBox("Makefile settings")
        form = QFormLayout(box)

        self.project_name = QLineEdit()
        form.addRow("Project name:", self.project_name)

        self.device_combo = QComboBox()
        self.device_combo.currentTextChanged.connect(self.update_device_info)
        self.device_info = QLabel()
        dev_row = QHBoxLayout()
        dev_row.addWidget(self.device_combo)
        dev_row.addWidget(self.device_info, 1)
        form.addRow("Device:", dev_row)

        self.f_cpu = QComboBox()
        self.f_cpu.setEditable(True)
        self.f_cpu.addItems(F_CPU_CHOICES)
        form.addRow("F_CPU (Hz):", self.f_cpu)

        self.vdd_mv = QSpinBox()
        self.vdd_mv.setRange(1800, 5500)
        self.vdd_mv.setSingleStep(100)
        self.vdd_mv.setSuffix(" mV")
        self.vdd_mv.setToolTip("Supply voltage of your circuit. Used to calibrate the clock and by 'Run'.")
        form.addRow("Target VDD:", self.vdd_mv)

        self.save_btn = QPushButton("Save to Makefile")
        self.save_btn.clicked.connect(self.save_makefile)
        form.addRow("", self.save_btn)
        return box

    def build_action_row(self):
        row = QHBoxLayout()
        self.action_buttons = []
        for label, target, tip in [
            ("Build", "all", "Compile and show ROM/RAM usage"),
            ("Program", "program", "Compile and write the chip"),
            ("Run", "run", "Power the chip from the programmer and show its serial output (PA7)"),
            ("Probe", "probe", "Detect the chip in the programmer socket"),
            ("Erase", "erase", "Erase a flash (PFS) chip"),
            ("Clean", "clean", "Delete build output"),
        ]:
            btn = QPushButton(label)
            btn.setToolTip(tip)
            btn.clicked.connect(lambda _=False, t=target: self.run_target(t))
            row.addWidget(btn)
            self.action_buttons.append(btn)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_process)
        row.addWidget(self.stop_btn)
        return row

    # ----- Project handling -------------------------------------------------
    @property
    def makefile(self):
        return os.path.join(self.project_dir, "Makefile")

    def set_project_dir(self, path):
        self.project_dir = path
        self.dir_edit.setText(path or "(no project selected)")
        has_project = bool(path) and os.path.isfile(self.makefile)
        for w in self.action_buttons + [self.save_btn]:
            w.setEnabled(has_project)
        if has_project:
            self.settings.setValue("project_dir", path)
            self.load_devices()
            self.load_makefile()

    def choose_project_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select project folder", self.project_dir or os.path.expanduser("~"))
        if not path:
            return
        if not os.path.isfile(os.path.join(path, "Makefile")):
            QMessageBox.warning(self, APP_NAME, "That folder has no Makefile. Use 'New project...' to create one.")
            return
        self.set_project_dir(path)

    def new_project(self):
        base = QFileDialog.getExistingDirectory(self, "Create the project inside...", os.path.expanduser("~"))
        if not base:
            return
        name, ok = QInputDialog.getText(self, "New project", "Project name:", text="MyProject")
        name = re.sub(r"[^A-Za-z0-9_-]", "_", name.strip())
        if not ok or not name:
            return
        dest = os.path.join(base, name)
        if os.path.exists(dest):
            QMessageBox.warning(self, APP_NAME, f"{dest} already exists.")
            return

        examples_dir = os.path.join(resource_dir(), "examples")
        examples = sorted(os.listdir(examples_dir)) if os.path.isdir(examples_dir) else []
        example, ok = QInputDialog.getItem(self, "New project", "Start from:", ["template (blink)"] + examples, 0, False)
        if not ok:
            return

        shutil.copytree(os.path.join(resource_dir(), "template"), dest,
                        ignore=shutil.ignore_patterns(".build", ".output"))
        if example in examples:
            shutil.copy(os.path.join(examples_dir, example, "main.c"), os.path.join(dest, "main.c"))
        cbp = os.path.join(dest, "padauk.cbp")
        if os.path.isfile(cbp):
            with open(cbp) as f:
                text = re.sub(r'<Option title="[^"]*"', f'<Option title="{name}"', f.read(), count=1)
            with open(os.path.join(dest, f"{name}.cbp"), "w") as f:
                f.write(text)
            os.remove(cbp)
        mk = os.path.join(dest, "Makefile")
        with open(mk) as f:
            text = write_setting(f.read(), "PROJECT_NAME", name)
        with open(mk, "w") as f:
            f.write(text)
        self.set_project_dir(dest)
        self.log(f"Created {dest}\n")

    def load_devices(self):
        """Ask the project Makefile which devices it knows (`make devices`)."""
        proc = QProcess()
        proc.setWorkingDirectory(self.project_dir)
        proc.start("make", ["-s", "devices"])
        if proc.waitForFinished(5000) and proc.exitCode() == 0:
            devices = {}
            for line in proc.readAllStandardOutput().data().decode(errors="replace").splitlines()[1:]:
                parts = line.split()
                if len(parts) == 5:
                    devices[parts[0]] = (parts[1], int(parts[2]), int(parts[3]), parts[4])
            if devices:
                self.devices = devices
        current = self.device_combo.currentText()
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        self.device_combo.addItems(sorted(self.devices))
        self.device_combo.blockSignals(False)
        if current:
            self.device_combo.setCurrentText(current)

    def load_makefile(self):
        with open(self.makefile) as f:
            text = f.read()
        self.project_name.setText(read_setting(text, "PROJECT_NAME") or "MyProject")
        device = read_setting(text, "DEVICE") or "PFS154"
        if device not in self.devices:
            self.device_combo.addItem(device)
        self.device_combo.setCurrentText(device)
        self.f_cpu.setCurrentText(read_setting(text, "F_CPU") or "8000000")
        self.vdd_mv.setValue(int(read_setting(text, "TARGET_VDD_MV") or 5000))
        self.update_device_info(device)

    def update_device_info(self, device):
        info = self.devices.get(device)
        if not info:
            self.device_info.setText("unknown device")
            return
        arch, rom, ram, mem = info
        kind = "flash, rewritable" if mem == "mtp" else "OTP, write once!"
        self.device_info.setText(f"{arch}   ROM {rom} words   RAM {ram} bytes   {kind}")

    def save_makefile(self):
        f_cpu = self.f_cpu.currentText().strip()
        if not f_cpu.isdigit():
            QMessageBox.warning(self, APP_NAME, "F_CPU must be a number in Hz, e.g. 8000000.")
            return False
        name = re.sub(r"[^A-Za-z0-9_-]", "_", self.project_name.text().strip()) or "MyProject"
        with open(self.makefile) as f:
            text = f.read()
        text = write_setting(text, "PROJECT_NAME", name)
        text = write_setting(text, "DEVICE", self.device_combo.currentText())
        text = write_setting(text, "F_CPU", f_cpu)
        text = write_setting(text, "TARGET_VDD_MV", str(self.vdd_mv.value()))
        with open(self.makefile, "w") as f:
            f.write(text)
        self.log("Makefile saved.\n")
        return True

    # ----- Running make -----------------------------------------------------
    def run_target(self, target):
        if self.process.state() != QProcess.NotRunning:
            return
        if target in ("all", "program", "run") and not self.save_makefile():
            return
        device = self.device_combo.currentText()
        if target == "program" and self.devices.get(device, ("", 0, 0, ""))[3] == "otp":
            answer = QMessageBox.question(
                self, "OTP chip",
                f"{device} is one-time programmable. It can only be written once.\n\nWrite it now?")
            if answer != QMessageBox.Yes:
                return
        if target == "erase":
            if QMessageBox.question(self, "Erase", f"Erase the {device} in the programmer?") != QMessageBox.Yes:
                return
        self.output.clear()
        self.log(f"$ make {target}\n")
        self.process.setWorkingDirectory(self.project_dir)
        # On Linux/macOS run make in its own process group, so "Stop" also
        # ends easypdkprog (e.g. a running `make run`) and frees the programmer.
        if USE_SETSID:
            self.process.start("setsid", ["make", target])
        else:
            self.process.start("make", [target])
        if not self.process.waitForStarted(3000):
            self.log("Could not start 'make'. Is it installed and on your PATH?\n")
            return
        self.set_running(True)

    def stop_process(self):
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
        pid = self.process.processId()
        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            self.process.kill()

    def set_running(self, running):
        for btn in self.action_buttons:
            btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)

    def on_output(self):
        self.log(self.process.readAllStandardOutput().data().decode(errors="replace"))

    def on_finished(self, code, status):
        if status == QProcess.CrashExit or code in (-signal.SIGINT, 128 + signal.SIGINT, 130):
            self.log("\n[stopped]\n")
        else:
            self.log("\n[done]\n" if code == 0 else f"\n[failed, exit code {code}]\n")
        self.set_running(False)

    def log(self, text):
        self.output.moveCursor(QTextCursor.End)
        self.output.insertPlainText(text)
        self.output.moveCursor(QTextCursor.End)

    def closeEvent(self, event):
        if self.process.state() != QProcess.NotRunning:
            self.stop_process()
            self.process.waitForFinished(3000)
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
