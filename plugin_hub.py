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
plugin_hub.py — Shared "plugin family" hub, embedded in every plugin.

IT: Questo modulo è identico in tutti i plugin della famiglia SinoCloud.
Fornisce l'elenco degli altri plugin dell'autore, il widget con menù a
tendina mostrato nella scheda Info (il plugin che ospita il widget viene
escluso dall'elenco) e il foglio di stile scuro condiviso, derivato dal
tema di SARIAG. Compatibile con QGIS 3 (Qt5) e QGIS 4 (Qt6).

EN: This module is identical across every plugin of the SinoCloud
family. It provides the list of the author's other plugins, the
drop-down widget shown in the Info tab (the hosting plugin is excluded
from the list) and the shared dark stylesheet derived from the SARIAG
theme. Compatible with QGIS 3 (Qt5) and QGIS 4 (Qt6).
"""

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

AUTHOR_NAME = "Dott. Sarino Alfonso Grande"
AUTHOR_EMAIL = "sino.grande@gmail.com"
AUTHOR_WEBSITE = "https://sinocloud.it"
AUTHOR_GITHUB = "https://github.com/sag1687"

# One entry per published plugin of the family. "key" identifies the
# hosting plugin so it can exclude itself from the drop-down list.
PLUGIN_FAMILY = (
    {
        "key": "sariag",
        "name": "SARIAG",
        "repo": "https://github.com/sag1687/sariag",
        "it": "Serie temporali InSAR Sentinel-1: mappe di spostamento "
              "Est-Ovest e Verticale tramite SNAP e SNAPHU.",
        "en": "Sentinel-1 InSAR time series: East-West and Vertical "
              "displacement maps through SNAP and SNAPHU.",
    },
    {
        "key": "stac_browser",
        "name": "STAC Browser",
        "repo": "https://github.com/sag1687/stac_browser",
        "it": "Trova e scarica dati di osservazione della Terra dai "
              "cataloghi STAC disegnando un'area sulla mappa.",
        "en": "Finds and downloads Earth-observation data from STAC "
              "catalogs by drawing an area on the map.",
    },
    {
        "key": "geobridge",
        "name": "GeoBridge",
        "repo": "https://github.com/sag1687/geobridge",
        "it": "Client QGIS non ufficiale per i servizi IGM: conversione "
              "di coordinate e di layer vettoriali.",
        "en": "Unofficial QGIS client for the IGM services: coordinate "
              "and vector layer conversion.",
    },
    {
        "key": "quick_crs_fixer",
        "name": "Quick CRS Fixer",
        "repo": "https://github.com/sag1687/CRS_FIXER",
        "it": "Rileva e corregge automaticamente i problemi di CRS dei "
              "layer, con suggerimenti EPSG intelligenti.",
        "en": "Automatically detects and fixes layer CRS issues, with "
              "smart EPSG suggestions.",
    },
    {
        "key": "geocsv_mapper",
        "name": "GeoCSV Mapper",
        "repo": "https://github.com/sag1687/GeoCSV-Mapper",
        "it": "Importa CSV con coordinate (anche DMS), anteprima su "
              "OpenStreetMap e salvataggio in GeoPackage.",
        "en": "Imports coordinate CSV files (DMS too), OpenStreetMap "
              "preview and GeoPackage export.",
    },
    {
        "key": "q_press",
        "name": "Q-Press",
        "repo": "https://github.com/sag1687/q_press",
        "it": "Genera PDF cartografici professionali selezionando "
              "l'area con Shift+Trascina sul canvas.",
        "en": "Generates professional cartographic PDFs by selecting "
              "the area with Shift+Drag on the canvas.",
    },
    {
        "key": "qgis_ledger",
        "name": "QGIS Ledger",
        "repo": "https://github.com/sag1687/qgis_ledger",
        "it": "Versionamento in stile Git per QGIS: snapshot, diff "
              "geometrico, rollback e sincronizzazione cloud.",
        "en": "Git-like version control for QGIS: snapshots, geometric "
              "diff, rollback and cloud synchronization.",
    },
    {
        "key": "taf_italia",
        "name": "TAF Italia",
        "repo": "https://github.com/sag1687/TAF_ITALIA_DOWNLOAD",
        "it": "Scarica e converte i Punti Fiduciali catastali (TAF) "
              "dell'Agenzia delle Entrate in CSV/WGS84.",
        "en": "Downloads and converts the cadastral Fiducial Points "
              "(TAF) of the Italian Revenue Agency to CSV/WGS84.",
    },
)

# Shared dark theme (muted slate-blue), identical to the SARIAG dialog
# stylesheet so the whole plugin family looks and feels the same.
FAMILY_STYLE = """
QDialog {
    background-color: #141a22;
    color: #f2f5f8;
    font-family: 'Segoe UI', 'Inter', 'Roboto', Tahoma, Geneva,
                 Verdana, sans-serif;
    font-size: 13px;
}
QWidget { background-color: #141a22; color: #f2f5f8; }
QLabel { color: #c3ccd6; font-size: 13px; background: transparent; }
QGroupBox {
    border: 1px solid #2c3a48;
    border-radius: 8px;
    margin-top: 10px;
    padding: 12px 10px;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 #1b2430,stop:1 #141a22);
    color: #f2f5f8;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: #5b9bd5;
    font-size: 12px;
}
QPushButton {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 #3f6f9e,stop:1 #2c4f70);
    color: #f2f5f8;
    border: 1px solid #5b9bd5;
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 700;
    font-size: 12px;
}
QPushButton:hover {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 #4d84b8,stop:1 #3f6f9e);
    color: #ffffff;
}
QPushButton:pressed { background: #2c4f70; }
QPushButton:disabled {
    background: #1b2430; color: #6b7785; border-color: #2c3a48;
}
QPushButton#btnLang {
    background: #1b2430;
    color: #c3ccd6;
    border: 1px solid #2c3a48;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 700;
    border-radius: 4px;
}
QPushButton#btnLang:hover { background: #22303e; color: #5b9bd5; }
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit, QDateEdit,
QDateTimeEdit, QListWidget, QTreeWidget, QTableWidget {
    padding: 5px 8px;
    border: 1px solid #2c3a48;
    border-radius: 5px;
    background: #1b2430;
    color: #f2f5f8;
    selection-background-color: #2c4f70;
}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QLineEdit:focus, QDateEdit:focus, QDateTimeEdit:focus {
    border-color: #5b9bd5;
}
QComboBox::drop-down { border: none; padding-right: 6px; }
QComboBox QAbstractItemView {
    background: #1b2430;
    color: #f2f5f8;
    border: 1px solid #2c3a48;
    selection-background-color: #2c4f70;
}
QCheckBox, QRadioButton { color: #c3ccd6; background: transparent; }
QTabWidget::pane {
    border: 1px solid #2c3a48;
    border-radius: 6px;
    top: -1px;
    background: #141a22;
}
QTabBar::tab {
    background: #1b2430;
    border: 1px solid #2c3a48;
    padding: 7px 14px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    color: #8a97a5;
    font-size: 12px;
}
QTabBar::tab:selected {
    background: #141a22;
    border-bottom-color: #141a22;
    font-weight: bold;
    color: #5b9bd5;
}
QTabBar::tab:hover:!selected { background: #22303e; color: #c3ccd6; }
QProgressBar {
    border: 1px solid #2c3a48;
    border-radius: 4px;
    height: 6px;
    background: #1b2430;
    color: transparent;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #3f6f9e,stop:1 #5b9bd5);
    border-radius: 3px;
}
QPlainTextEdit, QTextEdit, QTextBrowser {
    background: #1b2430;
    border: 1px solid #2c3a48;
    border-radius: 5px;
    color: #c3ccd6;
    font-size: 12px;
}
QHeaderView::section {
    background: #22303e;
    color: #c3ccd6;
    border: none;
    border-bottom: 2px solid #2c3a48;
    padding: 5px 8px;
}
QScrollBar:vertical, QScrollBar:horizontal {
    background: #1b2430;
    border: none;
    width: 8px; height: 8px;
}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
    background: #2c3a48;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
    background: #5b9bd5;
}
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QFrame { background: transparent; }
"""

# Flag symbols used by every language toggle of the family.
FLAG_IT = "\U0001f1ee\U0001f1f9"  # Italian flag
FLAG_EN = "\U0001f1ec\U0001f1e7"  # UK flag
LANG_LABEL_IT = FLAG_IT + " IT"
LANG_LABEL_EN = FLAG_EN + " EN"


def lang_button_label(current_lang):
    """
    Return the label the language button must show: the language you
    would switch TO, with its flag (Italian UI shows the UK flag).
    """
    return LANG_LABEL_EN if current_lang == "it" else LANG_LABEL_IT


def other_plugins(self_key):
    """Return the family entries excluding the hosting plugin."""
    return [p for p in PLUGIN_FAMILY if p["key"] != self_key]


def family_html(self_key):
    """
    Bilingual HTML block (author + plugin family) that Info tabs can
    embed inside an existing QTextBrowser, if preferred to the widget.
    """
    rows = "".join(
        '<tr><td><b>%s</b></td><td>%s<br/>%s</td>'
        '<td><a href="%s">GitHub</a></td></tr>'
        % (p["name"], p["it"], p["en"], p["repo"])
        for p in other_plugins(self_key)
    )
    return (
        "<h3>ALTRI PLUGIN DELL'AUTORE / MORE PLUGINS BY THE AUTHOR</h3>"
        "<table><tr><th>Plugin</th><th>IT / EN</th><th>Link</th></tr>"
        f"{rows}</table>"
    )


class PluginFamilyWidget(QGroupBox):
    """
    Drop-down selector of the author's other plugins, for Info tabs.

    IT: mostra un menù a tendina con gli altri plugin della famiglia
    (quello corrente è escluso); alla selezione appare la descrizione
    bilingue e un pulsante apre il repository GitHub.

    EN: shows a drop-down with the other plugins of the family (the
    current one is excluded); on selection the bilingual description
    appears and a button opens the GitHub repository.
    """

    def __init__(self, self_key, lang="it", parent=None):
        super().__init__(parent)
        self._lang = lang
        self._entries = other_plugins(self_key)
        self._build_ui()
        self.set_lang(lang)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        self.combo = QComboBox()
        for entry in self._entries:
            self.combo.addItem(entry["name"], entry["repo"])
        self.combo.currentIndexChanged.connect(self._on_changed)
        row.addWidget(self.combo, 1)

        self.btn_open = QPushButton()
        self.btn_open.clicked.connect(self._open_repo)
        row.addWidget(self.btn_open)
        layout.addLayout(row)

        self.lbl_desc = QLabel()
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setOpenExternalLinks(True)
        layout.addWidget(self.lbl_desc)

        self.lbl_author = QLabel()
        self.lbl_author.setWordWrap(True)
        self.lbl_author.setOpenExternalLinks(True)
        self.lbl_author.setText(
            '%s — <a href="mailto:%s">%s</a> — '
            '<a href="%s">sinocloud.it</a> — '
            '<a href="%s">github.com/sag1687</a>'
            % (AUTHOR_NAME, AUTHOR_EMAIL, AUTHOR_EMAIL,
               AUTHOR_WEBSITE, AUTHOR_GITHUB)
        )
        layout.addWidget(self.lbl_author)

    def set_lang(self, lang):
        """Retranslate the widget ('it' or 'en')."""
        self._lang = lang if lang in ("it", "en") else "it"
        if self._lang == "en":
            self.setTitle(FLAG_EN + " More plugins by the author")
            self.btn_open.setText("Open GitHub")
        else:
            self.setTitle(FLAG_IT + " Altri plugin dell'autore")
            self.btn_open.setText("Apri GitHub")
        self._on_changed(self.combo.currentIndex())

    def _on_changed(self, index):
        if 0 <= index < len(self._entries):
            entry = self._entries[index]
            desc = entry["en"] if self._lang == "en" else entry["it"]
            self.lbl_desc.setText(
                "<b>%s</b> — %s<br/><a href=\"%s\">%s</a>"
                % (entry["name"], desc, entry["repo"], entry["repo"])
            )

    def _open_repo(self):
        repo = self.combo.currentData()
        if repo:
            QDesktopServices.openUrl(QUrl(repo))


def make_family_widget(self_key, lang="it", parent=None):
    """Convenience factory used by the plugins' Info tabs."""
    return PluginFamilyWidget(self_key, lang=lang, parent=parent)


def make_family_container(self_key, lang="it", parent=None):
    """
    Plain QWidget wrapper (family widget + stretch), handy when the
    Info tab wants a full-page widget instead of a group box only.
    """
    container = QWidget(parent)
    layout = QVBoxLayout(container)
    layout.addWidget(make_family_widget(self_key, lang=lang))
    layout.addStretch(1)
    return container
