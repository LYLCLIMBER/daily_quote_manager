# daily_quote_manager

A small local KDE Plasma application for managing quotes and displaying a random quote through a desktop notification after each Plasma login.

## Features

- View, add, edit, and delete quotes
- UTF-8 and Chinese text support
- Random notification preview
- Enable or disable Plasma login notifications with one click
- Open the quote data directory
- Save quotes safely using atomic temporary-file replacement

## Dependencies

This project uses Python 3 and PyQt6. On EndeavourOS or Arch Linux, install the dependencies with:

```bash
sudo pacman -S python-pyqt6 libnotify
```

## Running

Run the application from the project directory:

```bash
cd /home/liuyulong/Codes/daily-quote-manager
python3 daily_quote_manager.py
```

You can also run it directly as an executable:

```bash
chmod +x daily_quote_manager.py
./daily_quote_manager.py
```

## Data Locations

The application files are kept in the project directory, while user data and KDE configuration are stored separately:

```text
~/.local/share/daily-quote/quotes.txt
~/.config/autostart/daily-quote.desktop
```

This is intentional: project code can be kept in a Git repository, while user data and desktop configuration follow the Linux/XDG directory conventions.

The quote file is a plain text file with one quote per line:

```text
“有“为什么”而活的人，几乎可以承受任何“怎么做”。 ——尼采“
```

Blank lines and lines beginning with `#` are ignored.

## Enabling And Disabling Notifications

The recommended method is to use the checkbox at the bottom of the GUI. You can also use the command line:

```bash
python3 daily_quote_manager.py --enable-autostart
python3 daily_quote_manager.py --disable-autostart
```

Once enabled, the following command runs when you log in to Plasma:

```bash
python3 /home/liuyulong/Codes/daily-quote-manager/daily_quote_manager.py --notify
```

Notification mode waits for approximately 8 seconds to ensure that the Plasma notification service has started.

To test notifications manually:

```bash
python3 daily_quote_manager.py --notify
```

## Testing

Run the complete test suite:

```bash
python3 -m unittest discover -s tests -v
```

Validate the autostart file:

```bash
desktop-file-validate ~/.config/autostart/daily-quote.desktop
```

## Rollback

Disable automatic notifications:

```bash
python3 daily_quote_manager.py --disable-autostart
```

Alternatively, remove the autostart file:

```bash
rm ~/.config/autostart/daily-quote.desktop
```

Application data can be removed separately:

```bash
rm -rf ~/.local/share/daily-quote
```

## Project Structure

```text
daily-quote-manager/
├── daily_quote_manager.py
├── tests/
│   └── test_daily_quote_manager.py
└── README.md
```
