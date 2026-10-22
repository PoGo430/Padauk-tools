"""Padauk Studio main window."""

import os
import shutil
import subprocess
import sys

from PySide6.QtCore import QProcess, QProcessEnvironment, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QFontDatabase, QIcon, QKeySequence, QColor, QBrush
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDockWidget, QFileDialog, QHBoxLayout,
                               QLabel, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                               QSplitter, QTabWidget, QToolBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from .. import __version__, checks, chips, codegen, examples, toolchain
from ..project import PROJECT_FILE, Project, default_project
from .chip_view import COLORS, ChipView
from .dialogs import NewProjectDialog, ProgrammerDialog, SettingsDialog
from .editor import CodePanel
from .panels import AdcPage, ClockPage, ComparatorPage, PinPage, SerialPage, TimersPage


class BuildThread(QThread):
    line = Signal(str)
    finished_result = Signal(object)

    def __init__(self, project):
        super().__init__()
        self.project = project

    def run(self):
        res = toolchain.build(self.project, log=self.line.emit)
        self.finished_result.emit(res)


class MainWindow(QMainWindow):
    def __init__(self, folder=None):
        super().__init__()
        self.resize(1360, 860)
        self.project = Project(default_project("PFS154", "untitled"))
        self.build_result = None
        self.build_thread = None
        self.after_build = None
        self.proc = None            # easypdkprog process (write / monitor / erase / probe)
        self.proc_kind = ""
        self.generated_state = None  # project JSON at the last Generate
        self._make_ui()
        self._make_actions()
        settings = toolchain.load_settings()
        if folder:
            self.open_project(folder)
        elif settings.get("last") and os.path.exists(os.path.join(settings["last"], PROJECT_FILE)):
            self.open_project(settings["last"])
        else:
            self.set_project(self.project)
            QTimer.singleShot(200, self.new_project)

    # ---- UI ---------------------------------------------------------------------
    def _make_ui(self):
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # pinout tab: chip drawing | settings pages
        pin_tab = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        top = QHBoxLayout()
        top.addWidget(QLabel("Chip"))
        self.chip_combo = QComboBox()
        for n in chips.names():
            self.chip_combo.addItem(n, n)
        self.chip_combo.currentIndexChanged.connect(self._chip_changed)
        top.addWidget(self.chip_combo)
        top.addWidget(QLabel("Package"))
        self.pkg_combo = QComboBox()
        self.pkg_combo.currentIndexChanged.connect(self._package_changed)
        top.addWidget(self.pkg_combo, 1)
        ll.addLayout(top)
        self.chip_view = ChipView()
        self.chip_view.pinSelected.connect(self._pin_selected)
        self.chip_view.pinFunctionChosen.connect(self._pin_function)
        ll.addWidget(self.chip_view, 1)
        legend = QLabel(self._legend_html())
        legend.setWordWrap(True)
        ll.addWidget(legend)
        hint = QLabel("Click a pin to set it up. Right-click: quick menu. Delete: reset the selected pin.")
        hint.setStyleSheet("color:#666")
        ll.addWidget(hint)
        pin_tab.addWidget(left)

        self.pages = QTabWidget()
        self.pin_page = PinPage()
        self.pin_page.jump.connect(self.show_page)
        self.page_list = [self.pin_page, ClockPage(), TimersPage(), ComparatorPage(), AdcPage(), SerialPage()]
        for pg in self.page_list:
            self.pages.addTab(pg, pg.title.replace("&", "&&"))
            pg.changed.connect(self.on_change)
        self.pages.setMinimumWidth(400)
        pin_tab.addWidget(self.pages)
        pin_tab.setStretchFactor(0, 3)
        pin_tab.setStretchFactor(1, 2)
        self.tabs.addTab(pin_tab, "Pinout && settings")

        code_tab = QWidget()
        cl = QVBoxLayout(code_tab)
        row = QHBoxLayout()
        for text, fn in (("Open folder", self.open_folder), ("Open in VS Code", self.open_vscode),
                         ("Open main.c in your editor", self.open_external)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        cl.addLayout(row)
        self.code = CodePanel()
        cl.addWidget(self.code, 1)
        self.tabs.addTab(code_tab, "Code")

        # bottom: problems / output / monitor
        self.bottom = QTabWidget()
        self.problems = QTreeWidget()
        self.problems.setHeaderLabels(["", "Problem", "Where"])
        self.problems.setRootIsDecorated(False)
        self.problems.setColumnWidth(0, 70)
        self.problems.setColumnWidth(1, 760)
        self.problems.itemDoubleClicked.connect(self._problem_clicked)
        self.bottom.addTab(self.problems, "Problems")
        mono = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setFont(mono)
        self.output.setMaximumBlockCount(5000)
        self.bottom.addTab(self.output, "Output")
        mon = QWidget()
        ml = QVBoxLayout(mon)
        ml.setContentsMargins(0, 0, 0, 0)
        mrow = QHBoxLayout()
        self.mon_btn = QPushButton("Start monitor")
        self.mon_btn.clicked.connect(self.toggle_monitor)
        mrow.addWidget(self.mon_btn)
        clr = QPushButton("Clear")
        mrow.addWidget(clr)
        self.mon_info = QLabel("Shows what the chip prints with serial_print(). The chip stays in the programmer.")
        self.mon_info.setStyleSheet("color:#666")
        mrow.addWidget(self.mon_info, 1)
        ml.addLayout(mrow)
        self.monitor = QPlainTextEdit()
        self.monitor.setReadOnly(True)
        self.monitor.setFont(mono)
        self.monitor.setMaximumBlockCount(20000)
        clr.clicked.connect(self.monitor.clear)
        ml.addWidget(self.monitor, 1)
        self.bottom.addTab(mon, "Monitor")
        dock = QDockWidget("", self)
        dock.setTitleBarWidget(QWidget())
        dock.setWidget(self.bottom)
        dock.setFeatures(QDockWidget.NoDockWidgetFeatures)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        self.resizeDocks([dock], [170], Qt.Vertical)

        sb = self.statusBar()
        self.status_text = QLabel("")
        sb.addWidget(self.status_text, 1)
        self.rom_bar = QProgressBar()
        self.ram_bar = QProgressBar()
        for b in (self.rom_bar, self.ram_bar):
            b.setFixedWidth(220)
            b.setTextVisible(True)
            b.setFormat("")
            b.setValue(0)
            sb.addPermanentWidget(b)

    def _legend_html(self):
        names = [("output", "output"), ("input", "input"), ("interrupt", "interrupt"), ("pwm", "PWM"),
                 ("comp_plus", "comparator"), ("adc", "ADC"), ("serial_tx", "serial"), ("unused", "unused")]
        return " ".join(f"<span style='background:{COLORS[k]};padding:2px 6px'>&nbsp;{t}&nbsp;</span>"
                        for k, t in names)

    def _make_actions(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.addToolBar(tb)
        menu = self.menuBar()
        filem = menu.addMenu("&File")
        progm = menu.addMenu("&Chip")
        helpm = menu.addMenu("&Help")

        def act(text, slot, shortcut=None, m=None, toolbar=True, tip=""):
            a = QAction(text, self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            if tip:
                a.setToolTip(tip)
            if m is not None:
                m.addAction(a)
            if toolbar:
                tb.addAction(a)
            return a

        act("New", self.new_project, "Ctrl+N", filem, tip="New project (from an example)")
        act("Open", self.open_dialog, "Ctrl+O", filem)
        act("Save", self.save_all, "Ctrl+S", filem)
        filem.addSeparator()
        act("Settings...", self.settings, None, filem, toolbar=False)
        filem.addAction("Quit", self.close, QKeySequence("Ctrl+Q"))
        tb.addSeparator()
        act("Generate code", self.generate, "Ctrl+G", progm, tip="Write pdk_init.c/h and main.c")
        act("Build", self.build, "Ctrl+B", progm, tip="Generate and compile")
        self.write_act = act("Write to chip", self.write_chip, "Ctrl+U", progm,
                             tip="Build, then write the chip in the programmer")
        self.mon_act = act("Monitor", self.toggle_monitor, "Ctrl+M", progm,
                           tip="Run the chip in the programmer and show its serial output")
        self.stop_act = act("Stop", self.stop_proc, None, progm)
        self.stop_act.setEnabled(False)
        tb.addSeparator()
        act("Programmer...", self.programmer, None, progm, tip="Probe, firmware update")
        progm.addSeparator()
        act("Erase chip", self.erase_chip, None, progm, toolbar=False)
        act("Probe", self.probe, None, progm, toolbar=False)
        helpm.addAction("About", self.about)
        helpm.addAction("free-pdk website", lambda: QDesktopServices.openUrl(QUrl("https://free-pdk.github.io")))

    # ---- project -------------------------------------------------------------------
    def set_project(self, project):
        self.project = project
        self.chip_combo.blockSignals(True)
        self.chip_combo.setCurrentIndex(self.chip_combo.findData(project.chip.name))
        self.chip_combo.blockSignals(False)
        self._fill_packages()
        self.chip_view.set_project(project)
        for pg in self.page_list:
            pg.set_project(project)
        self.pin_page.show_pin(self.chip_view.selected)
        self.code.set_folder(project.path)
        self.build_result = None
        self._update_bars()
        self.refresh()
        self._title()

    def _title(self):
        where = self.project.path or "not saved yet"
        self.setWindowTitle(f"{self.project.name} ({self.project.chip.name}) - {where} - Padauk Studio")

    def _fill_packages(self):
        self.pkg_combo.blockSignals(True)
        self.pkg_combo.clear()
        for p in self.project.chip.packages:
            self.pkg_combo.addItem(p.label, p.key)
        self.pkg_combo.setCurrentIndex(self.pkg_combo.findData(self.project.data["package"]))
        self.pkg_combo.blockSignals(False)

    def _chip_changed(self):
        name = self.chip_combo.currentData()
        if name == self.project.chip.name:
            return
        lost = [p for p, c in self.project.pins.items()
                if p not in chips.get(name).pins or c["fn"] not in chips.get(name).pins[p].functions]
        if lost:
            r = QMessageBox.question(self, "Change chip",
                                     f"The {name} can't keep these pin settings: {', '.join(lost)}. Change anyway?")
            if r != QMessageBox.Yes:
                self.chip_combo.blockSignals(True)
                self.chip_combo.setCurrentIndex(self.chip_combo.findData(self.project.chip.name))
                self.chip_combo.blockSignals(False)
                return
        self.project.set_chip(name)
        self._fill_packages()
        for pg in self.page_list:
            pg.set_project(self.project)
        self.chip_view.set_project(self.project)
        self.pin_page.show_pin(self.chip_view.selected)
        self.on_change()

    def _package_changed(self):
        key = self.pkg_combo.currentData()
        if key and key != self.project.data["package"]:
            self.project.set_package(key)
            self.on_change()

    def on_change(self):
        """Something in the settings changed: save, redraw, re-check."""
        self.chip_view.request_redraw()
        for pg in self.page_list:
            if pg is not self.pin_page:
                pg.load()
        sel = self.chip_view.selected
        QTimer.singleShot(0, lambda: self.pin_page.show_pin(sel))
        if self.project.path:
            self.project.save()
        self.refresh()
        self._title()

    def refresh(self):
        """Fill the Problems list from the checks (and the last build)."""
        self.problems.clear()
        found = checks.check(self.project)
        if self.build_result:
            for m in self.build_result.messages:
                where = f"{os.path.basename(m.file)}:{m.line}" if m.file else ""
                found.append((m.kind, m.text, where))
        icons = {"error": ("Error", "#c62828"), "warning": ("Warning", "#b26a00"), "info": ("Note", "#555")}
        for lvl, text, where in found:
            it = QTreeWidgetItem([icons[lvl][0], text, where])
            it.setForeground(0, QBrush(QColor(icons[lvl][1])))
            it.setData(0, Qt.UserRole, where)
            self.problems.addTopLevelItem(it)
        if not found:
            it = QTreeWidgetItem(["", "No problems.", ""])
            it.setForeground(1, QBrush(QColor("#888")))
            self.problems.addTopLevelItem(it)
        n_err = sum(1 for f in found if f[0] == "error")
        n_warn = sum(1 for f in found if f[0] == "warning")
        label = "Problems" + (f" ({n_err} errors, {n_warn} warnings)" if (n_err or n_warn) else "")
        self.bottom.setTabText(0, label)

    def _problem_clicked(self, item):
        where = item.data(0, Qt.UserRole) or ""
        if ":" in where and where.split(":")[0].endswith((".c", ".h")):
            fname, line = where.rsplit(":", 1)
            self.tabs.setCurrentIndex(1)
            self.code.open(fname, int(line))
            return
        if where in self.project.chip.pins:
            self.tabs.setCurrentIndex(0)
            self.chip_view.select_pin(where)
            self.show_page("Pin")
            return
        page = {"clock": "Clock & power", "system": "Clock & power", "comparator": "Comparator",
                "serial": "Serial", "T16": "Timers", "TM2": "Timers", "TM3": "Timers"}.get(where)
        if where.startswith("PWMG"):
            page = "Timers"
        if page:
            self.tabs.setCurrentIndex(0)
            self.show_page(page)

    def show_page(self, title):
        for i, pg in enumerate(self.page_list):
            if pg.title == title:
                self.pages.setCurrentIndex(i)

    def _pin_selected(self, pin):
        self.pin_page.show_pin(pin)
        self.show_page("Pin")

    def _pin_function(self, pin, fn):
        try:
            self.project.set_pin(pin, fn)
        except ValueError as e:
            self.status(str(e))
            return
        self.on_change()

    # ---- file actions ----------------------------------------------------------------
    def new_project(self):
        d = NewProjectDialog(self, self.project.chip.name)
        if d.exec() != NewProjectDialog.Accepted:
            return
        v = d.result_values()
        if v["example"]:
            p, code = examples.make_project(v["example"], v["chip"], v["name"])
            old_main = examples.main_with_code(code)
        else:
            p, old_main = Project(default_project(v["chip"], v["name"])), ""
        p.data["package"] = v["package"]
        os.makedirs(v["folder"], exist_ok=True)
        if old_main and not os.path.exists(os.path.join(v["folder"], "main.c")):
            with open(os.path.join(v["folder"], "main.c"), "w", encoding="utf-8") as f:
                f.write(old_main)
        codegen.write_project(p, v["folder"])
        self.open_project(v["folder"])
        self.tabs.setCurrentIndex(0)

    def open_dialog(self):
        d = QFileDialog.getExistingDirectory(self, "Open project folder", os.path.expanduser("~"))
        if d:
            if not os.path.exists(os.path.join(d, PROJECT_FILE)):
                QMessageBox.warning(self, "Open", f"No {PROJECT_FILE} in that folder.")
                return
            self.open_project(d)

    def open_project(self, folder):
        try:
            p = Project.load(folder)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Open", f"Can't open {folder}: {e}")
            return
        self.chip_view.selected = None
        self.set_project(p)
        s = toolchain.load_settings()
        s["last"] = folder
        toolchain.save_settings(s)
        self.generated_state = p.to_json() if os.path.exists(os.path.join(folder, "pdk_init.c")) else None
        self.status(f"Opened {folder}")

    def ensure_folder(self):
        if self.project.path:
            return True
        d = QFileDialog.getExistingDirectory(self, "Folder to save the project in", os.path.expanduser("~"))
        if not d:
            return False
        self.project.save(d)
        self.code.set_folder(d)
        self._title()
        return True

    def save_all(self):
        self.code.save()
        if self.ensure_folder():
            self.project.save()
            self.status("Saved")

    # ---- generate / build ----------------------------------------------------------
    def generate(self, quiet=False):
        if not self.ensure_folder():
            return False
        errs = checks.errors(self.project)
        if errs:
            self.bottom.setCurrentIndex(0)
            self.status("Fix the errors in Problems first.")
            return False
        self.code.save()
        written = codegen.write_project(self.project, self.project.path)
        self.generated_state = self.project.to_json()
        self.code.refresh_files()
        self.code.reload_if_clean()
        if not quiet:
            self.status("Generated: " + (", ".join(written) if written else "no changes"))
        return True

    def build(self, then=None):
        if self.build_thread and self.build_thread.isRunning():
            return
        if not self.generate(quiet=True):
            return
        self.output.clear()
        self.bottom.setCurrentIndex(1)
        self.after_build = then
        self.status("Building...")
        self.build_thread = BuildThread(self.project)
        self.build_thread.line.connect(self.output.appendPlainText)
        self.build_thread.finished_result.connect(self._build_done)
        self.build_thread.start()

    def _build_done(self, res):
        self.build_result = res
        self.code.set_marks(res.messages)
        self._update_bars()
        self.refresh()
        then, self.after_build = self.after_build, None
        if res.ok:
            self.output.appendPlainText(f"\nBuild OK: {res.rom_words} of {res.rom_total} words ROM, "
                                        f"{res.ram_bytes} of {res.ram_total} bytes RAM "
                                        f"({res.ram_total - res.ram_bytes} left for the stack)")
            self.status("Build OK")
            if then:
                then()
        else:
            self.output.appendPlainText("\nBuild failed.")
            self.status("Build failed: see Problems")
            self.bottom.setCurrentIndex(0)
            errs = [m for m in res.messages if m.kind == "error" and m.file]
            if errs:
                self.tabs.setCurrentIndex(1)
                self.code.open(os.path.basename(errs[0].file), errs[0].line)

    def _update_bars(self):
        r = self.build_result
        if not r or not r.ok:
            for b in (self.rom_bar, self.ram_bar):
                b.setValue(0)
            self.rom_bar.setFormat("ROM: not built")
            self.ram_bar.setFormat("RAM: not built")
            return
        self.rom_bar.setMaximum(r.rom_total)
        self.rom_bar.setValue(r.rom_words)
        self.rom_bar.setFormat(f"ROM {r.rom_words}/{r.rom_total} words")
        self.ram_bar.setMaximum(r.ram_total)
        self.ram_bar.setValue(r.ram_bytes)
        self.ram_bar.setFormat(f"RAM {r.ram_bytes}/{r.ram_total} B")

    # ---- programmer --------------------------------------------------------------------
    def _start_proc(self, kind, cmd, sink):
        if self.proc and self.proc.state() != QProcess.NotRunning:
            self.status("The programmer is busy: press Stop first.")
            return False
        if not cmd:
            QMessageBox.warning(self, "easypdkprog", "easypdkprog wasn't found. Set its path in File > Settings.")
            return False
        self.proc_kind = kind
        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        env = QProcessEnvironment()
        for k, v in toolchain.tool_env().items():
            env.insert(k, v)
        self.proc.setProcessEnvironment(env)
        self.proc_out = ""

        def read():
            t = bytes(self.proc.readAllStandardOutput()).decode(errors="replace").replace("\r\n", "\n")
            self.proc_out += t
            sink.moveCursor(sink.textCursor().MoveOperation.End)
            sink.insertPlainText(t)
            sink.ensureCursorVisible()

        self.proc.readyReadStandardOutput.connect(read)
        self.proc.finished.connect(self._proc_done)
        self.proc.errorOccurred.connect(lambda e: sink.appendPlainText(f"[could not run easypdkprog: {e}]"))
        sink.appendPlainText("$ " + " ".join(cmd))
        self.proc.start(cmd[0], cmd[1:])
        self.stop_act.setEnabled(True)
        if kind == "monitor":
            self.mon_btn.setText("Stop monitor")
        return True

    def _proc_done(self, code, _status):
        kind, out = self.proc_kind, self.proc_out
        self.stop_act.setEnabled(False)
        self.mon_btn.setText("Start monitor")
        if kind == "write":
            if code == 0 and "ERROR" not in out:
                cal = [l for l in out.splitlines() if "calibration result" in l.lower() or "IHRC" in l]
                self.status("Written to the chip." + (f" {cal[-1].strip()}" if cal else ""))
                self.output.appendPlainText("\nDone.")
            else:
                self.status("Writing failed: see Output.")
                self._explain_prog_error(out)
        elif kind == "monitor":
            self.monitor.appendPlainText("\n[monitor stopped]")
            if code != 0:
                self._explain_prog_error(out)
        elif kind in ("erase", "probe"):
            info = toolchain.parse_probe(out)
            if kind == "probe":
                self.status(f"Programmer firmware {info.get('firmware', '?')}, chip: {info.get('ic') or 'none'}")
            else:
                self.status("Erased." if code == 0 else "Erase failed: see Output.")

    def _explain_prog_error(self, out):
        hints = []
        if "No programmer found" in out:
            hints.append("No programmer found: is it plugged in? On Linux, add yourself to the dialout group "
                         "(sudo usermod -aG dialout $USER, then log in again).")
        if "needs programmer firmware 1.4" in out or "PROTOCOL" in out.upper():
            hints.append("The programmer firmware is too old: Chip > Programmer... > Write firmware.")
        if "Nothing found" in out or "IC not found" in out or "No IC found" in out:
            hints.append("No chip found in the socket: check how it sits (pin 1) and the adapter.")
        if "Unknown calibration" in out:
            hints.append("easypdkprog didn't recognize the calibration code: use the bundled easypdkprog.")
        if hints:
            QMessageBox.warning(self, "Programmer", "\n\n".join(hints))

    def write_chip(self):
        p = self.project
        if p.chip.otp:
            r = QMessageBox.question(
                self, "One-time programmable",
                f"The {p.chip.name} can be written only once. Write this program to the chip in the socket now?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if r != QMessageBox.Yes:
                return
        if self.proc and self.proc.state() != QProcess.NotRunning:
            if self.proc_kind == "monitor":
                self.stop_proc()
                QTimer.singleShot(1800, self.write_chip_now)
                return
        self.build(then=self.write_chip_now)

    def write_chip_now(self):
        if not self.build_result or not self.build_result.ok:
            self.build(then=self.write_chip_now)
            return
        self.bottom.setCurrentIndex(1)
        self.status("Writing...")
        self._start_proc("write", toolchain.cmd_write(self.project, self.build_result.ihx), self.output)

    def toggle_monitor(self):
        if self.proc and self.proc.state() != QProcess.NotRunning and self.proc_kind == "monitor":
            self.stop_proc()
            return
        self.bottom.setCurrentIndex(2)
        vdd = self.project.data["vdd_mv"] / 1000
        self.mon_info.setText(f"Running the chip at {vdd:g} V. Text from serial_print() shows below.")
        self._start_proc("monitor", toolchain.cmd_start(self.project), self.monitor)

    def stop_proc(self):
        if not self.proc or self.proc.state() == QProcess.NotRunning:
            return
        if self.proc_kind == "monitor":
            self.proc.write(b"\x1b")      # easypdkprog stops the chip on Esc
            proc = self.proc
            QTimer.singleShot(1500, lambda: proc.state() != QProcess.NotRunning and proc.kill())
        else:
            self.proc.kill()

    def erase_chip(self):
        if self.project.chip.otp:
            QMessageBox.information(self, "Erase", "OTP chips can't be erased.")
            return
        self.bottom.setCurrentIndex(1)
        self._start_proc("erase", toolchain.cmd_erase(self.project), self.output)

    def probe(self):
        self.bottom.setCurrentIndex(1)
        self._start_proc("probe", toolchain.cmd_probe(), self.output)

    def programmer(self):
        if self.proc and self.proc.state() != QProcess.NotRunning:
            QMessageBox.information(self, "Programmer", "Stop the running programmer command first.")
            return
        ProgrammerDialog(self).exec()

    def settings(self):
        SettingsDialog(self).exec()

    # ---- misc ----------------------------------------------------------------------------
    def open_folder(self):
        if self.project.path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.project.path))

    def open_external(self):
        if self.project.path:
            self.code.save()
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.join(self.project.path, "main.c")))

    def open_vscode(self):
        if not self.project.path:
            return
        code = shutil.which("code") or shutil.which("code.cmd") or shutil.which("codium")
        if not code:
            QMessageBox.information(self, "VS Code", "The 'code' command wasn't found on your PATH.")
            return
        self.code.save()
        subprocess.Popen([code, self.project.path, os.path.join(self.project.path, "main.c")])

    def status(self, text):
        self.status_text.setText(text)

    def about(self):
        tools = "<br>".join(f"{t}: {toolchain.find_tool(t)[0] or 'not found'}"
                            for t in ("sdcc", "easypdkprog", "dfu-util"))
        QMessageBox.about(self, "Padauk Studio",
                          f"<b>Padauk Studio {__version__}</b><p>Set up, generate, build and write programs for "
                          "the Padauk PMS150C, PFS154 and PFS122 with SDCC and the Easy PDK programmer.</p>"
                          f"<p>{tools}</p><p>Uses free-pdk (free-pdk.github.io) tools and knowledge.</p>")

    def closeEvent(self, e):
        self.code.save()
        if self.project.path:
            self.project.save()
        if self.proc and self.proc.state() != QProcess.NotRunning:
            self.stop_proc()
            self.proc.waitForFinished(2000)
        super().closeEvent(e)


def run(folder=None):
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Padauk Studio")
    app.setStyle("Fusion")
    w = MainWindow(folder)
    w.show()
    return app.exec()
