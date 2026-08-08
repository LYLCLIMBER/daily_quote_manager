#!/usr/bin/env python3
"""A small Qt application for managing login-time quote notifications."""

from __future__ import annotations

import argparse
import os
import random
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QAction, QDesktopServices
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "daily_quote_manager"
DEFAULT_DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "daily-quote"
DEFAULT_AUTOSTART = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart" / "daily-quote.desktop"


class QuoteStore:
    def __init__(self, path: Path):
        self.path = Path(path).expanduser()

    def load(self) -> list[str]:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.touch()
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")]

    def save(self, quotes: list[str]) -> None:
        cleaned = [quote.strip() for quote in quotes if quote.strip()]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=".quotes-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as temporary:
                temporary.write("\n".join(cleaned))
                if cleaned:
                    temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, self.path)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass


class Autostart:
    def __init__(self, path: Path = DEFAULT_AUTOSTART):
        self.path = Path(path).expanduser()

    def is_enabled(self) -> bool:
        return self.path.exists()

    def enable(self, script: Path) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        command = shlex.join([sys.executable, str(script.resolve()), "--notify"])
        content = "\n".join(
            [
                "[Desktop Entry]",
                "Type=Application",
                "Version=1.0",
                f"Name={APP_NAME}",
                "Comment=登录 Plasma 后随机显示一句名言",
                f"Exec={command}",
                "Terminal=false",
                "StartupNotify=false",
                "X-KDE-autostart-after=panel",
                "X-GNOME-Autostart-enabled=true",
                "",
            ]
        )
        temporary = self.path.with_suffix(".desktop.tmp")
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, self.path)

    def disable(self) -> None:
        self.path.unlink(missing_ok=True)


def notify_from_store(store: QuoteStore, delay: float = 8) -> str | None:
    if delay:
        time.sleep(delay)
    quotes = store.load()
    if not quotes:
        return None
    quote = random.choice(quotes)
    subprocess.run(
        [
            "/usr/bin/notify-send",
            f"--app-name={APP_NAME}",
            "--icon=dialog-information",
            "--urgency=normal",
            "--expire-time=10000",
            APP_NAME,
            quote,
        ],
        check=True,
        shell=False,
    )
    return quote


class QuoteDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, text: str = ""):
        super().__init__(parent)
        self.setWindowTitle("编辑语录")
        self.resize(520, 180)
        layout = QVBoxLayout(self)
        self.editor = QTextEdit(self)
        self.editor.setPlainText(text)
        self.editor.setPlaceholderText("输入一句名言……")
        layout.addWidget(self.editor)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def text(self) -> str:
        return self.editor.toPlainText().strip()


class MainWindow(QMainWindow):
    def __init__(self, store: QuoteStore, autostart: Autostart):
        super().__init__()
        self.store = store
        self.autostart = autostart
        self.quotes = self.store.load()
        self.setWindowTitle(APP_NAME)
        self.resize(720, 520)
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.status = QLabel()
        layout.addWidget(self.status)
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(lambda _item: self.edit_quote())
        layout.addWidget(self.list_widget)

        row = QHBoxLayout()
        self.add_button = QPushButton("添加")
        self.edit_button = QPushButton("编辑")
        self.delete_button = QPushButton("删除")
        self.add_button.clicked.connect(self.add_quote)
        self.edit_button.clicked.connect(self.edit_quote)
        self.delete_button.clicked.connect(self.delete_quote)
        row.addWidget(self.add_button)
        row.addWidget(self.edit_button)
        row.addWidget(self.delete_button)
        row.addStretch()
        layout.addLayout(row)

        actions = QHBoxLayout()
        save_button = QPushButton("保存")
        preview_button = QPushButton("随机预览")
        open_button = QPushButton("打开数据目录")
        save_button.clicked.connect(self.save_quotes)
        preview_button.clicked.connect(self.preview)
        open_button.clicked.connect(self.open_data_dir)
        actions.addWidget(save_button)
        actions.addWidget(preview_button)
        actions.addWidget(open_button)
        actions.addStretch()
        layout.addLayout(actions)

        self.autostart_box = QCheckBox("登录 Plasma 时显示随机名言")
        self.autostart_box.setChecked(self.autostart.is_enabled())
        self.autostart_box.toggled.connect(self.toggle_autostart)
        layout.addWidget(self.autostart_box)

        menu = self.menuBar().addMenu("文件")
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        menu.addAction(exit_action)

    def _refresh(self) -> None:
        self.list_widget.clear()
        for quote in self.quotes:
            self.list_widget.addItem(QListWidgetItem(quote))
        state = "已启用" if self.autostart.is_enabled() else "已停用"
        self.status.setText(f"共 {len(self.quotes)} 条语录；登录通知：{state}")

    def add_quote(self) -> None:
        dialog = QuoteDialog(self)
        if dialog.exec() and dialog.text():
            self.quotes.append(dialog.text())
            self._refresh()

    def edit_quote(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            QMessageBox.information(self, APP_NAME, "请先选择一条语录。")
            return
        dialog = QuoteDialog(self, self.quotes[row])
        if dialog.exec() and dialog.text():
            self.quotes[row] = dialog.text()
            self._refresh()

    def delete_quote(self) -> None:
        row = self.list_widget.currentRow()
        if row < 0:
            QMessageBox.information(self, APP_NAME, "请先选择一条语录。")
            return
        answer = QMessageBox.question(self, APP_NAME, "确定删除选中的语录吗？")
        if answer == QMessageBox.StandardButton.Yes:
            del self.quotes[row]
            self._refresh()

    def save_quotes(self) -> None:
        try:
            self.store.save(self.quotes)
            self._refresh()
        except OSError as error:
            QMessageBox.critical(self, APP_NAME, f"保存失败：{error}")

    def preview(self) -> None:
        try:
            if not self.quotes:
                QMessageBox.information(self, APP_NAME, "还没有可显示的语录。")
                return
            temporary_store = QuoteStore(self.store.path)
            temporary_store.save(self.quotes)
            notify_from_store(temporary_store, delay=0)
        except (OSError, subprocess.SubprocessError) as error:
            QMessageBox.critical(self, APP_NAME, f"发送通知失败：{error}")

    def open_data_dir(self) -> None:
        self.store.path.parent.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.path.parent)))

    def toggle_autostart(self, enabled: bool) -> None:
        try:
            if enabled:
                self.autostart.enable(Path(__file__))
            else:
                self.autostart.disable()
            self._refresh()
        except OSError as error:
            self.autostart_box.blockSignals(True)
            self.autostart_box.setChecked(not enabled)
            self.autostart_box.blockSignals(False)
            QMessageBox.critical(self, APP_NAME, f"更新自动启动项失败：{error}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="daily_quote_manager")
    parser.add_argument("--notify", action="store_true", help="随机发送一条通知后退出")
    parser.add_argument("--enable-autostart", action="store_true", help="启用 Plasma 登录自动通知")
    parser.add_argument("--disable-autostart", action="store_true", help="停用 Plasma 登录自动通知")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = QuoteStore(DEFAULT_DATA_DIR / "quotes.txt")
    autostart = Autostart()

    if args.notify:
        notify_from_store(store)
        return 0
    if args.enable_autostart:
        autostart.enable(Path(__file__))
        return 0
    if args.disable_autostart:
        autostart.disable()
        return 0

    application = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    window = MainWindow(store, autostart)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
