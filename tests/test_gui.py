"""GUI smoke test (offscreen): pin selection, reset with Delete, chip switch, build."""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_main_window(app, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from padauk_studio import codegen, examples, toolchain
    from padauk_studio.ui.main_window import MainWindow
    monkeypatch.setattr(toolchain, "CONFIG_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setattr(toolchain, "CONFIG_DIR", str(tmp_path))

    folder = str(tmp_path / "proj")
    p, code = examples.make_project("button_interrupt", "PFS154", "proj")
    os.makedirs(folder)
    with open(os.path.join(folder, "main.c"), "w") as f:
        f.write(examples.main_with_code(code))
    codegen.write_project(p, folder)

    w = MainWindow(folder)
    w.show()
    app.processEvents()
    # select a pin: the Pin page shows it, no popup
    w.chip_view.select_pin("PA3")
    app.processEvents()
    assert w.pin_page.pin == "PA3"
    # choose a function through the radio buttons
    w.pin_page.buttons["output"].setChecked(True)
    app.processEvents()
    assert w.project.fn("PA3") == "output"
    # Delete resets the selected pin
    w.chip_view.setFocus()
    QTest.keyClick(w.chip_view, Qt.Key_Delete)
    app.processEvents()
    assert w.project.fn("PA3") == "unused"
    # and "Unused" on the page does the same
    w.chip_view.select_pin("PA4")
    app.processEvents()
    w.pin_page.buttons["unused"].setChecked(True)
    app.processEvents()
    assert w.project.fn("PA4") == "unused"
    # clicking the background deselects
    w.chip_view.select_pin(None)
    app.processEvents()
    assert w.pin_page.pin is None
    # switch chip
    w.chip_combo.setCurrentIndex(w.chip_combo.findData("PMS150C"))
    app.processEvents()
    assert w.project.chip.name == "PMS150C"
    # settings were saved to the project file
    from padauk_studio.project import Project
    assert Project.load(folder).chip.name == "PMS150C"
    w.project.set_pin("PA4", "output", label="LED")   # the example code uses LED_toggle()
    w.on_change()
    if toolchain.find_tool("sdcc")[0]:
        w.build()
        t = time.time()
        while w.build_thread.isRunning() and time.time() - t < 60:
            app.processEvents()
            time.sleep(0.02)
        for _ in range(5):
            app.processEvents()
        assert w.build_result.ok, w.build_result.log
    w.close()


def test_pages_and_menu(app, tmp_path, monkeypatch):
    """Drive every settings page like a user would; any exception in a slot fails the test."""
    import sys

    from padauk_studio import toolchain
    from padauk_studio.ui.main_window import MainWindow
    monkeypatch.setattr(toolchain, "CONFIG_FILE", str(tmp_path / "settings.json"))
    monkeypatch.setattr(toolchain, "CONFIG_DIR", str(tmp_path))
    errors = []
    import traceback
    monkeypatch.setattr(sys, "excepthook", lambda *a: errors.append("".join(traceback.format_exception(*a))))

    from padauk_studio import codegen
    from padauk_studio.project import Project, default_project
    folder = str(tmp_path / "p")
    codegen.write_project(Project(default_project("PFS154", "p")), folder)
    w = MainWindow(folder)
    w.show()

    def settle():
        for _ in range(4):
            app.processEvents()

    settle()
    pages = {pg.title: pg for pg in w.page_list}
    for chip in ("PFS154", "PFS122", "PMS150C"):
        w.chip_combo.setCurrentIndex(w.chip_combo.findData(chip))
        settle()
        for i in range(w.pkg_combo.count()):
            w.pkg_combo.setCurrentIndex(i)
            settle()
        w.pkg_combo.setCurrentIndex(0)
        settle()
        # comparator: enable, choose PA4 as plus input (sets the pin), interrupt, output pin
        cp = pages["Comparator"]
        cp.en.setChecked(True)
        settle()
        cp.plus.setCurrentIndex(cp.plus.findData("PA4"))
        settle()
        assert w.project.fn("PA4") == "comp_plus"
        cp.irq.setCurrentIndex(cp.irq.findData("rise"))
        cp.outpin.setChecked(True)
        cp.level.setValue(3)
        settle()
        assert w.project.fn("PA0") == "comp_out"
        cp.en.setChecked(False)
        settle()
        assert w.project.fn("PA4") == "unused" and w.project.fn("PA0") == "unused"
        # serial on, then a different baud
        sp = pages["Serial"]
        sp.en.setChecked(True)
        settle()
        assert w.project.serial_enabled()
        sp.baud.setCurrentIndex(sp.baud.findData(57600))
        settle()
        # timers: periodic interrupt on Timer16
        tp = pages["Timers"]
        mc = tp.rows["T16"][0]
        mc.setCurrentIndex(mc.findData("tick"))
        settle()
        assert w.project.timer("T16")["mode"] == "tick"
        # clock: slowest IHRC clock -> serial problem appears
        ck = pages["Clock & power"]
        ck.clock.setCurrentIndex(ck.clock.findData("IHRC_DIV64"))
        settle()
        texts = [w.problems.topLevelItem(i).text(1) for i in range(w.problems.topLevelItemCount())]
        assert any("baud" in t for t in texts), texts
        ck.clock.setCurrentIndex(ck.clock.findData("IHRC_DIV2"))
        settle()
        # every pin, every function, through the same path as the right-click menu
        for pin, info in w.project.chip.pins.items():
            for fn in info.functions + ["unused"]:
                w.chip_view.pinFunctionChosen.emit(pin, fn)
                w.chip_view.select_pin(pin)
                settle()
    w.close()
    assert not errors, errors
