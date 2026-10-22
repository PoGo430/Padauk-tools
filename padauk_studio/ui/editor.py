"""A small C editor for main.c (generated files open read-only)."""

import os
import re

from PySide6.QtCore import QRect, QRegularExpression, QSize, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QPainter, QSyntaxHighlighter, QTextCharFormat,
                           QTextCursor, QTextFormat)
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QTextEdit, QVBoxLayout, QWidget

GENERATED = ("pdk_init.c", "pdk_init.h", "pms150c.h", "pfs154.h", "pfs122.h")


def fmt(color, bold=False, italic=False):
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Bold)
    f.setFontItalic(italic)
    return f


class CHighlighter(QSyntaxHighlighter):
    KEYWORDS = ("if else for while do return switch case default break continue goto static const volatile "
                "unsigned signed char int long short void struct union enum typedef sizeof extern "
                "uint8_t uint16_t uint32_t int8_t int16_t int32_t __sfr __at __interrupt __asm __endasm")

    def __init__(self, doc):
        super().__init__(doc)
        self.rules = [
            (QRegularExpression(r"\b(" + "|".join(self.KEYWORDS.split()) + r")\b"), fmt("#0033b3", True)),
            (QRegularExpression(r"^\s*#\s*\w+"), fmt("#9e5d00")),
            (QRegularExpression(r"\b0x[0-9A-Fa-f]+\b|\b\d+\b"), fmt("#1750eb")),
            (QRegularExpression(r"\b[A-Z][A-Z0-9_]{2,}\b"), fmt("#871094")),
            (QRegularExpression(r"\"([^\"\\\\]|\\\\.)*\"|'([^'\\\\]|\\\\.)*'"), fmt("#067d17")),
            (QRegularExpression(r"//[^\n]*"), fmt("#8c8c8c", italic=True)),
        ]
        self.comment = fmt("#8c8c8c", italic=True)
        self.user = fmt("#2a7d2a", bold=True)
        self.start = QRegularExpression(r"/\*")
        self.end = QRegularExpression(r"\*/")

    def highlightBlock(self, text):
        for rx, f in self.rules:
            it = rx.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), f)
        self.setCurrentBlockState(0)
        continuing = self.previousBlockState() == 1
        start = 0 if continuing else text.find("/*")
        while start >= 0:
            end = text.find("*/", start if continuing else start + 2)
            continuing = False
            if end < 0:
                self.setCurrentBlockState(1)
                length = len(text) - start
            else:
                length = end - start + 2
            seg = text[start:start + length]
            self.setFormat(start, length, self.user if "USER CODE" in seg else self.comment)
            start = text.find("/*", start + length)


class LineNumbers(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.number_width(), 0)

    def paintEvent(self, e):
        self.editor.paint_numbers(e)


class CodeEdit(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        font.setPointSize(10)
        self.setFont(font)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 2)
        self.numbers = LineNumbers(self)
        self.blockCountChanged.connect(lambda _: self.setViewportMargins(self.number_width(), 0, 0, 0))
        self.updateRequest.connect(self._update_numbers)
        self.setViewportMargins(self.number_width(), 0, 0, 0)
        self.highlighter = CHighlighter(self.document())
        self.marks = {}

    def number_width(self):
        return 12 + self.fontMetrics().horizontalAdvance("9") * max(3, len(str(self.blockCount())))

    def _update_numbers(self, rect, dy):
        if dy:
            self.numbers.scroll(0, dy)
        else:
            self.numbers.update(0, rect.y(), self.numbers.width(), rect.height())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cr = self.contentsRect()
        self.numbers.setGeometry(QRect(cr.left(), cr.top(), self.number_width(), cr.height()))

    def paint_numbers(self, e):
        p = QPainter(self.numbers)
        p.fillRect(e.rect(), QColor("#f3f3f3"))
        block = self.firstVisibleBlock()
        n = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        while block.isValid() and top <= e.rect().bottom():
            if block.isVisible() and bottom >= e.rect().top():
                kind = self.marks.get(n + 1)
                if kind:
                    p.fillRect(0, top, self.numbers.width(), bottom - top,
                               QColor("#f8c8c8" if kind == "error" else "#f8e8b0"))
                p.setPen(QColor("#999"))
                p.drawText(0, top, self.numbers.width() - 6, self.fontMetrics().height(), Qt.AlignRight, str(n + 1))
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            n += 1

    def goto_line(self, line):
        block = self.document().findBlockByLineNumber(max(0, line - 1))
        cur = QTextCursor(block)
        self.setTextCursor(cur)
        self.centerCursor()
        sel = QTextEdit.ExtraSelection()
        sel.format.setBackground(QColor("#fff3b0"))
        sel.format.setProperty(QTextFormat.FullWidthSelection, True)
        sel.cursor = cur
        self.setExtraSelections([sel])
        self.setFocus()


class CodePanel(QWidget):
    """File picker + editor. Only main.c and your own files are editable."""
    saved = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.folder = None
        self.current = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        self.files = QComboBox()
        self.files.currentIndexChanged.connect(self._pick)
        top.addWidget(self.files, 1)
        self.state = QLabel("")
        top.addWidget(self.state)
        self.save_btn = QPushButton("Save")
        self.save_btn.clicked.connect(self.save)
        top.addWidget(self.save_btn)
        lay.addLayout(top)
        self.edit = CodeEdit()
        self.edit.document().modificationChanged.connect(self._modified)
        lay.addWidget(self.edit)

    def set_folder(self, folder):
        self.folder = folder
        self.refresh_files()

    def refresh_files(self, keep=True):
        cur = self.current if keep else None
        names = []
        if self.folder and os.path.isdir(self.folder):
            names = sorted(f for f in os.listdir(self.folder) if f.endswith((".c", ".h")))
            names.sort(key=lambda f: (f != "main.c", f in GENERATED, f))
        self.files.blockSignals(True)
        self.files.clear()
        for n in names:
            self.files.addItem(n + ("   (generated, read-only)" if n in GENERATED else ""), n)
        self.files.blockSignals(False)
        if names:
            target = cur if cur in names else names[0]
            self.files.setCurrentIndex(names.index(target))
            self.open(target)
        else:
            self.current = None
            self.edit.setPlainText("")

    def _pick(self):
        name = self.files.currentData()
        if name and name != self.current:
            if self.edit.document().isModified():
                self.save()
            self.open(name)

    def open(self, name, line=None):
        if not self.folder:
            return
        path = os.path.join(self.folder, name)
        if not os.path.exists(path):
            return
        if name != self.current and self.edit.document().isModified():
            self.save()
        with open(path, encoding="utf-8", errors="replace") as f:
            text = f.read()
        if name != self.current or self.edit.toPlainText() != text:
            pos = self.edit.verticalScrollBar().value() if name == self.current else 0
            self.edit.setPlainText(text)
            self.edit.verticalScrollBar().setValue(pos)
        self.current = name
        i = self.files.findData(name)
        if i >= 0:
            self.files.blockSignals(True)
            self.files.setCurrentIndex(i)
            self.files.blockSignals(False)
        ro = name in GENERATED
        self.edit.setReadOnly(ro)
        self.edit.setStyleSheet("QPlainTextEdit { background: #f7f7f7; }" if ro else "")
        self.edit.document().setModified(False)
        self.save_btn.setEnabled(False)
        if line:
            self.edit.goto_line(line)

    def reload_if_clean(self):
        """After Generate: show the new text (unsaved edits were saved before generating)."""
        if self.current:
            self.open(self.current)

    def save(self):
        if not self.current or self.edit.isReadOnly() or not self.edit.document().isModified():
            return
        with open(os.path.join(self.folder, self.current), "w", encoding="utf-8", newline="\n") as f:
            f.write(self.edit.toPlainText())
        self.edit.document().setModified(False)
        self.saved.emit()

    def set_marks(self, messages):
        self.edit.marks = {}
        for m in messages:
            if self.current and os.path.basename(m.file) == self.current:
                if self.edit.marks.get(m.line) != "error":
                    self.edit.marks[m.line] = m.kind
        self.edit.numbers.update()

    def _modified(self, mod):
        self.save_btn.setEnabled(mod)
        self.state.setText("modified" if mod else "")
