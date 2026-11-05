#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# NAME: Home Dashboard — Nautilus Python Extension
# AUTHOR: Tof
# VERSION: 1.0
# LICENSE: GNU General Public License v3.0
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
#
# NAME: Home Dashboard – Nautilus Python Extension
# REQUIRES: python3-nautilus (>= 4.0), python3-gi, gir1.2-gtk-4.0,
#           gir1.2-adw-1
# INSTALL:
#   cp home-dashboard.py ~/.local/share/nautilus-python/extensions/
#   rm -rf ~/.local/share/nautilus-python/extensions/__pycache__
#   nautilus -q
#
# WHAT IT DOES
# ------------
# Nautilus has no public "custom view" API (LocationWidgetProvider was removed
# in Nautilus 43). To give Home a curated dashboard anyway, this extension
# injects one extra child into the per-tab GtkStack that Nautilus uses for the
# file view, then shows that child only while the tab is at $HOME.
#
# This is deliberately a presentation layer:
#   * no file is moved, renamed or deleted;
#   * the real home directory is never modified;
#   * "Show all files" reveals the normal Nautilus view for $HOME;
#   * shortcuts are just paths stored in a JSON config file.
#
# Because the injection uses Nautilus internals, it may need small adjustments
# when Nautilus changes its widget tree. The menu item remains available even
# if injection is not possible, so the dashboard can still be extended later.

import json
import locale
import os
import tempfile
import weakref
from dataclasses import dataclass, field

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
gi.require_version("Pango", "1.0")

# Nautilus 46 ships the 4.0 typelib; Nautilus 49+ ships 4.1.  Supporting both
# means the same file works on the versions this repository targets.
try:
    gi.require_version("Nautilus", "4.0")
    from gi.repository import Nautilus
except (ValueError, ImportError):
    gi.require_version("Nautilus", "4.1")
    from gi.repository import Nautilus

from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk, Pango

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HOME_DIR = os.path.realpath(GLib.get_home_dir())
HOME_FILE = Gio.File.new_for_path(HOME_DIR)

CONFIG_DIR = os.path.join(GLib.get_user_config_dir(), "nautilus-home-dashboard")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

STACK_CHILD_PREFIX = "home-dashboard-"
SHORTCUT_ACCEL = "<Control><Alt>h"
DEBUG = os.environ.get("NAUTILUS_HOME_DASHBOARD_DEBUG", "").lower() in (
    "1", "true", "yes", "on"
)

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------

_lang = (locale.getlocale()[0] or os.environ.get("LANG", "") or "").lower()

if _lang.startswith("fr"):
    T = {
        "menu_add": "Ajouter au tableau de bord…",
        "menu_add_tip": "Afficher ce dossier sur la page d'accueil personnalisée",
        "menu_remove": "Retirer du tableau de bord",
        "menu_remove_tip": "Retirer le raccourci (les fichiers restent sur le disque)",
        "menu_open": "Tableau de bord d'accueil",
        "menu_open_tip": "Ouvrir la page d'accueil personnalisée",
        "menu_show_all": "Afficher tous les fichiers",
        "menu_show_all_tip": "Afficher le véritable contenu du dossier personnel",
        "menu_customize": "Personnaliser le tableau de bord…",
        "menu_customize_tip": "Ajouter, renommer ou retirer des raccourcis",
        "title": "Accueil",
        "subtitle": "Un point de départ clair vers les dossiers qui comptent.",
        "show_all": "Afficher tous les fichiers",
        "edit": "Modifier le tableau de bord",
        "add_folder": "Ajouter un dossier",
        "empty_title": "Aucun raccourci pour l'instant",
        "empty_sub": "Ajoutez des dossiers pour construire votre page d'accueil.",
        "missing": "Dossier introuvable",
        "missing_body": "Le dossier n'existe pas ou n'est pas accessible :\n{path}",
        "section_workspace": "Espace de travail",
        "section_places": "Emplacements",
        "section_shortcuts": "Raccourcis",
        "footer": "Cette page est une vue personnalisée. Vos fichiers restent exactement là où ils sont.",
        "editor_title": "Tableau de bord d'accueil",
        "editor_subtitle": "Choisissez ce qui apparaît sur votre page d'accueil",
        "editor_general": "Général",
        "editor_auto_show": "Afficher le tableau de bord en ouvrant l'accueil",
        "editor_auto_show_sub": "Si désactivé, l'accueil affiche les fichiers normaux. Le tableau de bord reste accessible par le menu contextuel ou Ctrl+Alt+H.",
        "editor_reset": "Rétablir les valeurs par défaut",
        "editor_reset_title": "Rétablir le tableau de bord ?",
        "editor_reset_body": "Les raccourcis personnalisés seront remplacés par la sélection automatique de dossiers. Aucun fichier ne sera supprimé.",
        "editor_config_hint": "Configuration : {path}",
        "editor_empty": "Aucun raccourci. Utilisez « Ajouter un dossier » ci-dessous.",
        "dialog_add_title": "Ajouter un dossier",
        "dialog_edit_title": "Modifier le raccourci",
        "dialog_name": "Nom affiché",
        "dialog_section": "Section",
        "dialog_path": "Emplacement réel",
        "choose_folder": "Choisir un dossier à ajouter",
        "name_required": "Le nom affiché ne peut pas être vide.",
        "already_added": "Ce dossier figure déjà sur le tableau de bord.",
        "cancel": "Annuler",
        "save": "Enregistrer",
        "reset": "Rétablir",
        "move_up": "Monter",
        "move_down": "Descendre",
        "edit_item": "Modifier",
        "remove_item": "Retirer du tableau de bord",
        "done": "Terminé",
        "folder_missing": "Dossier introuvable :\n{path}",
    }
elif _lang.startswith("de"):
    T = {
        "menu_add": "Zum Home-Dashboard hinzufügen…",
        "menu_add_tip": "Diesen Ordner auf der persönlichen Startseite anzeigen",
        "menu_remove": "Vom Home-Dashboard entfernen",
        "menu_remove_tip": "Die Verknüpfung entfernen (Dateien bleiben auf der Festplatte)",
        "menu_open": "Home-Dashboard",
        "menu_open_tip": "Die persönliche Startseite öffnen",
        "menu_show_all": "Alle Dateien anzeigen",
        "menu_show_all_tip": "Den echten Inhalt des Home-Ordners anzeigen",
        "menu_customize": "Home-Dashboard anpassen…",
        "menu_customize_tip": "Verknüpfungen hinzufügen, umbenennen oder entfernen",
        "title": "Home",
        "subtitle": "Ein aufgeräumter Einstiegspunkt zu den Ordnern, die zählen.",
        "show_all": "Alle Dateien anzeigen",
        "edit": "Dashboard bearbeiten",
        "add_folder": "Ordner hinzufügen",
        "empty_title": "Noch keine Verknüpfungen",
        "empty_sub": "Füge Ordner hinzu, um deine Startseite aufzubauen.",
        "missing": "Ordner nicht gefunden",
        "missing_body": "Der Ordner existiert nicht oder ist nicht erreichbar:\n{path}",
        "section_workspace": "Arbeitsbereich",
        "section_places": "Orte",
        "section_shortcuts": "Verknüpfungen",
        "footer": "Diese Seite ist nur eine Ansicht. Deine Dateien bleiben genau dort, wo sie sind.",
        "editor_title": "Home-Dashboard",
        "editor_subtitle": "Lege fest, was auf deiner Startseite erscheint",
        "editor_general": "Allgemein",
        "editor_auto_show": "Dashboard beim Öffnen von Home anzeigen",
        "editor_auto_show_sub": "Wenn deaktiviert, zeigt Home die normalen Dateien. Das Dashboard bleibt über das Kontextmenü oder Strg+Alt+H erreichbar.",
        "editor_reset": "Standard wiederherstellen",
        "editor_reset_title": "Dashboard zurücksetzen?",
        "editor_reset_body": "Eigene Verknüpfungen werden durch die automatische Ordnerauswahl ersetzt. Es werden keine Dateien gelöscht.",
        "editor_config_hint": "Konfiguration: {path}",
        "editor_empty": "Keine Verknüpfungen. Verwende unten „Ordner hinzufügen“.",
        "dialog_add_title": "Ordner hinzufügen",
        "dialog_edit_title": "Verknüpfung bearbeiten",
        "dialog_name": "Anzeigename",
        "dialog_section": "Bereich",
        "dialog_path": "Tatsächlicher Speicherort",
        "choose_folder": "Ordner zum Hinzufügen wählen",
        "name_required": "Der Anzeigename darf nicht leer sein.",
        "already_added": "Dieser Ordner ist bereits auf dem Dashboard.",
        "cancel": "Abbrechen",
        "save": "Speichern",
        "reset": "Zurücksetzen",
        "move_up": "Nach oben",
        "move_down": "Nach unten",
        "edit_item": "Bearbeiten",
        "remove_item": "Vom Dashboard entfernen",
        "done": "Fertig",
        "folder_missing": "Ordner nicht gefunden:\n{path}",
    }
else:
    T = {
        "menu_add": "Add to Home Dashboard…",
        "menu_add_tip": "Show this folder on the curated Home page",
        "menu_remove": "Remove from Home Dashboard",
        "menu_remove_tip": "Remove the shortcut (files stay on disk)",
        "menu_open": "Home Dashboard",
        "menu_open_tip": "Open the curated Home page",
        "menu_show_all": "Show All Files",
        "menu_show_all_tip": "Show the real contents of your home folder",
        "menu_customize": "Customize Home Dashboard…",
        "menu_customize_tip": "Add, rename or remove shortcuts",
        "title": "Home",
        "subtitle": "A clean starting point for the folders that matter.",
        "show_all": "Show all files",
        "edit": "Edit dashboard",
        "add_folder": "Add folder",
        "empty_title": "No shortcuts yet",
        "empty_sub": "Add folders to build your own Home page.",
        "missing": "Folder not found",
        "missing_body": "The folder does not exist or is not accessible:\n{path}",
        "section_workspace": "Workspace",
        "section_places": "Places",
        "section_shortcuts": "Shortcuts",
        "footer": "This page is a presentation layer. Your files stay exactly where they are.",
        "editor_title": "Home Dashboard",
        "editor_subtitle": "Choose what appears on your Home page",
        "editor_general": "General",
        "editor_auto_show": "Show dashboard when Home is opened",
        "editor_auto_show_sub": "When disabled, Home shows normal files. The dashboard stays available from the context menu or Ctrl+Alt+H.",
        "editor_reset": "Restore defaults",
        "editor_reset_title": "Restore the dashboard?",
        "editor_reset_body": "Custom shortcuts will be replaced by the automatic folder selection. No files will be deleted.",
        "editor_config_hint": "Configuration: {path}",
        "editor_empty": "No shortcuts. Use “Add folder” below.",
        "dialog_add_title": "Add folder",
        "dialog_edit_title": "Edit shortcut",
        "dialog_name": "Display name",
        "dialog_section": "Section",
        "dialog_path": "Real location",
        "choose_folder": "Choose a folder to add",
        "name_required": "The display name cannot be empty.",
        "already_added": "This folder is already on the dashboard.",
        "cancel": "Cancel",
        "save": "Save",
        "reset": "Restore",
        "move_up": "Move up",
        "move_down": "Move down",
        "edit_item": "Edit",
        "remove_item": "Remove from dashboard",
        "done": "Done",
        "folder_missing": "Folder not found:\n{path}",
    }

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def _log(message):
    if DEBUG:
        print(f"HomeDashboard: {message}", flush=True)


# ---------------------------------------------------------------------------
# Configuration model
# ---------------------------------------------------------------------------


def _normalise_path(path):
    if not path:
        return ""
    return os.path.normpath(os.path.abspath(os.path.expanduser(path)))


def _short_path(path):
    path = path or ""
    if path == HOME_DIR:
        return "~"
    prefix = HOME_DIR + os.sep
    if path.startswith(prefix):
        return "~" + path[len(HOME_DIR):]
    return path


def _is_real_dir(path):
    try:
        if not os.path.isdir(path):
            return False
        return os.path.realpath(path) != HOME_DIR
    except OSError:
        return False


_ICON_BY_NAME = {
    "projects": "folder-symbolic",
    "project": "folder-symbolic",
    "my files": "folder-symbolic",
    "files": "folder-symbolic",
    "documents": "folder-documents-symbolic",
    "downloads": "folder-download-symbolic",
    "pictures": "folder-pictures-symbolic",
    "photos": "folder-pictures-symbolic",
    "music": "folder-music-symbolic",
    "videos": "folder-videos-symbolic",
    "desktop": "user-desktop-symbolic",
    "development": "folder-symbolic",
    "dev": "folder-symbolic",
    "code": "folder-symbolic",
}


def _icon_for(name, path=""):
    key = (name or "").strip().lower()
    if key in _ICON_BY_NAME:
        return _ICON_BY_NAME[key]
    base = os.path.basename(path or "").lower()
    if base in _ICON_BY_NAME:
        return _ICON_BY_NAME[base]
    if "project" in key or "project" in base:
        return "folder-symbolic"
    return "folder-symbolic"


def _safe_icon_name(name):
    name = name or "folder-symbolic"
    try:
        display = Gdk.Display.get_default()
        if display is None:
            return name
        theme = Gtk.IconTheme.get_for_display(display)
        if theme.has_icon(name):
            return name
    except Exception:
        return name
    return "folder-symbolic"


@dataclass
class Shortcut:
    name: str
    path: str
    icon: str = "folder-symbolic"

    def to_dict(self):
        return {
            "name": self.name,
            "path": self.path,
            "icon": self.icon,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            name=str(data.get("name") or "").strip(),
            path=_normalise_path(str(data.get("path") or "")),
            icon=str(data.get("icon") or "folder-symbolic"),
        )


@dataclass
class Section:
    title: str
    items: list = field(default_factory=list)

    def to_dict(self):
        return {
            "title": self.title,
            "items": [item.to_dict() for item in self.items],
        }

    @classmethod
    def from_dict(cls, data):
        section = cls(title=str(data.get("title") or "").strip())
        for raw in data.get("items") or []:
            if not isinstance(raw, dict):
                continue
            item = Shortcut.from_dict(raw)
            if item.name and item.path:
                section.items.append(item)
        return section


@dataclass
class DashboardConfig:
    auto_show: bool = True
    sections: list = field(default_factory=list)

    # -- serialisation ------------------------------------------------------

    def to_dict(self):
        return {
            "version": 1,
            "auto_show": bool(self.auto_show),
            "sections": [section.to_dict() for section in self.sections],
        }

    @classmethod
    def from_dict(cls, data):
        config = cls(auto_show=bool(data.get("auto_show", True)))
        for raw in data.get("sections") or []:
            if not isinstance(raw, dict):
                continue
            section = Section.from_dict(raw)
            if section.title:
                config.sections.append(section)
        config._normalise()
        return config

    def _normalise(self):
        seen = set()
        clean_sections = []
        for section in self.sections:
            title = (section.title or "").strip()
            if not title:
                continue
            clean_items = []
            for item in section.items:
                path = _normalise_path(item.path)
                if not item.name or not path or path in seen:
                    continue
                seen.add(path)
                icon = item.icon or _icon_for(item.name, path)
                clean_items.append(Shortcut(item.name.strip(), path, icon))
            if clean_items:
                clean_sections.append(Section(title, clean_items))
        self.sections = clean_sections

    def save(self):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                prefix=".config-", suffix=".json", dir=CONFIG_DIR
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(self.to_dict(), handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    os.chmod(tmp_path, 0o600)
                except OSError:
                    pass
                os.replace(tmp_path, CONFIG_PATH)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as exc:
            _log(f"could not save config: {exc}")

    @classmethod
    def load(cls):
        if not os.path.exists(CONFIG_PATH):
            config = cls.default(save=False)
            config.save()
            return config
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            if not isinstance(data, dict):
                raise ValueError("top-level JSON value is not an object")
            return cls.from_dict(data)
        except Exception as exc:
            _log(f"could not read config ({exc}); using in-memory defaults")
            return cls.default(save=False)

    # -- default dashboard --------------------------------------------------

    @classmethod
    def default(cls, save=False):
        config = cls(auto_show=True)
        seen = set()

        def add_section(title, entries):
            items = []
            for name, candidates, icon in entries:
                for candidate in candidates:
                    path = _normalise_path(candidate)
                    if path in seen or not _is_real_dir(path):
                        continue
                    seen.add(path)
                    items.append(Shortcut(name, path, icon))
                    break
            if items:
                config.sections.append(Section(title, items))

        add_section(
            T["section_workspace"],
            [
                ("Projects", ["~/Projects", "~/projects"], "folder-symbolic"),
                ("My Files", ["~/MyFiles", "~/myfiles", "~/Files", "~/files"],
                 "folder-symbolic"),
                ("Development",
                 ["~/Development", "~/development", "~/Dev", "~/dev",
                  "~/Code", "~/code"], "folder-symbolic"),
            ],
        )

        special_dirs = [
            (GLib.UserDirectory.DIRECTORY_DOCUMENTS, "folder-documents-symbolic"),
            (GLib.UserDirectory.DIRECTORY_DOWNLOAD, "folder-download-symbolic"),
            (GLib.UserDirectory.DIRECTORY_PICTURES, "folder-pictures-symbolic"),
            (GLib.UserDirectory.DIRECTORY_MUSIC, "folder-music-symbolic"),
            (GLib.UserDirectory.DIRECTORY_VIDEOS, "folder-videos-symbolic"),
            (GLib.UserDirectory.DIRECTORY_DESKTOP, "user-desktop-symbolic"),
        ]
        places = []
        for directory, icon in special_dirs:
            try:
                path = GLib.get_user_special_dir(directory)
            except Exception:
                continue
            if not path:
                continue
            path = _normalise_path(path)
            if path in seen or not _is_real_dir(path):
                continue
            name = os.path.basename(path.rstrip(os.sep)) or "Folder"
            seen.add(path)
            places.append(Shortcut(name, path, icon))
        if places:
            config.sections.append(Section(T["section_places"], places))

        if save:
            config.save()
        return config

    # -- queries ------------------------------------------------------------

    def iter_items(self):
        for section in self.sections:
            for item in section.items:
                yield section, item

    def find_item(self, path):
        path = _normalise_path(path)
        for section, item in self.iter_items():
            if item.path == path:
                return section, item
        return None, None

    def section_titles(self):
        return [section.title for section in self.sections]

    def _find_section(self, title):
        title = (title or "").strip()
        for section in self.sections:
            if section.title == title:
                return section
        return None

    def _ensure_section(self, title):
        title = (title or "").strip() or T["section_shortcuts"]
        section = self._find_section(title)
        if section is None:
            section = Section(title, [])
            self.sections.append(section)
        return section

    # -- mutations ----------------------------------------------------------

    def add_paths(self, paths, preferred_sections=None):
        preferred_sections = preferred_sections or [T["section_shortcuts"], "Shortcuts"]
        new_paths = []
        seen = set()
        for raw in paths:
            path = _normalise_path(raw)
            if (
                not path
                or path in seen
                or self.find_item(path)[1] is not None
            ):
                continue
            seen.add(path)
            new_paths.append(path)
        if not new_paths:
            return 0

        target = None
        for title in preferred_sections:
            target = self._find_section(title)
            if target is not None:
                break
        if target is None:
            target = self._ensure_section(preferred_sections[0])
        for path in new_paths:
            target.items.append(
                Shortcut(
                    os.path.basename(path) or path,
                    path,
                    _icon_for(os.path.basename(path), path),
                )
            )
        return len(new_paths)

    def add_item(self, section_title, item):
        existing_section, existing = self.find_item(item.path)
        if existing is not None:
            return existing_section, existing
        section = self._ensure_section(section_title)
        section.items.append(item)
        return section, item

    def update_item(self, old_section, old_item, new_name, new_section_title):
        new_name = (new_name or "").strip()
        if not new_name:
            return
        old_section.items = [i for i in old_section.items if i is not old_item]
        target = self._ensure_section(new_section_title)
        old_item.name = new_name
        target.items.append(old_item)
        self._drop_empty_sections()

    def remove_item(self, item):
        for section in self.sections:
            section.items = [i for i in section.items if i is not item]
        self._drop_empty_sections()

    def move_item(self, section, item, delta):
        try:
            index = section.items.index(item)
        except ValueError:
            return False
        new_index = index + delta
        if new_index < 0 or new_index >= len(section.items):
            return False
        section.items[index], section.items[new_index] = (
            section.items[new_index],
            section.items[index],
        )
        return True

    def _drop_empty_sections(self):
        self.sections = [s for s in self.sections if s.items]


# ---------------------------------------------------------------------------
# Small UI helpers
# ---------------------------------------------------------------------------

_CSS = """
.home-dashboard-card {
    background-color: @theme_base_color;
    border: 1px solid alpha(@borders, 0.85);
    border-radius: 14px;
    padding: 16px;
    transition: 120ms ease;
}
.home-dashboard-card:hover {
    background-color: alpha(@theme_selected_bg_color, 0.10);
    border-color: alpha(@theme_selected_bg_color, 0.45);
}
.home-dashboard-card:focus {
    outline: 2px solid alpha(@theme_selected_bg_color, 0.65);
    outline-offset: 2px;
}
.home-dashboard-missing {
    opacity: 0.55;
}
.home-dashboard-path {
    font-size: 0.86em;
}
.home-dashboard-footer {
    font-size: 0.9em;
}
"""

_css_installed = False


def install_css():
    global _css_installed
    if _css_installed:
        return
    try:
        provider = Gtk.CssProvider()
        provider.load_from_string(_CSS)
        display = Gdk.Display.get_default()
        if display is None:
            return
        Gtk.StyleContext.add_provider_for_display(
            display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        _css_installed = True
    except Exception as exc:
        _log(f"could not install CSS: {exc}")


def _label(text, css=None, xalign=0.0, wrap=False, justify=Gtk.Justification.LEFT):
    label = Gtk.Label(label=text)
    label.set_xalign(xalign)
    if wrap:
        label.set_wrap(True)
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
    label.set_justify(justify)
    if css:
        for item in css.split():
            label.add_css_class(item)
    return label


def _image(icon_name, pixel_size=None, icon_size=None):
    image = Gtk.Image.new_from_icon_name(icon_name)
    if pixel_size is not None:
        image.set_pixel_size(pixel_size)
    elif icon_size is not None:
        image.set_icon_size(icon_size)
    return image


def _icon_button(icon_name, tooltip, css=("flat", "circular")):
    button = Gtk.Button()
    button.set_icon_name(icon_name)
    button.set_tooltip_text(tooltip)
    button.set_valign(Gtk.Align.CENTER)
    for item in css:
        button.add_css_class(item)
    return button


def _text_button(label, icon_name=None, css=None):
    button = Gtk.Button()
    button.set_has_frame(False)
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
    if icon_name:
        box.append(_image(icon_name, icon_size=Gtk.IconSize.NORMAL))
    if label:
        box.append(Gtk.Label(label=label))
    button.set_child(box)
    if css:
        for item in css:
            button.add_css_class(item)
    return button


def _alert(parent, message):
    try:
        Gtk.AlertDialog(message=message).show(parent)
    except Exception as exc:
        _log(f"could not show alert: {exc}")


def _window_for_slot(slot):
    try:
        root = slot.get_root()
        if isinstance(root, Gtk.Window):
            return root
    except Exception:
        pass
    return None


def _nautilus_window():
    try:
        app = Gtk.Application.get_default()
        if app is not None:
            win = app.get_active_window()
            if isinstance(win, Gtk.Window):
                return win
            windows = app.get_windows()
            if windows:
                return windows[0]
    except Exception:
        pass
    return None


def _all_widgets(widget):
    if widget is None:
        return
    yield widget
    child = widget.get_first_child()
    while child is not None:
        yield from _all_widgets(child)
        child = child.get_next_sibling()


def _find_tab_view(window):
    for widget in _all_widgets(window):
        if isinstance(widget, Adw.TabView):
            return widget
    return None


def _window_slots(window):
    tab_view = _find_tab_view(window)
    if tab_view is not None:
        for index in range(tab_view.get_n_pages()):
            page = tab_view.get_nth_page(index)
            slot = page.get_child() if page is not None else None
            if slot is not None:
                yield slot
        return
    for widget in _all_widgets(window):
        if "Slot" in type(widget).__name__:
            yield widget


def _find_slot_stack(slot):
    for widget in _all_widgets(slot):
        if isinstance(widget, Gtk.Stack):
            return widget
    return None


def _slot_location(slot):
    try:
        return slot.get_property("location")
    except (TypeError, AttributeError):
        return None


def _location_is_home(location):
    if location is None:
        return False
    try:
        return location.equal(HOME_FILE)
    except Exception:
        return False


def _slot_ready(slot):
    try:
        if slot.get_property("location") is None:
            return False
        return not slot.get_property("allow-stop")
    except (TypeError, AttributeError):
        return True


def _slot_is_active(slot):
    try:
        if slot.get_property("active"):
            return True
    except (TypeError, AttributeError):
        pass
    return False


def _active_slot(window):
    try:
        slot = window.get_property("active-slot")
        if slot is not None:
            return slot
    except (TypeError, AttributeError):
        pass
    slots = list(_window_slots(window))
    for slot in slots:
        if _slot_is_active(slot):
            return slot
    return slots[-1] if slots else None


def _make_menu_item(name, label, tip, icon, callback, *args):
    try:
        item = Nautilus.MenuItem(name=name, label=label, tip=tip, icon=icon)
    except TypeError:
        item = Nautilus.MenuItem(name=name, label=label)
    item.connect("activate", callback, *args)
    return item


# ---------------------------------------------------------------------------
# Dashboard panel
# ---------------------------------------------------------------------------


def build_dashboard_body(config, callbacks):
    """Build the scrollable dashboard contents.

    callbacks: open(path), show_all(), edit(), add()
    Returns (Adw.Clamp, refs-dict).
    """
    refs = {"first_card": None, "add_button": None}

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    outer.add_css_class("home-dashboard-page")
    outer.set_margin_top(36)
    outer.set_margin_bottom(32)
    outer.set_margin_start(28)
    outer.set_margin_end(28)

    title = _label(T["title"], "title-1")
    subtitle = _label(T["subtitle"], "dim-label", wrap=True)
    header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    header.append(title)
    header.append(subtitle)
    outer.append(header)

    actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
    actions.set_halign(Gtk.Align.START)
    actions.set_margin_top(2)
    show_all = _text_button(T["show_all"], "folder-open-symbolic")
    show_all.set_tooltip_text(T["menu_show_all_tip"])
    show_all.connect("clicked", lambda *_args: callbacks["show_all"]())
    edit = _text_button(T["edit"], "document-edit-symbolic")
    edit.connect("clicked", lambda *_args: callbacks["edit"]())
    add = _text_button(T["add_folder"], "list-add-symbolic")
    add.connect("clicked", lambda *_args: callbacks["add"]())
    actions.append(show_all)
    actions.append(edit)
    actions.append(add)
    outer.append(actions)

    separator = Gtk.Separator()
    separator.set_margin_top(2)
    outer.append(separator)

    sections_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=26)
    outer.append(sections_box)

    total_items = 0

    for section in config.sections:
        if not section.items:
            continue
        total_items += len(section.items)
        heading = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        heading.append(_label(section.title, "title-4"))
        count = _label(str(len(section.items)), "dim-label")
        count.set_hexpand(True)
        count.set_xalign(1.0)
        heading.append(count)
        sections_box.append(heading)

        flow = Gtk.FlowBox()
        flow.set_selection_mode(Gtk.SelectionMode.NONE)
        flow.set_homogeneous(True)
        flow.set_min_children_per_line(1)
        flow.set_max_children_per_line(4)
        flow.set_column_spacing(12)
        flow.set_row_spacing(12)
        flow.set_valign(Gtk.Align.START)
        flow.set_hexpand(True)

        for item in section.items:
            exists = os.path.isdir(item.path)
            button = Gtk.Button()
            button.set_has_frame(False)
            button.add_css_class("home-dashboard-card")
            button.set_size_request(190, 142)
            button.set_hexpand(True)
            button.set_tooltip_text(item.path)

            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            card.set_halign(Gtk.Align.CENTER)
            card.set_valign(Gtk.Align.CENTER)
            card.set_hexpand(True)

            card.append(_image(_safe_icon_name(item.icon), pixel_size=44))

            name = _label(item.name, "heading", xalign=0.5)
            name.set_ellipsize(Pango.EllipsizeMode.END)
            name.set_max_width_chars(20)
            name.set_justify(Gtk.Justification.CENTER)
            card.append(name)

            if exists:
                path_label = _label(_short_path(item.path), None, xalign=0.5)
                path_label.add_css_class("dim-label")
                path_label.add_css_class("home-dashboard-path")
                path_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
                path_label.set_max_width_chars(24)
            else:
                path_label = _label(T["missing"], None, xalign=0.5)
                path_label.add_css_class("dim-label")
                path_label.add_css_class("home-dashboard-path")
                button.add_css_class("home-dashboard-missing")
            card.append(path_label)

            button.set_child(card)

            def on_clicked(_button, path=item.path, name=item.name):
                callbacks["open"](path)

            button.connect("clicked", on_clicked)
            flow.append(button)
            if refs["first_card"] is None:
                refs["first_card"] = button

        sections_box.append(flow)

    if total_items == 0:
        empty = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        empty.set_halign(Gtk.Align.CENTER)
        empty.set_valign(Gtk.Align.CENTER)
        empty.set_margin_top(48)
        empty.set_margin_bottom(64)
        empty_icon = _image("folder-open-symbolic", pixel_size=64)
        empty_icon.set_opacity(0.55)
        empty.append(empty_icon)
        empty.append(_label(T["empty_title"], "title-2", xalign=0.5))
        empty.append(_label(T["empty_sub"], "dim-label", xalign=0.5, wrap=True))
        add_button = _text_button(T["add_folder"], "list-add-symbolic")
        add_button.add_css_class("suggested-action")
        add_button.set_halign(Gtk.Align.CENTER)
        add_button.connect("clicked", lambda *_args: callbacks["add"]())
        empty.append(add_button)
        sections_box.append(empty)
        refs["add_button"] = add_button

    footer = _label(
        T["footer"],
        "dim-label home-dashboard-footer",
        xalign=0.5,
        wrap=True,
        justify=Gtk.Justification.CENTER,
    )
    footer.set_margin_top(8)
    outer.append(footer)

    clamp = Adw.Clamp()
    clamp.set_maximum_size(1080)
    clamp.set_tightening_threshold(720)
    clamp.set_child(outer)
    return clamp, refs


def build_dashboard_panel(config, callbacks):
    panel = Gtk.ScrolledWindow()
    panel.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    panel.set_hexpand(True)
    panel.set_vexpand(True)
    panel.set_overlay_scrolling(True)
    body, refs = build_dashboard_body(config, callbacks)
    panel.set_child(body)
    return panel, refs


# ---------------------------------------------------------------------------
# Shortcut add/edit dialog
# ---------------------------------------------------------------------------


class ShortcutDialog(Adw.Window):
    __gtype_name__ = "HomeDashboardShortcutDialog"

    def __init__(self, parent, path, name, section, on_save):
        super().__init__(title=T["dialog_edit_title"])
        self._on_save = on_save
        self._path = path
        self.set_modal(True)
        self.set_transient_for(parent)
        self.set_default_size(460, -1)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(
            Adw.WindowTitle(title=T["dialog_edit_title"], subtitle="")
        )
        cancel = Gtk.Button(label=T["cancel"])
        cancel.connect("clicked", lambda *_args: self.close())
        save = Gtk.Button(label=T["save"])
        save.add_css_class("suggested-action")
        save.connect("clicked", lambda *_args: self._save())
        header.pack_start(cancel)
        header.pack_end(save)
        toolbar.add_top_bar(header)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        content.set_margin_top(18)
        content.set_margin_bottom(18)
        content.set_margin_start(18)
        content.set_margin_end(18)

        group = Adw.PreferencesGroup()
        self._name_row = Adw.EntryRow(title=T["dialog_name"])
        self._name_row.set_text(name or os.path.basename(path) or path)
        self._section_row = Adw.EntryRow(title=T["dialog_section"])
        self._section_row.set_text(section or T["section_shortcuts"])
        self._name_row.connect("activate", lambda *_args: self._save())
        self._section_row.connect("activate", lambda *_args: self._save())
        group.add(self._name_row)
        group.add(self._section_row)

        path_row = Adw.ActionRow(title=T["dialog_path"], subtitle=path)
        path_row.set_subtitle_selectable(True)
        group.add(path_row)
        content.append(group)

        toolbar.set_content(content)
        self.set_content(toolbar)

    def present(self):
        super().present()
        GLib.idle_add(self._focus_name)

    def _focus_name(self):
        self._name_row.grab_focus()
        return GLib.SOURCE_REMOVE

    def _save(self):
        name = self._name_row.get_text().strip()
        if not name:
            _alert(self, T["name_required"])
            return
        section = self._section_row.get_text().strip() or T["section_shortcuts"]
        self._on_save(name, section)
        self.close()


# ---------------------------------------------------------------------------
# Dashboard editor
# ---------------------------------------------------------------------------


class DashboardEditor(Adw.Window):
    __gtype_name__ = "HomeDashboardEditor"

    def __init__(self, extension, parent, slot=None):
        super().__init__(title=T["editor_title"])
        self._ext = extension
        self._slot = slot
        self._file_dialog = None
        self.set_transient_for(parent)
        self.set_modal(False)
        self.set_default_size(700, 760)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(
            Adw.WindowTitle(title=T["editor_title"], subtitle=T["editor_subtitle"])
        )
        done = Gtk.Button(label=T["done"])
        done.add_css_class("suggested-action")
        done.connect("clicked", lambda *_args: self.close())
        header.pack_end(done)
        toolbar.add_top_bar(header)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        self._content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self._content.set_margin_top(18)
        self._content.set_margin_bottom(24)
        self._content.set_margin_start(18)
        self._content.set_margin_end(18)

        clamp = Adw.Clamp()
        clamp.set_maximum_size(760)
        clamp.set_tightening_threshold(560)
        clamp.set_child(self._content)
        scrolled.set_child(clamp)

        toolbar.set_content(scrolled)
        self.set_content(toolbar)

        self._build()

    # -- build --------------------------------------------------------------

    def _clear(self):
        child = self._content.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            self._content.remove(child)
            child = next_child

    def _build(self):
        self._clear()
        config = self._ext.config

        general = Adw.PreferencesGroup(title=T["editor_general"])
        auto_row = Adw.SwitchRow(
            title=T["editor_auto_show"],
            subtitle=T["editor_auto_show_sub"],
        )
        auto_row.set_active(config.auto_show)
        auto_row.connect("notify::active", self._on_auto_show_changed)
        general.add(auto_row)
        self._content.append(general)

        has_items = False
        for section in list(config.sections):
            if not section.items:
                continue
            has_items = True
            group = Adw.PreferencesGroup(title=section.title)
            for index, item in enumerate(list(section.items)):
                row = Adw.ActionRow(title=item.name, subtitle=_short_path(item.path))
                row.set_activatable(True)
                row.set_tooltip_text(item.path)
                row.add_prefix(
                    _image(_safe_icon_name(item.icon), icon_size=Gtk.IconSize.NORMAL)
                )

                suffix = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=1)
                up = _icon_button("go-up-symbolic", T["move_up"])
                up.set_sensitive(index > 0)
                up.connect(
                    "clicked",
                    lambda *_args, s=section, i=item: self._move(i, s, -1),
                )
                down = _icon_button("go-down-symbolic", T["move_down"])
                down.set_sensitive(index < len(section.items) - 1)
                down.connect(
                    "clicked",
                    lambda *_args, s=section, i=item: self._move(i, s, 1),
                )
                edit = _icon_button("document-edit-symbolic", T["edit_item"])
                edit.connect(
                    "clicked",
                    lambda *_args, s=section, i=item: self._edit_item(s, i),
                )
                remove = _icon_button("user-trash-symbolic", T["remove_item"])
                remove.add_css_class("destructive-action")
                remove.connect(
                    "clicked",
                    lambda *_args, s=section, i=item: self._remove_item(s, i),
                )
                suffix.append(up)
                suffix.append(down)
                suffix.append(edit)
                suffix.append(remove)
                row.add_suffix(suffix)
                row.connect(
                    "activated",
                    lambda *_args, s=section, i=item: self._edit_item(s, i),
                )
                group.add(row)
            self._content.append(group)

        if not has_items:
            empty = Gtk.Label(label=T["editor_empty"])
            empty.set_wrap(True)
            empty.add_css_class("dim-label")
            empty.set_margin_top(12)
            empty.set_margin_bottom(12)
            self._content.append(empty)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        add = _text_button(T["add_folder"], "list-add-symbolic")
        add.add_css_class("suggested-action")
        add.connect("clicked", lambda *_args: self.add_folder())
        reset = _text_button(T["editor_reset"], "edit-clear-symbolic")
        reset.add_css_class("destructive-action")
        reset.connect("clicked", lambda *_args: self._confirm_reset())
        actions.append(add)
        actions.append(reset)
        self._content.append(actions)

        hint = _label(
            T["editor_config_hint"].format(path=_short_path(CONFIG_PATH)),
            "dim-label",
            wrap=True,
        )
        self._content.append(hint)

    def refresh(self):
        if self.get_visible():
            self._build()

    # -- config changes -----------------------------------------------------

    def _on_auto_show_changed(self, row, _pspec):
        self._ext.set_auto_show(row.get_active())

    def _move(self, item, section, delta):
        if self._ext.config.move_item(section, item, delta):
            self._ext.save_and_refresh()
            self._build()

    def _remove_item(self, section, item):
        self._ext.config.remove_item(item)
        self._ext.save_and_refresh()
        self._build()

    def _edit_item(self, section, item):
        ShortcutDialog(
            self,
            path=item.path,
            name=item.name,
            section=section.title,
            on_save=lambda name, new_section: self._save_edited_item(
                section, item, name, new_section
            ),
        ).present()

    def _save_edited_item(self, section, item, name, new_section):
        self._ext.config.update_item(section, item, name, new_section)
        self._ext.save_and_refresh()
        self._build()

    # -- add folder ---------------------------------------------------------

    def add_folder(self):
        try:
            dialog = Gtk.FileDialog(title=T["choose_folder"], modal=True)
            dialog.select_folder(self, None, self._on_folder_chosen)
            self._file_dialog = dialog
        except Exception as exc:
            _log(f"could not open folder chooser: {exc}")

    def _on_folder_chosen(self, dialog, result):
        self._file_dialog = None
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return
        if folder is None:
            return
        path = folder.get_path()
        if not path:
            return
        path = _normalise_path(path)
        if self._ext.config.find_item(path)[1] is not None:
            _alert(self, T["already_added"])
            return
        section_title = T["section_shortcuts"]
        if self._ext.config.sections:
            section_title = self._ext.config.sections[-1].title
        ShortcutDialog(
            self,
            path=path,
            name=os.path.basename(path) or path,
            section=section_title,
            on_save=lambda name, section: self._save_new_item(path, name, section),
        ).present()

    def _save_new_item(self, path, name, section):
        item = Shortcut(name, path, _icon_for(name, path))
        self._ext.config.add_item(section, item)
        self._ext.save_and_refresh()
        self._build()

    # -- reset --------------------------------------------------------------

    def _confirm_reset(self):
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading=T["editor_reset_title"],
            body=T["editor_reset_body"],
        )
        dialog.add_response("cancel", T["cancel"])
        dialog.add_response("reset", T["reset"])
        dialog.set_response_appearance(
            "reset", Adw.ResponseAppearance.DESTRUCTIVE
        )
        dialog.connect("response", self._on_reset_response)
        dialog.present()

    def _on_reset_response(self, _dialog, response):
        if response != "reset":
            return
        self._ext.reset_config()
        self._build()


# ---------------------------------------------------------------------------
# Nautilus extension
# ---------------------------------------------------------------------------


class HomeDashboardExtension(GObject.GObject, Nautilus.MenuProvider):
    __gtype_name__ = "HomeDashboardExtension"

    def __init__(self):
        super().__init__()
        self._config = DashboardConfig.load()
        self._windows = weakref.WeakSet()
        self._slots = weakref.WeakSet()
        self._editor = None
        self._shortcut_windows = weakref.WeakSet()

        install_css()
        GLib.timeout_add(350, self._scan_windows)

    # -- config -------------------------------------------------------------

    @property
    def config(self):
        return self._config

    def set_auto_show(self, enabled):
        self._config.auto_show = bool(enabled)
        self.save_and_refresh()

    def reset_config(self):
        self._config = DashboardConfig.default(save=False)
        self.save_and_refresh()

    def save_and_refresh(self):
        self._config.save()
        self._refresh_all()

    # -- window / slot discovery -------------------------------------------

    def _scan_windows(self):
        try:
            for window in Gtk.Window.list_toplevels():
                if self._is_nautilus_window(window):
                    self._init_window(window)
        except Exception as exc:
            _log(f"window scan failed: {exc}")
        return GLib.SOURCE_CONTINUE

    @staticmethod
    def _is_nautilus_window(window):
        if not isinstance(window, Gtk.Window):
            return False
        name = type(window).__name__
        if "FileChooser" in name:
            return False
        if name == "NautilusWindow":
            return True
        try:
            if window.get_buildable_id() == "NautilusWindow":
                return True
        except Exception:
            pass
        try:
            if window.has_css_class("nautilus-window"):
                return True
        except Exception:
            pass
        # Structural fallback for renamed/repackaged Nautilus builds.
        try:
            widgets = list(_all_widgets(window))
            has_tab_view = any(isinstance(w, Adw.TabView) for w in widgets)
            has_slot = any("Slot" in type(w).__name__ for w in widgets)
            return has_tab_view and has_slot
        except Exception:
            return False

    def _init_window(self, window):
        if window in self._windows:
            return
        tab_view = _find_tab_view(window)
        if tab_view is None:
            return
        self._windows.add(window)
        try:
            window.connect("destroy", self._on_window_destroyed)
            tab_view.connect("page-attached", self._on_page_attached, window)
        except Exception as exc:
            _log(f"could not watch window: {exc}")
        self._install_shortcut(window)
        for slot in _window_slots(window):
            self._watch_slot(window, slot)

    def _on_window_destroyed(self, window):
        self._windows.discard(window)

    def _on_page_attached(self, _tab_view, page, _position, window):
        slot = page.get_child() if page is not None else None
        self._watch_slot(window, slot)

    def _install_shortcut(self, window):
        if window in self._shortcut_windows:
            return
        try:
            trigger = Gtk.ShortcutTrigger.parse_string(SHORTCUT_ACCEL)
            if trigger is None:
                _log(f"could not parse shortcut {SHORTCUT_ACCEL}")
                return
            action = Gtk.CallbackAction.new(
                lambda *_args, w=window: self._on_shortcut(w)
            )
            controller = Gtk.ShortcutController()
            controller.set_scope(Gtk.ShortcutScope.MANAGED)
            controller.add_shortcut(Gtk.Shortcut.new(trigger, action))
            window.add_controller(controller)
            self._shortcut_windows.add(window)
        except Exception as exc:
            _log(f"could not install shortcut: {exc}")

    def _on_shortcut(self, window):
        slot = _active_slot(window)
        if slot is None:
            return True
        state = getattr(slot, "_hd_state", None)
        if (
            state is not None
            and state.get("wants_visible")
            and _location_is_home(_slot_location(slot))
        ):
            self._show_native(slot)
        else:
            self._open_dashboard_for_slot(slot)
        return True

    def _watch_slot(self, window, slot):
        if slot is None:
            return
        if getattr(slot, "_hd_state", None) is not None:
            return
        if getattr(slot, "_hd_pending", False):
            return
        slot._hd_pending = True
        attempts = [0]

        def try_inject():
            if getattr(slot, "_hd_state", None) is not None:
                return GLib.SOURCE_REMOVE
            try:
                if slot.get_parent() is None:
                    return GLib.SOURCE_REMOVE
            except Exception:
                return GLib.SOURCE_REMOVE
            attempts[0] += 1
            if not _slot_ready(slot) and attempts[0] < 200:
                return GLib.SOURCE_CONTINUE
            GLib.idle_add(
                self._inject_slot, window, slot, priority=GLib.PRIORITY_LOW
            )
            return GLib.SOURCE_REMOVE

        GLib.timeout_add(50, try_inject)

    def _inject_slot(self, window, slot):
        slot._hd_pending = False
        if getattr(slot, "_hd_state", None) is not None:
            return GLib.SOURCE_REMOVE
        stack = _find_slot_stack(slot)
        if stack is None:
            _log("no GtkStack found in slot; dashboard not injected")
            return GLib.SOURCE_REMOVE

        def open_path(path):
            self._open_path(slot, path)

        callbacks = {
            "open": open_path,
            "show_all": lambda: self._show_native(slot),
            "edit": lambda: self._open_editor(slot),
            "add": lambda: self._open_editor(slot, start_add=True),
        }
        panel, refs = build_dashboard_panel(self._config, callbacks)
        child_name = f"{STACK_CHILD_PREFIX}{id(slot)}"
        state = {
            "window": window,
            "slot": slot,
            "stack": stack,
            "panel": panel,
            "refs": refs,
            "callbacks": callbacks,
            "child_name": child_name,
            "wants_visible": False,
            "force_native": False,
            "manual_show": bool(getattr(slot, "_hd_manual_show", False)),
            "previous_child": None,
            "switching": False,
        }
        slot._hd_state = state
        self._slots.add(slot)
        _log(f"injected dashboard into {type(slot).__name__} ({type(stack).__name__})")

        try:
            stack.add_named(panel, child_name)
            stack.connect("notify::visible-child", self._on_stack_visible_child, slot)
            slot.connect("notify::location", self._on_slot_location)
        except Exception as exc:
            _log(f"could not inject dashboard: {exc}")
            slot._hd_state = None
            self._slots.discard(slot)
            return GLib.SOURCE_REMOVE

        self._on_slot_location(slot)
        return GLib.SOURCE_REMOVE

    # -- showing / hiding ---------------------------------------------------

    def _on_stack_visible_child(self, stack, _pspec, slot):
        state = getattr(slot, "_hd_state", None)
        if state is None or state["switching"] or not state["wants_visible"]:
            return
        if state["force_native"]:
            return
        if not _location_is_home(_slot_location(slot)):
            return
        if not (self._config.auto_show or state["manual_show"]):
            return
        if stack.get_visible_child() is not state["panel"]:
            state["switching"] = True
            stack.set_visible_child(state["panel"])
            state["switching"] = False

    def _on_slot_location(self, slot, _pspec=None):
        state = getattr(slot, "_hd_state", None)
        if state is None:
            return
        is_home = _location_is_home(_slot_location(slot))
        if not is_home:
            state["force_native"] = False
            state["manual_show"] = False
            self._leave(state)
            return
        if state["force_native"]:
            self._leave(state)
            return
        if self._config.auto_show or state["manual_show"]:
            self._enter(state)
        else:
            self._leave(state)

    def _enter(self, state):
        stack = state["stack"]
        panel = state["panel"]
        if panel.get_parent() is not stack:
            return
        current = stack.get_visible_child()
        if current is not panel:
            state["previous_child"] = current
        state["wants_visible"] = True
        if current is panel:
            return
        state["switching"] = True
        try:
            stack.set_visible_child(panel)
            _log("showing Home dashboard")
        finally:
            state["switching"] = False
        GLib.idle_add(self._focus_panel, state)

    def _leave(self, state):
        state["wants_visible"] = False
        stack = state["stack"]
        panel = state["panel"]
        if stack.get_visible_child() is not panel:
            return
        previous = state.get("previous_child")
        if (
            previous is None
            or previous is panel
            or previous.get_parent() is not stack
        ):
            previous = None
            child = stack.get_first_child()
            while child is not None:
                if child is not panel:
                    previous = child
                    break
                child = child.get_next_sibling()
        state["switching"] = True
        try:
            if previous is not None:
                stack.set_visible_child(previous)
                _log("showing native view")
        finally:
            state["switching"] = False

    @staticmethod
    def _focus_panel(state):
        refs = state.get("refs") or {}
        target = refs.get("first_card") or refs.get("add_button")
        if target is not None:
            try:
                target.grab_focus()
            except Exception:
                pass
        return GLib.SOURCE_REMOVE

    def _show_native(self, slot):
        state = getattr(slot, "_hd_state", None)
        if state is None:
            return
        state["force_native"] = True
        state["manual_show"] = False
        self._leave(state)

    def _open_dashboard_for_slot(self, slot):
        state = getattr(slot, "_hd_state", None)
        if state is None:
            slot._hd_manual_show = True
        if not _location_is_home(_slot_location(slot)):
            if not self._navigate(slot, HOME_DIR):
                return
            # _on_slot_location() will enter because manual_show is set below
            if state is not None:
                state["manual_show"] = True
                state["force_native"] = False
            return
        if state is None:
            return
        state["manual_show"] = True
        state["force_native"] = False
        self._enter(state)

    def _refresh_all(self):
        for slot in list(self._slots):
            state = getattr(slot, "_hd_state", None)
            if state is None or state["panel"].get_parent() is None:
                continue
            body, refs = build_dashboard_body(self._config, state["callbacks"])
            state["panel"].set_child(body)
            state["refs"] = refs
            is_home = _location_is_home(_slot_location(slot))
            if (
                is_home
                and not state["force_native"]
                and (self._config.auto_show or state["manual_show"])
            ):
                self._enter(state)
            else:
                self._leave(state)

    # -- navigation ---------------------------------------------------------

    def _navigate(self, slot, path):
        if not os.path.isdir(path):
            _alert(_window_for_slot(slot), T["folder_missing"].format(path=path))
            return False
        uri = Gio.File.new_for_path(path).get_uri()
        variant = GLib.Variant("s", uri)
        for action in ("slot.open-location", "win.open-location"):
            try:
                if slot.activate_action(action, variant):
                    return True
            except Exception:
                pass
        window = _window_for_slot(slot)
        if window is not None:
            try:
                if window.activate_action("win.open-location", variant):
                    return True
            except Exception:
                pass
        try:
            Gio.AppInfo.launch_default_for_uri(uri, None)
            return True
        except Exception as exc:
            _log(f"navigation failed for {path}: {exc}")
        return False

    def _open_path(self, slot, path):
        if not os.path.isdir(path):
            _alert(_window_for_slot(slot), T["missing_body"].format(path=path))
            return
        self._navigate(slot, path)

    # -- slot lookup --------------------------------------------------------

    def _find_slot_for_folder(self, folder):
        target = None
        try:
            target = folder.get_location() if folder is not None else None
        except Exception:
            target = None

        candidates = []
        try:
            for window in Gtk.Window.list_toplevels():
                if not self._is_nautilus_window(window):
                    continue
                active_window = window.is_active()
                for slot in _window_slots(window):
                    location = _slot_location(slot)
                    if target is not None and location is not None:
                        try:
                            matches = location.equal(target)
                        except Exception:
                            matches = False
                        if not matches:
                            continue
                    score = 1
                    if active_window:
                        score += 2
                    if _slot_is_active(slot):
                        score += 1
                    candidates.append((score, slot))
        except Exception as exc:
            _log(f"slot lookup failed: {exc}")

        if candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)
            return candidates[0][1]

        for window in Gtk.Window.list_toplevels():
            if self._is_nautilus_window(window) and window.is_active():
                slot = _active_slot(window)
                if slot is not None:
                    return slot
        return None

    # -- editor -------------------------------------------------------------

    def _open_editor(self, slot=None, start_add=False):
        window = _window_for_slot(slot) if slot is not None else _nautilus_window()
        if self._editor is not None:
            self._editor.present()
        else:
            editor = DashboardEditor(self, window, slot)
            editor.connect("destroy", self._on_editor_destroyed)
            self._editor = editor
            editor.present()
        if start_add:
            GLib.idle_add(self._editor_add_folder)

    def _editor_add_folder(self):
        if self._editor is not None:
            self._editor.add_folder()
        return GLib.SOURCE_REMOVE

    def _on_editor_destroyed(self, _editor):
        self._editor = None

    # -- Nautilus menu provider --------------------------------------------

    def get_file_items(self, files):
        directories = []
        for file_info in files:
            try:
                if file_info.get_uri_scheme() != "file":
                    continue
                if not file_info.is_directory():
                    continue
                path = file_info.get_location().get_path()
                if path:
                    directories.append(path)
            except Exception:
                continue
        if not directories:
            return []

        missing = []
        existing = []
        for path in directories:
            if self._config.find_item(path)[1] is None:
                missing.append(path)
            else:
                existing.append(path)

        items = []
        if missing:
            items.append(
                _make_menu_item(
                    "HomeDashboard::Add",
                    T["menu_add"],
                    T["menu_add_tip"],
                    "list-add-symbolic",
                    self._on_add_selected,
                    missing,
                )
            )
        if existing:
            items.append(
                _make_menu_item(
                    "HomeDashboard::Remove",
                    T["menu_remove"],
                    T["menu_remove_tip"],
                    "user-trash-symbolic",
                    self._on_remove_selected,
                    existing,
                )
            )
        return items

    def get_background_items(self, folder):
        items = []
        is_home = False
        try:
            if folder is not None:
                is_home = _location_is_home(folder.get_location())
        except Exception:
            pass

        items.append(
            _make_menu_item(
                "HomeDashboard::Open",
                T["menu_open"],
                T["menu_open_tip"],
                "user-home-symbolic",
                self._on_open_dashboard_bg,
                folder,
            )
        )
        if is_home:
            items.append(
                _make_menu_item(
                    "HomeDashboard::ShowAll",
                    T["menu_show_all"],
                    T["menu_show_all_tip"],
                    "folder-open-symbolic",
                    self._on_show_all_bg,
                    folder,
                )
            )
        items.append(
            _make_menu_item(
                "HomeDashboard::Customize",
                T["menu_customize"],
                T["menu_customize_tip"],
                "document-edit-symbolic",
                self._on_customize_bg,
                folder,
            )
        )
        return items

    # -- menu callbacks -----------------------------------------------------

    def _on_add_selected(self, _item, paths):
        self._config.add_paths(
            paths, preferred_sections=[T["section_shortcuts"], "Shortcuts"]
        )
        self.save_and_refresh()

    def _on_remove_selected(self, _item, paths):
        for path in paths:
            _section, item = self._config.find_item(path)
            if item is not None:
                self._config.remove_item(item)
        self.save_and_refresh()

    def _on_open_dashboard_bg(self, _item, folder):
        slot = self._find_slot_for_folder(folder)
        if slot is None:
            _alert(_nautilus_window(), T["folder_missing"].format(path=HOME_DIR))
            return
        self._open_dashboard_for_slot(slot)

    def _on_show_all_bg(self, _item, folder):
        slot = self._find_slot_for_folder(folder)
        if slot is not None:
            self._show_native(slot)

    def _on_customize_bg(self, _item, folder):
        slot = self._find_slot_for_folder(folder)
        self._open_editor(slot)


# ---------------------------------------------------------------------------
# Standalone preview (python3 home-dashboard.py)
# ---------------------------------------------------------------------------


def _preview():
    install_css()
    app = Adw.Application(application_id="io.github.tofpon.HomeDashboardPreview")

    def on_activate(application):
        window = Adw.ApplicationWindow(
            application=application,
            title=T["editor_title"],
        )
        window.set_default_size(1000, 720)

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(
            Adw.WindowTitle(title=T["title"], subtitle=T["subtitle"])
        )
        toolbar.add_top_bar(header)

        callbacks = {
            "open": lambda path: Gio.AppInfo.launch_default_for_uri(
                Gio.File.new_for_path(path).get_uri(), None
            ),
            "show_all": lambda: None,
            "edit": lambda: None,
            "add": lambda: None,
        }
        panel, _refs = build_dashboard_panel(
            DashboardConfig.default(save=False), callbacks
        )
        toolbar.set_content(panel)
        window.set_content(toolbar)
        window.present()

    app.connect("activate", on_activate)
    app.run(None)


if __name__ == "__main__":
    _preview()
