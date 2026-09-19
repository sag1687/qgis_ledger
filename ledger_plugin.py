# -*- coding: utf-8 -*-
"""
ledger_plugin.py — Main Plugin Class

Orchestrates all QGIS Ledger components:
  - QGIS Ledger Toolbar (Sync, Commit, Timeline, Settings)
  - Transaction Ledger
  - Timeline Side Panel
  - Visual Diff Engine
  - Merge Wizard
  - Status Bar LED
  - AI Sentinel (stub)
  - Network Sync (stub)
"""

import os
import platform
import configparser
from functools import partial

from qgis.PyQt.QtCore import Qt, QTimer, QSettings, QObject, QEvent
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QAction, QMessageBox, QDialog, QVBoxLayout,
    QLabel, QComboBox, QPushButton, QDialogButtonBox, QHBoxLayout,
    QWidget, QFileDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QTabWidget,
)

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsRasterLayer,
    QgsFeature,
    QgsGeometry,
)
from qgis.gui import QgisInterface as QGISInterface

from .ledger_ledger import LedgerDB
from .ledger_diff import LedgerDiff
from .ledger_browser import LedgerBrowserProvider
from qgis.core import QgsApplication
from .ledger_settings import SettingsDialog, LedgerSettings
from .ledger_sync import NetworkSync
from .ledger_nextcloud import NextcloudBrowserPanel
from .ledger_hub_gui import LedgerCommandCenter
from .ledger_i18n import tr, init_i18n, set_language


class _DropEventFilter(QObject):
    """QObject che intercetta gli eventi drag-drop Nextcloud a livello di QApplication."""  # noqa: E501

    def __init__(self, plugin, parent=None):
        super().__init__(parent)
        self._plugin = plugin

    def eventFilter(self, obj, event):
        etype = event.type()
        if etype == getattr(getattr(QEvent, "Type", QEvent), "DragEnter") or etype == getattr(  # noqa: E501
                getattr(QEvent, "Type", QEvent), "DragMove"):
            try:
                mime = event.mimeData()
                if mime and mime.hasFormat("application/x-qgis-ledger-nc"):
                    event.setDropAction(
                        getattr(
                            getattr(
                                Qt,
                                "DropAction",
                                Qt),
                            "CopyAction"))
                    event.accept()
                    event.acceptProposedAction()
                    return True
            except Exception:  # nosec B110
                pass
        elif etype == getattr(getattr(QEvent, "Type", QEvent), "Drop"):
            try:
                mime = event.mimeData()
                if mime and mime.hasFormat("application/x-qgis-ledger-nc"):
                    event.setDropAction(
                        getattr(
                            getattr(
                                Qt,
                                "DropAction",
                                Qt),
                            "CopyAction"))
                    event.accept()
                    import json
                    raw = bytes(
                        mime.data("application/x-qgis-ledger-nc")).decode("utf-8")  # noqa: E501
                    item_data = json.loads(raw)
                    panel = self._plugin.nextcloud_panel
                    if panel:
                        QTimer.singleShot(
                            0, lambda d=item_data: panel._auto_download_and_load(d))  # noqa: E501
                    return True
            except Exception as e:
                from qgis.PyQt.QtWidgets import QMessageBox
                QMessageBox.warning(None, "QGIS Ledger", tr(
                    "Errore drop Nextcloud: {e}").format(e=e))
                return True
        return False


class _CommitDialog(QDialog):
    """Dialogo custom per inserire msg di commit e scegliere se salvare in Cloud."""  # noqa: E501

    def __init__(self, title="Nuovo Commit", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(350)

        layout = QVBoxLayout(self)

        lbl = QLabel(tr("Descrivi le modifiche (Perché):"))
        layout.addWidget(lbl)

        from qgis.PyQt.QtWidgets import QLineEdit, QCheckBox
        self.txt_msg = QLineEdit()
        layout.addWidget(self.txt_msg)

        self.chk_cloud = QCheckBox(tr("Sincronizza subito su Cloud"))
        # Se Nextcloud è attivo, spunta di default
        if LedgerSettings.remote_type() == "webdav":
            self.chk_cloud.setChecked(True)
        else:
            self.chk_cloud.setChecked(False)
            self.chk_cloud.setEnabled(False)
            self.chk_cloud.setToolTip(
                tr("Cloud non configurato nelle Impostazioni"))

        layout.addWidget(self.chk_cloud)

        btns = QDialogButtonBox(
            getattr(
                getattr(
                    QDialogButtonBox,
                    "StandardButton",
                    QDialogButtonBox),
                "Ok") | getattr(
                getattr(
                    QDialogButtonBox,
                    "StandardButton",
                    QDialogButtonBox),
                "Cancel"))
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_data(self):
        return self.txt_msg.text().strip(), self.chk_cloud.isChecked()


class LedgerPlugin:
    """QGIS QGIS Ledger — Main Plugin Class."""

    SYNCED = 'synced'
    MODIFIED = 'modified'
    CONFLICT = 'conflict'
    DISCONNECTED = 'disconnected'

    def __init__(self, iface: QGISInterface):
        self.iface = iface
        self.ledger = LedgerDB()
        self.diff_engine = LedgerDiff(self.ledger)
        self.sync = NetworkSync()

        self.timeline_panel = None
        self.nextcloud_panel = None
        self.main_panel = None
        self._act_status = None
        self._browser_provider = None
        self.toolbar = None
        self._actions = []
        self._preview_mode = False
        self._sync_timer = None
        self._autosave_timer = None
        self._autosave_action = None
        self._nextcloud_action = None

    # ================================================================== #
    # Plugin lifecycle
    # ================================================================== #

    # ------------------------------------------------------------------ #
    # Utility: crea QIcon stilizzata da emoji/testo
    # ------------------------------------------------------------------ #
    @staticmethod
    def _make_icon(
            symbol: str,
            bg_color: str = "#141a22",
            fg_color: str = "#f2f5f8",
            size: int = 24):
        """Genera una QIcon con un simbolo centrato su sfondo arrotondato."""
        from qgis.PyQt.QtGui import QPixmap, QPainter, QColor, QFont
        from qgis.PyQt.QtCore import Qt as QtConst, QRect
        pm = QPixmap(size, size)
        pm.fill(QColor(0, 0, 0, 0))  # trasparente
        p = QPainter(pm)
        p.setRenderHint(getattr(QPainter, "RenderHint", QPainter).Antialiasing)
        # sfondo arrotondato
        p.setBrush(QColor(bg_color))
        p.setPen(QColor(bg_color))
        p.drawRoundedRect(1, 1, size - 2, size - 2, 6, 6)
        # testo emoji/simbolo
        p.setPen(QColor(fg_color))
        font = QFont()
        font.setPixelSize(int(size * 0.55))
        font.setBold(True)
        p.setFont(font)
        p.drawText(
            QRect(
                0,
                0,
                size,
                size),
            getattr(
                getattr(
                    QtConst,
                    "AlignmentFlag",
                    QtConst),
                "AlignCenter"),
            symbol)
        p.end()
        return QIcon(pm)

    def _set_status(self, status: str):
        if not hasattr(self, '_act_status') or not self._act_status:
            return
        if status == self.DISCONNECTED:
            self._act_status.setIcon(
                self._make_icon(
                    "⚪", "transparent", "#c3ccd6"))
            self._act_status.setToolTip(
                tr("QGIS Ledger: Nessun progetto aperto"))
        elif status == self.SYNCED:
            self._act_status.setIcon(
                self._make_icon(
                    "🟢", "transparent", "#2ecc71"))
            self._act_status.setToolTip(
                tr("QGIS Ledger: Sincronizzato con l'ultima versione"))
        elif status == self.MODIFIED:
            self._act_status.setIcon(
                self._make_icon(
                    "🟡", "transparent", "#f1c40f"))
            self._act_status.setToolTip(
                tr("QGIS Ledger: Modifiche in attesa di commit"))
        elif status == self.CONFLICT:
            self._act_status.setIcon(
                self._make_icon(
                    "🔴", "transparent", "#e74c3c"))
            self._act_status.setToolTip(tr("QGIS Ledger: Conflitti rilevati!"))

    def initGui(self):
        """Called by QGIS when the plugin is loaded."""
        # Initialize translation
        init_i18n()

        # Check first run language
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
        if not settings.contains("qgis_ledger/language"):
            set_language("it")

        # -- Toolbar --------------------------------------------------- #
        self.toolbar = self.iface.addToolBar("QGIS Ledger")
        self.toolbar.setObjectName("QGIS LedgerToolbar")
        self.toolbar.setStyleSheet(
            "QToolBar { spacing: 2px; }"
            "QToolButton { min-width: 36px; min-height: 36px; font-size: 11px; }")  # noqa: E501

        # Command Center button (launcher for every plugin command).
        # Kept in a dedicated attribute so retranslateUi does not depend on
        # its position inside self._actions (indexes 0..8 stay stable).
        self._cmdcenter_action = QAction(
            self._make_icon("▦", "#5b9bd5"),
            tr("Centro Comandi"),
            self.iface.mainWindow())
        self._cmdcenter_action.setToolTip(
            tr("Mostra tutti i comandi del plugin come pulsanti"))
        self._cmdcenter_action.triggered.connect(self._on_command_center)
        self.toolbar.addAction(self._cmdcenter_action)
        self.toolbar.addSeparator()

        # Open Project button
        act_open = QAction(
            self._make_icon(
                "📂",
                "#3f6f9e"),
            tr("Apri Progetto"),
            self.iface.mainWindow())
        act_open.setToolTip(tr("Apri un progetto QGIS esistente"))
        act_open.triggered.connect(self._on_open_project)
        self.toolbar.addAction(act_open)
        self._actions.append(act_open)

        # Commit button (dropdown combining Layer and Project commit)
        from qgis.PyQt.QtWidgets import QToolButton, QMenu
        self.btn_commit = QToolButton(self.toolbar)
        self.btn_commit.setIcon(self._make_icon("✔", "#16a085"))
        self.btn_commit.setPopupMode(
            getattr(
                getattr(
                    QToolButton,
                    "ToolButtonPopupMode",
                    QToolButton),
                "InstantPopup"))
        self.btn_commit.setToolTip(tr("Salva snapshot (Layer o Progetto)"))

        self.menu_commit = QMenu(self.btn_commit)

        act_commit = QAction(self._make_icon("✔", "#16a085"), tr(
            "Salva solo questo Layer"), self.iface.mainWindow())
        act_commit.triggered.connect(self._on_commit)
        self.menu_commit.addAction(act_commit)
        self._actions.append(act_commit)

        act_commit_proj = QAction(
            self._make_icon(
                "💾",
                "#8e44ad"),
            tr("Salva intero Progetto"),
            self.iface.mainWindow())
        act_commit_proj.triggered.connect(self._on_commit_project)
        self.menu_commit.addAction(act_commit_proj)
        self._actions.append(act_commit_proj)

        self.btn_commit.setMenu(self.menu_commit)
        self.toolbar.addWidget(self.btn_commit)

        # Main Panel button (unifies Timeline and Nextcloud)
        self._panel_action = QAction(
            self._make_icon(
                "🕘☁",
                "#141a22"),
            tr("Pannello Ledger"),
            self.iface.mainWindow())
        self._panel_action.setToolTip(
            tr("Mostra/nascondi il pannello principale (Timeline & Nextcloud)"))  # noqa: E501
        self._panel_action.setCheckable(True)
        self._panel_action.triggered.connect(self._toggle_main_panel)
        self.toolbar.addAction(self._panel_action)
        self._actions.append(self._panel_action)

        # Diff button
        act_diff = QAction(
            self._make_icon(
                "Δ",
                "#e67e22"),
            tr("Diff"),
            self.iface.mainWindow())
        act_diff.setToolTip(tr("Confronto visuale tra due versioni"))
        act_diff.triggered.connect(self._on_diff_dialog)
        self.toolbar.addAction(act_diff)
        self._actions.append(act_diff)

        # Browser button
        act_browser = QAction(
            self._make_icon(
                "🗂",
                "#22303e"),
            tr("Esplora Storico"),
            self.iface.mainWindow())
        act_browser.setToolTip(
            tr("Sfoglia ed Estrai vecchie versioni dal database"))
        act_browser.triggered.connect(self._on_browser_dialog)
        self.toolbar.addAction(act_browser)
        self._actions.append(act_browser)

        self.toolbar.addSeparator()

        # Auto-Save Timer button
        self._autosave_action = QAction(
            self._make_icon(
                "⏱",
                "#f39c12"),
            tr("Auto-Save"),
            self.iface.mainWindow())
        self._autosave_action.setCheckable(True)
        self._autosave_action.setToolTip(
            tr("Attiva/Disattiva il salvataggio automatico periodico"))
        self._autosave_action.triggered.connect(self._toggle_autosave)
        self.toolbar.addAction(self._autosave_action)
        self._actions.append(self._autosave_action)
        self.toolbar.addSeparator()

        # Settings button
        act_settings = QAction(
            self._make_icon(
                "⚙",
                "#8a97a5"),
            tr("Settings"),
            self.iface.mainWindow())
        act_settings.setToolTip(tr("Impostazioni QGIS Ledger"))
        act_settings.triggered.connect(self._on_settings)
        self.toolbar.addAction(act_settings)
        self._actions.append(act_settings)

        # -- Aggiungi tutti i pulsanti al Menu Plugins -- #
        for action in self._actions:
            self.iface.addPluginToMenu("&QGIS Ledger", action)

        # -- Status indicator in Toolbar -------------------------------- #
        self._act_status = QAction(
            self._make_icon(
                "⚪", "transparent", "#c3ccd6"), tr("Stato Ledger"), self.iface.mainWindow())  # noqa: E501
        self._act_status.setToolTip(
            tr("QGIS Ledger: Nessun progetto aperto"))
        self._act_status.triggered.connect(self._on_led_clicked)
        self.toolbar.addAction(self._act_status)
        self._actions.append(self._act_status)

        # Register the Command Center in the Plugins menu and mark it for
        # cleanup. Appended last so indexes 0..8 used by retranslateUi stay
        # valid; it is not referenced by numeric index anywhere.
        self.iface.addPluginToMenu("&QGIS Ledger", self._cmdcenter_action)
        self._actions.append(self._cmdcenter_action)

        # Apply the toolbar display mode (compact = only Command Center).
        self._apply_toolbar_mode()

        # -- Browser Provider Integration ------------------------------- #
        self._browser_provider = LedgerBrowserProvider(self)
        QgsApplication.dataItemProviderRegistry().addProvider(self._browser_provider)  # noqa: E501

        # self.timeline_panel = TimelinePanel(self.ledger)
        # self.timeline_panel.preview_requested.connect(self._on_preview)
        # self.timeline_panel.rollback_requested.connect(self._on_rollback)
        # self.timeline_panel.diff_requested.connect(self._on_diff_from_commit)
        # self.timeline_panel.commit_requested.connect(self._on_commit)
        # self.iface.addDockWidget(getattr(getattr(Qt, "DockWidgetArea", Qt), "RightDockWidgetArea"), self.timeline_panel)  # noqa: E501
        # self.timeline_panel.hide()

        # -- Nextcloud Browser Panel ----------------------------------- #
        # self.nextcloud_panel = NextcloudBrowserPanel(self.iface.mainWindow())
        # self.iface.addDockWidget(getattr(getattr(Qt, "DockWidgetArea", Qt), "LeftDockWidgetArea"), self.nextcloud_panel)  # noqa: E501
        # self.nextcloud_panel.hide()
        # self.nextcloud_panel.visibilityChanged.connect(
        #     lambda visible: self._nextcloud_action.setChecked(visible)
        # )

        # -- Nextcloud Panel (not a dock, embedded in tab) ------------ #
        from qgis.PyQt.QtWidgets import QDockWidget, QTabWidget
        self.nextcloud_panel = NextcloudBrowserPanel()
        self.nextcloud_panel.tree.layer_dropped.connect(
            self._on_layer_dropped_to_nc)
        self.nextcloud_panel.layer_loaded.connect(self._on_cloud_layer_loaded)
        # -- Timeline Panel (not a dock, embedded in tab) ------------- #
        from .ledger_timeline import TimelinePanel
        self.timeline_panel = TimelinePanel(self.ledger, parent=None)
        self.timeline_panel.preview_requested.connect(self._on_preview)
        self.timeline_panel.rollback_requested.connect(self._on_rollback)
        self.timeline_panel.diff_requested.connect(self._on_diff_from_commit)
        self.timeline_panel.commit_requested.connect(self._on_commit)

        # -- Unified Main Panel (Dock Widget) ------------------------- #
        self.main_panel = QDockWidget(
            tr("QGIS Ledger"), self.iface.mainWindow())
        self.main_panel.setObjectName("QGISLedgerMainPanel")

        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.timeline_panel, tr("🕓 Timeline"))
        self.tab_widget.addTab(self.nextcloud_panel, tr("☁️ Nextcloud"))
        self.tab_widget.currentChanged.connect(
            self._on_tab_changed)  # _on_tab_changed needs to be defined

        self.main_panel.setWidget(self.tab_widget)
        self.iface.addDockWidget(
            getattr(
                getattr(
                    Qt,
                    "DockWidgetArea",
                    Qt),
                "RightDockWidgetArea"),
            self.main_panel)
        self.main_panel.hide()
        self.main_panel.visibilityChanged.connect(
            self._panel_action.setChecked)

        # Configura Nextcloud action (context menu upload) ------------- #
        self.upload_nc_action = QAction(self._make_icon("☁️", "#5b9bd5"), tr(
            "Invia a Nextcloud (QGIS Ledger)"), self.iface.mainWindow())
        self.upload_nc_action.triggered.connect(self._on_upload_layer_to_nc)

        try:
            from qgis.core import QgsMapLayerType
            self.iface.addCustomActionForLayerType(
                self.upload_nc_action, "QGIS Ledger", QgsMapLayerType.VectorLayer, False)  # noqa: E501
            self.iface.addCustomActionForLayerType(
                self.upload_nc_action, "QGIS Ledger", QgsMapLayerType.RasterLayer, False)  # noqa: E501
            self.iface.addCustomActionForLayerType(
                self.upload_nc_action, "QGIS Ledger", QgsMapLayerType.MeshLayer, False)  # noqa: E501
        except Exception:  # nosec B110
            pass

        # -- Connect project signals ---------------------------------- #
        QgsProject.instance().readProject.connect(self._on_project_opened)
        QgsProject.instance().cleared.connect(self._on_project_closed)

        # -- Enable Drag & Drop from Nextcloud panel → ovunque in QGIS -- #
        # Usiamo l'event filter sulla mainWindow invece che su QApplication
        # intera per sicurezza.
        self._drop_filter = _DropEventFilter(self)
        self.iface.mainWindow().installEventFilter(self._drop_filter)

        # If a project is already open, connect now
        if QgsProject.instance().fileName():
            self._on_project_opened()

        # -- Sync timer (check every 10 seconds) ---------------------- #
        self._sync_timer = QTimer()
        self._sync_timer.timeout.connect(self._check_sync)
        self._sync_timer.start(10000)

    def retranslateUi(self):
        """Aggiorna i testi in base alla lingua scelta al volo."""
        # 1. Update toolbar buttons text and tooltips
        act_open = self._actions[0]
        act_open.setText(tr("Apri Progetto"))
        act_open.setToolTip(tr("Apri un progetto QGIS esistente"))

        # 2. Commit buttons
        self.btn_commit.setToolTip(tr("Salva snapshot (Layer o Progetto)"))
        self._actions[1].setText(tr("Salva solo questo Layer"))
        self._actions[2].setText(tr("Salva intero Progetto"))

        # 3. Main Panel action
        self._actions[3].setText(tr("Pannello Ledger"))
        self._actions[3].setToolTip(
            tr("Mostra/nascondi il pannello principale (Timeline & Nextcloud)"))  # noqa: E501

        # 4. Diff and Browser actions
        self._actions[4].setText(tr("Diff"))
        self._actions[4].setToolTip(tr("Confronto visuale tra due versioni"))
        self._actions[5].setText(tr("Esplora Storico"))
        self._actions[5].setToolTip(
            tr("Sfoglia ed Estrai vecchie versioni dal database"))

        # 5. Autosave, Settings
        self._actions[6].setText(tr("Auto-Save"))
        self._actions[6].setToolTip(
            tr("Attiva/Disattiva il salvataggio automatico periodico"))
        self._actions[7].setText(tr("Settings"))
        self._actions[7].setToolTip(tr("Impostazioni QGIS Ledger"))

        # 6. Status action
        self._actions[8].setText(tr("Stato Ledger"))
        self._actions[8].setToolTip(
            tr("QGIS Ledger: Nessun progetto aperto"))

        # 7. Main panel title & tabs
        self.main_panel.setWindowTitle(tr("QGIS Ledger"))
        self.tab_widget.setTabText(0, tr("🕓 Timeline"))
        self.tab_widget.setTabText(1, tr("☁️ Nextcloud"))
        self.upload_nc_action.setText(tr("Invia a Nextcloud (QGIS Ledger)"))

        # 8. Command Center action + open window (if any)
        if getattr(self, "_cmdcenter_action", None) is not None:
            self._cmdcenter_action.setText(tr("Centro Comandi"))
            self._cmdcenter_action.setToolTip(
                tr("Mostra tutti i comandi del plugin come pulsanti"))
        _cc = getattr(self, "_cmd_center", None)
        if _cc is not None:
            _cc.retranslate()

        # Re-apply current status to update translations dynamically
        self._set_status(self._last_status if hasattr(
            self, '_last_status') else self.DISCONNECTED)

    def unload(self):
        """Called by QGIS when the plugin is unloaded."""
        try:
            if self._sync_timer:
                self._sync_timer.stop()
            if self._autosave_timer:
                self._autosave_timer.stop()
        except Exception:  # nosec B110
            pass

        # Rimuovi provider del browser
        try:
            if hasattr(self, "_browser_provider") and self._browser_provider:
                from qgis.core import QgsApplication
                QgsApplication.dataItemProviderRegistry().removeProvider(self._browser_provider)  # noqa: E501
                self._browser_provider = None
        except Exception:  # nosec B110
            pass

        # Rimuovi azioni
        for act in getattr(self, "_actions", []):
            try:
                self.iface.removePluginMenu("&QGIS Ledger", act)
                self.iface.removeToolBarIcon(act)
            except Exception:  # nosec B110
                pass

        # Rimuovi lo stato dalla toolbar
        try:
            _st_act = getattr(self, "_act_status", None)
            _tb = getattr(self, "toolbar", None)
            if _st_act and _tb:
                _tb.removeAction(_st_act)
                _st_act.deleteLater()
                self._act_status = None
        except Exception:  # nosec B110
            pass

        # Rimuovi la toolbar
        try:
            _tb = getattr(self, "toolbar", None)
            if _tb:
                self.iface.mainWindow().removeToolBar(_tb)
                _tb.deleteLater()
                self.toolbar = None
        except Exception:  # nosec B110
            pass

        # Chiudi il Centro Comandi se aperto
        try:
            _cc = getattr(self, "_cmd_center", None)
            if _cc is not None:
                _cc.close()
                _cc.deleteLater()
                self._cmd_center = None
        except Exception:  # nosec B110
            pass

        # Rimuovi pannelli
        for p_name in ["timeline_panel", "nextcloud_panel", "main_panel"]:
            try:
                p = getattr(self, p_name, None)
                if p:
                    try:
                        self.iface.removeDockWidget(p)
                    except Exception:  # nosec B110
                        pass
                    p.deleteLater()
                    setattr(self, p_name, None)
            except Exception:  # nosec B110
                pass

        try:
            self.iface.removeCustomActionForLayerType(
                getattr(self, "upload_nc_action", None))
        except Exception:  # nosec B110
            pass

        try:
            self.diff_engine.clear_diff()
        except Exception:  # nosec B110
            pass
        try:
            self.ledger.close()
        except Exception:  # nosec B110
            pass

        # Rimuovi event filter
        try:
            if getattr(self, "_drop_filter", None):
                self.iface.mainWindow().removeEventFilter(self._drop_filter)
                self._drop_filter = None
        except Exception:  # nosec B110
            pass

        # Disconnetti segnali
        try:
            from qgis.core import QgsProject
            QgsProject.instance().readProject.disconnect(self._on_project_opened)  # noqa: E501
            QgsProject.instance().cleared.disconnect(self._on_project_closed)
        except Exception:  # nosec B110
            pass
    # ================================================================== #
    # Drag & Drop event filter (Nextcloud → Canvas)
    # ================================================================== #

    # Menù contestuale nativo gestito via addCustomActionForLayerType

    # ================================================================== #
    # Project lifecycle
    # ================================================================== #

    def _on_project_opened(self, *args):
        """Connect to the ledger when a project is opened."""
        if self.ledger.connect():
            self._set_status(self.SYNCED)
            self.timeline_panel.populate_layers()
            # Start network sync monitoring
            db_path = self.ledger.db_path()
            if db_path:
                self.sync.start_watching(db_path)
            # Connect layer edit signals for auto-commit
            self._connect_layer_signals()
            # Check for modifying mod_user
            self._check_mod_user_commits()
        else:
            self._set_status(self.DISCONNECTED)

    def _on_project_closed(self, *args):
        self.ledger.close()
        self.sync.stop_watching()
        self._set_status(self.DISCONNECTED)
        self.diff_engine.clear_diff()

    def _check_mod_user_commits(self):
        """Check if mod_user have made changes since the project was last opened on this machine."""  # noqa: E501
        proj_file = QgsProject.instance().fileName()
        if not proj_file:
            return

        settings = QSettings()
        setting_key = f"qgis_ledger/last_seen_commit/{proj_file}"
        last_seen = settings.value(setting_key, 0, type=int)

        history = self.ledger.get_history()
        if not history:
            return

        latest_commit_id = history[0]["id"]
        me = LedgerSettings.user_name()

        new_commits_by_others = []
        for commit in history:
            if commit["id"] <= last_seen:
                break
            if commit["user_name"] != me:
                new_commits_by_others.append(commit)

        settings.setValue(setting_key, latest_commit_id)

        if new_commits_by_others:
            mod_users = set(c["user_name"] for c in new_commits_by_others)
            layer_names = set(
                c["layer_name"] for c in new_commits_by_others if c.get("commit_type") in (  # noqa: E501
                    "VECTOR", "RASTER"))

            msg = tr("Ottime notizie! {} nuove modifiche aggiunte dai mod_user ({}).").format(  # noqa: E501
                len(new_commits_by_others), ', '.join(mod_users))

            self.iface.messageBar().pushInfo(
                tr("QGIS Ledger — Novità dai mod_user"), msg
            )

            details = tr("Sono state trovate {} nuove modifiche apportate dai mod_user:\n").format(  # noqa: E501
                len(new_commits_by_others))
            details += tr("• Autori: {}\n").format(', '.join(mod_users))
            if layer_names:
                details += tr("• Layer toccati: {}\n").format(', '.join(layer_names))  # noqa: E501
            details += tr("\nApri la Timeline per esaminare in dettaglio cosa hanno fatto.")  # noqa: E501

            QMessageBox.information(
                self.iface.mainWindow(),
                tr("QGIS Ledger — Aggiornamenti Disponibili"),
                details
            )
            self._set_status(self.MODIFIED)

    def _connect_layer_signals(self):
        """Connect to layer edit signals for status updates."""
        for lid, layer in QgsProject.instance().mapLayers().items():
            if isinstance(layer, QgsVectorLayer):
                try:
                    layer.editingStarted.connect(
                        partial(self._on_editing_started, layer)
                    )
                    layer.editingStopped.connect(
                        partial(self._on_editing_stopped, layer)
                    )
                except RuntimeError:
                    pass  # already connected

    def _on_editing_started(self, layer):
        self._set_status(self.MODIFIED)

    def _on_editing_stopped(self, layer):
        """Auto-commit if enabled."""
        if LedgerSettings.auto_commit() and self.ledger.is_connected():
            msg = "[AUTO] Salvataggio automatico durante editing"
            cid = self.ledger.create_commit(
                layer, msg, LedgerSettings.user_name()
            )
            if cid > 0:
                self._trigger_cloud_sync(cid)
            self.timeline_panel.refresh()
        self._set_status(self.SYNCED)

    # ================================================================== #
    # Toolbar actions
    # ================================================================== #

    def _connect_and_open_cloud(self, cloud_id: str):
        """Called from QGIS Browser to open a specific cloud."""
        from .ledger_settings import LedgerSettings
        # Check if config is present for token/server based clouds
        missing = False
        if cloud_id == "webdav" and not LedgerSettings.nextcloud_server():
            missing = True
        elif cloud_id == "generic_webdav" and not LedgerSettings.webdav_url():
            missing = True
        elif cloud_id == "dropbox" and not LedgerSettings.dropbox_token():
            missing = True
        elif cloud_id == "onedrive" and not LedgerSettings.onedrive_token():
            missing = True
        elif cloud_id == "google_drive" and not LedgerSettings.gdrive_access_token():  # noqa: E501
            missing = True

        if missing:
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.information(self.iface.mainWindow(), "QGIS Ledger", tr(
                "Questo servizio Cloud non è ancora configurato.\nApri le Impostazioni per aggiungere le relative credenziali o i token di accesso."))  # noqa: E501
            self._on_settings()
            return

        # Swap provider dynamically
        LedgerSettings.set("remote_type", cloud_id)

        # Show panel
        self._panel_action.setChecked(True)
        if getattr(self, 'main_panel', None):
            self.main_panel.show()
        if getattr(self, 'tab_widget', None):
            self.tab_widget.setCurrentIndex(1)

        # Re-initialize the client directly in the panel
        if getattr(self, 'nextcloud_panel', None):
            client = LedgerSettings.get_cloud_client()
            self.nextcloud_panel.connect_cloud(client)

    def _on_open_project(self):
        """Open a QGIS project from disk or cloud."""
        if LedgerSettings.remote_type() != "locale" and self.nextcloud_panel:
            m1 = tr(
                "Vuoi esplorare un progetto LOCALE o scaricarlo dal tuo provider CLOUD?\n\n")  # noqa: E501
            m2 = tr("• 'Yes' per scegliere un file nel disco locale (PC)\n")
            m3 = tr("• 'No' per sfogliare l'archivio CLOUD selezionato")
            reply = QMessageBox.question(
                self.iface.mainWindow(),
                "QGIS Ledger",
                m1 + m2 + m3,
                getattr(getattr(QMessageBox, "StandardButton", QMessageBox), "Yes") | getattr(getattr(QMessageBox, "StandardButton", QMessageBox), "No"))  # noqa: E501
            if reply == getattr(
                    getattr(QMessageBox, "StandardButton", QMessageBox), "No"):
                self._panel_action.setChecked(True)
                if getattr(self, 'main_panel', None):
                    self.main_panel.show()
                if getattr(self, 'tab_widget', None):
                    self.tab_widget.setCurrentIndex(1)
                QMessageBox.information(self.iface.mainWindow(), "QGIS Ledger", tr(  # noqa: E501
                    "Naviga nel pannello Cloud a destra e fai doppio clic sul file .qgz per scaricarlo e aprirlo."))  # noqa: E501
                return

        file_path, _ = QFileDialog.getOpenFileName(
            self.iface.mainWindow(),
            tr("Seleziona Progetto QGIS"),
            QgsProject.instance().homePath() or "",
            tr("QGIS Project (*.qgz *.qgs *.gpkg);;Tutti i file (*)")
        )
        if file_path:
            if file_path.endswith('.gpkg'):
                try:
                    import sqlite3
                    conn = sqlite3.connect(file_path)
                    c = conn.cursor()
                    c.execute("SELECT name FROM qgis_projects LIMIT 1")
                    row = c.fetchone()
                    conn.close()
                    if row:
                        uri = f"geopackage:{file_path}?projectName={row[0]}"
                        QgsProject.instance().read(uri)
                    else:
                        QMessageBox.warning(self.iface.mainWindow(), "QGIS Ledger", tr(  # noqa: E501
                            "Nessun progetto trovato nel GeoPackage selezionato."))  # noqa: E501
                except Exception as e:
                    QMessageBox.warning(
                        self.iface.mainWindow(),
                        "QGIS Ledger",
                        tr("Errore lettura GeoPackage: {}").format(e))
            else:
                QgsProject.instance().read(file_path)

    def _on_commit(self):
        """Commit the active layer with a user message."""
        layer = self.iface.activeLayer()
        if not isinstance(layer, (QgsVectorLayer, QgsRasterLayer)):
            QMessageBox.warning(self.iface.mainWindow(), "QGIS Ledger", tr(
                "Seleziona un layer vettoriale o raster per fare il commit."))
            return

        if not self.ledger.is_connected():
            if not self.ledger.connect():
                QMessageBox.warning(
                    self.iface.mainWindow(), "QGIS Ledger",
                    tr("Salva il progetto prima di usare QGIS Ledger.")
                )
                return

        dlg = _CommitDialog(
            tr("QGIS Ledger — Nuovo Commit"),
            self.iface.mainWindow())
        if not dlg.exec():
            return

        message, sync_cloud = dlg.get_data()
        if not message:
            return

        user = LedgerSettings.user_name()
        warn_text = ""

        if isinstance(layer, QgsVectorLayer):
            commit_id = self.ledger.create_commit(layer, message.strip(), user)
            feat_count = layer.featureCount()
        else:
            commit_id = self.ledger.create_raster_commit(
                layer, message.strip(), user)
            feat_count = 1

        if commit_id > 0:
            self._capture_screenshot(commit_id)
            QMessageBox.information(
                self.iface.mainWindow(),
                tr("QGIS Ledger — Commit Salvato ✅"),
                tr("Commit #{} salvato con successo!\nLayer: {}\nFeatures/File: {}\nUtente: {}{}\n\n💡 Ricorda: salva il progetto QGIS (Ctrl+S) per consolidare le modifiche.").format(  # noqa: E501
                    commit_id,
                    layer.name(),
                    feat_count,
                    user,
                    warn_text))
            self._set_status(self.SYNCED)
            self.timeline_panel.populate_layers()
            if sync_cloud:
                self._trigger_cloud_sync(commit_id)
        else:
            QMessageBox.critical(self.iface.mainWindow(), "QGIS Ledger", tr(
                "Errore durante il salvataggio del commit (file non accessibile o ledger chiuso)."))  # noqa: E501

    def _on_cloud_layer_loaded(self, layer, source_name: str):
        """Called when a cloud vector/raster layer is successfully downloaded and loaded into the project."""  # noqa: E501
        if not self.ledger.is_connected() or not layer:
            return

        # Create an initial commit to track the layer from the start (enables
        # rollback)
        msg = tr("Import iniziale da Cloud ({})").format(source_name)

        from qgis.core import QgsVectorLayer, QgsRasterLayer
        from functools import partial
        if isinstance(layer, QgsVectorLayer):
            self.ledger.create_commit(
                layer, msg, LedgerSettings.user_name())
            # Connect editing signals so auto-commit works for this layer
            try:
                layer.editingStarted.connect(
                    partial(self._on_editing_started, layer))
                layer.editingStopped.connect(
                    partial(self._on_editing_stopped, layer))
            except RuntimeError:
                pass
        elif isinstance(layer, QgsRasterLayer):
            self.ledger.create_raster_commit(
                layer, msg, LedgerSettings.user_name())

        self.timeline_panel.refresh()

    def _trigger_cloud_sync(self, commit_id: int):
        """Esegue l'upload in background dei file generati da un commit se Nextcloud è attivo."""  # noqa: E501
        if LedgerSettings.remote_type() != "webdav" or not self.nextcloud_panel:  # noqa: E501
            return

        import os
        from qgis.core import QgsProject
        from .ledger_nextcloud import _Worker, NextcloudClient
        from qgis.PyQt.QtCore import QThreadPool

        proj_path = QgsProject.instance().fileName()
        if not proj_path:
            return

        # Determina la cartella remota
        cloud_base = QgsProject.instance().readEntry(
            "QGIS_Ledger", "cloud_sync_path", "")[0]
        if cloud_base:
            remote_dir = os.path.dirname(cloud_base)
        else:
            remote_dir = ""  # default root o la cartella in settings

        info = self.ledger.get_commit_info(commit_id)
        if not info:
            return

        files_to_sync = []

        # 1. Il database di ledger (sempre)
        db_path = self.ledger.db_path()
        if not db_path or not os.path.exists(db_path):
            return  # Non c'è database, non possiamo sincronizzare
        files_to_sync.append(
            (db_path, f"{os.path.basename(proj_path)}.ledger.db"))

        # 2. File WAL e SHM se presenti (SQLite in WAL mode)
        if os.path.exists(str(db_path) + "-wal"):
            files_to_sync.append((str(db_path) + "-wal",
                                  f"{os.path.basename(proj_path)}.ledger.db-wal"))  # noqa: E501
        if os.path.exists(str(db_path) + "-shm"):
            files_to_sync.append((str(db_path) + "-shm",
                                  f"{os.path.basename(proj_path)}.ledger.db-shm"))  # noqa: E501

        # 3. Snapshot o copia progetto
        ctype = info.get("commit_type")
        file_path = info.get("file_path", "")
        if file_path:
            if ctype == "PROJECT":
                local_f = os.path.join(
                    self.ledger.history_dir(), "project", file_path)
                files_to_sync.append((local_f, file_path))

                # Sincronizza anche l'attuale .qgz se stiamo committando il
                # progetto
                if os.path.exists(proj_path):
                    files_to_sync.append(
                        (proj_path, os.path.basename(proj_path)))

                # Upload all ledger project history (the entire .ledger sidecar
                # folder)
                ledger_sidecar = proj_path + ".ledger"
                if os.path.exists(ledger_sidecar) and os.path.isdir(
                        ledger_sidecar):
                    for root, dirs, files in os.walk(ledger_sidecar):
                        for f in files:
                            abs_p = os.path.join(root, f)
                            rel_p = os.path.relpath(
                                abs_p, os.path.dirname(ledger_sidecar))
                            files_to_sync.append((abs_p, rel_p))
            elif ctype == "VECTOR":
                local_f = os.path.join(
                    self.ledger.history_dir(),
                    "vector",
                    file_path.split('|')[0])
                files_to_sync.append((local_f, os.path.basename(local_f)))
            elif ctype == "RASTER":
                local_f = os.path.join(
                    self.ledger.history_dir(), "raster", file_path)
                files_to_sync.append((local_f, file_path))

        def sync_task():
            client = NextcloudClient(
                LedgerSettings.nextcloud_server(),
                LedgerSettings.nextcloud_user(),
                LedgerSettings.nextcloud_password(),
                LedgerSettings.nextcloud_folder(),
                verify_ssl=LedgerSettings.verify_ssl()
            )
            # Create remote dir if not exists (try block)
            if remote_dir:
                try:
                    client.make_directory(remote_dir)
                except BaseException:
                    pass

            for local_p, remote_name in files_to_sync:
                if os.path.exists(local_p):
                    target_remote = (
                        remote_dir + "/" + remote_name).lstrip("/")
                    client.upload(target_remote, local_p)

        worker = _Worker(sync_task)
        # Mostriamo un tooltip leggero o cambiamo il led
        self._act_status.setToolTip(tr("Sincronizzazione Cloud in corso..."))
        worker.signals.finished.connect(
            lambda res: self._act_status.setToolTip("Sincronizzato col Cloud ✅"))  # noqa: E501
        QThreadPool.globalInstance().start(worker)

    def _on_layer_dropped_to_nc(self, drop_data: str):
        """Gestisce il drop di un layer da QGIS nel pannello Nextcloud."""
        from qgis.core import QgsProject

        target_layer = None
        # data format typically: TYPE:name:uri or layer ID. Let's do a fuzzy
        # match.
        for lyr in QgsProject.instance().mapLayers().values():
            if lyr.id() in drop_data or lyr.name() in drop_data or drop_data in lyr.source():  # noqa: E501
                target_layer = lyr
                break

        if not target_layer:
            target_layer = self.iface.activeLayer()  # Fallback al layer attivo

        if target_layer:
            self.iface.setActiveLayer(target_layer)
            self._on_upload_layer_to_nc()

    def _on_upload_layer_to_nc(self):
        if LedgerSettings.remote_type() != "webdav" or not self.nextcloud_panel:  # noqa: E501
            QMessageBox.warning(self.iface.mainWindow(), "QGIS Ledger", tr(
                "Sincronizzazione Nextcloud disattivata o non configurata.\nVai in Impostazioni e verifica i parametri."))  # noqa: E501
            return

        layer = self.iface.activeLayer()
        if not layer:
            return

        import os
        src_file = layer.source()
        if not os.path.isfile(src_file) and "|" in src_file:
            src_file = src_file.split("|")[0]

        if not os.path.exists(src_file):
            QMessageBox.warning(self.iface.mainWindow(), "QGIS Ledger", tr(
                "Impossibile determinare il file sorgente del layer.\nForse è in memoria o non salvato?"))  # noqa: E501
            return

        from qgis.PyQt.QtWidgets import QInputDialog
        base_dir = LedgerSettings.nextcloud_folder()
        default_dest = base_dir + "/" + layer.name() if base_dir else layer.name()  # noqa: E501

        text, ok = QInputDialog.getText(
            self.iface.mainWindow(),
            tr("Carica Layer su Nextcloud"),
            tr("Inserisci il percorso remoto in Nextcloud (creerà la cartella se non esiste):"),  # noqa: E501
            text=default_dest
        )
        if not ok or not text.strip():
            return

        target_dir = text.strip()
        files_to_sync = []
        name = os.path.basename(src_file)
        ext = os.path.splitext(name)[1].lower()

        import tempfile
        temp_dir = tempfile.gettempdir()

        # 1. Esporta sempre anche un QML sidecar per massima retrocompatibilità
        qml_path = os.path.join(temp_dir, f"{layer.name()}_style.qml")
        layer.saveNamedStyle(qml_path)
        files_to_sync.append((qml_path, f"{layer.name()}.qml"))

        # 2. Gestione file vettoriale (GPKG nativo vs Conversione)
        if ext == ".gpkg":
            # Sorgente già GeoPackage: salviamo lo stile nel DB esistente per
            # auto-embedding
            layer.saveStyleToDatabase("default", "", True, "")
            files_to_sync.append((src_file, name))
        else:
            # Non-GPKG (es. shp): converti on-the-fly in GeoPackage per il
            # Cloud
            from qgis.core import QgsVectorFileWriter, QgsProject, QgsVectorLayer  # noqa: E501
            target_name = os.path.splitext(name)[0] + ".gpkg"
            temp_gpkg = os.path.join(temp_dir, f"qgis_ledger_{target_name}")

            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "GPKG"
            options.layerName = layer.name()

            result = QgsVectorFileWriter.writeAsVectorFormatV3(
                layer, temp_gpkg, QgsProject.instance().transformContext(), options)  # noqa: E501
            err = result[0] if isinstance(result, tuple) else result

            if err == QgsVectorFileWriter.WriterError.NoError:
                # Carica il gpkg temporaneo per incorporare lo stile QML
                temp_lyr = QgsVectorLayer(
                    f"{temp_gpkg}|layername={
                        layer.name()}", layer.name(), "ogr")
                if temp_lyr.isValid():
                    temp_lyr.loadNamedStyle(qml_path)
                    temp_lyr.saveStyleToDatabase("default", "", True, "")

                files_to_sync.append((temp_gpkg, target_name))
            else:
                QMessageBox.warning(self.iface.mainWindow(), "QGIS Ledger", tr(
                    "Errore durante la conversione in GeoPackage: codice {err}").format(err=err))  # noqa: E501
                return

        def sync_task():
            from .ledger_nextcloud import NextcloudClient
            client = NextcloudClient(
                LedgerSettings.nextcloud_server(),
                LedgerSettings.nextcloud_user(),
                LedgerSettings.nextcloud_password(),
                LedgerSettings.nextcloud_folder(),
                verify_ssl=LedgerSettings.verify_ssl()
            )
            if target_dir:
                try:
                    client.make_directory(target_dir)
                except BaseException:
                    pass

            for local_p, remote_name in files_to_sync:
                if os.path.exists(local_p):
                    target_remote = (
                        target_dir + "/" + remote_name).lstrip("/")
                    client.upload(target_remote, local_p)

        from .ledger_nextcloud import _Worker
        from qgis.PyQt.QtCore import QThreadPool
        worker = _Worker(sync_task)
        self._act_status.setToolTip(tr("Upload Layer in corso..."))
        layer_name = layer.name()
        worker.signals.finished.connect(
            lambda res: QMessageBox.information(
                self.iface.mainWindow(),
                "QGIS Ledger",
                tr("Layer {} caricato su Cloud con successo!").format(layer_name)))  # noqa: E501
        worker.signals.error.connect(
            lambda err: QMessageBox.warning(
                self.iface.mainWindow(),
                "QGIS Ledger",
                tr("Errore durante l'upload: {}").format(err)))
        QThreadPool.globalInstance().start(worker)

    def _on_commit_project(self):
        """Commit the entire QGIS project."""
        if not QgsProject.instance().fileName():
            QMessageBox.warning(
                self.iface.mainWindow(), "QGIS Ledger",
                tr("Il progetto non è stato ancora salvato su disco.")
            )
            return
        if not self.ledger.is_connected():
            self.ledger.connect()

        dlg = _CommitDialog(
            tr("QGIS Ledger — Commit Progetto"),
            self.iface.mainWindow())
        if not dlg.exec():
            return

        message, sync_cloud = dlg.get_data()
        if not message:
            return

        user = LedgerSettings.user_name()

        # Chiedi conferma per autocommit + geopackage automatico
        reply = QMessageBox.question(
            self.iface.mainWindow(), tr("QGIS Ledger — Export Avanzato"),
            tr("Vuoi creare un unico commit del progetto e di tutti i layer, ed estrarlo "  # noqa: E501
               "subito in un GeoPackage portatile (con tutti gli URI aggiornati)?\n\n"  # noqa: E501
               "• 'Yes': Auto-Commit di tutti i vettori e salvataggio GeoPackage completo.\n"  # noqa: E501
               "• 'No': Commit del solo file di progetto (comportamento standard)."),  # noqa: E501
            getattr(
                getattr(
                    QMessageBox,
                    "StandardButton",
                    QMessageBox),
                "Yes") | getattr(
                getattr(
                    QMessageBox,
                    "StandardButton",
                    QMessageBox),
                "No")
        )

        if reply == getattr(
                getattr(QMessageBox, "StandardButton", QMessageBox), "Yes"):
            # Auto-commit layer vettoriali
            committed = 0
            for lid, layer in QgsProject.instance().mapLayers().items():
                if isinstance(layer, QgsVectorLayer):
                    cid = self.ledger.create_commit(
                        layer, f"[AUTO] {message.strip()}", user)
                    if cid > 0:
                        committed += 1

        commit_id = self.ledger.create_project_commit(message.strip(), user)
        info = self.ledger.get_commit_info(commit_id)

        if commit_id > 0:
            self._capture_screenshot(commit_id)

            if reply == getattr(
                    getattr(QMessageBox, "StandardButton", QMessageBox), "Yes"):  # noqa: E501
                from qgis.PyQt.QtWidgets import QFileDialog
                out, _ = QFileDialog.getSaveFileName(
                    self.iface.mainWindow(), tr("Estrai Progetto Self-Contained in GeoPackage"),  # noqa: E501
                    f"Progetto_v{commit_id}.gpkg", "GeoPackage (*.gpkg)"
                )
                if out:
                    self.export_project_to_gpkg(
                        commit_id, info['timestamp'], out, parent_widget=self.iface.mainWindow())  # noqa: E501
            else:
                QMessageBox.information(self.iface.mainWindow(), tr("QGIS Ledger — Commit Progetto ✅"), tr(  # noqa: E501
                    "Commit Progetto #{} salvato con successo!\nL'intero progetto .qgz è stato archiviato nello storico.\nUtente: {}\n\n💡 Ricorda: salva il progetto QGIS (Ctrl+S) per consolidare le modifiche.").format(commit_id, user))  # noqa: E501
            self._set_status(self.SYNCED)
            self.timeline_panel.populate_layers()
            if sync_cloud:
                self._trigger_cloud_sync(commit_id)
        else:
            QMessageBox.critical(
                self.iface.mainWindow(), "QGIS Ledger",
                tr("Errore durante il salvataggio del progetto.")
            )

    def export_project_to_gpkg(
            self,
            cid: int,
            proj_ts: str,
            out: str,
            parent_widget=None):
        """Estrae un progetto dal ledger e lo trasforma in un GeoPackage auto-contenuto e portabile."""  # noqa: E501
        import shutil
        import os
        import tempfile as _tempfile
        from qgis.core import (
            QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
            QgsVectorFileWriter, QgsWkbTypes, Qgis as QGIS
        )
        import sqlite3

        if not parent_widget:
            parent_widget = self.iface.mainWindow()

        src = os.path.join(
            self.ledger.history_dir(),
            "project",
            f"commit_{cid}.qgz")
        if not os.path.exists(src):
            QMessageBox.warning(parent_widget, "QGIS Ledger", tr(
                "File di progetto storicizzato non trovato."))
            return

        out_dir = os.path.dirname(out)

        # Leggi il progetto storico in un'istanza separata
        temp_proj = QgsProject()
        if not temp_proj.read(src):
            QMessageBox.critical(parent_widget, "QGIS Ledger", tr(
                "Errore durante la lettura del progetto storicizzato."))
            return

        # Crea il GPKG container come file vuoto
        conn = sqlite3.connect(out)
        conn.close()

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer  # noqa: E501

        layers = temp_proj.mapLayers()
        errors = []

        for lid, layer in list(layers.items()):
            # ── LAYER VETTORIALE ─────
            if layer.type() == layer.VectorLayer:
                snap = None
                style_qml = None
                hist = self.ledger.get_history(layer.name())
                past = [c for c in hist if c['timestamp'] <= proj_ts]
                if past:
                    layer_commit_rec = past[0]
                    snap = self.ledger.get_snapshot_features(
                        layer_commit_rec['id'])
                    style_qml = layer_commit_rec.get('style_qml')

                if not snap:
                    live_layer = None
                    for _lid, _l in QgsProject.instance().mapLayers().items():
                        if _l.name() == layer.name() and _l.type() == _l.VectorLayer:  # noqa: E501
                            live_layer = _l
                            break
                    if live_layer and live_layer.isValid():
                        feats_live = [
                            QgsFeature(f) for f in live_layer.getFeatures()]
                        snap = [
                            {
                                'geometry': f.geometry().asWkt() if f.hasGeometry() else None,  # noqa: E501
                                'attributes': {
                                    live_layer.fields().field(i).name(): f.attribute(i)  # noqa: E501
                                    for i in range(live_layer.fields().count())
                                }
                            }
                            for f in feats_live
                        ]
                        layer_ref = live_layer
                    else:
                        errors.append(
                            f"Layer '{
                                layer.name()}': nussuno snapshot nel DB e non trovato nel progetto corrente.")  # noqa: E501
                        continue
                else:
                    layer_ref = layer

                geom_type_str = "None"
                for item in snap:
                    if item.get('geometry'):
                        wkb = QgsGeometry.fromWkt(item['geometry']).wkbType()
                        if QgsWkbTypes.geometryType(
                                wkb) == QgsWkbTypes.GeometryType.PointGeometry:
                            geom_type_str = "Point"
                        elif QgsWkbTypes.geometryType(wkb) == QgsWkbTypes.GeometryType.LineGeometry:  # noqa: E501
                            geom_type_str = "LineString"
                        else:
                            geom_type_str = "Polygon"
                        break

                crs_id = layer_ref.crs().authid() or 'EPSG:4326'
                mem_vl = QgsVectorLayer(
                    f"{geom_type_str}?crs={crs_id}", layer.name(), "memory")
                mem_pr = mem_vl.dataProvider()
                mem_pr.addAttributes(layer_ref.fields())
                mem_vl.updateFields()

                feats = []
                for item in snap:
                    feat = QgsFeature(mem_vl.fields())
                    if item.get('geometry'):
                        feat.setGeometry(QgsGeometry.fromWkt(item['geometry']))
                    for fname, val in item.get('attributes', {}).items():
                        idx = mem_vl.fields().lookupField(fname)
                        if idx >= 0:
                            feat.setAttribute(idx, val)
                    feats.append(feat)
                mem_pr.addFeatures(feats)

                options.layerName = layer.name()
                QgsVectorFileWriter.writeAsVectorFormatV3(
                    mem_vl, out, temp_proj.transformContext(), options)

                new_uri = f"{out}|layername={layer.name()}"
                layer.setDataSource(new_uri, layer.name(), "ogr")

                if style_qml:
                    tmp = _tempfile.NamedTemporaryFile(
                        suffix=".qml", mode="w", encoding="utf-8", delete=False)  # noqa: E501
                    tmp.write(style_qml)
                    tmp.close()
                    layer.loadNamedStyle(tmp.name)
                    os.remove(tmp.name)

            # ── LAYER RASTER ─────
            elif layer.type() == layer.RasterLayer:
                raster_copied = False
                hist = self.ledger.get_history(layer.name())
                past = [c for c in hist if c['timestamp'] <= proj_ts]
                if past:
                    layer_commit_rec = past[0]
                    fp = layer_commit_rec.get('file_path')
                    if fp:
                        src_raster = os.path.join(
                            self.ledger.history_dir(), "raster", fp)
                        if os.path.exists(src_raster):
                            ext = os.path.splitext(src_raster)[1]
                            raster_name = f"{
                                layer.name()}_v{
                                layer_commit_rec['id']}{ext}"
                            dest_raster = os.path.join(out_dir, raster_name)
                            shutil.copy2(src_raster, dest_raster)
                            layer.setDataSource(
                                dest_raster, layer.name(), layer.providerType())  # noqa: E501
                            raster_copied = True
                            if layer_commit_rec.get('style_qml'):
                                tmp = _tempfile.NamedTemporaryFile(
                                    suffix=".qml", mode="w", encoding="utf-8", delete=False)  # noqa: E501
                                tmp.write(layer_commit_rec['style_qml'])
                                tmp.close()
                                layer.loadNamedStyle(tmp.name)
                                os.remove(tmp.name)

                if not raster_copied:
                    src_raster = layer.source()
                    if os.path.isfile(src_raster):
                        ext = os.path.splitext(src_raster)[1]
                        raster_name = f"{layer.name()}{ext}"
                        dest_raster = os.path.join(out_dir, raster_name)
                        shutil.copy2(src_raster, dest_raster)
                        layer.setDataSource(
                            dest_raster, layer.name(), layer.providerType())
                    else:
                        errors.append(
                            f"Raster '{
                                layer.name()}': file originale non trovato e nessuno snapshot disponibile.")  # noqa: E501

        try:
            temp_proj.setFilePathStorage(QGIS.FilePathType.Relative)
        except AttributeError:
            pass

        out_uri = f"geopackage:{out}?projectName=Storico_v{cid}"
        if temp_proj.write(out_uri):
            msg = (
                f"Progetto self-contained esportato con successo!\n(Commit #{cid}):\n{out}\n\n"  # noqa: E501
                f"💡 Per aprirlo: Progetto › Apri Da › GeoPackage, oppure trascinalo in QGIS."  # noqa: E501
            )
            if errors:
                msg += "\n\n⚠️ Avvisi (layer non incorporati):\n" + \
                    "\n".join(f"• {e}" for e in errors)
            QMessageBox.information(
                parent_widget, "QGIS Ledger — Estrazione Progetto ✅", msg)
        else:
            QMessageBox.critical(parent_widget, "QGIS Ledger", tr(
                "Errore nel salvataggio del progetto nel GeoPackage."))

    def _capture_screenshot(self, commit_id: int):
        """Saves a screenshot of the current map canvas."""
        canvas = self.iface.mapCanvas()
        if not canvas:
            return
        try:
            folder = os.path.join(self.ledger.history_dir(), "screenshots")
            os.makedirs(folder, exist_ok=True)

            info = self.ledger.get_commit_info(commit_id)
            if info:
                msg = info.get("message", "")
                ts = info.get("timestamp", "").replace(
                    ":", "-").replace(" ", "_").replace("T", "_")
                usr = info.get("user_name", "user")

                import re
                safe_msg = re.sub(r'[^\w\-_]', '_', msg)[:30].strip('_')
                if "[AUTO" in msg:
                    fname = f"autocommit_{commit_id}_{ts}_{usr}.png"
                else:
                    fname = f"commit_{commit_id}_{safe_msg}_{ts}_{usr}.png"
            else:
                fname = f"commit_{commit_id}.png"

            path = os.path.join(folder, fname)
            canvas.saveAsImage(path)
        except Exception:  # nosec B110
            pass

    def _on_preview(self, commit_id: int):
        """Enter read-only preview of a specific commit version."""
        info = self.ledger.get_commit_info(commit_id)
        if not info or info.get("commit_type") != "VECTOR":
            return

        layer_name = info["layer_name"]
        # Find the layer in the project
        target = None
        for lid, layer in QgsProject.instance().mapLayers().items():
            if isinstance(
                    layer,
                    QgsVectorLayer) and layer.name() == layer_name:
                target = layer
                break

        if not target:
            QMessageBox.warning(
                self.iface.mainWindow(), "QGIS Ledger",
                tr("Layer '{}' non trovato nel progetto.").format(layer_name)
            )
            return

        reply = QMessageBox.question(
            self.iface.mainWindow(),
            tr("QGIS Ledger — Preview"),
            tr("Entrare in modalità preview del commit #{commit_id}?\n({info_time} di {info_user})\n\nIl layer verrà ripristinato temporaneamente.\nUsa Rollback per confermare, o Ctrl+Z per annullare.").format(  # noqa: E501
                commit_id=commit_id,
                info_time=info["timestamp"],
                info_user=info["user_name"]),
            getattr(
                getattr(
                    QMessageBox,
                    "StandardButton",
                    QMessageBox),
                "Yes") | getattr(
                getattr(
                    QMessageBox,
                    "StandardButton",
                    QMessageBox),
                "No"),
        )
        if reply != getattr(
                getattr(QMessageBox, "StandardButton", QMessageBox), "Yes"):
            return

        # Perform a temporary rollback (user can undo with Ctrl+Z)
        target.startEditing()
        success = self.ledger.rollback_to(target, commit_id)
        if success:
            self._preview_mode = True
            self.iface.messageBar().pushInfo(
                "QGIS Ledger",
                f"Preview del commit #{commit_id}. "
                f"Premi 'Annulla modifiche' per tornare allo stato attuale."
            )

    def _on_rollback(self, commit_id: int):
        """Rollback the layer or project to a specific commit."""
        info = self.ledger.get_commit_info(commit_id)
        if not info:
            return

        if info.get("commit_type") == "PROJECT":
            reply = QMessageBox.warning(
                self.iface.mainWindow(),
                tr("QGIS Ledger — Rollback Progetto"),
                tr("\u26A0 ATTENZIONE: Stai per ripristinare l'intero Progetto QGIS al commit #{commit_id}\n({info_time} di {info_user})\n\nQuesto sovrascriverà il file .qgz corrente e ricaricherà il progetto.\nVuoi procedere?").format(  # noqa: E501
                    commit_id=commit_id,
                    info_time=info["timestamp"],
                    info_user=info["user_name"]),
                getattr(
                    getattr(
                        QMessageBox,
                        "StandardButton",
                        QMessageBox),
                    "Yes") | getattr(
                    getattr(
                        QMessageBox,
                        "StandardButton",
                        QMessageBox),
                    "No"),
                getattr(
                    getattr(
                        QMessageBox,
                        "StandardButton",
                        QMessageBox),
                    "No"),
            )
            if reply != getattr(
                    getattr(QMessageBox, "StandardButton", QMessageBox), "Yes"):  # noqa: E501
                return

            safety_msg = tr(
                "[AUTO] Backup prima di rollback al commit #{}").format(commit_id)  # noqa: E501
            self.ledger.create_project_commit(
                safety_msg, LedgerSettings.user_name())

            success = self.ledger.rollback_to(None, commit_id)
            if success:
                QMessageBox.information(self.iface.mainWindow(), "QGIS Ledger", tr(  # noqa: E501
                    "Rollback del Progetto completato con successo!\nIl progetto è stato ricaricato allo stato del commit #{}.").format(commit_id))  # noqa: E501
            else:
                QMessageBox.critical(
                    self.iface.mainWindow(),
                    "QGIS Ledger",
                    tr("Errore durante il rollback del progetto."))
            return

        layer_name = info["layer_name"]
        target = None
        for lid, layer in QgsProject.instance().mapLayers().items():
            if layer.name() == layer_name:  # Handle both Vector and Raster
                target = layer
                break

        if not target:
            # Attempt auto-restore if file_path is known
            known_path = info.get("file_path")
            clean_path = known_path

            if known_path:
                # Handle GeoPackage/SQLite URIs (e.g.
                # path/to.gpkg|layername=my_layer)
                if "|" in known_path:
                    clean_path = known_path.split("|")[0]

                # For Rasters, known_path historically held just the backup
                # filename
                if info.get("commit_type") == "RASTER" and not os.path.isabs(
                        known_path):
                    clean_path = os.path.join(
                        self.ledger.history_dir(), "raster", known_path)
                    known_path = clean_path  # Load directly from backup if original is missing  # noqa: E501

            if known_path and os.path.exists(clean_path):
                if info.get("commit_type") == "RASTER":
                    target = self.iface.addRasterLayer(known_path, layer_name)
                else:
                    target = self.iface.addVectorLayer(
                        known_path, layer_name, "ogr")

            # Fallback to manual restore if auto-restore fails
            if not target or not target.isValid():
                target = None
                display_path = known_path if known_path else 'Sconosciuto'
                reply = QMessageBox.question(
                    self.iface.mainWindow(),
                    "QGIS Ledger",
                    tr("Il layer '{}' non è presente e non è stato possibile ripristinarlo automaticamente in:\n{}\nVuoi cercarlo manualmente sul disco?").format(  # noqa: E501
                        layer_name,
                        display_path),
                    getattr(getattr(QMessageBox, "StandardButton", QMessageBox), "Yes") | getattr(getattr(QMessageBox, "StandardButton", QMessageBox), "No"))  # noqa: E501
                if reply == getattr(
                        getattr(QMessageBox, "StandardButton", QMessageBox), "Yes"):  # noqa: E501
                    file_path, _ = QFileDialog.getOpenFileName(
                        self.iface.mainWindow(
                        ), f"Seleziona il file sorgente per il layer '{layer_name}'",  # noqa: E501
                        QgsProject.instance().homePath(
                        ), "Dati Geografici (*.gpkg *.shp *.tif *.geojson);;Tutti i file (*)"  # noqa: E501
                    )
                    if file_path:
                        if info.get("commit_type") == "RASTER":
                            target = self.iface.addRasterLayer(
                                file_path, layer_name)
                        else:
                            target = self.iface.addVectorLayer(
                                file_path, layer_name, "ogr")

                        if not target or not target.isValid():
                            QMessageBox.warning(
                                self.iface.mainWindow(),
                                "QGIS Ledger",
                                tr("Impossibile caricare il layer selezionato."))  # noqa: E501
                            return
                    else:
                        return
                else:
                    return

        reply = QMessageBox.warning(
            self.iface.mainWindow(),
            tr("QGIS Ledger — Rollback"),
            tr("\u26A0 ATTENZIONE: Stai per ripristinare il layer '{layer_name}' al commit #{commit_id}\n({info_time} di {info_user})\n\nQuesta operazione sovrascriverà tutte le feature attuali.\nVuoi procedere?").format(  # noqa: E501
                layer_name=layer_name,
                commit_id=commit_id,
                info_time=info["timestamp"],
                info_user=info["user_name"]),
            getattr(
                getattr(
                    QMessageBox,
                    "StandardButton",
                    QMessageBox),
                "Yes") | getattr(
                getattr(
                    QMessageBox,
                    "StandardButton",
                    QMessageBox),
                "No"),
            getattr(getattr(QMessageBox, "StandardButton", QMessageBox), "No"),
        )
        if reply != getattr(
                getattr(QMessageBox, "StandardButton", QMessageBox), "Yes"):
            return

        # First create a safety commit of current state
        safety_msg = tr(
            "[AUTO] Backup prima di rollback al commit #{}").format(commit_id)
        if info.get("commit_type") == "RASTER":
            self.ledger.create_raster_commit(
                target, safety_msg, LedgerSettings.user_name())
        else:
            self.ledger.create_commit(
                target, safety_msg, LedgerSettings.user_name())

        success = self.ledger.rollback_to(target, commit_id)
        if success:
            # Create a new commit for the rollback state
            rollback_msg = tr("Rollback al commit #{}").format(commit_id)
            if info.get("commit_type") == "RASTER":
                self.ledger.create_raster_commit(
                    target, rollback_msg, LedgerSettings.user_name())
            else:
                self.ledger.create_commit(
                    target, rollback_msg, LedgerSettings.user_name())

            QMessageBox.information(
                self.iface.mainWindow(),
                tr("QGIS Ledger — Rollback Completato ✅"),
                tr("Rollback completato con successo!\nIl layer '{layer_name}' è stato ripristinato allo stato del commit #{commit_id}.\n\n⚠️ IMPORTANTE: Salva il progetto QGIS ora (Ctrl+S) per rendere permanente il ripristino!").format(  # noqa: E501
                    layer_name=layer_name,
                    commit_id=commit_id))
            self.timeline_panel.refresh()
        else:
            QMessageBox.critical(
                self.iface.mainWindow(), "QGIS Ledger",
                tr("Errore durante il rollback.")
            )

    def _on_diff_from_commit(self, commit_id: int):
        """Show diff between a commit and the current layer state."""
        info = self.ledger.get_commit_info(commit_id)
        if not info or info.get("commit_type") != "VECTOR":
            return

        # Find latest commit for same layer
        history = self.ledger.get_history(info["layer_name"])
        if len(history) < 2:
            QMessageBox.information(
                self.iface.mainWindow(), "QGIS Ledger",
                tr("Serve almeno 2 commit per calcolare il diff.")
            )
            return

        latest = history[0]["id"]
        if latest == commit_id and len(history) > 1:
            latest = history[1]["id"]

        old_id = min(commit_id, latest)
        new_id = max(commit_id, latest)

        added, removed, modified = self.diff_engine.compute_diff(
            old_id, new_id, info["layer_name"]
        )

        dlg = _DiffResultDialog(
            old_id, new_id, info["layer_name"], added, removed, modified,
            self.ledger, self.iface.mainWindow()
        )
        dlg.exec()
        self.timeline_panel.refresh()

    def _on_diff_dialog(self):
        """Open a dialog to select two commits for visual diff."""
        if not self.ledger.is_connected():
            QMessageBox.warning(
                self.iface.mainWindow(), "QGIS Ledger",
                tr("Nessun database di QGIS Ledger aperto.")
            )
            return

        history = self.ledger.get_history()
        if len(history) < 2:
            QMessageBox.information(
                self.iface.mainWindow(), "QGIS Ledger",
                tr("Serve almeno 2 commit per calcolare il diff.")
            )
            return

        dlg = _DiffDialog(history, self.iface.mainWindow())
        if dlg.exec() == getattr(getattr(QDialog, "DialogCode", QDialog), "Accepted"):  # noqa: E501
            old_id, new_id = dlg.get_selection()
            if old_id and new_id and old_id != new_id:
                self.diff_engine.clear_diff()
                added, removed, modified = self.diff_engine.compute_diff(
                    min(old_id, new_id), max(old_id, new_id)
                )
                layer_name = self.ledger.get_commit_info(
                    old_id).get("layer_name", tr("Sconosciuto"))
                res_dlg = _DiffResultDialog(
                    min(old_id, new_id), max(old_id, new_id), layer_name,
                    added, removed, modified, self.ledger, self.iface.mainWindow()  # noqa: E501
                )
                res_dlg.exec()
                self.timeline_panel.refresh()

    def _toggle_timeline(self, checked: bool):
        if self.timeline_panel:
            if checked:
                self.timeline_panel.show()
                self.timeline_panel.populate_layers()
            else:
                self.timeline_panel.hide()

    def _on_browser_dialog(self):
        """Open the complete history browser for extracting files."""
        if not self.ledger.is_connected():
            QMessageBox.information(
                self.iface.mainWindow(),
                "QGIS Ledger",
                tr("Nessun registro attivo in questo progetto.")
            )
            return

        dlg = _HistoryBrowserDialog(self, self.ledger, self.iface.mainWindow())
        dlg.exec()

    def _on_settings(self):
        info_tabs = self.get_info_widget()
        # Aggiungi la scheda Help dinamica
        info_tabs.addTab(self._create_help_widget(), "❓ " + tr("Help"))

        dlg = SettingsDialog(info_tabs, self.iface.mainWindow())
        dlg.exec()
        self.retranslateUi()

    def get_info_widget(self):
        """Return a QTabWidget containing Info and Activity tabs to embed in Settings."""  # noqa: E501
        # Read metadata.txt from the plugin directory
        plugin_dir = os.path.dirname(os.path.abspath(__file__))
        meta_path = os.path.join(plugin_dir, "metadata.txt")

        name = "QGIS Ledger"
        version = "N/A"
        author = "N/A"
        email = ""
        homepage = ""
        description = ""

        if os.path.exists(meta_path):
            cfg = configparser.ConfigParser()
            cfg.read(meta_path, encoding="utf-8")
            if cfg.has_section("general"):
                name = cfg.get(
                    "general",
                    "name",
                    fallback=name).replace(
                    "_",
                    " ")
                version = cfg.get("general", "version", fallback=version)
                author = cfg.get("general", "author", fallback=author)
                email = cfg.get("general", "email", fallback=email)
                homepage = cfg.get("general", "homepage", fallback=homepage)
                description = cfg.get(
                    "general", "description", fallback=description)

        # Build rich HTML content
        plugin_logo_path = os.path.join(plugin_dir, "logoplugin.jpg")
        plugin_logo_url = f"file:///{
            os.path.abspath(plugin_logo_path).replace(
                os.sep, '/')}"

        author_logo_path = os.path.join(plugin_dir, "sinocloud-logo.png")
        author_logo_url = f"file:///{
            os.path.abspath(author_logo_path).replace(
                os.sep, '/')}"

        info_html = (
            f'<div style="text-align:center;padding:10px;">'
            f'<img src="{plugin_logo_url}" width="140" style="margin-bottom:10px; border-radius: 6px;"/><br>'  # noqa: E501
            f'<h2 style="color:#5b9bd5;margin-bottom:2px;">\U0001F6E1\uFE0F {name}</h2>'  # noqa: E501
            f'<p style="color:#8a97a5;font-size:12px;margin-top:0;">'
            f'Intelligent Versioning for QGIS</p>'
            f'<hr style="border:1px solid #22303e;"/>'
            f'<table style="margin:auto;font-size:13px;">'
            f'<tr><td style="padding:4px 12px;color:#c3ccd6;"><b>Versione:</b></td>'  # noqa: E501
            f'<td style="padding:4px 12px;color:#2ecc71;font-weight:bold;">{version}</td></tr>'  # noqa: E501
            f'<tr><td style="padding:4px 12px;color:#c3ccd6;"><b>Autore:</b></td>'  # noqa: E501
            f'<td style="padding:4px 12px;color:#f2f5f8;">'
            f'<img src="{author_logo_url}" height="18" style="vertical-align:middle; margin-right:6px;"/>{author}</td></tr>'  # noqa: E501
        )
        if email:
            info_html += (
                f'<tr><td style="padding:4px 12px;color:#c3ccd6;"><b>Email:</b></td>'  # noqa: E501
                f'<td style="padding:4px 12px;"><a href="mailto:{email}" '
                f'style="color:#5b9bd5;">{email}</a></td></tr>'
            )
        if homepage:
            info_html += (
                f'<tr><td style="padding:4px 12px;color:#c3ccd6;"><b>Sito Web:</b></td>'  # noqa: E501
                f'<td style="padding:4px 12px;"><a href="{homepage}" '
                f'style="color:#5b9bd5;">{homepage}</a></td></tr>'
            )

        db_path = self.ledger.db_path()
        db_size_str = tr("Sconosciuto")
        if db_path and os.path.exists(db_path):
            size_mb = os.path.getsize(db_path) / (1024 * 1024)
            db_size_str = f"{size_mb:.2f} MB"

        info_html += (
            f'<tr><td style="padding:4px 12px;color:#c3ccd6;"><b>DB Size:</b></td>'  # noqa: E501
            f'<td style="padding:4px 12px;color:#f2f5f8;">{db_size_str}</td></tr>'  # noqa: E501
        )

        info_html += (
            f'</table>'
            f'<hr style="border:1px solid #22303e;"/>'
            f'<p style="color:#c3ccd6;font-size:11px;padding:4px 16px;">{description}</p>'  # noqa: E501
            f'</div>'
        )

        tabs = QTabWidget()
        tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #22303e; background: #141a22; }"  # noqa: E501
            "QTabBar::tab { background: #22303e; color: #f2f5f8; padding: 6px 12px; margin-right: 2px; border-top-left-radius: 4px; border-top-right-radius: 4px; }"  # noqa: E501
            "QTabBar::tab:selected { background: #5b9bd5; font-weight: bold; }"
            "QTabBar::tab:hover { background: #3f6f9e; }")

        # Tab 1: Info
        tab_info = QWidget()
        lay_info = QVBoxLayout(tab_info)
        lbl = QLabel(info_html)
        lbl.setOpenExternalLinks(True)
        lbl.setWordWrap(True)
        lay_info.addWidget(lbl)

        btn_tutorial = QPushButton(tr("▶ Guarda Video Tutorial"))
        btn_tutorial.setStyleSheet(
            "QPushButton{background:#8e44ad;color:white;border:none;"
            "border-radius:4px;padding:6px;font-weight:bold;margin:4px 16px;}"
            "QPushButton:hover{background:#9b59b6;}"
        )

        def open_tut():
            from qgis.PyQt.QtGui import QDesktopServices
            from qgis.PyQt.QtCore import QUrl
            QDesktopServices.openUrl(
                QUrl("https://mega.nz/embed/1vdnCayB#Ep91QMDOu4HBw5PdL8fm9ug87PztME-eBQ1_hNWsN08!1a"))  # noqa: E501
        btn_tutorial.clicked.connect(open_tut)
        lay_info.addWidget(btn_tutorial)

        btn_screens = QPushButton(tr("📂 Apri Cartella Screenshot"))
        btn_screens.setStyleSheet(
            "QPushButton{background:#e67e22;color:white;border:none;"
            "border-radius:4px;padding:6px;font-weight:bold;margin:4px 16px;}"
            "QPushButton:hover{background:#d35400;}"
        )

        def _open_screens():
            import platform
            import subprocess  # nosec B404 - apre solo il file manager
            if not self.ledger.is_connected():
                QMessageBox.warning(
                    self.iface.mainWindow(),
                    "QGIS Ledger",
                    tr("Nessun progetto aperto."))
                return
            s_dir = os.path.join(self.ledger.history_dir(), "screenshots")
            if not os.path.exists(s_dir):
                os.makedirs(s_dir, exist_ok=True)
            # Percorso locale generato dal plugin, nessun input utente
            if platform.system() == "Windows":
                os.startfile(s_dir)  # nosec B606
            elif platform.system() == "Darwin":
                subprocess.Popen(["open", s_dir])  # nosec B603 B607
            else:
                subprocess.Popen(["xdg-open", s_dir])  # nosec B603 B607

        btn_screens.clicked.connect(_open_screens)
        lay_info.addWidget(btn_screens)

        # Drop-down with the author's other plugins (shared hub).
        from . import plugin_hub
        from .ledger_i18n import current_language
        fam_lang = "en" if current_language() != "it" else "it"
        lay_info.addWidget(
            plugin_hub.make_family_widget("qgis_ledger", lang=fam_lang)
        )

        tabs.addTab(tab_info, "\u2139\uFE0F Info Plugin")

        # Tab 2: Attività (Alerts)
        tab_activity = QWidget()
        lay_act = QVBoxLayout(tab_activity)

        if not self.ledger.is_connected():
            lbl_conn = QLabel(
                tr("⚠️ Database chiuso. Apri/salva il progetto per vedere l'attività."))  # noqa: E501
            lbl_conn.setAlignment(
                getattr(
                    getattr(
                        Qt,
                        "AlignmentFlag",
                        Qt),
                    "AlignCenter"))
            lay_act.addWidget(lbl_conn)
        else:
            history = self.ledger.get_history()
            me = LedgerSettings.user_name()
            my_machine = platform.node() if hasattr(platform, 'node') else ""

            others_commits = [
                c for c in history if c["user_name"] != me or (
                    my_machine and c.get(
                        "machine", "") != my_machine)]

            if not others_commits:
                lbl_no_act = QLabel(
                    tr("Nessuna modifica recente da altri mod_user o postazioni."))  # noqa: E501
                lbl_no_act.setAlignment(
                    getattr(
                        getattr(
                            Qt,
                            "AlignmentFlag",
                            Qt),
                        "AlignCenter"))
                lbl_no_act.setStyleSheet("color: #8a97a5; font-style: italic;")
                lay_act.addWidget(lbl_no_act)
            else:
                lbl_act_title = QLabel(
                    tr("Trovate {} modifiche da mod_user/altre postazioni:").format(len(others_commits)))  # noqa: E501
                lbl_act_title.setStyleSheet(
                    "font-weight: bold; margin-bottom: 5px;")
                lay_act.addWidget(lbl_act_title)

                table = QTableWidget(len(others_commits), 4)
                table.setHorizontalHeaderLabels(
                    [tr("Data"), tr("Utente"), tr("Postazione"), tr("Layer modified")])  # noqa: E501
                table.horizontalHeader().setSectionResizeMode(
                    getattr(getattr(QHeaderView, "ResizeMode", QHeaderView), "ResizeToContents"))  # noqa: E501
                table.horizontalHeader().setSectionResizeMode(3, getattr(
                    getattr(QHeaderView, "ResizeMode", QHeaderView), "Stretch"))  # noqa: E501
                table.setEditTriggers(
                    getattr(
                        getattr(
                            QTableWidget,
                            "EditTrigger",
                            QTableWidget),
                        "NoEditTriggers"))
                table.setSelectionBehavior(
                    getattr(
                        getattr(
                            QTableWidget,
                            "SelectionBehavior",
                            QTableWidget),
                        "SelectRows"))
                table.setStyleSheet(
                    "QTableWidget { background: #22303e; color: #f2f5f8; border: none; gridline-color: #141a22; }"  # noqa: E501
                    "QHeaderView::section { background: #3f6f9e; color: white; padding: 4px; border: 1px solid #141a22; font-weight: bold; }")  # noqa: E501

                for r, c in enumerate(others_commits):
                    # date format YYYY-MM-DD HH:MM
                    date_str = c["timestamp"][:16].replace("T", " ")
                    item_date = QTableWidgetItem(date_str)
                    item_user = QTableWidgetItem(c["user_name"])
                    item_mach = QTableWidgetItem(
                        c.get("machine", tr("Sconosciuto")))
                    item_layer = QTableWidgetItem(c["layer_name"])

                    table.setItem(r, 0, item_date)
                    table.setItem(r, 1, item_user)
                    table.setItem(r, 2, item_mach)
                    table.setItem(r, 3, item_layer)

                lay_act.addWidget(table)

        tabs.addTab(tab_activity, tr("🔔 Notifiche mod_user"))

        return tabs

    def _on_sync(self):
        """Check for external changes to the database."""
        if not self.ledger.is_connected():
            QMessageBox.warning(
                self.iface.mainWindow(), "QGIS Ledger",
                tr("Nessun database di QGIS Ledger aperto.")
            )
            return

        if self.sync.check_for_updates():
            self._set_status(self.MODIFIED)
            QMessageBox.information(self.iface.mainWindow(), "QGIS Ledger", tr(
                "Modifiche esterne rilevate nel database.\nLa timeline è stata aggiornata."))  # noqa: E501
            self.timeline_panel.refresh()
        else:
            self.iface.messageBar().pushInfo(
                "QGIS Ledger", tr("Nessuna modifica esterna rilevata.")
            )

    def _on_command_center(self):
        """Open (or focus) the Command Center: every command as a button."""
        dlg = getattr(self, "_cmd_center", None)
        if dlg is None:
            dlg = LedgerCommandCenter(self, self.iface.mainWindow())
            self._cmd_center = dlg
        else:
            # Refresh labels in case the language changed meanwhile.
            dlg.retranslate()
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _apply_toolbar_mode(self):
        """Show/hide toolbar buttons according to the compact setting.

        Compact mode (default) keeps only the Command Center icon on the
        toolbar; every other command stays reachable from that window.
        """
        if getattr(self, "toolbar", None) is None:
            return
        compact = LedgerSettings.compact_toolbar()
        for act in self.toolbar.actions():
            if act is getattr(self, "_cmdcenter_action", None):
                act.setVisible(True)
            else:
                act.setVisible(not compact)

    def _set_toolbar_compact(self, compact: bool):
        """Persist the toolbar mode and apply it immediately."""
        LedgerSettings.set("compact_toolbar", "true" if compact else "false")
        self._apply_toolbar_mode()

    def _toggle_main_panel(self, checked: bool):
        """Show or hide the unified main panel (Timeline + Nextcloud)."""
        if getattr(self, 'main_panel', None) is None:
            return
        if checked:
            self.main_panel.show()
            self._on_tab_changed(self.tab_widget.currentIndex())
        else:
            self.main_panel.hide()

    def _on_tab_changed(self, index: int):
        """Trigger updates when switching between Timeline and Nextcloud."""
        if index == 0:  # Timeline
            if self.timeline_panel:
                self.timeline_panel.populate_layers()
        elif index == 1:  # Nextcloud
            if self.nextcloud_panel:
                self.nextcloud_panel.connect_nextcloud(
                    LedgerSettings.nextcloud_server(),
                    LedgerSettings.nextcloud_user(),
                    LedgerSettings.nextcloud_password(),
                    LedgerSettings.nextcloud_folder(),
                )

    def _on_led_clicked(self):
        """Toggle unified panel and show timeline when LED is clicked."""
        if self.main_panel:
            visible = self.main_panel.isVisible()
            self.main_panel.setVisible(not visible)
            if not visible:
                self.tab_widget.setCurrentIndex(0)  # Switch to Timeline
                self.timeline_panel.populate_layers()

    def _check_sync(self):
        """Periodic check for external database changes."""
        if self.sync.is_watching() and self.sync.check_for_updates():
            self._set_status(self.MODIFIED)

    def _toggle_autosave(self, checked: bool):
        """Start or stop the auto-save timer."""
        if checked:
            interval_min = LedgerSettings.autosave_interval()
            self._autosave_timer = QTimer()
            self._autosave_timer.timeout.connect(self._do_autosave)
            self._autosave_timer.start(interval_min * 60 * 1000)
            self.iface.messageBar().pushInfo("QGIS Ledger — Auto-Save ⏱️",
                                             f"Auto-Save attivato! Salvataggio automatico ogni {interval_min} minuti.")  # noqa: E501
        else:
            if self._autosave_timer:
                self._autosave_timer.stop()
                self._autosave_timer = None
            self.iface.messageBar().pushInfo(
                "QGIS Ledger — Auto-Save ⏱️",
                "Auto-Save disattivato."
            )

    def _do_autosave(self):
        """Timer callback: auto-commit all modified layers and save the project."""  # noqa: E501
        if not self.ledger.is_connected():
            return

        user = LedgerSettings.user_name()
        committed = 0

        # Auto-commit all vector layers
        for lid, layer in QgsProject.instance().mapLayers().items():
            if isinstance(layer, QgsVectorLayer):
                cid = self.ledger.create_commit(
                    layer,
                    "[AUTO-SAVE] Salvataggio automatico periodico",
                    user
                )
                if cid > 0:
                    self._capture_screenshot(cid)
                    committed += 1

        # Save QGIS project file
        QgsProject.instance().write()

        if committed > 0:
            self.iface.messageBar().pushInfo("QGIS Ledger — Auto-Save ⏱️ ✅",
                                             f"Auto-Save completato: {committed} layer committati e progetto salvato.")  # noqa: E501
            self._set_status(self.SYNCED)
            self.timeline_panel.populate_layers()
        else:
            self.iface.messageBar().pushInfo("QGIS Ledger — Auto-Save ⏱️",
                                             "Auto-Save completato: nessuna modifica rilevata. Progetto salvato.")  # noqa: E501

    def _create_help_widget(self):
        """Crea il widget della scheda Help per il dialogo Settings."""
        from qgis.PyQt.QtWidgets import QTextBrowser
        self.help_browser = QTextBrowser()
        self.help_browser.setOpenExternalLinks(True)
        self.help_browser.setHtml(self._get_help_html())
        return self.help_browser

    def _get_help_html(self):
        """Ritorna il contenuto HTML della scheda Help, tradotto in
        tutte le lingue."""
        from .ledger_settings import LedgerSettings
        lang = LedgerSettings.language()

        # Dizionario dei contenuti per lingua
        help_data = {
            "it": {
                "title": "🛡️ Guida Rapida QGIS Ledger",
                "intro": (
                    "QGIS Ledger è un sistema di versionamento Git-like per i "
                    "tuoi dati spaziali, progettato per garantire l'integrità "
                    "dei dati e la collaborazione senza dipendenze esterne."),
                "feat_title": "🚀 Funzionalità Principali:",
                "feat1": (
                    "Snapshot Atomici: Salva versioni (commit) dei tuoi layer "
                    "(vettoriali/raster) o dell'intero progetto in un "
                    "database SQLite locale."),
                "feat2": (
                    "Timeline Interattiva: Sfoglia la cronologia delle "
                    "modifiche, vedi chi ha fatto cosa e quando."),
                "feat3": (
                    "Rollback Deterministico: Ripristina istantaneamente una "
                    "versione precedente in caso di errori."),
                "feat4": (
                    "Visual Diff (Δ): Confronto geometrico tra due versioni "
                    "per evidenziare aggiunte, rimovioni e modifiche."),
                "feat5": (
                    "Cloud Sincronizzato: Supporto nativo per Nextcloud, "
                    "Dropbox, OneDrive e Google Drive per lavorare in team."),
                "start_title": "📖 Come iniziare:",
                "step1": (
                    "Apri/Salva: Assicurati che il progetto QGIS sia salvato "
                    "su disco."),
                "step2": (
                    "Commit (✔): Usa il pulsante nella toolbar per salvare "
                    "lo stato attuale di un layer."),
                "step3": (
                    "Timeline (🕘): Apri il pannello laterale per gestire le "
                    "versioni."),
                "step4": (
                    "Impostazioni (⚙): Configura il tuo nome utente e "
                    "l'archiviazione Cloud."),
                "video_btn": "▶ Guarda Video Tutorial",
                "footer": (
                    "Versione 3.9 per QGIS 4.0 e Qt6.")
            },
            "en": {
                "title": "🛡️ QGIS Ledger Quick Guide",
                "intro": (
                    "QGIS Ledger is a Git-like versioning system for your "
                    "spatial data, designed to ensure data integrity and "
                    "collaboration without external dependencies."),
                "feat_title": "🚀 Main Features:",
                "feat1": (
                    "Atomic Snapshots: Save versions (commits) of your layers "
                    "(vector/raster) or the entire project in a local "
                    "SQLite database."),
                "feat2": (
                    "Interactive Timeline: Browse the change history, see who "
                    "did what and when."),
                "feat3": (
                    "Deterministic Rollback: Instantly restore a previous "
                    "version in case of errors."),
                "feat4": (
                    "Visual Diff (Δ): Geometric comparison between two "
                    "versions to highlight additions, removals, and "
                    "modifications."),
                "feat5": (
                    "Cloud Sync: Native support for Nextcloud, Dropbox, "
                    "OneDrive, and Google Drive for teamwork."),
                "start_title": "📖 How to start:",
                "step1": (
                    "Open/Save: Ensure your QGIS project is saved to "
                    "disk."),
                "step2": (
                    "Commit (✔): Use the toolbar button to save the current "
                    "state of a layer."),
                "step3": (
                    "Timeline (🕘): Open the side panel to manage versions."),
                "step4": (
                    "Settings (⚙): Configure your username and Cloud "
                    "storage."),
                "video_btn": "▶ Watch Video Tutorial",
                "footer": "Version 3.9 for QGIS 4.0 and Qt6."
            },
            "fr": {
                "title": "🛡️ Guide Rapide QGIS Ledger",
                "intro": (
                    "QGIS Ledger est un système de versionnage de type Git "
                    "pour i vostri dati spaziali, progettato per garantire "
                    "l'integrità dei dati e la collaborazione senza "
                    "dipendenze esterne."),
                "feat_title": "🚀 Fonctionnalités Principales :",
                "feat1": (
                    "Instantanés Atomiques : Enregistrez des versions "
                    "(commits) de vos couches (vecteur/raster) ou de tout le "
                    "projet dans une base de données SQLite locale."),
                "feat2": (
                    "Timeline Interactive : Parcourez l'historique des "
                    "modifications, voyez qui ha fatto cosa e quando."),
                "feat3": (
                    "Rollback Déterministe : Restaurez instantanément une "
                    "version précédente en cas d'erreur."),
                "feat4": (
                    "Visual Diff (Δ) : Comparaison géométrique entre deux "
                    "versions pour mettre en évidence les ajouts, les "
                    "suppressions et les modifications."),
                "feat5": (
                    "Cloud Synchronisé : Support natif pour Nextcloud, "
                    "Dropbox, OneDrive et Google Drive pour travailler en "
                    "équipe."),
                "start_title": "📖 Comment commencer :",
                "step1": (
                    "Ouvrir/Sauvegarder : Assurez-vous que le progetto QGIS è "
                    "salvato su disco."),
                "step2": (
                    "Commit (✔) : Utilisez le bouton della toolbar per "
                    "salvare lo stato attuale di un layer."),
                "step3": (
                    "Timeline (🕘) : Ouvrez le panneau latéral per gestire "
                    "le versioni."),
                "step4": (
                    "Paramètres (⚙) : Configurez votre nom d'utilisateur et "
                    "l'archiviazione Cloud."),
                "video_btn": "▶ Regarder le tutoriel vidéo",
                "footer": "Version 3.9 pour QGIS 4.0 et Qt6."
            },
            "de": {
                "title": "🛡️ QGIS Ledger Kurzanleitung",
                "intro": (
                    "QGIS Ledger ist ein Git-ähnliches Versionierungssystem "
                    "für Ihre Geodaten, das die Datenteintegrität und "
                    "Zusammenarbeit ohne externe Abhängigkeiten "
                    "gewährleistet."),
                "feat_title": "🚀 Hauptmerkmale:",
                "feat1": (
                    "Atomare Snapshots: Speichern Sie Versionen (Commits) "
                    "Ihrer Layer (Vektor/Raster) oder des gesamten Projekts "
                    "in einer lokalen SQLite-Datenbank."),
                "feat2": (
                    "Interaktive Timeline: Durchsuchen Sie den "
                    "Änderungsverlauf, sehen Sie, wer was wann getan hat."),
                "feat3": (
                    "Deterministisches Rollback: Stellen Sie bei Fehlern "
                    "sofort eine vorherige Version wieder her."),
                "feat4": (
                    "Visueller Diff (Δ): Geometrischer Vergleich zwischen "
                    "zwei Versionen zur Hervorhebung von Ergänzungen, "
                    "Entfernungen und Änderungen."),
                "feat5": (
                    "Synchronisierte Cloud: Native Unterstützung für "
                    "Nextcloud, Dropbox, OneDrive und Google Drive für die "
                    "Teamarbeit."),
                "start_title": "📖 Erste Schritte:",
                "step1": (
                    "Öffnen/Speichern: Stellen Sie sicher, dass das "
                    "QGIS-Projekt auf der Festplatte gespeichert ist."),
                "step2": (
                    "Commit (✔): Verwenden Sie die Schaltfläche in der "
                    "Symbolleiste, um den aktuellen Status eines Layers "
                    "zu speichern."),
                "step3": (
                    "Timeline (🕘): Öffnen Sie die Seitenleiste, um "
                    "Versionen zu verwalten."),
                "step4": (
                    "Einstellungen (⚙): Konfigurieren Sie Ihren "
                    "Benutzernamen und den Cloud-Speicher."),
                "video_btn": "▶ Video-Tutorial ansehen",
                "footer": (
                    "Version 3.9 für QGIS 4.0 und Qt6.")
            },
            "pt-BR": {
                "title": "🛡️ Guia Rápido QGIS Ledger",
                "intro": (
                    "QGIS Ledger è um sistema de versionamento tipo Git para "
                    "seus dados espaciais, progettato per garantire a "
                    "integridade dei dati e la collaborazione senza "
                    "dipendenze esterne."),
                "feat_title": "🚀 Principais Funcionalidades:",
                "feat1": (
                    "Snapshots Atômicos: Salve versões (commits) de suas "
                    "camadas (vetor/raster) ou de todo o projeto em um "
                    "banco di dati SQLite local."),
                "feat2": (
                    "Timeline Interativa: Navegue pelo histórico de "
                    "alterações, veja quem fez o quê e quando."),
                "feat3": (
                    "Rollback Determinístico: Restaure instantaneamente una "
                    "versão anterior em caso de erros."),
                "feat4": (
                    "Visual Diff (Δ): Comparação geométrica entre duas "
                    "versões para destacar adições, remoções e modificações."),
                "feat5": (
                    "Nuvem Sincronizada: Suporte nativo para Nextcloud, "
                    "Dropbox, OneDrive e Google Drive para trabalho em "
                    "equipe."),
                "start_title": "📖 Como começar:",
                "step1": (
                    "Abrir/Salvar: Certifique-se de che o progetto QGIS "
                    "esteja salvo no disco."),
                "step2": (
                    "Commit (✔): Use o botão na barra de ferramentas per "
                    "salvare o stato attuale di uma camada."),
                "step3": (
                    "Timeline (🕘): Abra o painel lateral para gerenciar "
                    "as versioni."),
                "step4": (
                    "Configurações (⚙): Configure seu nome de usuário e "
                    "o armazenamento na nuvem."),
                "video_btn": "▶ Assistir ao Tutorial em Vídeo",
                "footer": "Versão 3.9 para QGIS 4.0 e Qt6."
            },
            "zh-SG": {
                "title": "🛡️ QGIS Ledger 快速指南",
                "intro": (
                    "QGIS Ledger 是一个类似于 Git 的空间数据版本控制系统，"
                    "旨在确保数据完整性和协作，无需外部依赖。"),
                "feat_title": "🚀 主要功能：",
                "feat1": (
                    "原子快照：在本地 SQLite 数据库中保存图层（矢量/栅格）"
                    "或整个项目的版本（提交）。"),
                "feat2": (
                    "交互式时间轴：浏览更改历史记录，查看谁在何时做了什么。"),
                "feat3": "确定性回滚：在出错时立即恢复到以前的版本。",
                "feat4": (
                    "视觉差异 (Δ)：两个版本之间的几何比较，以突出显示"
                    "添加、删除和修改。"),
                "feat5": (
                    "同步云：原生支持 Nextcloud, Dropbox, OneDrive 和 "
                    "Google Drive，以便团队协作。"),
                "start_title": "📖 如何开始：",
                "step1": "打开/保存：确保 QGIS 项目已保存到磁盘。",
                "step2": "提交 (✔)：使用工具栏中的按钮保存图层的当前状态。",
                "step3": "时间轴 (🕘)：打开侧边栏以管理版本。",
                "step4": "设置 (⚙)：配置您的用户名和云存储。",
                "video_btn": "▶ 观看视频教程",
                "footer": "版本 3.9 针对 QGIS 4.0 和 Qt6。"
            },
            "hi-IN": {
                "title": "🛡️ QGIS Ledger त्वरित मार्गदर्शिका",
                "intro": (
                    "QGIS Ledger आपके स्थानिक डेटा के लिए एक Git जैसा संस्करण "
                    "नियंत्रण प्रणाली है, जिसे बाहरी निर्भरता के बिना डेटा "
                    "अखंडता और सहयोग सुनिश्चित करने के लिए डिज़ाइन किया "
                    "गया है।"),
                "feat_title": "🚀 मुख्य विशेषताएं:",
                "feat1": (
                    "परमाणु स्नैपशॉट: स्थानीय SQLite डेटाबेस में अपने लेयर्स "
                    "(वेक्टर/रॉस्टर) या पूरे प्रोजेक्ट के संस्करण (कमिट) "
                    "सहेजें।"),
                "feat2": (
                    "इंटरैक्टिव टाइमलाइन: परिवर्तन इतिहास ब्राउज़ करें, "
                    "देखें कि किसने कब क्या किया।"),
                "feat3": (
                    "नियतत्ववादी रोलबैक: त्रुटियों के मामले में तुरंत पिछले "
                    "संस्करण को पुनर्स्थापित करें।"),
                "feat4": (
                    "विजुअल डिफ (Δ): परिवर्धन, विलोपन और संशोधनों को उजागर "
                    "करने के लिए दो संस्करणों के बीच ज्यामितीय तुलना।"),
                "feat5": (
                    "सिंक्रनाइज़ क्लाउड: टीम वर्क के लिए Nextcloud, Dropbox, "
                    "OneDrive and Google Drive के लिए मूल समर्थन।"),
                "start_title": "📖 कैसे शुरू करें:",
                "step1": (
                    "खोलें/सहेजें: सुनिश्चित करें कि QGIS प्रोजेक्ट डिस्क पर "
                    "सहेजा गया है।"),
                "step2": (
                    "कमिट (✔): लेयर की वर्तमान स्थिति को सहेजने के लिए "
                    "टूलबार में बटन का उपयोग करें।"),
                "step3": (
                    "टाइमलाइन (🕘): संस्करणों को प्रबंधित करने के लिए साइड "
                    "पैनल खोलें।"),
                "step4": (
                    "सेटिंग्स (⚙): अपना उपयोगकर्ता नाम और क्लाउड स्टोरेज "
                    "कॉन्फ़िगर करें।"),
                "video_btn": "▶ वीडियो ट्यूटोरियल देखें",
                "footer": (
                    "संस्करण 3.9 — QGIS 4.0 और Qt6 के लिए।")
            }
        }

        # Fallback to English if language not found
        d = help_data.get(lang, help_data["en"])

        video_url = (
            "https://mega.nz/embed/1vdnCayB#Ep91QMDOu4HBw5PdL8fm9ug87PztME-e"
            "BQ1_hNWsN08!1a")

        return f"""
        <div style="padding:15px; font-family: sans-serif; color: #f2f5f8;
             background-color: #141a22;">
            <h1 style="color:#5b9bd5; text-align: center;">{d['title']}</h1>
            <p style="font-size: 13px; line-height: 1.6;">{d['intro']}</p>
            <div style="background-color: #22303e; padding: 10px;
                 border-radius: 8px; margin: 15px 0;">
                <h3 style="color:#2ecc71;
                   margin-top: 0;">{d['feat_title']}</h3>
                <ul style="font-size: 12px; line-height: 1.5;">
                    <li>{d['feat1']}</li>
                    <li>{d['feat2']}</li>
                    <li>{d['feat3']}</li>
                    <li>{d['feat4']}</li>
                    <li>{d['feat5']}</li>
                </ul>
            </div>
            <h3 style="color:#f1c40f;">{d['start_title']}</h3>
            <ol style="font-size: 12px; line-height: 1.5;">
                <li>{d['step1']}</li>
                <li>{d['step2']}</li>
                <li>{d['step3']}</li>
                <li>{d['step4']}</li>
            </ol>
            <div style="text-align: center; margin: 25px 0;">
                <a href="{video_url}" style="background-color: #e74c3c;
                   color: white; padding: 10px 20px; text-decoration: none;
                   border-radius: 5px; font-weight: bold; font-size: 14px;">
                    {d['video_btn']}
                </a>
            </div>
            <hr style="border: 0; border-top: 1px solid #22303e;
                margin: 20px 0;">
            <p style="color:#8a97a5; font-size: 11px; text-align: center;">
                <i>{d['footer']}</i>
            </p>
        </div>
        """

# ====================================================================== #
# Diff selection dialog
# ====================================================================== #


class _DiffDialog(QDialog):
    """Simple dialog to select two commits for comparison."""

    def __init__(self, history, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("QGIS Ledger — Seleziona Commit per Diff"))
        self.setMinimumWidth(500)
        self.history = history
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        lbl = QLabel(
            "<b>" + tr("Seleziona due versioni da confrontare:") + "</b>"
        )
        lbl.setStyleSheet("color:#f2f5f8;font-size:13px;padding:6px;")
        layout.addWidget(lbl)

        # Commit A (old)
        row_a = QHBoxLayout()
        row_a.addWidget(QLabel(tr("Versione A (vecchia):")))
        self.cmb_a = QComboBox()
        for c in self.history:
            self.cmb_a.addItem(
                f"#{c['id']} — {c['layer_name']} — "
                f"{c['user_name']} — {c['timestamp']}",
                c["id"],
            )
        if len(self.history) > 1:
            self.cmb_a.setCurrentIndex(1)
        row_a.addWidget(self.cmb_a, stretch=1)
        layout.addLayout(row_a)

        # Commit B (new)
        row_b = QHBoxLayout()
        row_b.addWidget(QLabel(tr("Versione B (nuova):")))
        self.cmb_b = QComboBox()
        for c in self.history:
            self.cmb_b.addItem(
                f"#{c['id']} — {c['layer_name']} — "
                f"{c['user_name']} — {c['timestamp']}",
                c["id"],
            )
        row_b.addWidget(self.cmb_b, stretch=1)
        layout.addLayout(row_b)

        # Buttons
        buttons = QDialogButtonBox(
            getattr(
                getattr(
                    QDialogButtonBox,
                    "StandardButton",
                    QDialogButtonBox),
                "Ok") | getattr(
                getattr(
                    QDialogButtonBox,
                    "StandardButton",
                    QDialogButtonBox),
                "Cancel")
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setStyleSheet(
            "QDialog{background:#141a22;}"
            "QLabel{color:#f2f5f8;}"
            "QComboBox{background:#22303e;color:#f2f5f8;"
            "border:1px solid #8a97a5;border-radius:4px;padding:4px;}"
        )

    def get_selection(self):
        return (
            self.cmb_a.currentData(),
            self.cmb_b.currentData(),
        )


class _DiffResultDialog(QDialog):
    """Dialog showing diff results with Extract and Replace actions."""

    def __init__(
            self,
            old_id,
            new_id,
            layer_name,
            added,
            removed,
            modified,
            ledger,
            parent=None):
        super().__init__(parent)
        self.old_id = old_id
        self.new_id = new_id
        self.layer_name = layer_name
        self.added = added
        self.removed = removed
        self.modified = modified
        self.ledger = ledger
        self.setWindowTitle(tr("QGIS Ledger — Risultati Diff"))
        self.setMinimumWidth(400)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        lbl_title = QLabel(
            f"<b>Diff tra commit #{
                self.old_id} e #{
                self.new_id}</b><br/>Layer: <i>{
                self.layer_name}</i>")
        layout.addWidget(lbl_title)

        lbl_stats = QLabel(
            f"<ul>"
            f"<li>\U0001F7E2 <b>Aggiunte:</b> {self.added}</li>"
            f"<li>\U0001F534 <b>Rimosse:</b> {self.removed}</li>"
            f"<li>\U0001F7E0 <b>Modificate:</b> {self.modified}</li>"
            f"</ul>"
            f"<i>I layer temporanei per visualizzare queste differenze sono stati aggiunti alla mappa.</i>"  # noqa: E501
        )
        layout.addWidget(lbl_stats)

        # Action Buttons
        layout.addSpacing(10)
        lbl_actions = QLabel(
            "<b>Azioni rapide sulla vecchia versione (#{}):</b>".format(self.old_id))  # noqa: E501
        layout.addWidget(lbl_actions)

        btn_layout = QHBoxLayout()

        btn_extract = QPushButton("\U0001F4E5 Estrai Versione")
        btn_extract.setToolTip(
            tr("Salva la vecchia versione come un nuovo file sul disco"))
        btn_extract.setStyleSheet("padding: 8px; font-weight: bold;")
        btn_extract.clicked.connect(self._on_extract)
        btn_layout.addWidget(btn_extract)

        btn_replace = QPushButton("\U0001F504 Sostituisci corrente")
        btn_replace.setToolTip(
            tr("Esegui un Rollback immediato a questa vecchia versione"))
        btn_replace.setStyleSheet(
            "padding: 8px; font-weight: bold; color: #c0392b;")
        btn_replace.clicked.connect(self._on_replace)
        btn_layout.addWidget(btn_replace)

        layout.addLayout(btn_layout)

        layout.addSpacing(10)
        btn_close = QPushButton(tr("Chiudi finestra"))
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def _on_extract(self):
        """Export the old snapshot to a standard Geopackage."""
        snap = self.ledger.get_snapshot_features(self.old_id)
        if not snap:
            QMessageBox.warning(
                self, "QGIS Ledger", tr("Impossibile caricare snapshot."))
            return

        filename, _ = QFileDialog.getSaveFileName(
            self, "Estrai Versione come GeoPackage",
            f"{self.layer_name}_v{self.old_id}.gpkg",
            "GeoPackage (*.gpkg)"
        )
        if not filename:
            return

        # Find original layer logic to duplicate structure
        target = None
        for lid, layer in QgsProject.instance().mapLayers().items():
            if layer.name() == self.layer_name and layer.type() == layer.VectorLayer:  # noqa: E501
                target = layer
                break

        if not target:
            QMessageBox.warning(
                self,
                "QGIS Ledger",
                "Sorgente originaria non trovata. Impossibile copiare schema.")
            return

        from qgis.core import QgsVectorFileWriter
        # Save exact layer with current snapshot features
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = f"{self.layer_name}_v{self.old_id}"

        # We write to a temporary memory layer first
        from qgis.core import QgsVectorLayer
        temp_vl = QgsVectorLayer(
            target.source().split("?")[0], "temp", "memory")
        temp_pr = temp_vl.dataProvider()
        temp_pr.addAttributes(target.fields())
        temp_vl.updateFields()

        feats = []
        for item in snap:
            feat = QgsFeature(target.fields())
            if item["geometry"]:
                feat.setGeometry(QgsGeometry.fromWkt(item["geometry"]))
            for fname, val in item["attributes"].items():
                idx = target.fields().lookupField(fname)
                if idx >= 0:
                    feat.setAttribute(idx, val)
            feats.append(feat)

        temp_pr.addFeatures(feats)

        # Now write out
        result = QgsVectorFileWriter.writeAsVectorFormatV3(
            temp_vl, filename, QgsProject.instance().transformContext(), options)  # noqa: E501
        err = result[0] if isinstance(result, tuple) else result
        error_msg = result[1] if isinstance(result, tuple) else str(err)

        if err == QgsVectorFileWriter.WriterError.NoError:
            QMessageBox.information(
                self,
                "QGIS Ledger",
                tr("Versione estratta e salvata in:\n{filename}").format(
                    filename=filename))
            self.accept()
        else:
            QMessageBox.critical(
                self,
                "QGIS Ledger",
                tr("Errore scrittura:\n{error_msg}").format(
                    error_msg=error_msg))

    def _on_replace(self):
        """Invoke rollback."""
        reply = QMessageBox.warning(
            self,
            tr("QGIS Ledger — Sostituisci"),
            tr("Vuoi davvero sovrascrivere lo stato corrente del layer '{layer_name}' con il layout del commit #{old_id}?\n\nQuesta operazione è irreversibile.").format(  # noqa: E501
                layer_name=self.layer_name,
                old_id=self.old_id),
            getattr(getattr(QMessageBox, "StandardButton", QMessageBox), "Yes") | getattr(getattr(QMessageBox, "StandardButton", QMessageBox), "No"))  # noqa: E501
        if reply == getattr(
                getattr(QMessageBox, "StandardButton", QMessageBox), "Yes"):
            target = None
            for lid, layer in QgsProject.instance().mapLayers().items():
                if layer.name() == self.layer_name and layer.type() == layer.VectorLayer:  # noqa: E501
                    target = layer
                    break

            if not target:
                # PHASE 13: Layer not in map. Auto-restore from known path or
                # extract from DB to temp file.
                info = self.ledger.get_commit_info(self.old_id)
                known_path = info.get("file_path")
                import os
                from qgis.utils import iface

                if known_path and os.path.exists(known_path):
                    target = iface.addVectorLayer(
                        known_path, self.layer_name, "ogr")

                if not target or not target.isValid():
                    # Fallback Extraction
                    import tempfile
                    from qgis.core import QgsVectorLayer, QgsFeature, QgsGeometry, QgsVectorFileWriter, QgsFields, QgsField, QgsWkbTypes  # noqa: E501
                    from qgis.PyQt.QtCore import QVariant

                    temp_dir = tempfile.gettempdir()
                    filename = os.path.join(
                        temp_dir, f"{
                            self.layer_name}_restored.gpkg")

                    snap = self.ledger.get_snapshot_features(self.old_id)
                    if not snap:
                        QMessageBox.warning(
                            self, "QGIS Ledger", tr("Sorgente non trovata e snapshot DB vuoto."))  # noqa: E501
                        return

                    fields = QgsFields()
                    if len(snap) > 0:
                        for k, v in snap[0]["attributes"].items():
                            if isinstance(v, int):
                                fields.append(
                                    QgsField(
                                        k,
                                        getattr(
                                            getattr(
                                                QVariant,
                                                "Type",
                                                QVariant),
                                            "Int")))
                            elif isinstance(v, float):
                                fields.append(
                                    QgsField(
                                        k,
                                        getattr(
                                            getattr(
                                                QVariant,
                                                "Type",
                                                QVariant),
                                            "Double")))
                            else:
                                fields.append(
                                    QgsField(
                                        k,
                                        getattr(
                                            getattr(
                                                QVariant,
                                                "Type",
                                                QVariant),
                                            "String")))

                    geom_type_str = "Polygon"
                    for item in snap:
                        if item["geometry"]:
                            wkb = QgsGeometry.fromWkt(
                                item["geometry"]).wkbType()
                            gtype = QgsWkbTypes.geometryType(wkb)
                            point_t = QgsWkbTypes.GeometryType.PointGeometry
                            line_t = QgsWkbTypes.GeometryType.LineGeometry
                            if gtype == point_t:
                                geom_type_str = "Point"
                            elif gtype == line_t:
                                geom_type_str = "LineString"
                            break

                    temp_vl = QgsVectorLayer(
                        f"{geom_type_str}?crs=EPSG:4326", "temp", "memory")
                    temp_pr = temp_vl.dataProvider()
                    temp_pr.addAttributes(fields)
                    temp_vl.updateFields()

                    feats = []
                    for item in snap:
                        feat = QgsFeature(temp_vl.fields())
                        if item["geometry"]:
                            feat.setGeometry(
                                QgsGeometry.fromWkt(
                                    item["geometry"]))
                        for fname, val in item["attributes"].items():
                            idx = temp_vl.fields().lookupField(fname)
                            if idx >= 0:
                                feat.setAttribute(idx, val)
                        feats.append(feat)

                    temp_pr.addFeatures(feats)

                    options = QgsVectorFileWriter.SaveVectorOptions()
                    options.driverName = "GPKG"
                    options.layerName = self.layer_name
                    result = QgsVectorFileWriter.writeAsVectorFormatV3(
                        temp_vl, filename, QgsProject.instance().transformContext(), options)  # noqa: E501
                    err = result[0] if isinstance(result, tuple) else result

                    if err == QgsVectorFileWriter.WriterError.NoError:
                        target = iface.addVectorLayer(
                            filename, self.layer_name, "ogr")
                        QMessageBox.information(self, tr("QGIS Ledger — Ripristino dal DB ✅"),  # noqa: E501
                                                f"Layer '{
                            self.layer_name}' ricostruito dai dati storici del database e caricato in mappa.\n\n"  # noqa: E501
                            f"⚠️ IMPORTANTE: Salva il progetto QGIS ora (Ctrl+S) per rendere permanente il ripristino!")  # noqa: E501
                    else:
                        QMessageBox.warning(
                            self, "QGIS Ledger", tr("Errore nella ricostruzione del layer dal database."))  # noqa: E501
                        return

            if target and target.isValid():
                success = self.ledger.rollback_to(target, self.old_id)
                if success:
                    user = LedgerSettings.user_name()
                    self.ledger.create_commit(
                        target, f"Sostituito con '#{
                            self.old_id}' da Diff", user)
                    QMessageBox.information(
                        self, tr("QGIS Ledger — Sostituzione Completata ✅"), f"Il layer '{  # noqa: E501
                            self.layer_name}' è stato aggiornato allo stato del commit #{  # noqa: E501
                            self.old_id}.\n\n" f"⚠️ IMPORTANTE: Salva il progetto QGIS ora (Ctrl+S) per rendere permanente la sostituzione!")  # noqa: E501
                    self.accept()
                else:
                    QMessageBox.critical(
                        self, "QGIS Ledger", tr("Errore durante rollback."))
            else:
                QMessageBox.warning(
                    self, "QGIS Ledger", tr("Layer non trovato nel progetto attuale."))  # noqa: E501


class _HistoryBrowserDialog(QDialog):
    """Dialog to list all historical files and allow extraction or map loading."""  # noqa: E501

    def __init__(self, plugin, ledger, parent=None):
        super().__init__(parent)
        self.plugin = plugin
        self.ledger = ledger
        self.setWindowTitle(tr("QGIS Ledger — Esplora Storico File"))
        self.resize(700, 450)
        self.setWindowFlags(
            self.windowFlags() | getattr(
                getattr(
                    Qt,
                    "WindowType",
                    Qt),
                "WindowMaximizeButtonHint"))
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        lbl_info = QLabel(
            tr("<b>Archivio Completo File Storici</b><br>Seleziona un salvataggio dal passato per estrarlo sul tuo computer o caricarlo in mappa."))  # noqa: E501
        layout.addWidget(lbl_info)

        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "ID", "Tipo", "Nome", "Data", "Utente", "Path Originale"
        ])
        self.table.horizontalHeader().setSectionResizeMode(
            getattr(getattr(QHeaderView, "ResizeMode", QHeaderView), "ResizeToContents"))  # noqa: E501
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(
            getattr(
                getattr(
                    QTableWidget,
                    "SelectionBehavior",
                    QTableWidget),
                "SelectRows"))
        self.table.setSelectionMode(
            getattr(
                getattr(
                    QTableWidget,
                    "SelectionMode",
                    QTableWidget),
                "SingleSelection"))
        self.table.setEditTriggers(
            getattr(
                getattr(
                    QTableWidget,
                    "EditTrigger",
                    QTableWidget),
                "NoEditTriggers"))
        layout.addWidget(self.table)

        # Action Buttons
        btn_layout = QHBoxLayout()

        self.btn_extract = QPushButton(
            tr("⬇️ Estrai File / Salva con nome..."))
        self.btn_extract.setStyleSheet("padding: 6px; font-weight: bold;")
        self.btn_extract.clicked.connect(self._on_extract)
        btn_layout.addWidget(self.btn_extract)

        self.btn_load = QPushButton(
            tr("🗺️ Carica in QGIS come Layer isolato"))
        self.btn_load.setStyleSheet(
            "padding: 6px; font-weight: bold; color: #27ae60;")
        self.btn_load.clicked.connect(self._on_load_map)
        btn_layout.addWidget(self.btn_load)

        btn_layout.addStretch()

        btn_close = QPushButton(tr("Chiudi"))
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def _load_data(self):
        history = self.ledger.get_history(None)
        self.table.setRowCount(len(history))
        for row, commit in enumerate(history):
            self.table.setItem(row, 0, QTableWidgetItem(f"#{commit['id']}"))
            self.table.item(
                row,
                0).setData(
                getattr(
                    getattr(
                        Qt,
                        "ItemDataRole",
                        Qt),
                    "UserRole"),
                commit)

            self.table.setItem(
                row, 1, QTableWidgetItem(
                    commit.get(
                        'commit_type', 'VECTOR')))
            self.table.setItem(row, 2, QTableWidgetItem(commit['layer_name']))
            self.table.setItem(row, 3, QTableWidgetItem(commit['timestamp']))
            self.table.setItem(row, 4, QTableWidgetItem(commit['user_name']))
            self.table.setItem(
                row, 5, QTableWidgetItem(
                    commit.get(
                        'file_path', 'N/D')))

    def get_selected_commit(self):
        sel = self.table.selectedItems()
        if not sel:
            return None
        return self.table.item(sel[0].row(), 0).data(
            getattr(getattr(Qt, "ItemDataRole", Qt), "UserRole"))

    def _on_extract(self):
        commit = self.get_selected_commit()
        if not commit:
            return

        cid = commit['id']
        ctype = commit.get('commit_type', 'VECTOR')
        name = commit['layer_name']

        if ctype == 'PROJECT':
            out, _ = QFileDialog.getSaveFileName(
                self, tr("Estrai Progetto Self-Contained in GeoPackage"),
                f"{name}_v{cid}.gpkg", "GeoPackage (*.gpkg)"
            )
            if not out:
                return

            # Delega l'estrazione alla classe principale del plugin
            self.plugin.export_project_to_gpkg(
                cid, commit['timestamp'], out, parent_widget=self)

        elif ctype == 'RASTER':
            import shutil
            import glob
            import os

            base = os.path.join(
                self.ledger.history_dir(),
                "raster",
                f"commit_{cid}_*")
            files = glob.glob(base)
            if not files:
                QMessageBox.warning(
                    self, "QGIS Ledger", tr("File raster storicizzato non trovato."))  # noqa: E501
                return

            src = files[0]
            ext = os.path.splitext(src)[1]
            out, _ = QFileDialog.getSaveFileName(
                self, tr("Estrai Raster"), f"{name}_v{cid}{ext}", f"Raster (*{ext})")  # noqa: E501
            if out:
                shutil.copy2(src, out)
                msg_text = tr("Il file raster del commit #{cid} è stato estratto con successo in:\n{out}\n\n").format(  # noqa: E501
                    cid=cid, out=out) + tr("💡 Puoi caricarlo in QGIS con Layer > Aggiungi Layer Raster.")  # noqa: E501
                QMessageBox.information(
                    self,
                    tr("QGIS Ledger — Estrazione Raster ✅"),
                    msg_text)

        elif ctype == 'VECTOR':
            # Needs to extract from DB snapshot
            snap = self.ledger.get_snapshot_features(cid)
            if not snap:
                QMessageBox.warning(
                    self, "QGIS Ledger", tr("Impossibile caricare snapshot."))
                return

            out, _ = QFileDialog.getSaveFileName(self, tr(
                "Estrai Vettore come GeoPackage"), f"{name}_v{cid}.gpkg", "GeoPackage (*.gpkg)")  # noqa: E501
            if not out:
                return

            from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsVectorFileWriter, QgsFields, QgsField, QgsWkbTypes  # noqa: E501
            from qgis.PyQt.QtCore import QVariant

            fields = QgsFields()
            target = None
            for lid, layer in QgsProject.instance().mapLayers().items():
                if layer.name() == name and layer.type() == layer.VectorLayer:
                    target = layer
                    break

            if target:
                fields = target.fields()
            elif len(snap) > 0:
                for k, v in snap[0]["attributes"].items():
                    if isinstance(v, int):
                        fields.append(
                            QgsField(
                                k,
                                getattr(
                                    getattr(
                                        QVariant,
                                        "Type",
                                        QVariant),
                                    "Int")))
                    elif isinstance(v, float):
                        fields.append(
                            QgsField(
                                k,
                                getattr(
                                    getattr(
                                        QVariant,
                                        "Type",
                                        QVariant),
                                    "Double")))
                    else:
                        fields.append(
                            QgsField(
                                k,
                                getattr(
                                    getattr(
                                        QVariant,
                                        "Type",
                                        QVariant),
                                    "String")))

            geom_type_str = "Polygon"
            for item in snap:
                if item["geometry"]:
                    wkb = QgsGeometry.fromWkt(item["geometry"]).wkbType()
                    if QgsWkbTypes.geometryType(
                            wkb) == QgsWkbTypes.GeometryType.PointGeometry:
                        geom_type_str = "Point"
                    elif QgsWkbTypes.geometryType(wkb) == QgsWkbTypes.GeometryType.LineGeometry:  # noqa: E501
                        geom_type_str = "LineString"
                    break

            temp_vl = QgsVectorLayer(
                f"{geom_type_str}?crs=EPSG:4326", "temp", "memory")
            temp_pr = temp_vl.dataProvider()
            temp_pr.addAttributes(fields)
            temp_vl.updateFields()

            feats = []
            for item in snap:
                feat = QgsFeature(temp_vl.fields())
                if item["geometry"]:
                    feat.setGeometry(QgsGeometry.fromWkt(item["geometry"]))
                for fname, val in item["attributes"].items():
                    idx = temp_vl.fields().lookupField(fname)
                    if idx >= 0:
                        feat.setAttribute(idx, val)
                feats.append(feat)

            temp_pr.addFeatures(feats)

            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "GPKG"
            options.layerName = f"{name}_v{cid}"
            result = QgsVectorFileWriter.writeAsVectorFormatV3(
                temp_vl, out, QgsProject.instance().transformContext(), options)  # noqa: E501
            err = result[0] if isinstance(result, tuple) else result
            msg = result[1] if isinstance(result, tuple) else str(err)
            if err == QgsVectorFileWriter.WriterError.NoError:
                msg1 = tr("Il vettore \'{name}\' del commit #{cid} è stato estratto con successo in:\n{out}\n\n").format(  # noqa: E501
                    name=name, cid=cid, out=out)
                msg2 = tr(
                    "💡 Puoi caricarlo in QGIS con Layer > Aggiungi Layer Vettoriale.")  # noqa: E501
                QMessageBox.information(
                    self,
                    tr("QGIS Ledger — Estrazione Vettore ✅"),
                    msg1 + msg2)
            else:
                QMessageBox.critical(self, "QGIS Ledger", tr(
                    "Errore scrittura:\n{msg}").format(msg=msg))

    def _on_load_map(self):
        commit = self.get_selected_commit()
        if not commit:
            return

        cid = commit['id']
        ctype = commit.get('commit_type', 'VECTOR')
        name = commit['layer_name']

        if ctype == 'PROJECT':
            QMessageBox.warning(
                self, "QGIS Ledger", tr("Impossibile caricare un intero Progetto come singolo Layer. Usa la funzione Estrai."))  # noqa: E501
            return

        elif ctype == 'RASTER':
            import glob
            import os
            from qgis.utils import iface

            base = os.path.join(
                self.ledger.history_dir(),
                "raster",
                f"commit_{cid}_*")
            files = glob.glob(base)
            if not files:
                QMessageBox.warning(
                    self, "QGIS Ledger", tr("File raster storicizzato non trovato."))  # noqa: E501
                return
            src = files[0]
            iface.addRasterLayer(src, f"{name} (v{cid})")
            QMessageBox.information(
                self,
                tr("QGIS Ledger — Raster Caricato ✅"),
                tr("Il raster \'{name}\' (versione #{cid}) è stato aggiunto alla mappa come layer isolato.\n\n").format(name=name, cid=cid) + tr("💡 Ricorda: salva il progetto QGIS (Ctrl+S) se vuoi conservare questo layer nella sessione."))  # noqa: E501

        elif ctype == 'VECTOR':
            import os
            from qgis.utils import iface

            snap = self.ledger.get_snapshot_features(cid)
            if not snap:
                QMessageBox.warning(
                    self, "QGIS Ledger", tr("Impossibile caricare snapshot."))
                return

            import tempfile
            from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsVectorFileWriter, QgsField, QgsFields, QgsWkbTypes  # noqa: E501
            from qgis.PyQt.QtCore import QVariant

            temp_dir = tempfile.gettempdir()
            filename = os.path.join(temp_dir, f"{name}_v{cid}.gpkg")

            target = None
            for lid, layer in QgsProject.instance().mapLayers().items():
                if layer.name() == name and layer.type() == layer.VectorLayer:
                    target = layer
                    break

            fields = QgsFields()
            if target:
                fields = target.fields()
            elif len(snap) > 0:
                for k, v in snap[0]["attributes"].items():
                    if isinstance(v, int):
                        fields.append(
                            QgsField(
                                k,
                                getattr(
                                    getattr(
                                        QVariant,
                                        "Type",
                                        QVariant),
                                    "Int")))
                    elif isinstance(v, float):
                        fields.append(
                            QgsField(
                                k,
                                getattr(
                                    getattr(
                                        QVariant,
                                        "Type",
                                        QVariant),
                                    "Double")))
                    else:
                        fields.append(
                            QgsField(
                                k,
                                getattr(
                                    getattr(
                                        QVariant,
                                        "Type",
                                        QVariant),
                                    "String")))

            geom_type_str = "Polygon"
            for item in snap:
                if item["geometry"]:
                    wkb = QgsGeometry.fromWkt(item["geometry"]).wkbType()
                    if QgsWkbTypes.geometryType(
                            wkb) == QgsWkbTypes.GeometryType.PointGeometry:
                        geom_type_str = "Point"
                    elif QgsWkbTypes.geometryType(wkb) == QgsWkbTypes.GeometryType.LineGeometry:  # noqa: E501
                        geom_type_str = "LineString"
                    break

            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "GPKG"
            options.layerName = f"{name}_v{cid}"

            temp_vl = QgsVectorLayer(
                f"{geom_type_str}?crs=EPSG:4326", "temp", "memory")
            temp_pr = temp_vl.dataProvider()
            temp_pr.addAttributes(fields)
            temp_vl.updateFields()

            feats = []
            for item in snap:
                feat = QgsFeature(temp_vl.fields())
                if item["geometry"]:
                    feat.setGeometry(QgsGeometry.fromWkt(item["geometry"]))
                for fname, val in item["attributes"].items():
                    idx = temp_vl.fields().lookupField(fname)
                    if idx >= 0:
                        feat.setAttribute(idx, val)
                feats.append(feat)

            temp_pr.addFeatures(feats)
            result = QgsVectorFileWriter.writeAsVectorFormatV3(
                temp_vl, filename, QgsProject.instance().transformContext(), options)  # noqa: E501
            err = result[0] if isinstance(result, tuple) else result

            if err == QgsVectorFileWriter.WriterError.NoError:
                iface.addVectorLayer(filename, f"{name} (v{cid})", "ogr")
                msg_text = tr("Il vettore \'{name}\' (versione #{cid}) è stato caricato in mappa come layer temporaneo (estratto dal DB).\n\n").format(  # noqa: E501
                    name=name, cid=cid) + tr("💡 Ricorda: salva il progetto QGIS (Ctrl+S) se vuoi conservare questo layer nella sessione.")  # noqa: E501
                QMessageBox.information(
                    self,
                    tr("QGIS Ledger — Vettore Caricato ✅"),
                    msg_text)
            else:
                QMessageBox.critical(self, "QGIS Ledger", tr(
                    "Errore nell'estrazione del vettore per il caricamento."))
