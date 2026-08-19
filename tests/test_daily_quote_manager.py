import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1]))
import daily_quote_manager as app


class QuoteStoreTests(unittest.TestCase):
    def test_load_ignores_blank_lines_and_comments(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quotes.txt"
            path.write_text("\n# 注释\n第一句\n  \n第二句\n", encoding="utf-8")
            self.assertEqual(app.QuoteStore(path).load(), ["第一句", "第二句"])

    def test_save_uses_utf8_and_can_read_chinese(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quotes.txt"
            store = app.QuoteStore(path)
            store.save(["有‘为什么’而活的人，几乎可以承受任何‘怎么做’。 ——尼采"])
            self.assertEqual(store.load(), ["有‘为什么’而活的人，几乎可以承受任何‘怎么做’。 ——尼采"])

    def test_save_replaces_existing_file_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quotes.txt"
            path.write_text("旧内容\n", encoding="utf-8")
            app.QuoteStore(path).save(["新内容"])
            self.assertEqual(path.read_text(encoding="utf-8"), "新内容\n")
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])


class SettingsStoreTests(unittest.TestCase):
    def test_load_returns_defaults_and_save_persists_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = app.SettingsStore(Path(tmp) / "settings.json")
            self.assertEqual(store.load(), {"periodic_enabled": False, "interval_minutes": 60})
            store.save({"periodic_enabled": True, "interval_minutes": 15})
            self.assertEqual(store.load(), {"periodic_enabled": True, "interval_minutes": 15})

    def test_load_normalizes_invalid_interval(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text('{"periodic_enabled": true, "interval_minutes": 0}', encoding="utf-8")
            self.assertEqual(app.SettingsStore(path).load()["interval_minutes"], 1)

    def test_load_parses_string_boolean_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text('{"periodic_enabled": "false"}', encoding="utf-8")
            self.assertFalse(app.SettingsStore(path).load()["periodic_enabled"])

    def test_save_does_not_leave_temporary_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            app.SettingsStore(path).save({"periodic_enabled": True, "interval_minutes": 5})
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])


class NotificationTests(unittest.TestCase):
    @patch.object(app.time, "sleep")
    @patch.object(app.subprocess, "run")
    def test_notify_uses_notify_send_without_shell(self, run, sleep):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quotes.txt"
            path.write_text("测试语录\n", encoding="utf-8")
            app.notify_from_store(app.QuoteStore(path), delay=8)
            sleep.assert_called_once_with(8)
            run.assert_called_once()
            command = run.call_args.args[0]
            self.assertEqual(command[0], "/usr/bin/notify-send")
            self.assertIn("测试语录", command)
            self.assertFalse(run.call_args.kwargs["shell"])

    @patch.object(app.time, "sleep", side_effect=[None, KeyboardInterrupt])
    @patch.object(app, "notify_from_store")
    def test_periodic_daemon_notifies_using_saved_interval(self, notify, sleep):
        with tempfile.TemporaryDirectory() as tmp:
            settings = app.SettingsStore(Path(tmp) / "settings.json")
            settings.save({"periodic_enabled": True, "interval_minutes": 1})
            with self.assertRaises(KeyboardInterrupt):
                app.run_notification_daemon(app.QuoteStore(Path(tmp) / "quotes.txt"), settings)
            self.assertEqual(notify.call_count, 2)
            self.assertEqual(sleep.call_args_list[0].args, (60,))


class AutostartTests(unittest.TestCase):
    def test_enable_writes_valid_desktop_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "daily-quote.desktop"
            app.Autostart(path).enable(Path("/opt/daily quote/daily_quote_manager.py"))
            content = path.read_text(encoding="utf-8")
            self.assertIn("[Desktop Entry]", content)
            self.assertIn("--notify", content)
            self.assertIn("Type=Application", content)

    def test_disable_removes_only_managed_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "daily-quote.desktop"
            path.write_text("managed", encoding="utf-8")
            app.Autostart(path).disable()
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
