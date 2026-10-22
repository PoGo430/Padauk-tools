"""New project, Settings and Programmer dialogs."""

import os
import re
import sys

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                               QPlainTextEdit, QPushButton, QVBoxLayout)

from .. import chips, examples, toolchain


def default_projects_dir():
    return os.path.join(os.path.expanduser("~"), "PadaukProjects")


class NewProjectDialog(QDialog):
    def __init__(self, parent=None, chip="PFS154"):
        super().__init__(parent)
        self.setWindowTitle("New project")
        self.resize(720, 520)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.chip = QComboBox()
        for n in chips.names():
            c = chips.get(n)
            self.chip.addItem(f"{n}  ({'OTP' if c.otp else 'flash'}, {c.rom_words} words, {c.ram_bytes} B RAM)", n)
        self.chip.setCurrentIndex(max(0, self.chip.findData(chip)))
        self.chip.currentIndexChanged.connect(self._chip_changed)
        form.addRow("Chip", self.chip)
        self.package = QComboBox()
        form.addRow("Package", self.package)
        self.name = QLineEdit("blink")
        form.addRow("Name", self.name)
        row = QHBoxLayout()
        self.where = QLineEdit(default_projects_dir())
        b = QPushButton("Browse...")
        b.clicked.connect(self._browse)
        row.addWidget(self.where, 1)
        row.addWidget(b)
        form.addRow("Folder", row)
        lay.addLayout(form)
        h = QHBoxLayout()
        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._show)
        h.addWidget(self.list, 1)
        self.desc = QLabel()
        self.desc.setWordWrap(True)
        self.desc.setAlignment(Qt.AlignTop)
        self.desc.setMinimumWidth(300)
        h.addWidget(self.desc, 1)
        lay.addLayout(h, 1)
        self.path_note = QLabel()
        self.path_note.setStyleSheet("color:#666")
        lay.addWidget(self.path_note)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Create")
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.name.textChanged.connect(self._update_path)
        self.where.textChanged.connect(self._update_path)
        self._chip_changed()

    def _chip_changed(self):
        c = chips.get(self.chip.currentData())
        self.package.clear()
        for p in c.packages:
            self.package.addItem(p.label, p.key)
        prev = self.list.currentItem().data(Qt.UserRole) if self.list.currentItem() else None
        self.list.clear()
        empty = QListWidgetItem("Empty project")
        empty.setData(Qt.UserRole, "")
        self.list.addItem(empty)
        for e in examples.available(c.name):
            it = QListWidgetItem(e["title"])
            it.setData(Qt.UserRole, e["key"])
            self.list.addItem(it)
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == prev:
                self.list.setCurrentRow(i)
                break
        else:
            self.list.setCurrentRow(0)

    def _show(self, item):
        if not item:
            return
        key = item.data(Qt.UserRole)
        if not key:
            self.desc.setText("<b>Empty project</b><p>Just main.c and the start-up code. Set up pins on the chip "
                              "drawing, then press Generate.</p>")
            return
        e = examples.by_key(key)
        wiring = "".join(f"<li>{w}</li>" for w in e.get("wiring", []))
        self.desc.setText(f"<b>{e['title']}</b><p>{e['text']}</p><p><b>Wiring</b></p><ul>{wiring}</ul>")
        cur = self.name.text().strip()
        known = {"blink", ""} | {x["key"] for x in examples.EXAMPLES}
        if cur in known:
            self.name.setText(key)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Folder for the project", self.where.text())
        if d:
            self.where.setText(d)

    def _update_path(self):
        self.path_note.setText("Creates " + self.folder())

    def folder(self):
        return os.path.join(self.where.text().strip(), self.name.text().strip())

    def _accept(self):
        name = self.name.text().strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", name or ""):
            QMessageBox.warning(self, "Name", "Use letters, digits, _ - and . for the project name.")
            return
        if os.path.exists(os.path.join(self.folder(), "project.pdkstudio")):
            QMessageBox.warning(self, "Exists", "There is already a project in that folder.")
            return
        self.accept()

    def result_values(self):
        item = self.list.currentItem()
        return {"chip": self.chip.currentData(), "package": self.package.currentData(),
                "name": self.name.text().strip(), "folder": self.folder(),
                "example": item.data(Qt.UserRole) if item else ""}


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(640, 260)
        self.data = toolchain.load_settings()
        lay = QVBoxLayout(self)
        box = QGroupBox("Tools (leave empty to use the bundled ones, or the ones on your PATH)")
        f = QFormLayout(box)
        self.paths = {}
        for tool in ("sdcc", "easypdkprog", "dfu-util"):
            row = QHBoxLayout()
            e = QLineEdit(self.data.get("paths", {}).get(tool, ""))
            found, where = toolchain.find_tool(tool)
            e.setPlaceholderText(f"{found} ({where})" if found else "not found")
            b = QPushButton("...")
            b.setFixedWidth(30)
            b.clicked.connect(lambda _=0, ed=e: self._pick(ed))
            row.addWidget(e, 1)
            row.addWidget(b)
            f.addRow(tool, row)
            self.paths[tool] = e
        lay.addWidget(box)
        box2 = QGroupBox("Programmer")
        f2 = QFormLayout(box2)
        self.port = QLineEdit(self.data.get("port", ""))
        self.port.setPlaceholderText("automatic (e.g. /dev/ttyACM0 or COM3)")
        f2.addRow("Port", self.port)
        lay.addWidget(box2)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self._save)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _pick(self, edit):
        f, _ = QFileDialog.getOpenFileName(self, "Program")
        if f:
            edit.setText(f)

    def _save(self):
        self.data["paths"] = {k: e.text().strip() for k, e in self.paths.items() if e.text().strip()}
        self.data["port"] = self.port.text().strip()
        toolchain.save_settings(self.data)
        self.accept()


class ProgrammerDialog(QDialog):
    """Probe the Easy PDK programmer, show its firmware, update the firmware."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Easy PDK programmer")
        self.resize(720, 560)
        self.proc = None
        lay = QVBoxLayout(self)
        fw = toolchain.firmware_file()
        exe, where = toolchain.find_tool("easypdkprog")
        info = QLabel(
            f"<b>easypdkprog:</b> {exe or 'not found'} {f'({where})' if exe else ''}<br>"
            f"<b>Bundled programmer firmware:</b> {os.path.basename(fw) if fw else 'missing'} "
            "(PoGo430 fork: stable 1.3 + native PFS122)")
        info.setWordWrap(True)
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(info)
        row = QHBoxLayout()
        self.probe_btn = QPushButton("Probe programmer and chip")
        self.probe_btn.clicked.connect(self.probe)
        row.addWidget(self.probe_btn)
        row.addStretch(1)
        lay.addLayout(row)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        box = QGroupBox("Update the programmer's firmware to 1.4")
        bl = QVBoxLayout(box)
        steps = QLabel(
            "Needed once for the PFS122 (the PFS154 and PMS150C also work with 1.3).<ol>"
            "<li>Unplug the programmer.</li>"
            "<li>Hold its button and plug it in, then let go: it's now in update (DFU) mode.</li>"
            "<li>Press <b>Write firmware</b> and wait for it to finish.</li>"
            "<li>Unplug it, plug it in again, and press Probe: it should show Firmware 1.4.</li></ol>"
            + ("Linux: if it says it can't open the device, allow USB access once with:<br>"
               "<code>echo 'SUBSYSTEM==\"usb\", ATTR{idVendor}==\"0483\", ATTR{idProduct}==\"df11\", "
               "MODE=\"0666\"' | sudo tee /etc/udev/rules.d/49-stm32-dfu.rules; "
               "sudo udevadm control --reload</code>" if sys.platform.startswith("linux") else
               "Windows: if the device isn't found, install the WinUSB driver for \"STM32 BOOTLOADER\" "
               "with Zadig (zadig.akeo.ie) once."))
        steps.setWordWrap(True)
        steps.setTextFormat(Qt.RichText)
        steps.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bl.addWidget(steps)
        self.fw_btn = QPushButton("Write firmware")
        self.fw_btn.clicked.connect(self.flash_fw)
        self.fw_btn.setEnabled(bool(fw))
        bl.addWidget(self.fw_btn, 0, Qt.AlignLeft)
        lay.addWidget(box)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        lay.addWidget(self.log, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _run(self, cmd, done):
        if self.proc and self.proc.state() != QProcess.NotRunning:
            return
        self.log.appendPlainText("$ " + " ".join(cmd))
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        env = QProcessEnvironment()
        for k, v in toolchain.tool_env().items():
            env.insert(k, v)
        self.proc.setProcessEnvironment(env)
        self.out = ""

        def read():
            t = bytes(self.proc.readAllStandardOutput()).decode(errors="replace")
            self.out += t
            self.log.insertPlainText(t)
            self.log.ensureCursorVisible()

        self.proc.readyReadStandardOutput.connect(read)
        self.proc.finished.connect(lambda code, _s: done(code, self.out))
        self.proc.errorOccurred.connect(lambda e: self.log.appendPlainText(f"could not start: {e}"))
        self.proc.start(cmd[0], cmd[1:])
        self.probe_btn.setEnabled(False)
        self.fw_btn.setEnabled(False)

    def _done_common(self):
        self.probe_btn.setEnabled(True)
        self.fw_btn.setEnabled(bool(toolchain.firmware_file()))

    def probe(self):
        cmd = toolchain.cmd_probe()
        if not cmd:
            self.status.setText("easypdkprog not found (Settings).")
            return

        def done(code, out):
            self._done_common()
            info = toolchain.parse_probe(out)
            parts = []
            if info.get("error"):
                parts.append(info["error"])
            if info.get("firmware"):
                fw = info["firmware"]
                ok = tuple(int(x) for x in fw.split(".")) >= (1, 4)
                parts.append(f"Programmer firmware <b>{fw}</b>"
                             + (" (fine)" if ok else " &mdash; <b style='color:#c00'>update to 1.4 for the PFS122</b>"))
            if "ic" in info:
                parts.append(f"Chip in the socket: <b>{info['ic'] or 'none'}</b>")
            self.status.setText("<br>".join(parts) or "No answer, see the log below.")
        self._run(cmd, done)

    def flash_fw(self):
        fw = toolchain.firmware_file()
        cmd = toolchain.cmd_dfu(fw) if fw else None
        if not cmd:
            self.status.setText("dfu-util not found. Linux: sudo apt install dfu-util. "
                                "Windows: it's bundled with the Windows build.")
            return

        def done(code, out):
            self._done_common()
            if code == 0 or "File downloaded successfully" in out or "Download done" in out:
                self.status.setText("<b>Firmware written.</b> Unplug the programmer, plug it in again, then Probe.")
            else:
                self.status.setText("<b style='color:#c00'>Firmware update failed</b>, see the log. Is the "
                                    "programmer in DFU mode (button held while plugging in)?")
        self._run(cmd, done)
