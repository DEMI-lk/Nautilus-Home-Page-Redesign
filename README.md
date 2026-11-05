# Nautilus Home Page Redesign

A clean, beginner-friendly **Home Dashboard** for GNOME Files (Nautilus). When you open *Home*, you get a curated page of folder shortcuts — Workspace, Places, and your own — instead of a messy wall of everything in `~`.

> This is a vibe-coded solution 😅 — I built it because I really love Windows Explorer's tidy, organized feel and wanted GNOME Files to feel the same way. It should especially help Linux beginners get comfortable with the GNOME file manager, so they don't get overwhelmed by a cluttered home folder on day one.

---

## What it does

| Before | After — Home Dashboard |
|---|---|
| Every file & folder in `~` dumped in one view | Only the folders that matter |
| Hidden dotfiles & dev dirs in your face | Hidden / config clutter never shown |
| No clear starting point | Big, friendly shortcut cards |

- **Workspace** section auto-detects `Projects/`, `My Files/`, `Development/` and similar folders if they exist locally.
- **Places** section auto-adds Documents, Downloads, Pictures, Music, Videos, Desktop (only those present on disk).
- Click any card → opens the real folder. "Show all files" toggles back to the normal Nautilus view for `~`.
- **100% presentation layer** — no file is ever moved, renamed, or deleted. Shortcuts are just paths stored in one JSON config.

---

## Features

- ✅ Curated dashboard replaces the Home listing
- ✅ Right-click any folder → **Add to Home Dashboard…**
- ✅ Right-click empty space in Home → **Home Dashboard / Show all files / Customize…**
- ✅ `Ctrl+Alt+H` toggles Dashboard ↔ normal view
- ✅ Dashboard editor: add, rename, reorder, remove shortcuts
- ✅ Auto-show toggle (show dashboard every time you open Home)
- ✅ Per-tab awareness (each Nautilus tab behaves independently)
- ✅ English, French, and German UI strings
- ✅ Tested on Nautilus 51.1 (Fedora 45) · also supports Nautilus 46 via the 4.0 import fallback

---

## Requirements

- GNOME Files (Nautilus) 46 or newer
- Python 3 + PyGObject
- GTK 4 + libadwaita 1 (`gir1.2-gtk-4.0`, `gir1.2-adw-1` on Debian/Ubuntu)
- `nautilus-python` (the runtime that loads Python extensions)
- No other dependencies

## Installation

### Fedora

```bash
sudo dnf install nautilus-python
mkdir -p ~/.local/share/nautilus-python/extensions
cp home-dashboard.py ~/.local/share/nautilus-python/extensions/
rm -rf ~/.local/share/nautilus-python/extensions/__pycache__
nautilus -q
```

### Ubuntu / Debian

```bash
sudo apt install python3-nautilus python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
mkdir -p ~/.local/share/nautilus-python/extensions
cp home-dashboard.py ~/.local/share/nautilus-python/extensions/
rm -rf ~/.local/share/nautilus-python/extensions/__pycache__
nautilus -q
```

> The `nautilus-python` package is essential — without it, Nautilus simply ignores the `.py` file and nothing changes.

### Verify

```bash
ls /usr/lib64/nautilus/extensions-4/libnautilus-python.so   # Fedora
```

Reopen Files → **Home**. You should see the dashboard instead of the raw folder list.

---

## Usage

| Action | How |
|---|---|
| Toggle dashboard | `Ctrl+Alt+H` |
| Pin a folder | Right-click folder → *Add to Home Dashboard…* |
| Unpin | Right-click it → *Remove from Home Dashboard* |
| Open dashboard | Right-click empty area in Home / Home sidebar |
| Show real files | *Show all files* button or context menu |
| Customize | *Customize Home Dashboard…* (rename, reorder, remove, restore defaults) |
| Disable auto-show | Editor → "Show dashboard when Home is opened" |

**Configuration** lives at `~/.config/nautilus-home-dashboard/config.json` (created on first run). It stores sections, names, paths, icons, and the auto-show flag.

---

## How it works

Nautilus 43+ removed `LocationWidgetProvider` and has no public "custom view" API. To still replace what Home shows, this extension:

1. Finds every `NautilusWindowSlot`'s top-level `GtkStack` (via `Adw.TabView → page → slot`).
2. Adds the dashboard as a third child of that stack, alongside Nautilus's own views.
3. Shows the dashboard child only when the slot's location equals `$HOME`, restoring the native child otherwise (handles tabs, back/forward, pathbar, location bar).
4. Uses solid GTK 4 + libadwaita widgets (FlowBox cards, `Adw.Clamp`, `Adw.WindowTitle`), so it follows your light/dark theme and icon theme.

Because step 1 touches internals, it may need small tweaks when Nautilus changes its widget tree — but the context-menu items keep working even if injection ever fails.

---

## Technical details

- Single file: `home-dashboard.py` (~1,900 lines)
- `Nautilus.MenuProvider` for all context menus & the `Ctrl+Alt+H` shortcut — no polling, event-driven via `notify::location` on each slot.
- Config model: `DashboardConfig` → JSON (atomic write via temp file + `os.replace`, mode `0600`).
- UI strings: EN / FR / DE. Icons: safe lookup with `folder-symbolic` fallback.
- Standalone preview: `python3 home-dashboard.py` opens the dashboard in its own window (for testing without Nautilus).

---

## Uninstall

```bash
rm ~/.local/share/nautilus-python/extensions/home-dashboard.py
rm -f ~/.config/nautilus-home-dashboard/config.json
nautilus -q
```

Removing the file reverts everything — no files were ever modified, so there's nothing to undo.

---

## Development notes

```bash
python3 -m py_compile home-dashboard.py
python3 home-dashboard.py            # preview window
```

Set `NAUTILUS_HOME_DASHBOARD_DEBUG=1` for diagnostic logging.

---

## Disclaimer

Built with ❤️ (and a lot of vibe coding) for newcomers to Linux who want GNOME Files to feel calmer and more organized. MIT-style onboarding helper — fork, customize, enjoy.

## License

GPL-3.0 — inherited from the original `Nautilus-Extensions` collection conventions. See `LICENSE`.

---

<sub>Made with ❤️ · No telemetry, no spyware · Presentation layer only — your files stay exactly where they are.</sub>
