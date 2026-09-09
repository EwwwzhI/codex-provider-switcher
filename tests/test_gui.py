import os
import time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextOption
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QDialog, QMessageBox
from PySide6.QtTest import QTest
import pytest

from provider_switcher import core
from provider_switcher.gui import MainWindow, PathDisplay, STYLE, app_icon, configure_app
from conftest import IDS


@pytest.fixture
def window(home):
    app = QApplication.instance() or QApplication([])
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    w = MainWindow(home, autoload=False, persist_settings=False)
    data = core.catalog(home)
    data["running"] = ["codex.exe"]
    w.loaded(data)
    w.show()
    app.processEvents()
    yield w
    w.close()


def test_filters_copy_id_parent_does_not_select_child(window):
    assert set(window.items) == {IDS[0], IDS[3]}
    window.agents.setChecked(True)
    assert IDS[1] in window.items
    assert window.items[IDS[1]].parent() == window.items[IDS[0]]
    window.items[IDS[0]].setCheckState(0, Qt.CheckState.Checked)
    assert window.checked == {IDS[0]}
    assert window.items[IDS[1]].checkState(0) == Qt.CheckState.Unchecked
    window.tree.setCurrentItem(window.items[IDS[0]])
    window.copy_id()
    assert QApplication.clipboard().text() == IDS[0]
    window.search.setText("独立任务")
    assert set(window.items) == {IDS[3]}
    assert "1 个被筛选隐藏" in window.selection_label.text()
    window.clear_selection()
    assert not window.checked


def test_archived_provider_filter_and_empty_projects(window):
    window.archived.setChecked(True)
    assert IDS[2] in window.items
    index = window.provider_filter.findData("retired")
    window.provider_filter.setCurrentIndex(index)
    assert set(window.items) == {IDS[2]}
    assert window.target.findData("retired") == -1
    window.provider_filter.setCurrentIndex(0)
    assert any("空项目" in window.tree.topLevelItem(i).text(0) for i in range(window.tree.topLevelItemCount()))


def test_pending_operation_disables_switch(window):
    window.pending_ops = [{"id": "test"}]
    window.items[IDS[0]].setCheckState(0, Qt.CheckState.Checked)
    assert not window.preview_button.isEnabled()


def test_typography_icon_and_control_geometry(window):
    assert "font-size: 14px" in STYLE
    assert "font-weight: 600" not in STYLE
    assert "QPushButton#primary" in STYLE and "font-weight: bold" in STYLE
    assert window.detail_title.styleSheet().startswith("font-size: 18px")
    assert window.preview_button.sizeHint().height() >= 39
    assert window.preview_button.fontMetrics().horizontalAdvance(window.preview_button.text()) < window.preview_button.width()
    assert not app_icon().isNull()


def test_extended_cwd_is_displayed_without_prefix(window):
    row = window.rows[IDS[0]]
    row["cwd"] = core.display_path(r"\\?\C:\Users\demo\Projects\Codex 工具")
    row["rollout_path"] = (
        r"\\?\C:\Users\demo\.codex\sessions\2026\09\09"
        r"\rollout-2026-09-09T17-47-00-long-session-name.jsonl"
    )
    window.tree.setCurrentItem(window.items[IDS[0]])
    window.on_current(window.items[IDS[0]])
    QApplication.processEvents()
    assert window.fields["cwd"].text() == r"C:\Users\demo\Projects\Codex 工具"
    assert window.fields["rollout_path"].text() == (
        r"C:\Users\demo\.codex\sessions\2026\09\09"
        r"\rollout-2026-09-09T17-47-00-long-session-name.jsonl"
    )
    for key in ("cwd", "rollout_path"):
        field = window.fields[key]
        assert isinstance(field, PathDisplay)
        assert field.document().defaultTextOption().wrapMode() == QTextOption.WrapMode.WrapAnywhere
        layout = field.document().firstBlock().layout()
        assert layout.lineCount() >= 2
        assert layout.lineAt(0).textLength() > 2
        assert field.height() >= field.fontMetrics().lineSpacing() * 2
        assert field.height() >= field.heightForWidth(field.width())


def test_gui_preview_apply_worker_and_refresh(window, monkeypatch):
    monkeypatch.setattr(QDialog, 'exec', lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: QMessageBox.StandardButton.Ok)
    errors = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: errors.append(args[-1]))
    window.items[IDS[0]].setCheckState(0, Qt.CheckState.Checked)
    window.target.setCurrentIndex(window.target.findData('wzh'))
    window.make_preview()
    for _ in range(400):
        QApplication.processEvents()
        time.sleep(.025)  # Release the GIL for the Python QThread worker.
        if window.last_result and window.worker is None:
            break
    assert not errors
    assert window.last_result is not None, window.status.text()
    assert window.last_result['state'] == 'committed'
    assert window.rows[IDS[0]]['provider'] == 'wzh'
    assert not window.checked
