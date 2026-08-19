#!/usr/bin/env python3
"""A small Qt application for managing login-time quote notifications."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import random
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QAction, QCloseEvent, QDesktopServices
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
    QMenu,
    QPushButton,
    QSpinBox,
    QStyle,
    QSystemTrayIcon,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "daily_quote_manager"
DEFAULT_DATA_DIR = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "daily-quote"
DEFAULT_AUTOSTART = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart" / "daily-quote.desktop"
DEFAULT_PERIODIC_AUTOSTART = DEFAULT_AUTOSTART.with_name("daily-quote-periodic.desktop")
DEFAULT_INTERVAL_MINUTES = 60
DEFAULT_SETTINGS: dict[str, object] = {
    "periodic_enabled": False,
    "interval_minutes": DEFAULT_INTERVAL_MINUTES,
}


def atomic_write_text(path: Path, content: str) -> None:
    """Write a file beside its destination, then replace it atomically."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


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
        content = "\n".join(cleaned) + ("\n" if cleaned else "")
        atomic_write_text(self.path, content)


class SettingsStore:
    def __init__(self, path: Path):
        self.path = Path(path).expanduser()

    def load(self) -> dict[str, object]:
        defaults = DEFAULT_SETTINGS.copy()
        if not self.path.exists():
            return defaults
        try:
            values = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return defaults
        if not isinstance(values, dict):
            return defaults
        enabled = values.get("periodic_enabled", defaults["periodic_enabled"])
        if isinstance(enabled, str):
            enabled = enabled.strip().lower() in {"1", "true", "yes", "on"}
        else:
            enabled = bool(enabled)
        defaults["periodic_enabled"] = enabled
        try:
            defaults["interval_minutes"] = max(1, int(values.get("interval_minutes", DEFAULT_INTERVAL_MINUTES)))
        except (TypeError, ValueError):
            defaults["interval_minutes"] = DEFAULT_INTERVAL_MINUTES
        return defaults

    def save(self, values: dict[str, object]) -> None:
        atomic_write_text(self.path, json.dumps(values, ensure_ascii=False, indent=2) + "\n")


class Autostart:
    def __init__(self, path: Path = DEFAULT_AUTOSTART, argument: str = "--notify"):
        self.path = Path(path).expanduser()
        self.argument = argument

    def is_enabled(self) -> bool:
        return self.path.exists()

    def enable(self, script: Path) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        command = shlex.join([sys.executable, str(script.resolve()), self.argument])
        content = "\n".join(
            [
                "[Desktop Entry]",
                "Type=Application",
                "Version=1.0",
                f"Name={APP_NAME}",
                "Comment=登录 Plasma 后显示名言",
                f"Exec={command}",
                "Terminal=false",
                "StartupNotify=false",
                "X-KDE-autostart-after=panel",
                "X-GNOME-Autostart-enabled=true",
                "",
            ]
        )
        atomic_write_text(self.path, content)

    def disable(self) -> None:
        self.path.unlink(missing_ok=True)


def run_notification_daemon(store: QuoteStore, settings: SettingsStore) -> None:
    """Run periodic notifications independently from the GUI process."""
    lock_path = settings.path.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w", encoding="utf-8") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        while True:
            values = settings.load()
            if not values["periodic_enabled"]:
                return
            notify_from_store(store, delay=8)
            time.sleep(int(values["interval_minutes"]) * 60)


def send_notification(quote: str) -> None:
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


def notify_from_store(store: QuoteStore, delay: float = 8) -> str | None:
    if delay:
        time.sleep(delay)
    quotes = store.load()
    if not quotes:
        return None
    quote = random.choice(quotes)
    send_notification(quote)
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
    def __init__(self, store: QuoteStore, autostart: Autostart, periodic_autostart: Autostart, settings: SettingsStore):
        super().__init__()
        self.store = store
        self.autostart = autostart
        self.periodic_autostart = periodic_autostart
        self.settings = settings
        self.notification_settings = settings.load()
        self.quotes = self.store.load()
        self.setWindowTitle(APP_NAME)
        self.resize(720, 520)
        self._build_ui()
        self._setup_tray()
        self._refresh()
        if self.periodic_box.isChecked():
            self.start_periodic_daemon()

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.status = QLabel()
        layout.addWidget(self.status)

        periodic_row = QHBoxLayout()
        self.periodic_box = QCheckBox("按频率显示随机名言")
        self.periodic_box.blockSignals(True)
        self.periodic_box.setChecked(bool(self.notification_settings["periodic_enabled"]))
        self.periodic_box.blockSignals(False)
        self.periodic_box.toggled.connect(self.toggle_periodic)
        periodic_row.addWidget(self.periodic_box)
        periodic_row.addWidget(QLabel("每"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 1440)
        self.interval_spin.setValue(int(self.notification_settings["interval_minutes"]))
        self.interval_spin.setSuffix(" 分钟")
        self.interval_spin.valueChanged.connect(self.change_interval)
        periodic_row.addWidget(self.interval_spin)
        periodic_row.addStretch()
        layout.addLayout(periodic_row)

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

    def _setup_tray(self) -> None:
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation))
        self.tray_icon.setToolTip("daily_quote_manager")

        tray_menu = QMenu(self)
        show_action = QAction("显示窗口", self)
        show_action.triggered.connect(self.show_window)
        quit_action = QAction("退出管理器", self)
        quit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._tray_activated)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon.show()

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_window()

    def show_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_application(self) -> None:
        self._allow_close = True
        self.tray_icon.hide()
        self.close()

    def closeEvent(self, event: QCloseEvent) -> None:
        if getattr(self, "_allow_close", False) or not QSystemTrayIcon.isSystemTrayAvailable():
            event.accept()
            return
        self.hide()
        event.ignore()

    def _refresh(self) -> None:
        self.list_widget.clear()
        for quote in self.quotes:
            self.list_widget.addItem(QListWidgetItem(quote))
        state = "已启用" if self.autostart.is_enabled() else "已停用"
        periodic_state = "已启用" if self.periodic_box.isChecked() else "已停用"
        self.status.setText(f"共 {len(self.quotes)} 条语录；登录通知：{state}；定时通知：{periodic_state}")
        tray_state = "运行中" if self.periodic_box.isChecked() else "未启用定时通知"
        self.tray_icon.setToolTip(f"daily_quote_manager：{tray_state}")

    def save_notification_settings(self) -> None:
        self.notification_settings["periodic_enabled"] = self.periodic_box.isChecked()
        self.notification_settings["interval_minutes"] = self.interval_spin.value()
        try:
            self.settings.save(self.notification_settings)
            if self.periodic_box.isChecked():
                self.start_periodic_daemon()
            else:
                self.periodic_autostart.disable()
            self._refresh()
        except (OSError, subprocess.SubprocessError) as error:
            QMessageBox.critical(self, APP_NAME, f"保存通知设置失败：{error}")

    def start_periodic_daemon(self) -> None:
        self.periodic_autostart.enable(Path(__file__))
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--notify-daemon"],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def toggle_periodic(self, _enabled: bool) -> None:
        self.save_notification_settings()

    def change_interval(self, _minutes: int) -> None:
        if self.periodic_box.isChecked():
            self.save_notification_settings()

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
            send_notification(random.choice(self.quotes))
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
    parser.add_argument("--notify-daemon", action="store_true", help="后台按设置周期发送通知")
    parser.add_argument("--enable-autostart", action="store_true", help="启用 Plasma 登录自动通知")
    parser.add_argument("--disable-autostart", action="store_true", help="停用 Plasma 登录自动通知")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = QuoteStore(DEFAULT_DATA_DIR / "quotes.txt")
    settings = SettingsStore(DEFAULT_DATA_DIR / "settings.json")
    autostart = Autostart()
    periodic_autostart = Autostart(DEFAULT_PERIODIC_AUTOSTART, "--notify-daemon")

    if args.notify:
        notify_from_store(store)
        return 0
    if args.notify_daemon:
        run_notification_daemon(store, settings)
        return 0
    if args.enable_autostart:
        autostart.enable(Path(__file__))
        return 0
    if args.disable_autostart:
        autostart.disable()
        return 0

    application = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    window = MainWindow(store, autostart, periodic_autostart, settings)
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
