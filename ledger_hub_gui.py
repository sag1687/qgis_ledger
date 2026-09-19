# -*- coding: utf-8 -*-
# Copyright (C) 2026 Dott. Sarino Alfonso Grande <sino.grande@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
ledger_hub_gui.py — Centro Comandi (Command Center).

IT: Una finestra unica che raffigura *tutti* i comandi del plugin come
grandi pulsanti raggruppati per categoria. L'utente ci clicca sopra ed
esegue direttamente il comando (aprire progetto, salvare snapshot,
timeline, diff, storico, cloud Nextcloud, auto-save e le impostazioni
già presenti per cambiare cartella / database / archiviazione cloud).

EN: A single window that depicts *every* plugin command as a large
grouped button. Clicking runs the command directly (open project, save
snapshots, timeline, diff, history, Nextcloud cloud, auto-save and the
existing settings to change folder / database / cloud storage).

Compatible with QGIS 3 (Qt5) and QGIS 4 (Qt6): every Qt/QGIS enum is
resolved in fully-scoped form with a Qt5 fallback.
"""

import os

from qgis.PyQt.QtCore import Qt, QSize
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QDialog,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QComboBox,
    QToolButton,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QCheckBox,
)

from .ledger_i18n import tr, set_language, current_language
from .ledger_settings import LedgerSettings
from . import plugin_hub

# (endonym label, language code, flag file) — mirrors the Settings dialog.
LANGUAGES = [
    ("Italiano", "it", "ITALIA.png"),
    ("English", "en", "REGNOUNITO.png"),
    ("Français", "fr", "France.png"),
    ("Deutsch", "de", "DE.png"),
    ("Português (Brasil)", "pt-BR", "Flag_of_Brazil.svg.png"),
    ("中文 (Singapore)", "zh-SG", "Singapore.png"),
    ("हिन्दी (India)", "hi-IN", "india.png"),
]


def _enum(base, scope, name):
    """Resolve a Qt/QGIS enum both scoped (Qt6) and unscoped (Qt5)."""
    return getattr(getattr(base, scope, base), name)


# Extra styling stacked on top of the shared SARIAG family theme so the
# big command tiles look at home in the plugin family.
HUB_STYLE = """
QToolButton#cmdTile {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 #1f2a38, stop:1 #16202b);
    border: 1px solid #2c3a48;
    border-radius: 10px;
    padding: 12px 8px;
    color: #f2f5f8;
    font-size: 12px;
    font-weight: 700;
}
QToolButton#cmdTile:hover {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 #294056, stop:1 #1d2c3b);
    border: 1px solid #5b9bd5;
}
QToolButton#cmdTile:pressed {
    background: #17222e;
}
QToolButton#cmdTile:checked {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 #2c4f70, stop:1 #1f3a54);
    border: 1px solid #5b9bd5;
    color: #ffffff;
}
QLabel#hubTitle {
    color: #f2f5f8;
    font-size: 18px;
    font-weight: 800;
    background: transparent;
}
QLabel#hubSubtitle {
    color: #8a97a5;
    font-size: 12px;
    background: transparent;
}
"""


class LedgerCommandCenter(QDialog):
    """Griglia di pulsanti che espone ogni comando del plugin.

    Riceve l'istanza del plugin (``LedgerPlugin``) e collega ciascun
    pulsante ai metodi handler già esistenti, senza duplicarne la logica.
    """

    def __init__(self, plugin, parent=None):
        super().__init__(parent)
        self.plugin = plugin
        self._tiles = []  # (button, emoji, color, title_fn, tooltip_fn)
        self._autosave_tile = None  # direct ref to the checkable Auto-Save tile
        self.setObjectName("LedgerCommandCenter")
        self.setWindowTitle(tr("QGIS Ledger — Centro Comandi"))
        self.setMinimumWidth(560)
        self.setStyleSheet(plugin_hub.FAMILY_STYLE + HUB_STYLE)
        self._build_ui()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 12)
        root.setSpacing(12)

        # -- Header ---------------------------------------------------- #
        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.lbl_title = QLabel("\U0001F6E1️ " + tr("Centro Comandi"))
        self.lbl_title.setObjectName("hubTitle")
        self.lbl_subtitle = QLabel(
            tr("Tutti i comandi di QGIS Ledger in un solo posto"))
        self.lbl_subtitle.setObjectName("hubSubtitle")
        title_box.addWidget(self.lbl_title)
        title_box.addWidget(self.lbl_subtitle)
        header.addLayout(title_box)
        header.addStretch(1)

        # Language selector (same set as the Settings dialog).
        lang_box = QVBoxLayout()
        lang_box.setSpacing(2)
        self.lbl_lang = QLabel(tr("Lingua / Language:"))
        self.cmb_lang = QComboBox()
        base_dir = os.path.dirname(__file__)
        for label, code, flag in LANGUAGES:
            self.cmb_lang.addItem(
                QIcon(os.path.join(base_dir, flag)), label, code)
        idx = self.cmb_lang.findData(current_language())
        if idx >= 0:
            self.cmb_lang.setCurrentIndex(idx)
        self.cmb_lang.currentIndexChanged.connect(self._on_lang_changed)
        lang_box.addWidget(self.lbl_lang)
        lang_box.addWidget(self.cmb_lang)
        header.addLayout(lang_box)
        root.addLayout(header)

        # -- Scrollable body ------------------------------------------- #
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(_enum(QScrollArea, "Shape", "NoFrame"))
        body = QWidget()
        self._body_layout = QVBoxLayout(body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(12)

        self._build_sections()

        self._body_layout.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        # -- Footer ---------------------------------------------------- #
        footer = QHBoxLayout()
        self.chk_full_toolbar = QCheckBox(
            tr("Mostra tutti i pulsanti nella toolbar"))
        self.chk_full_toolbar.setToolTip(
            tr("Se disattivato, la toolbar mostra solo l'icona del "
               "Centro Comandi"))
        self.chk_full_toolbar.setChecked(not LedgerSettings.compact_toolbar())
        self.chk_full_toolbar.toggled.connect(self._on_full_toolbar_toggled)
        footer.addWidget(self.chk_full_toolbar)
        footer.addStretch(1)
        self.btn_close = QPushButton(tr("Chiudi"))
        self.btn_close.clicked.connect(self.close)
        footer.addWidget(self.btn_close)
        root.addLayout(footer)

    def _on_full_toolbar_toggled(self, checked):
        """Enable/disable the full toolbar (checked = show every button)."""
        self.plugin._set_toolbar_compact(not checked)

    def _on_lang_changed(self, _index):
        """Switch language live and retranslate the whole plugin UI."""
        code = self.cmb_lang.currentData()
        if not code or code == current_language():
            return
        set_language(code)
        # retranslateUi also calls this dialog's retranslate().
        if hasattr(self.plugin, "retranslateUi"):
            self.plugin.retranslateUi()
        else:
            self.retranslate()

    def _build_sections(self):
        """Definisce tutte le sezioni e i relativi comandi."""
        p = self.plugin

        sections = [
            (tr("Progetto"), [
                ("\U0001F4C2", "#3f6f9e",
                 lambda: tr("Apri Progetto"),
                 lambda: tr("Apri un progetto QGIS esistente"),
                 p._on_open_project, False),
                ("✔", "#16a085",
                 lambda: tr("Salva solo questo Layer"),
                 lambda: tr("Salva uno snapshot del layer attivo"),
                 p._on_commit, False),
                ("\U0001F4BE", "#8e44ad",
                 lambda: tr("Salva intero Progetto"),
                 lambda: tr("Salva uno snapshot dell'intero progetto"),
                 p._on_commit_project, False),
            ]),
            (tr("Versioni & Storico"), [
                ("\U0001F558☁", "#141a22",
                 lambda: tr("Pannello Ledger"),
                 lambda: tr("Mostra il pannello Timeline & Nextcloud"),
                 self._show_timeline, False),
                ("Δ", "#e67e22",
                 lambda: tr("Diff"),
                 lambda: tr("Confronto visuale tra due versioni"),
                 p._on_diff_dialog, False),
                ("\U0001F5C2", "#22303e",
                 lambda: tr("Esplora Storico"),
                 lambda: tr(
                     "Sfoglia ed Estrai vecchie versioni dal database"),
                 p._on_browser_dialog, False),
            ]),
            (tr("Archiviazione Cloud"), [
                ("☁️", "#5b9bd5",
                 lambda: tr("Cloud Nextcloud"),
                 lambda: tr("Apri il pannello del cloud Nextcloud"),
                 self._show_nextcloud, False),
                ("\U0001F4E4", "#5b9bd5",
                 lambda: tr("Invia Layer a Nextcloud"),
                 lambda: tr("Carica il layer attivo su Nextcloud"),
                 p._on_upload_layer_to_nc, False),
            ]),
            (tr("Automazione"), [
                ("⏱", "#f39c12",
                 lambda: tr("Auto-Save"),
                 lambda: tr(
                     "Attiva/Disattiva il salvataggio automatico periodico"),
                 self._toggle_autosave, True),
            ]),
            (tr("Impostazioni & Archiviazione"), [
                ("⚙", "#8a97a5",
                 lambda: tr("Impostazioni"),
                 lambda: tr("Cambia cartella, database, cloud e lingua"),
                 p._on_settings, False),
            ]),
        ]

        for title, commands in sections:
            self._body_layout.addWidget(self._make_group(title, commands))

    def _make_group(self, title, commands):
        grp = QGroupBox(title)
        grid = QGridLayout(grp)
        grid.setSpacing(10)
        grid.setContentsMargins(12, 16, 12, 12)
        columns = 3
        for idx, (emoji, color, title_fn, tip_fn, cb, checkable) \
                in enumerate(commands):
            btn = self._make_tile(emoji, color, title_fn, tip_fn, cb,
                                  checkable)
            grid.addWidget(btn, idx // columns, idx % columns)
        # keep columns evenly stretched
        for c in range(columns):
            grid.setColumnStretch(c, 1)
        return grp

    def _make_tile(self, emoji, color, title_fn, tip_fn, callback,
                   checkable):
        btn = QToolButton()
        btn.setObjectName("cmdTile")
        btn.setToolButtonStyle(
            _enum(Qt, "ToolButtonStyle", "ToolButtonTextUnderIcon"))
        btn.setIcon(self.plugin._make_icon(emoji, color, size=40))
        btn.setIconSize(QSize(36, 36))
        btn.setText(title_fn())
        btn.setToolTip(tip_fn())
        btn.setCheckable(checkable)
        btn.setMinimumHeight(84)
        btn.setSizePolicy(
            _enum(QSizePolicy, "Policy", "Expanding"),
            _enum(QSizePolicy, "Policy", "Fixed"))
        cursor = _enum(Qt, "CursorShape", "PointingHandCursor")
        btn.setCursor(cursor)

        if checkable:
            # Reflect current state and forward the toggle.
            btn.setChecked(self._autosave_is_on())
            btn.toggled.connect(callback)
            self._autosave_tile = btn
        else:
            btn.clicked.connect(lambda _=False, f=callback: f())

        self._tiles.append((btn, emoji, color, title_fn, tip_fn))
        return btn

    # ------------------------------------------------------------------ #
    # Command wrappers (keep plugin logic untouched)
    # ------------------------------------------------------------------ #
    def _show_timeline(self):
        self._reveal_panel(0)

    def _show_nextcloud(self):
        self._reveal_panel(1)

    def _reveal_panel(self, tab_index):
        p = self.plugin
        panel = getattr(p, "main_panel", None)
        if panel is None:
            return
        panel.show()
        panel.raise_()
        tabs = getattr(p, "tab_widget", None)
        if tabs is not None:
            tabs.setCurrentIndex(tab_index)
        action = getattr(p, "_panel_action", None)
        if action is not None:
            action.setChecked(True)

    def _sync_state(self):
        """Refresh dynamic states (Auto-Save + toolbar mode) from the plugin."""
        if self._autosave_tile is not None:
            self._autosave_tile.blockSignals(True)
            self._autosave_tile.setChecked(self._autosave_is_on())
            self._autosave_tile.blockSignals(False)
        if getattr(self, "chk_full_toolbar", None) is not None:
            self.chk_full_toolbar.blockSignals(True)
            self.chk_full_toolbar.setChecked(
                not LedgerSettings.compact_toolbar())
            self.chk_full_toolbar.blockSignals(False)

    def showEvent(self, event):
        self._sync_state()
        super().showEvent(event)

    def _autosave_is_on(self):
        action = getattr(self.plugin, "_autosave_action", None)
        return bool(action.isChecked()) if action is not None else False

    def _toggle_autosave(self, checked):
        p = self.plugin
        # Keep the toolbar toggle in sync, then run the plugin logic.
        action = getattr(p, "_autosave_action", None)
        if action is not None and action.isChecked() != checked:
            action.setChecked(checked)
        p._toggle_autosave(checked)

    # ------------------------------------------------------------------ #
    # i18n
    # ------------------------------------------------------------------ #
    def retranslate(self):
        """Aggiorna testi al cambio lingua senza ricostruire la finestra."""
        self.setWindowTitle(tr("QGIS Ledger — Centro Comandi"))
        self.lbl_title.setText("\U0001F6E1️ " + tr("Centro Comandi"))
        self.lbl_subtitle.setText(
            tr("Tutti i comandi di QGIS Ledger in un solo posto"))
        self.lbl_lang.setText(tr("Lingua / Language:"))
        # Keep the language combo in sync without re-firing the change.
        idx = self.cmb_lang.findData(current_language())
        if idx >= 0 and idx != self.cmb_lang.currentIndex():
            self.cmb_lang.blockSignals(True)
            self.cmb_lang.setCurrentIndex(idx)
            self.cmb_lang.blockSignals(False)
        self.btn_close.setText(tr("Chiudi"))
        self.chk_full_toolbar.setText(
            tr("Mostra tutti i pulsanti nella toolbar"))
        self.chk_full_toolbar.setToolTip(
            tr("Se disattivato, la toolbar mostra solo l'icona del "
               "Centro Comandi"))
        for btn, emoji, color, title_fn, tip_fn in self._tiles:
            btn.setText(title_fn())
            btn.setToolTip(tip_fn())
