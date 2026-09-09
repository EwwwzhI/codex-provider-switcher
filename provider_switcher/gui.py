from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path
import sys

from PySide6.QtCore import QRect, QSize, Qt, QThread, QTimer, QSettings, QUrl
from PySide6.QtGui import (
    QColor, QFont, QIcon, QPainter, QPen, QPixmap, QShortcut, QKeySequence,
    QDesktopServices, QTextOption,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QCheckBox, QTreeWidget, QTreeWidgetItem, QSplitter, QFrame,
    QFormLayout, QMessageBox, QDialog, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QFileDialog, QProgressBar, QStyle, QScrollArea, QTextEdit,
    QSizePolicy, QLayout,
)

from . import core


STYLE = """
QWidget { font-family: 'Microsoft YaHei UI', 'Segoe UI'; font-size: 14px; font-weight: normal; color: #172a32; }
QMainWindow, QDialog { background: #f3f6f6; }
QLabel { background: transparent; }
QLabel#title { font-size: 25px; font-weight: 700; }
QLabel#subtitle, QLabel#muted { color: #52666e; }
QLabel#section { font-size: 16px; font-weight: bold; }
QLabel#banner { background: #fff4de; color: #714b09; border: 1px solid #eedcb6; border-radius: 7px; padding: 10px 14px; }
QFrame#card { background: #ffffff; border: 1px solid #dce5e6; border-radius: 9px; }
QPushButton { background: #ffffff; border: 1px solid #b9cacc; border-radius: 6px; padding: 8px 14px; min-height: 22px; font-weight: normal; }
QPushButton:hover { background: #eaf3f2; border-color: #699992; }
QPushButton:pressed { background: #dbece9; }
QPushButton#primary { background: #126957; border-color: #126957; color: white; font-weight: bold; }
QPushButton#primary:hover { background: #0c5142; }
QPushButton:disabled { background: #edf1f1; border-color: #dce3e4; color: #89999e; }
QPushButton#primary:disabled { background: #edf1f1; border-color: #dce3e4; color: #64767c; }
QPushButton:focus, QLineEdit:focus, QComboBox:focus, QTreeWidget:focus { border: 2px solid #16846d; }
QLineEdit, QComboBox { border: 1px solid #b9cacc; border-radius: 5px; background: white; padding: 7px 9px; min-height: 21px; }
QTreeWidget, QTableWidget { border: none; background: white; alternate-background-color: #f7f9f9; outline: none; }
QTreeWidget::item { min-height: 35px; padding: 2px 4px; }
QTreeWidget::item:selected, QTableWidget::item:selected { background: #dcefe9; color: #153e33; }
QTreeWidget::item:hover { background: #eef6f3; }
QHeaderView::section { background: #f6f9f9; color: #52666e; border: none; border-bottom: 1px solid #e2e9e9; padding: 9px 7px; text-align: left; }
QCheckBox { spacing: 6px; }
QCheckBox::indicator { width: 16px; height: 16px; }
QSplitter::handle { background: transparent; width: 14px; }
QProgressBar { max-height: 3px; border: none; background: #e4eceb; }
QProgressBar::chunk { background: #16846d; }
QToolTip { background: #172a32; color: white; border: none; padding: 6px; }
"""


def app_icon(size=128):
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    source = root / "provider_switcher" / "assets" / "app-icon.png"
    if source.is_file():
        icon = QIcon(str(source))
        if not icon.isNull():
            return icon
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#126957"))
    p.drawRoundedRect(0, 0, size, size, size * .23, size * .23)
    p.setPen(QPen(QColor("white"), size * .065, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawLine(int(size * .25), int(size * .35), int(size * .74), int(size * .35))
    p.drawLine(int(size * .74), int(size * .35), int(size * .61), int(size * .22))
    p.drawLine(int(size * .74), int(size * .35), int(size * .61), int(size * .48))
    p.drawLine(int(size * .75), int(size * .65), int(size * .26), int(size * .65))
    p.drawLine(int(size * .26), int(size * .65), int(size * .39), int(size * .52))
    p.drawLine(int(size * .26), int(size * .65), int(size * .39), int(size * .78))
    p.end()
    return QIcon(pix)


def configure_app(app):
    font = QFont("Microsoft YaHei UI")
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias | QFont.StyleStrategy.PreferQuality)
    app.setFont(font)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setWindowIcon(app_icon())


def label(text, name=None):
    w = QLabel(text)
    if name:
        w.setObjectName(name)
    return w


def button(text, callback, primary=False):
    w = QPushButton(text)
    w.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        w.setObjectName("primary")
    w.clicked.connect(callback)
    return w


class PathDisplay(QTextEdit):
    """Selectable label-like path display that wraps long tokens without altering them."""

    def __init__(self, text=""):
        super().__init__()
        self.setReadOnly(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setTabChangesFocus(True)
        self.document().setDocumentMargin(0)
        option = self.document().defaultTextOption()
        option.setWrapMode(QTextOption.WrapMode.WrapAnywhere)
        self.document().setDefaultTextOption(option)
        self.setStyleSheet("QTextEdit { background: transparent; border: none; padding: 0; }")
        policy = QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self._height_timer = QTimer(self)
        self._height_timer.setSingleShot(True)
        self._height_timer.timeout.connect(self._sync_height)
        self.setText(text)

    def text(self):
        return self.toPlainText()

    def setText(self, text):
        self.setPlainText(str(text))
        self.moveCursor(self.textCursor().MoveOperation.Start)
        self.updateGeometry()
        # Session selection happens after layout, so resize immediately for the
        # current width. Keep the queued pass for any layout change this causes.
        self._sync_height()
        self._schedule_height_sync()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_height_sync()

    def _schedule_height_sync(self):
        self._height_timer.start(0)

    def heightForWidth(self, width):
        flags = Qt.TextFlag.TextWrapAnywhere | Qt.TextFlag.TextExpandTabs
        bounds = self.fontMetrics().boundingRect(
            QRect(0, 0, max(1, width), 100000), flags, self.text()
        )
        return max(self.fontMetrics().lineSpacing(), bounds.height()) + 2

    def sizeHint(self):
        return QSize(0, self.heightForWidth(max(240, self.width())))

    def minimumSizeHint(self):
        return QSize(0, self.heightForWidth(max(1, self.width())))

    def _sync_height(self):
        height = self.heightForWidth(max(1, self.width()))
        if self.minimumHeight() == height and self.maximumHeight() == height:
            return
        self.setMinimumHeight(height)
        self.setMaximumHeight(height)
        self.updateGeometry()
        layout = self.parentWidget().layout() if self.parentWidget() else None
        if layout:
            layout.invalidate()
            layout.activate()


class Worker(QThread):
    def __init__(self, fn, parent):
        super().__init__(parent)
        self.fn = fn
        self.result = None
        self.error = None

    def run(self):
        try:
            self.result = self.fn()
        except Exception as e:
            self.error = str(e)


class MainWindow(QMainWindow):
    def __init__(self, home=None, autoload=True, persist_settings=True):
        super().__init__()
        self.home = core.home_path(home)
        self.settings = QSettings("LocalTools", "CodexProviderSwitcher")
        self.persist_settings = persist_settings
        self.setWindowTitle("Codex 会话 Provider 切换工具")
        self.setWindowIcon(app_icon())
        self.resize(1240, 900)
        self.setMinimumSize(1000, 680)
        self.worker = None
        self.data = {"threads": [], "projects": [], "providers": []}
        self.checked = set()
        self.items = {}
        self.rows = {}
        self.pending_ops = []
        self.last_result = None
        self.build_ui()
        QShortcut(QKeySequence("Ctrl+F"), self, self.search.setFocus)
        QShortcut(QKeySequence("F5"), self, self.refresh)
        QShortcut(QKeySequence("Ctrl+C"), self.tree, self.copy_id)
        saved = self.settings.value("geometry") if persist_settings else None
        if saved:
            self.restoreGeometry(saved)
        if autoload:
            QTimer.singleShot(0, self.refresh)

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(26, 23, 26, 18)
        layout.setSpacing(15)
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(5)
        titles.addWidget(label("会话 Provider", "title"))
        titles.addWidget(label("查找已有任务，选择它下一次请求使用的通道。", "subtitle"))
        header.addLayout(titles)
        header.addStretch()
        self.home_button = button("数据目录", self.choose_home)
        self.restore_button = button("备份与恢复", self.show_operations)
        self.refresh_button = button("刷新", self.refresh)
        for w in (self.home_button, self.restore_button, self.refresh_button):
            header.addWidget(w)
        layout.addLayout(header)
        self.banner = label("正在读取本地会话…", "banner")
        self.banner.setWordWrap(True)
        layout.addWidget(self.banner)
        split = QSplitter()
        left = QFrame()
        left.setObjectName("card")
        lv = QVBoxLayout(left)
        lv.setContentsMargins(16, 16, 16, 12)
        lv.setSpacing(12)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索名称、任务 ID 或项目路径    Ctrl+F")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("搜索会话")
        self.search.textChanged.connect(self.render_tree)
        lv.addWidget(self.search)
        filters = QHBoxLayout()
        self.provider_filter = QComboBox()
        self.provider_filter.setAccessibleName("按当前 Provider 筛选")
        self.provider_filter.addItem("所有 Provider", "")
        self.provider_filter.currentIndexChanged.connect(self.render_tree)
        self.archived = QCheckBox("归档会话")
        self.agents = QCheckBox("代理子会话")
        self.archived.toggled.connect(self.render_tree)
        self.agents.toggled.connect(self.render_tree)
        filters.addWidget(self.provider_filter, 1)
        filters.addWidget(self.archived)
        filters.addWidget(self.agents)
        lv.addLayout(filters)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["项目 / 会话", "Provider", "状态"])
        self.tree.setAccessibleName("项目与会话树，空格勾选当前会话")
        self.tree.setColumnWidth(0, 350)
        self.tree.setColumnWidth(1, 82)
        self.tree.setColumnWidth(2, 95)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.setUniformRowHeights(True)
        self.tree.setAlternatingRowColors(True)
        self.tree.itemChanged.connect(self.on_checked)
        self.tree.currentItemChanged.connect(self.on_current)
        lv.addWidget(self.tree, 1)
        self.tree_count = label("", "muted")
        lv.addWidget(self.tree_count)
        split.addWidget(left)
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(14)
        detail = QFrame()
        detail.setObjectName("card")
        dv = QVBoxLayout(detail)
        dv.setContentsMargins(20, 18, 20, 18)
        dv.addWidget(label("会话详情", "section"))
        self.detail_title = label("选择一个会话查看详情")
        self.detail_title.setWordWrap(True)
        self.detail_title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 9px 0;")
        self.detail_title.setTextFormat(Qt.TextFormat.PlainText)
        dv.addWidget(self.detail_title)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        fields_widget = QWidget()
        fields_widget.setStyleSheet("background: white;")
        form = QFormLayout(fields_widget)
        form.setContentsMargins(0, 5, 0, 5)
        form.setVerticalSpacing(9)
        form.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.fields = {}
        for key, title in [("id", "任务 ID"), ("provider", "Provider"), ("model", "模型"),
                           ("project_name", "所属项目"), ("cwd", "工作目录"),
                           ("rollout_path", "会话文件"), ("updated", "最近更新"),
                           ("state", "会话状态"), ("check", "文件检查")]:
            if key in {"cwd", "rollout_path"}:
                w = PathDisplay("—")
                w.setAccessibleName(title)
            else:
                w = label("—")
                w.setTextFormat(Qt.TextFormat.PlainText)
                w.setWordWrap(True)
                w.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
                w.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            if key == "id":
                w.setStyleSheet("font-family: Consolas; font-size: 13px;")
            form.addRow(label(title, "muted"), w)
            self.fields[key] = w
        scroll.setWidget(fields_widget)
        dv.addWidget(scroll, 1)
        actions = QHBoxLayout()
        self.copy_button = button("复制任务 ID", self.copy_id)
        self.check_button = button("完整检查", self.inspect_current)
        self.copy_button.setEnabled(False)
        self.check_button.setEnabled(False)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.check_button)
        dv.addLayout(actions)
        rv.addWidget(detail, 1)
        control = QFrame()
        control.setObjectName("card")
        cv = QVBoxLayout(control)
        cv.setContentsMargins(20, 18, 20, 18)
        cv.setSpacing(12)
        cv.addWidget(label("切换选中的会话", "section"))
        selection = QHBoxLayout()
        self.selection_label = label("已勾选 0 个会话", "muted")
        selection.addWidget(self.selection_label)
        selection.addStretch()
        self.clear_button = button("清空", self.clear_selection)
        selection.addWidget(self.clear_button)
        cv.addLayout(selection)
        cv.addWidget(label("目标 Provider", "muted"))
        self.target = QComboBox()
        self.target.setAccessibleName("目标 Provider")
        cv.addWidget(self.target)
        note = label("保留当前模型。选择父会话不会自动修改子会话。", "muted")
        note.setWordWrap(True)
        cv.addWidget(note)
        self.preview_button = button("查看变更清单", self.make_preview, True)
        self.preview_button.setEnabled(False)
        cv.addWidget(self.preview_button)
        rv.addWidget(control)
        split.addWidget(right)
        split.setSizes([710, 430])
        layout.addWidget(split, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = label(str(self.home), "muted")
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.status)

    def run_job(self, text, fn, callback):
        if self.worker:
            return
        self.status.setText(text)
        self.progress.show()
        self.centralWidget().setEnabled(False)
        w = Worker(fn, self)
        self.worker = w

        def finished():
            self.worker = None
            self.centralWidget().setEnabled(True)
            self.progress.hide()
            self.update_selection()
            self.status.setText(str(self.home))
            if w.error:
                self.pending_ops = core.pending(self.home)
                if self.pending_ops:
                    self.banner.setText("存在未完成操作，请打开“备份与恢复”处理后再继续切换。")
                self.update_selection()
                QMessageBox.warning(self, "操作未完成", w.error)
            else:
                callback(w.result)
            w.deleteLater()

        w.finished.connect(finished)
        w.start()

    def refresh(self):
        def load():
            data = core.catalog(self.home)
            data["operations"] = core.operations(self.home)
            try:
                data["running"] = core.running_processes()
                data["process_error"] = ""
            except core.SwitchError as e:
                data["running"] = []
                data["process_error"] = str(e)
            return data
        self.run_job("正在读取项目与会话…", load, self.loaded)

    def loaded(self, data):
        self.data = data
        self.rows = {r["id"]: r for r in data["threads"]}
        self.checked.intersection_update(self.rows)
        self.pending_ops = [o for o in data.get("operations", []) if o["state"] not in core.TERMINAL]
        if self.pending_ops:
            self.banner.setText(f"有 {len(self.pending_ops)} 个未完成操作。请先打开“备份与恢复”，处理后才能继续切换。")
        elif data.get("process_error"):
            self.banner.setText(data["process_error"])
        elif data.get("running"):
            self.banner.setText("Codex 正在运行 · 可以浏览和预览。应用变更前，请完全退出 Codex 及其 CLI / 扩展后端。")
        else:
            self.banner.setText("可以离线切换 · 先勾选会话并检查变更清单。完成后，由你重新打开 Codex。")
        old_filter = self.provider_filter.currentData()
        old_target = self.target.currentData()
        self.provider_filter.blockSignals(True)
        self.provider_filter.clear()
        self.provider_filter.addItem("所有 Provider", "")
        for p in sorted({r["provider"] for r in data["threads"]}):
            self.provider_filter.addItem(p, p)
        self.provider_filter.setCurrentIndex(max(0, self.provider_filter.findData(old_filter)))
        self.provider_filter.blockSignals(False)
        self.target.clear()
        for p in data["providers"]:
            self.target.addItem(f"{p['name']}  ·  {p['id']}", p["id"])
        self.target.setCurrentIndex(max(0, self.target.findData(old_target)))
        self.render_tree()

    def render_tree(self, *_):
        current = self.tree.currentItem()
        current_id = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        self.tree.blockSignals(True)
        self.tree.clear()
        self.items = {}
        query = self.search.text().casefold().strip()
        provider = self.provider_filter.currentData()
        visible = [r for r in self.data["threads"] if
                   (self.archived.isChecked() or not r["archived"]) and
                   (self.agents.isChecked() or not r["is_agent"]) and
                   (not provider or r["provider"] == provider) and
                   query in " ".join(str(r[k]) for k in ("id", "name", "cwd", "project_name")).casefold()]
        groups = {}
        # Show all projects, including empty ones, when no search/provider filter is active.
        for p in self.data["projects"]:
            if not query and not provider or any(r["project_id"] == p["id"] for r in visible):
                groups[p["id"]] = QTreeWidgetItem(self.tree, [p["name"]])
        for r in visible:
            key = r["project_id"] or r["project_name"]
            if key not in groups:
                groups[key] = QTreeWidgetItem(self.tree, [r["project_name"]])
        counts = {}
        for r in visible:
            key = r["project_id"] or r["project_name"]
            counts[key] = counts.get(key, 0) + 1
            status = r["error"] or ("已归档" if r["archived"] else "代理" if r["is_agent"] else "可检查")
            title = " ".join(r["name"].split())
            item = QTreeWidgetItem([title[:100], r["provider"], status])
            item.setData(0, Qt.ItemDataRole.UserRole, r["id"])
            item.setToolTip(0, r["name"][:2000] + "\n" + r["id"])
            item.setToolTip(2, r["error"] or "应用前将核对任务 ID、Provider 和历史索引。")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if r["error"]:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                item.setForeground(2, QColor("#a04724"))
                self.checked.discard(r["id"])
            else:
                item.setCheckState(0, Qt.CheckState.Checked if r["id"] in self.checked else Qt.CheckState.Unchecked)
            self.items[r["id"]] = item
        byid = {r["id"]: r for r in visible}
        for r in visible:
            key = r["project_id"] or r["project_name"]
            parent = r["parent_id"]
            visited = {r["id"]}
            cursor = parent
            cycle = False
            while cursor in byid:
                if cursor in visited:
                    cycle = True
                    break
                visited.add(cursor)
                cursor = byid[cursor]["parent_id"]
            if parent in self.items and not cycle and byid[parent]["project_id"] == r["project_id"]:
                self.items[parent].addChild(self.items[r["id"]])
            else:
                groups[key].addChild(self.items[r["id"]])
        for key, group in groups.items():
            group.setText(0, group.text(0) + f"  ({counts.get(key, 0)})")
            group.setIcon(0, self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
            font = group.font(0)
            font.setBold(True)
            group.setFont(0, font)
            group.setExpanded(bool(query) or counts.get(key, 0) > 0)
        if query or self.agents.isChecked():
            self.tree.expandAll()
        self.tree.blockSignals(False)
        self.tree_count.setText(f"显示 {len(visible)} / {len(self.data['threads'])} 个会话 · 项目节点仅用于分组")
        self.update_selection()
        if current_id in self.items:
            self.tree.setCurrentItem(self.items[current_id])
        else:
            self.on_current(None)

    def on_checked(self, item, column):
        tid = item.data(0, Qt.ItemDataRole.UserRole)
        if not tid or column != 0:
            return
        if item.checkState(0) == Qt.CheckState.Checked:
            self.checked.add(tid)
        else:
            self.checked.discard(tid)
        self.update_selection()

    def update_selection(self):
        hidden = len(self.checked - self.items.keys())
        self.selection_label.setText(f"已勾选 {len(self.checked)} 个会话" + (f"（{hidden} 个被筛选隐藏）" if hidden else ""))
        self.preview_button.setEnabled(bool(self.checked) and not self.pending_ops and not self.worker)

    def clear_selection(self):
        self.checked.clear()
        self.render_tree()

    def current_row(self):
        item = self.tree.currentItem()
        return self.rows.get(item.data(0, Qt.ItemDataRole.UserRole)) if item else None

    def on_current(self, item, previous=None):
        r = self.rows.get(item.data(0, Qt.ItemDataRole.UserRole)) if item else None
        self.copy_button.setEnabled(bool(r))
        self.check_button.setEnabled(bool(r))
        if not r:
            self.detail_title.setText("选择一个会话查看详情")
            for w in self.fields.values():
                w.setText("—")
            return
        self.detail_title.setText(" ".join(r["name"].split())[:150])
        for k in ("id", "provider", "model", "project_name", "cwd"):
            self.fields[k].setText(str(r[k]))
        self.fields["rollout_path"].setText(core.display_path(r["rollout_path"]))
        self.fields["updated"].setText(dt.datetime.fromtimestamp(r["updated_at"] / 1000).strftime("%Y-%m-%d %H:%M") if r["updated_at"] else "未记录")
        self.fields["state"].setText(("已归档" if r["archived"] else "未归档") + (" · 代理子会话" if r["is_agent"] else ""))
        self.fields["check"].setText(r["error"] or "文件存在 · 应用前执行完整检查")

    def copy_id(self):
        r = self.current_row()
        if r:
            QApplication.clipboard().setText(r["id"])
            self.status.setText("已复制任务 ID：" + r["id"])

    def inspect_current(self):
        r = self.current_row()
        if not r:
            return
        target = r["provider"] if r["provider"] in {p["id"] for p in self.data["providers"]} else "openai"

        def done(_):
            if self.current_row() and self.current_row()["id"] == r["id"]:
                self.fields["check"].setText("任务 ID、Provider、文件及历史索引检查通过")
        self.run_job("正在核对会话文件与历史索引…", lambda: core.preview(self.home, [r["id"]], target), done)

    def make_preview(self):
        ids = sorted(self.checked)
        target = self.target.currentData()
        self.run_job("正在生成变更清单并核对历史索引…", lambda: core.preview(self.home, ids, target), self.show_preview)

    def show_preview(self, plan):
        dialog = QDialog(self)
        dialog.setWindowTitle("检查变更清单")
        dialog.resize(850, 490)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(15)
        layout.addWidget(label(f"{plan['count']} 个会话将切换到 {plan['target']}", "section"))
        table = QTableWidget(len(plan["entries"]), 5)
        table.setHorizontalHeaderLabels(["会话", "任务 ID", "当前", "目标", "保留模型"])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.verticalHeader().hide()
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for row, e in enumerate(plan["entries"]):
            for col, text in enumerate((" ".join(e["name"].split())[:60], e["id"], e["before_provider"], e["after_provider"], e["model"])):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                table.setItem(row, col, item)
        layout.addWidget(table, 1)
        note = label("应用前请完全退出 Codex。工具会先备份，再修改选中会话及其历史索引。\n模型保持原值；目标服务是否支持该模型，需要在恢复会话后验证。", "muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(button("返回选择", dialog.reject))
        apply = button("应用变更", dialog.accept, True)
        apply.setEnabled(plan["count"] > 0)
        buttons.addWidget(apply)
        layout.addLayout(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.run_job("正在备份并应用变更，请保持 Codex 退出…",
                         lambda: core.switch(self.home, [e["id"] for e in plan["entries"]], plan["target"], plan["token"]), self.applied)

    def applied(self, result):
        self.last_result = result
        QMessageBox.information(self, "操作完成", result["message"] + ("\n\n备份：" + result["backup"] if "backup" in result else ""))
        self.checked.clear()
        self.refresh()

    def show_operations(self):
        ops = core.operations(self.home)
        dialog = QDialog(self)
        dialog.setWindowTitle("备份与恢复")
        dialog.resize(770, 450)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        info = label("恢复只涉及本次操作选中的会话。若会话已有新增内容，工具会拒绝覆盖。", "muted")
        info.setWordWrap(True)
        layout.addWidget(info)
        table = QTableWidget(len(ops), 3)
        table.setHorizontalHeaderLabels(["操作 ID", "状态", "会话数"])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().hide()
        states = {"committed": "切换完成", "restored": "已恢复", "rolled_back": "失败后已回滚", "aborted": "未执行修改",
                  "preparing": "待清理准备状态", "prepared": "待清理准备状态", "applying": "中断 · 待恢复",
                  "restoring": "恢复中断 · 待继续", "needs_recovery": "需要恢复", "unreadable": "日志损坏 · 人工检查"}
        for row, o in enumerate(ops):
            for col, text in enumerate((o["id"], states.get(o["state"], o["state"]), str(o["count"]))):
                item = QTableWidgetItem(text)
                item.setToolTip(o.get("error", "") or text)
                table.setItem(row, col, item)
        layout.addWidget(table, 1)
        if not ops:
            layout.addWidget(label("暂无操作记录。首次切换后，备份会显示在这里。", "muted"))
        controls = QHBoxLayout()
        open_folder = button("打开备份目录", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.home / "provider-switcher" / "operations"))))
        open_folder.setEnabled(bool(ops))
        controls.addWidget(open_folder)
        controls.addStretch()
        controls.addWidget(button("关闭", dialog.reject))
        restore_button = button("恢复所选操作", dialog.accept, True)
        restore_button.setEnabled(False)
        table.itemSelectionChanged.connect(lambda: restore_button.setEnabled(table.currentRow() >= 0 and ops[table.currentRow()]["state"] not in {"restored", "rolled_back", "aborted", "unreadable"}))
        controls.addWidget(restore_button)
        layout.addLayout(controls)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            opid = ops[table.currentRow()]["id"]
            self.run_job("正在验证备份并恢复，请保持 Codex 退出…", lambda: core.restore(self.home, opid), self.applied)

    def choose_home(self):
        path = QFileDialog.getExistingDirectory(self, "选择 Codex 数据目录", str(self.home))
        if path:
            self.home = core.home_path(path)
            self.checked.clear()
            self.rows = {}
            self.data = {"threads": [], "projects": [], "providers": []}
            self.render_tree()
            self.refresh()

    def closeEvent(self, event):
        if self.worker:
            self.status.setText("操作进行中，请等待完成后关闭。")
            event.ignore()
        else:
            if self.persist_settings:
                self.settings.setValue("geometry", self.saveGeometry())
            event.accept()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Codex 会话 Provider 切换工具")
    parser.add_argument("--codex-home")
    parser.add_argument("--smoke-test", metavar="SCREENSHOT", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    app = QApplication(sys.argv[:1])
    configure_app(app)
    window = MainWindow(args.codex_home, persist_settings=not bool(args.smoke_test))
    window.show()
    if args.smoke_test:
        # Packaged smoke test: read-only launch, capture our own widget, then exit.
        attempts = [0]

        def capture():
            attempts[0] += 1
            if not window.worker and window.data["threads"]:
                first = next(iter(window.items.values()), None)
                if first:
                    window.tree.setCurrentItem(first)
                window.grab().save(args.smoke_test)
                app.exit(0)
            elif attempts[0] > 120:
                app.exit(2)
            else:
                QTimer.singleShot(250, capture)
        QTimer.singleShot(250, capture)
    return app.exec()
