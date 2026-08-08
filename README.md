# 每日名言管理器

一个适用于 KDE Plasma 的本地小程序，用于管理名言语录，并在每次登录 Plasma 后通过桌面通知随机显示一句。

## 功能

- 查看、添加、编辑、删除语录
- UTF-8 中文支持
- 随机预览通知
- 一键启用或停用 Plasma 登录通知
- 打开语录数据目录
- 使用安全的临时文件替换方式保存语录
- 首次运行时自动迁移旧版 `~/.local/share/quotes.txt`，不会删除原文件

## 依赖

本项目使用 Python 3 和 PyQt6。EndeavourOS/Arch Linux 可以安装：

```bash
sudo pacman -S python-pyqt6 libnotify
```

## 运行

在项目目录执行：

```bash
cd /home/liuyulong/Codes/daily-quote-manager
python3 daily_quote_manager.py
```

也可以直接执行：

```bash
chmod +x daily_quote_manager.py
./daily_quote_manager.py
```

## 当前数据位置

程序文件位于项目目录，但用户数据和 KDE 配置不会写入项目目录：

```text
~/.local/share/daily-quote/quotes.txt
~/.config/autostart/daily-quote.desktop
```

这是有意设计的：项目代码可以放在 Git 仓库中，用户数据和桌面配置则遵循 Linux/XDG 目录规范。

语录文件仍然是普通文本文件，每行一句：

```text
“有“为什么”而活的人，几乎可以承受任何“怎么做”。 ——尼采“
```

空行和以 `#` 开头的行会被忽略。

## 启用和停用自动通知

推荐通过 GUI 底部的复选框操作，也可以使用命令行：

```bash
python3 daily_quote_manager.py --enable-autostart
python3 daily_quote_manager.py --disable-autostart
```

启用后，Plasma 登录时会执行：

```bash
python3 /home/liuyulong/Codes/daily-quote-manager/daily_quote_manager.py --notify
```

通知模式会等待约 8 秒，确保 Plasma 通知服务已经启动。

手动测试通知：

```bash
python3 daily_quote_manager.py --notify
```

## 数据迁移

程序首次运行时，如果新的数据文件不存在而旧文件存在：

```text
~/.local/share/quotes.txt
```

程序会将旧文件复制到：

```text
~/.local/share/daily-quote/quotes.txt
```

原文件不会被删除，便于回滚。旧版的：

```text
~/.local/bin/daily-quote
```

不会被程序自动删除；确认新程序工作正常后，可以手动删除。

## 测试

运行全部测试：

```bash
python3 -m unittest discover -s tests -v
```

检查自动启动文件：

```bash
desktop-file-validate ~/.config/autostart/daily-quote.desktop
```

## 回滚

停用自动通知：

```bash
python3 daily_quote_manager.py --disable-autostart
```

或者删除自动启动文件：

```bash
rm ~/.config/autostart/daily-quote.desktop
```

程序数据可以单独删除：

```bash
rm -rf ~/.local/share/daily-quote
```

如果需要恢复旧版配置，原来的以下文件不会被程序自动删除：

```text
~/.local/share/quotes.txt
~/.local/bin/daily-quote
```

## 项目结构

```text
daily-quote-manager/
├── daily_quote_manager.py
├── tests/
│   └── test_daily_quote_manager.py
└── README.md
```
