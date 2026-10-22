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
