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

from qgis.PyQt.QtCore import Qt, QTimer, QSettings, QObject
from qgis.PyQt.QtGui import QIcon, QColor
from qgis.PyQt.QtWidgets import (
    QAction, QToolBar, QInputDialog, QMessageBox,
    QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton,
    QDialogButtonBox, QHBoxLayout, QWidget, QFileDialog,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
)

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsRasterLayer,
    QgsFeature,
    QgsGeometry,
)
from qgis.gui import QgisInterface

from .ledger_ledger import LedgerDB
from .ledger_diff import LedgerDiff
from .ledger_merge import MergeWizard, ConflictItem
from .ledger_timeline import TimelinePanel
from .ledger_statusbar import StatusLED
from .ledger_settings import SettingsDialog, LedgerSettings
from .ledger_sync import NetworkSync
from .ledger_nextcloud import NextcloudBrowserPanel


class _DropEventFilter(QObject):
    """QObject che intercetta gli eventi drag-drop Nextcloud a livello di QApplication."""
    def __init__(self, plugin, parent=None):
        super().__init__(parent)
        self._plugin = plugin

    def eventFilter(self, obj, event):
        from qgis.PyQt.QtCore import QEvent
        etype = event.type()
        if etype in (QEvent.DragEnter, QEvent.DragMove):
            try:
                mime = event.mimeData()
                if mime and mime.hasFormat("application/x-qgis-ledger-nc"):
                    event.setDropAction(Qt.CopyAction)
                    event.accept()
                    event.acceptProposedAction()
                    return True
            except Exception:
                pass
        elif etype == QEvent.Drop:
            try:
                mime = event.mimeData()
                if mime and mime.hasFormat("application/x-qgis-ledger-nc"):
                    event.setDropAction(Qt.CopyAction)
                    event.accept()
                    import json
                    raw = bytes(mime.data("application/x-qgis-ledger-nc")).decode("utf-8")
                    item_data = json.loads(raw)
                    panel = self._plugin.nextcloud_panel
                    if panel:
                        QTimer.singleShot(0, lambda d=item_data: panel._auto_download_and_load(d))
                    return True
            except Exception as e:
                from qgis.PyQt.QtWidgets import QMessageBox
                QMessageBox.warning(None, "QGIS Ledger", f"Errore drop Nextcloud: {e}")
                return True
        return False


class LedgerPlugin:
    """QGIS QGIS Ledger — Main Plugin Class."""

    def __init__(self, iface: QgisInterface):
        self.iface = iface
        self.ledger = LedgerDB()
        self.diff_engine = LedgerDiff(self.ledger)
        self.sync = NetworkSync()

        self.timeline_panel = None
        self.nextcloud_panel = None
        self.status_led = None
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
    def _make_icon(symbol: str, bg_color: str = "#2c3e50", fg_color: str = "#ecf0f1", size: int = 32):
        """Genera una QIcon con un simbolo centrato su sfondo arrotondato."""
        from qgis.PyQt.QtGui import QPixmap, QPainter, QColor, QFont
        from qgis.PyQt.QtCore import Qt as QtConst, QRect
        pm = QPixmap(size, size)
        pm.fill(QColor(0, 0, 0, 0))  # trasparente
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
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
        p.drawText(QRect(0, 0, size, size), QtConst.AlignCenter, symbol)
        p.end()
        return QIcon(pm)

    def initGui(self):
        """Called by QGIS when the plugin is loaded."""
        # -- Toolbar --------------------------------------------------- #
        self.toolbar = self.iface.addToolBar("QGIS Ledger")
        self.toolbar.setObjectName("QGIS LedgerToolbar")
        self.toolbar.setStyleSheet(
            "QToolBar { spacing: 2px; }"
            "QToolButton { min-width: 36px; min-height: 36px; font-size: 11px; }"
        )

        # Open Project button
        act_open = QAction(self._make_icon("📂", "#2980b9"), "Apri Progetto", self.iface.mainWindow())
        act_open.setToolTip("Apri un progetto QGIS esistente")
        act_open.triggered.connect(self._on_open_project)
        self.toolbar.addAction(act_open)
        self._actions.append(act_open)

        # Sync button
        act_sync = QAction(self._make_icon("🔄", "#27ae60"), "Sync", self.iface.mainWindow())
        act_sync.setToolTip("Sincronizza con cartella condivisa")
        act_sync.triggered.connect(self._on_sync)
        self.toolbar.addAction(act_sync)
        self._actions.append(act_sync)

        self.toolbar.addSeparator()

        # Commit button
        act_commit = QAction(self._make_icon("✔", "#16a085"), "Commit", self.iface.mainWindow())
        act_commit.setToolTip("Salva snapshot del layer attivo")
        act_commit.triggered.connect(self._on_commit)
        self.toolbar.addAction(act_commit)
        self._actions.append(act_commit)

        # Commit Project button
        act_commit_proj = QAction(self._make_icon("💾", "#8e44ad"), "Commit Progetto", self.iface.mainWindow())
        act_commit_proj.setToolTip("Salva una copia intera del progetto QGIS (.qgz)")
        act_commit_proj.triggered.connect(self._on_commit_project)
        self.toolbar.addAction(act_commit_proj)
        self._actions.append(act_commit_proj)

        # Main Panel button (unifies Timeline and Nextcloud)
        self._panel_action = QAction(self._make_icon("🕘☁", "#2c3e50"), "Pannello Ledger", self.iface.mainWindow())
        self._panel_action.setToolTip("Mostra/nascondi il pannello principale (Timeline & Nextcloud)")
        self._panel_action.setCheckable(True)
        self._panel_action.triggered.connect(self._toggle_main_panel)
        self.toolbar.addAction(self._panel_action)
        self._actions.append(self._panel_action)

        # Diff button
        act_diff = QAction(self._make_icon("Δ", "#e67e22"), "Diff", self.iface.mainWindow())
        act_diff.setToolTip("Confronto visuale tra due versioni")
        act_diff.triggered.connect(self._on_diff_dialog)
        self.toolbar.addAction(act_diff)
        self._actions.append(act_diff)

        # Browser button
        act_browser = QAction(self._make_icon("🗂", "#34495e"), "Esplora Storico", self.iface.mainWindow())
        act_browser.setToolTip("Sfoglia ed Estrai vecchie versioni dal database")
        act_browser.triggered.connect(self._on_browser_dialog)
        self.toolbar.addAction(act_browser)
        self._actions.append(act_browser)

        self.toolbar.addSeparator()

        # Auto-Save Timer button
        self._autosave_action = QAction(self._make_icon("⏱", "#f39c12"), "Auto-Save", self.iface.mainWindow())
        self._autosave_action.setCheckable(True)
        self._autosave_action.setToolTip("Attiva/Disattiva il salvataggio automatico periodico")
        self._autosave_action.triggered.connect(self._toggle_autosave)
        self.toolbar.addAction(self._autosave_action)
        self._actions.append(self._autosave_action)
        self.toolbar.addSeparator()

        # Settings button
        act_settings = QAction(self._make_icon("⚙", "#7f8c8d"), "Settings", self.iface.mainWindow())
        act_settings.setToolTip("Impostazioni QGIS Ledger")
        act_settings.triggered.connect(self._on_settings)
        self.toolbar.addAction(act_settings)
        self._actions.append(act_settings)

        # Info button
        act_info = QAction(self._make_icon("ℹ", "#95a5a6"), "Info", self.iface.mainWindow())
        act_info.setToolTip("Informazioni sulla versione del plugin")
        act_info.triggered.connect(self._on_info)
        self.toolbar.addAction(act_info)
        self._actions.append(act_info)

        # -- Aggiungi tutti i pulsanti al Menu Plugins -- #
        for action in self._actions:
            self.iface.addPluginToMenu("&QGIS Ledger", action)

        # -- Status Bar LED -------------------------------------------- #
        self.status_led = StatusLED()
        self.status_led.clicked.connect(self._on_led_clicked)
        self.iface.statusBarIface().addPermanentWidget(self.status_led)


        # self.timeline_panel = TimelinePanel(self.ledger)
        # self.timeline_panel.preview_requested.connect(self._on_preview)
        # self.timeline_panel.rollback_requested.connect(self._on_rollback)
        # self.timeline_panel.diff_requested.connect(self._on_diff_from_commit)
        # self.timeline_panel.commit_requested.connect(self._on_commit)
        # self.iface.addDockWidget(Qt.RightDockWidgetArea, self.timeline_panel)
        # self.timeline_panel.hide()

        # -- Nextcloud Browser Panel ----------------------------------- #
        # self.nextcloud_panel = NextcloudBrowserPanel(self.iface.mainWindow())
        # self.iface.addDockWidget(Qt.LeftDockWidgetArea, self.nextcloud_panel)
        # self.nextcloud_panel.hide()
        # self.nextcloud_panel.visibilityChanged.connect(
        #     lambda visible: self._nextcloud_action.setChecked(visible)
        # )

        # -- Nextcloud Panel (not a dock, embedded in tab) ------------ #
        from qgis.PyQt.QtWidgets import QDockWidget, QTabWidget
        self.nextcloud_panel = NextcloudBrowserPanel()

        # -- Timeline Panel (not a dock, embedded in tab) ------------- #
        from .ledger_timeline import TimelinePanel
        self.timeline_panel = TimelinePanel(self.ledger, parent=None)
        self.timeline_panel.preview_requested.connect(self._on_preview)
        self.timeline_panel.rollback_requested.connect(self._on_rollback)
        self.timeline_panel.diff_requested.connect(self._on_diff_from_commit)
        self.timeline_panel.commit_requested.connect(self._on_commit)
        
        # -- Unified Main Panel (Dock Widget) ------------------------- #
        self.main_panel = QDockWidget("QGIS Ledger", self.iface.mainWindow())
        self.main_panel.setObjectName("QGISLedgerMainPanel")
        
        self.tab_widget = QTabWidget()
        self.tab_widget.addTab(self.timeline_panel, "🕓 Timeline")
        self.tab_widget.addTab(self.nextcloud_panel, "☁️ Nextcloud")
        self.tab_widget.currentChanged.connect(self._on_tab_changed) # _on_tab_changed needs to be defined
        
        self.main_panel.setWidget(self.tab_widget)
        self.iface.addDockWidget(Qt.RightDockWidgetArea, self.main_panel)
        self.main_panel.hide()
        self.main_panel.visibilityChanged.connect(self._panel_action.setChecked)

        # Configura Nextcloud action (context menu upload) ------------- #
        self.upload_nc_action = QAction(self._make_icon("☁️", "#3498db"), "Invia a Nextcloud (QGIS Ledger)", self.iface.mainWindow())
        self.upload_nc_action.triggered.connect(self._on_upload_layer_to_nc)
        
        # Metodo robusto: intercettiamo il menu contestuale del layer tree
        try:
            ltv = self.iface.layerTreeView()
            if ltv:
                ltv.setContextMenuPolicy(Qt.CustomContextMenu)
                ltv.customContextMenuRequested.connect(self._on_toc_context_menu)
        except Exception:
            pass
        
        # Fallback: prova anche addCustomActionForLayerType
        try:
            self.iface.addCustomActionForLayerType(self.upload_nc_action, "", 0, False)  # 0 = VectorLayer
            self.iface.addCustomActionForLayerType(self.upload_nc_action, "", 1, False)  # 1 = RasterLayer
        except Exception:
            pass

        # -- Connect project signals ---------------------------------- #
        QgsProject.instance().readProject.connect(self._on_project_opened)
        QgsProject.instance().cleared.connect(self._on_project_closed)

        # -- Enable Drag & Drop from Nextcloud panel → ovunque in QGIS -- #
        # Usiamo QApplication event filter con un QObject dedicato.
        from qgis.PyQt.QtWidgets import QApplication
        self._drop_filter = _DropEventFilter(self)
        QApplication.instance().installEventFilter(self._drop_filter)

        # If a project is already open, connect now
        if QgsProject.instance().fileName():
            self._on_project_opened()

        # -- Sync timer (check every 10 seconds) ---------------------- #
        self._sync_timer = QTimer()
        self._sync_timer.timeout.connect(self._check_sync)
        self._sync_timer.start(10000)

    def unload(self):
        """Called by QGIS when the plugin is unloaded."""
        if self._sync_timer:
            self._sync_timer.stop()
        if self._autosave_timer:
            self._autosave_timer.stop()

        for act in self._actions:
            self.iface.removeToolBarIcon(act)
            self.iface.removePluginMenu("&QGIS Ledger", act)
            
        if self.toolbar:
            del self.toolbar

        if self.main_panel:
            self.iface.removeDockWidget(self.main_panel)
            self.main_panel.deleteLater()
            self.nextcloud_panel.deleteLater()

        try:
            self.iface.removeCustomActionForLayerType(self.upload_nc_action)
        except Exception:
            pass

        if self.status_led:
            self.iface.statusBarIface().removeWidget(self.status_led)
            self.status_led.deleteLater()

        self.diff_engine.clear_diff()
        self.ledger.close()

        # Rimuovi app-level event filter
        try:
            from qgis.PyQt.QtWidgets import QApplication
            QApplication.instance().removeEventFilter(self._drop_filter)
            self._drop_filter = None
        except Exception:
            pass

        QgsProject.instance().readProject.disconnect(self._on_project_opened)
        QgsProject.instance().cleared.disconnect(self._on_project_closed)

    # ================================================================== #
    # Drag & Drop event filter (Nextcloud → Canvas)
    # ================================================================== #

    def _on_toc_context_menu(self, pos):
        """Menu contestuale personalizzato per il Layer Tree (TOC)."""
        ltv = self.iface.layerTreeView()
        if not ltv:
            return
        # Costruisci il menu standard di QGIS
        menu = self.iface.layerTreeView().menuProvider().createContextMenu()
        if not menu:
            from qgis.PyQt.QtWidgets import QMenu
            menu = QMenu()
        # Aggiungi la nostra azione solo se Nextcloud è configurato
        if LedgerSettings.remote_type() == "webdav":
            menu.addSeparator()
            menu.addAction(self.upload_nc_action)
        menu.exec_(ltv.mapToGlobal(pos))



    # ================================================================== #
    # Project lifecycle
    # ================================================================== #

    def _on_project_opened(self, *args):
        """Connect to the ledger when a project is opened."""
        if self.ledger.connect():
            self.status_led.set_status(StatusLED.SYNCED)
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
            self.status_led.set_status(StatusLED.DISCONNECTED)

    def _on_project_closed(self, *args):
        self.ledger.close()
        self.sync.stop_watching()
        self.status_led.set_status(StatusLED.DISCONNECTED)
        self.diff_engine.clear_diff()

    def _check_mod_user_commits(self):
        """Check if mod_user have made changes since the project was last opened on this machine."""
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
            layer_names = set(c["layer_name"] for c in new_commits_by_others if c.get("commit_type") in ("VECTOR", "RASTER"))
            
            msg = f"Ottime notizie! {len(new_commits_by_others)} nuove modifiche aggiunte dai mod_user ({', '.join(mod_users)})."
            
            self.iface.messageBar().pushInfo(
                "QGIS Ledger — Novità dai mod_user", msg
            )
            
            details = f"Sono state trovate {len(new_commits_by_others)} nuove modifiche apportate dai mod_user:\n"
            details += f"• Autori: {', '.join(mod_users)}\n"
            if layer_names:
                details += f"• Layer toccati: {', '.join(layer_names)}\n"
            details += "\nApri la Timeline per esaminare in dettaglio cosa hanno fatto."
            
            QMessageBox.information(
                self.iface.mainWindow(),
                "QGIS Ledger — Aggiornamenti Disponibili",
                details
            )
            self.status_led.set_status(StatusLED.MODIFIED)

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
        self.status_led.set_status(StatusLED.MODIFIED)

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
        self.status_led.set_status(StatusLED.SYNCED)

    # ================================================================== #
    # Toolbar actions
    # ================================================================== #

    def _on_open_project(self):
        """Open a QGIS project from disk or cloud."""
        if LedgerSettings.remote_type() == "webdav" and self.nextcloud_panel:
            reply = QMessageBox.question(
                self.iface.mainWindow(), "QGIS Ledger",
                "Vuoi esplorare un progetto LOCALE o scaricarlo dal CLOUD (Nextcloud)?\n\n"
                "• 'Yes' per scegliere un file in LOCALE\n"
                "• 'No' per sfogliare il CLOUD",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                self._nextcloud_action.setChecked(True)
                self._toggle_nextcloud(True)
                QMessageBox.information(
                    self.iface.mainWindow(), "QGIS Ledger",
                    "Naviga nel pannello Nextcloud a sinistra e fai doppio clic sul file .qgz per scaricarlo e aprirlo."
                )
                return

        file_path, _ = QFileDialog.getOpenFileName(
            self.iface.mainWindow(),
            "Seleziona Progetto QGIS",
            QgsProject.instance().homePath() or "",
            "QGIS Project (*.qgz *.qgs *.gpkg);;Tutti i file (*)"
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
                        QMessageBox.warning(self.iface.mainWindow(), "QGIS Ledger", "Nessun progetto trovato nel GeoPackage selezionato.")
                except Exception as e:
                    QMessageBox.warning(self.iface.mainWindow(), "QGIS Ledger", f"Errore lettura GeoPackage: {e}")
            else:
                QgsProject.instance().read(file_path)

    def _on_commit(self):
        """Commit the active layer with a user message."""
        layer = self.iface.activeLayer()
        if not isinstance(layer, (QgsVectorLayer, QgsRasterLayer)):
            QMessageBox.warning(
                self.iface.mainWindow(), "QGIS Ledger",
                "Seleziona un layer vettoriale o raster per fare il commit."
            )
            return

        if not self.ledger.is_connected():
            if not self.ledger.connect():
                QMessageBox.warning(
                    self.iface.mainWindow(), "QGIS Ledger",
                    "Salva il progetto prima di usare QGIS Ledger."
                )
                return

        message, ok = QInputDialog.getText(
            self.iface.mainWindow(),
            "QGIS Ledger — Nuovo Commit",
            "Descrivi le modifiche (Perché):",
        )
        if not ok or not message.strip():
            return

        user = LedgerSettings.user_name()
        warn_text = ""

        if isinstance(layer, QgsVectorLayer):
            commit_id = self.ledger.create_commit(layer, message.strip(), user)
            feat_count = layer.featureCount()
        else:
            commit_id = self.ledger.create_raster_commit(layer, message.strip(), user)
            feat_count = 1

        if commit_id > 0:
            self._capture_screenshot(commit_id)
            QMessageBox.information(
                self.iface.mainWindow(), "QGIS Ledger — Commit Salvato ✅",
                f"Commit #{commit_id} salvato con successo!\n"
                f"Layer: {layer.name()}\n"
                f"Features/File: {feat_count}\n"
                f"Utente: {user}"
                f"{warn_text}\n\n"
                f"💡 Ricorda: salva il progetto QGIS (Ctrl+S) per consolidare le modifiche."
            )
            self.status_led.set_status(StatusLED.SYNCED)
            self.timeline_panel.populate_layers()
            self._trigger_cloud_sync(commit_id)
        else:
            QMessageBox.critical(
                self.iface.mainWindow(), "QGIS Ledger",
                "Errore durante il salvataggio del commit (file non accessibile o ledger chiuso)."
            )

    def _trigger_cloud_sync(self, commit_id: int):
        """Esegue l'upload in background dei file generati da un commit se Nextcloud è attivo."""
        if LedgerSettings.remote_type() != "webdav" or not self.nextcloud_panel:
            return
            
        import os
        from qgis.core import QgsProject
        from .ledger_nextcloud import _Worker, NextcloudClient
        from qgis.PyQt.QtCore import QThreadPool
        
        proj_path = QgsProject.instance().fileName()
        if not proj_path: return
            
        # Determina la cartella remota
        cloud_base = QgsProject.instance().readEntry("QGIS_Ledger", "cloud_sync_path", "")[0]
        if cloud_base:
            remote_dir = os.path.dirname(cloud_base)
        else:
            remote_dir = "" # default root o la cartella in settings
            
        info = self.ledger.get_commit_info(commit_id)
        if not info: return
        
        files_to_sync = []
        
        # 1. Il database di ledger (sempre)
        db_path = self.ledger.db_path()
        if not db_path or not os.path.exists(db_path):
            return  # Non c'è database, non possiamo sincronizzare
        files_to_sync.append( (db_path, f"{os.path.basename(proj_path)}.ledger.db") )
        
        # 2. File WAL e SHM se presenti (SQLite in WAL mode)
        if os.path.exists(str(db_path) + "-wal"):
            files_to_sync.append( (str(db_path) + "-wal", f"{os.path.basename(proj_path)}.ledger.db-wal") )
        if os.path.exists(str(db_path) + "-shm"):
            files_to_sync.append( (str(db_path) + "-shm", f"{os.path.basename(proj_path)}.ledger.db-shm") )
            
        # 3. Snapshot o copia progetto
        ctype = info.get("commit_type")
        file_path = info.get("file_path", "")
        if file_path:
            if ctype == "PROJECT":
                local_f = os.path.join(self.ledger.history_dir(), "project", file_path)
                files_to_sync.append( (local_f, file_path) )
                
                # Sincronizza anche l'attuale .qgz se stiamo committando il progetto!
                if os.path.exists(proj_path):
                    files_to_sync.append( (proj_path, os.path.basename(proj_path)) )
            elif ctype == "VECTOR":
                local_f = os.path.join(self.ledger.history_dir(), "vector", file_path.split('|')[0])
                files_to_sync.append( (local_f, os.path.basename(local_f)) )
            elif ctype == "RASTER":
                local_f = os.path.join(self.ledger.history_dir(), "raster", file_path)
                files_to_sync.append( (local_f, file_path) )
                
        def sync_task():
            client = NextcloudClient(
                LedgerSettings.nextcloud_server(),
                LedgerSettings.nextcloud_user(),
                LedgerSettings.nextcloud_password(),
                LedgerSettings.nextcloud_folder()
            )
            # Create remote dir if not exists (try block)
            if remote_dir:
                try: client.make_directory(remote_dir)
                except: pass
                
            for local_p, remote_name in files_to_sync:
                if os.path.exists(local_p):
                    target_remote = (remote_dir + "/" + remote_name).lstrip("/")
                    client.upload(target_remote, local_p)
                    
        worker = _Worker(sync_task)
        # Mostriamo un tooltip leggero o cambiamo il led
        self.status_led.setToolTip("Sincronizzazione Cloud in corso...")
        worker.signals.finished.connect(lambda res: self.status_led.setToolTip("Sincronizzato col Cloud ✅"))
        QThreadPool.globalInstance().start(worker)

    def _on_upload_layer_to_nc(self):
        if LedgerSettings.remote_type() != "webdav" or not self.nextcloud_panel:
            QMessageBox.warning(self.iface.mainWindow(), "QGIS Ledger", "Sincronizzazione Nextcloud disattivata o non configurata.\nVai in Impostazioni e verifica i parametri.")
            return

        layer = self.iface.activeLayer()
        if not layer: return
        
        import os
        src_file = layer.source()
        if not os.path.isfile(src_file) and "|" in src_file:
            src_file = src_file.split("|")[0]
            
        if not os.path.exists(src_file):
            QMessageBox.warning(self.iface.mainWindow(), "QGIS Ledger", "Impossibile determinare il file sorgente del layer.\nForse è in memoria o non salvato?")
            return

        from qgis.PyQt.QtWidgets import QInputDialog
        base_dir = LedgerSettings.nextcloud_folder()
        default_dest = base_dir + "/" + layer.name() if base_dir else layer.name()

        text, ok = QInputDialog.getText(
            self.iface.mainWindow(),
            "Carica Layer su Nextcloud",
            "Inserisci il percorso remoto in Nextcloud (creerà la cartella se non esiste):",
            text=default_dest
        )
        if not ok or not text.strip():
            return
            
        target_dir = text.strip()
        files_to_sync = []
        name = os.path.basename(src_file)
        ext = os.path.splitext(name)[1].lower()
        files_to_sync.append( (src_file, name) )
        
        if ext == ".shp":
            base_name = os.path.splitext(name)[0]
            src_dir = os.path.dirname(src_file)
            related_exts = {".dbf", ".shx", ".prj", ".cpg", ".qix", ".sbn", ".sbx"}
            for f in os.listdir(src_dir):
                c_base, c_ext = os.path.splitext(f)
                if c_base == base_name and c_ext.lower() in related_exts:
                    files_to_sync.append( (os.path.join(src_dir, f), f) )
                    
        def sync_task():
            from .ledger_nextcloud import NextcloudClient
            client = NextcloudClient(
                LedgerSettings.nextcloud_server(),
                LedgerSettings.nextcloud_user(),
                LedgerSettings.nextcloud_password(),
                LedgerSettings.nextcloud_folder()
            )
            if target_dir:
                try: client.make_directory(target_dir)
                except: pass
                
            for local_p, remote_name in files_to_sync:
                if os.path.exists(local_p):
                    target_remote = (target_dir + "/" + remote_name).lstrip("/")
                    client.upload(target_remote, local_p)
                    
        from .ledger_nextcloud import _Worker
        from qgis.PyQt.QtCore import QThreadPool
        worker = _Worker(sync_task)
        self.status_led.setToolTip("Upload Layer in corso...")
        worker.signals.finished.connect(lambda res: QMessageBox.information(self.iface.mainWindow(), "QGIS Ledger", f"Layer {layer.name()} caricato su Nextcloud con successo!"))
        worker.signals.error.connect(lambda err: QMessageBox.warning(self.iface.mainWindow(), "QGIS Ledger", f"Errore durante l'upload: {err}"))
        QThreadPool.globalInstance().start(worker)

    def _on_commit_project(self):
        """Commit the entire QGIS project."""
        if not QgsProject.instance().fileName():
            QMessageBox.warning(
                self.iface.mainWindow(), "QGIS Ledger",
                "Il progetto non è stato ancora salvato su disco."
            )
            return
        if not self.ledger.is_connected():
            self.ledger.connect()

        message, ok = QInputDialog.getText(
            self.iface.mainWindow(),
            "QGIS Ledger — Commit Progetto",
            "Descrivi le modifiche al progetto (Perché):"
        )
        if not ok or not message.strip():
            return

        user = LedgerSettings.user_name()
        
        # Chiedi conferma per autocommit + geopackage automatico
        reply = QMessageBox.question(
            self.iface.mainWindow(), "QGIS Ledger — Export Avanzato",
            "Vuoi creare un unico commit del progetto e di tutti i layer, ed estrarlo "
            "subito in un GeoPackage portatile (con tutti gli URI aggiornati)?\n\n"
            "• 'Yes': Auto-Commit di tutti i vettori e salvataggio GeoPackage completo.\n"
            "• 'No': Commit del solo file di progetto (comportamento standard).",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Auto-commit layer vettoriali
            committed = 0
            for lid, layer in QgsProject.instance().mapLayers().items():
                if isinstance(layer, QgsVectorLayer):
                    cid = self.ledger.create_commit(layer, f"[AUTO] {message.strip()}", user)
                    if cid > 0: committed += 1
                    
        commit_id = self.ledger.create_project_commit(message.strip(), user)
        info = self.ledger.get_commit_info(commit_id)

        if commit_id > 0:
            self._capture_screenshot(commit_id)
            
            if reply == QMessageBox.Yes:
                from qgis.PyQt.QtWidgets import QFileDialog
                out, _ = QFileDialog.getSaveFileName(
                    self.iface.mainWindow(), "Estrai Progetto Self-Contained in GeoPackage",
                    f"Progetto_v{commit_id}.gpkg", "GeoPackage (*.gpkg)"
                )
                if out:
                    self.export_project_to_gpkg(commit_id, info['timestamp'], out, parent_widget=self.iface.mainWindow())
            else:
                QMessageBox.information(
                    self.iface.mainWindow(), "QGIS Ledger — Commit Progetto ✅",
                    f"Commit Progetto #{commit_id} salvato con successo!\n"
                    f"L'intero progetto .qgz è stato archiviato nello storico.\n"
                    f"Utente: {user}\n\n"
                    f"💡 Ricorda: salva il progetto QGIS (Ctrl+S) per consolidare le modifiche."
                )
            self.status_led.set_status(StatusLED.SYNCED)
            self.timeline_panel.populate_layers()
            self._trigger_cloud_sync(commit_id)
        else:
            QMessageBox.critical(
                self.iface.mainWindow(), "QGIS Ledger",
                "Errore durante il salvataggio del progetto."
            )

    def export_project_to_gpkg(self, cid: int, proj_ts: str, out: str, parent_widget=None):
        """Estrae un progetto dal ledger e lo trasforma in un GeoPackage auto-contenuto e portabile."""
        import shutil
        import os
        import tempfile as _tempfile
        from qgis.core import (
            QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry,
            QgsVectorFileWriter, QgsWkbTypes, Qgis
        )
        import sqlite3

        if not parent_widget:
            parent_widget = self.iface.mainWindow()

        src = os.path.join(self.ledger.history_dir(), "project", f"commit_{cid}.qgz")
        if not os.path.exists(src):
            QMessageBox.warning(parent_widget, "QGIS Ledger", "File di progetto storicizzato non trovato.")
            return

        out_dir = os.path.dirname(out)

        # Leggi il progetto storico in un'istanza separata
        temp_proj = QgsProject()
        if not temp_proj.read(src):
            QMessageBox.critical(parent_widget, "QGIS Ledger", "Errore durante la lettura del progetto storicizzato.")
            return

        # Crea il GPKG container come file vuoto
        conn = sqlite3.connect(out)
        conn.close()

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer

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
                    snap = self.ledger.get_snapshot_features(layer_commit_rec['id'])
                    style_qml = layer_commit_rec.get('style_qml')

                if not snap:
                    live_layer = None
                    for _lid, _l in QgsProject.instance().mapLayers().items():
                        if _l.name() == layer.name() and _l.type() == _l.VectorLayer:
                            live_layer = _l
                            break
                    if live_layer and live_layer.isValid():
                        feats_live = [QgsFeature(f) for f in live_layer.getFeatures()]
                        snap = [
                            {
                                'geometry': f.geometry().asWkt() if f.hasGeometry() else None,
                                'attributes': {
                                    live_layer.fields().field(i).name(): f.attribute(i)
                                    for i in range(live_layer.fields().count())
                                }
                            }
                            for f in feats_live
                        ]
                        layer_ref = live_layer
                    else:
                        errors.append(f"Layer '{layer.name()}': nussuno snapshot nel DB e non trovato nel progetto corrente.")
                        continue
                else:
                    layer_ref = layer

                geom_type_str = "None"
                for item in snap:
                    if item.get('geometry'):
                        wkb = QgsGeometry.fromWkt(item['geometry']).wkbType()
                        if QgsWkbTypes.geometryType(wkb) == QgsWkbTypes.PointGeometry:
                            geom_type_str = "Point"
                        elif QgsWkbTypes.geometryType(wkb) == QgsWkbTypes.LineGeometry:
                            geom_type_str = "LineString"
                        else:
                            geom_type_str = "Polygon"
                        break

                crs_id = layer_ref.crs().authid() or 'EPSG:4326'
                mem_vl = QgsVectorLayer(f"{geom_type_str}?crs={crs_id}", layer.name(), "memory")
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
                        if idx >= 0: feat.setAttribute(idx, val)
                    feats.append(feat)
                mem_pr.addFeatures(feats)

                options.layerName = layer.name()
                QgsVectorFileWriter.writeAsVectorFormatV3(mem_vl, out, temp_proj.transformContext(), options)

                new_uri = f"{out}|layername={layer.name()}"
                layer.setDataSource(new_uri, layer.name(), "ogr")

                if style_qml:
                    tmp = _tempfile.NamedTemporaryFile(suffix=".qml", mode="w", encoding="utf-8", delete=False)
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
                        src_raster = os.path.join(self.ledger.history_dir(), "raster", fp)
                        if os.path.exists(src_raster):
                            ext = os.path.splitext(src_raster)[1]
                            raster_name = f"{layer.name()}_v{layer_commit_rec['id']}{ext}"
                            dest_raster = os.path.join(out_dir, raster_name)
                            shutil.copy2(src_raster, dest_raster)
                            layer.setDataSource(dest_raster, layer.name(), layer.providerType())
                            raster_copied = True
                            if layer_commit_rec.get('style_qml'):
                                tmp = _tempfile.NamedTemporaryFile(suffix=".qml", mode="w", encoding="utf-8", delete=False)
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
                        layer.setDataSource(dest_raster, layer.name(), layer.providerType())
                    else:
                        errors.append(f"Raster '{layer.name()}': file originale non trovato e nessuno snapshot disponibile.")

        try:
            temp_proj.setFilePathStorage(Qgis.FilePathType.Relative)
        except AttributeError: pass

        out_uri = f"geopackage:{out}?projectName=Storico_v{cid}"
        if temp_proj.write(out_uri):
            msg = (
                f"Progetto self-contained esportato con successo!\n(Commit #{cid}):\n{out}\n\n"
                f"💡 Per aprirlo: Progetto › Apri Da › GeoPackage, oppure trascinalo in QGIS."
            )
            if errors: msg += "\n\n⚠️ Avvisi (layer non incorporati):\n" + "\n".join(f"• {e}" for e in errors)
            QMessageBox.information(parent_widget, "QGIS Ledger — Estrazione Progetto ✅", msg)
        else:
            QMessageBox.critical(parent_widget, "QGIS Ledger", "Errore nel salvataggio del progetto nel GeoPackage.")

    def _capture_screenshot(self, commit_id: int):
        """Saves a screenshot of the current map canvas."""
        canvas = self.iface.mapCanvas()
        if not canvas: return
        try:
            folder = os.path.join(self.ledger.history_dir(), "screenshots")
            os.makedirs(folder, exist_ok=True)
            path = os.path.join(folder, f"commit_{commit_id}.png")
            canvas.saveAsImage(path)
        except Exception:
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
            if isinstance(layer, QgsVectorLayer) and layer.name() == layer_name:
                target = layer
                break

        if not target:
            QMessageBox.warning(
                self.iface.mainWindow(), "QGIS Ledger",
                f"Layer '{layer_name}' non trovato nel progetto."
            )
            return

        reply = QMessageBox.question(
            self.iface.mainWindow(), "QGIS Ledger — Preview",
            f"Entrare in modalità preview del commit #{commit_id}?\n"
            f"({info['timestamp']} di {info['user_name']})\n\n"
            f"Il layer verrà ripristinato temporaneamente.\n"
            f"Usa Rollback per confermare, o Ctrl+Z per annullare.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
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
                self.iface.mainWindow(), "QGIS Ledger — Rollback Progetto",
                f"\u26A0 ATTENZIONE: Stai per ripristinare l'intero Progetto QGIS al commit #{commit_id}\n"
                f"({info['timestamp']} di {info['user_name']})\n\n"
                f"Questo sovrascriverà il file .qgz corrente e ricaricherà il progetto.\n"
                f"Vuoi procedere?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

            safety_msg = f"[AUTO] Backup prima di rollback al commit #{commit_id}"
            self.ledger.create_project_commit(safety_msg, LedgerSettings.user_name())

            success = self.ledger.rollback_to(None, commit_id)
            if success:
                QMessageBox.information(
                    self.iface.mainWindow(), "QGIS Ledger",
                    f"Rollback del Progetto completato con successo!\n"
                    f"Il progetto è stato ricaricato allo stato del commit #{commit_id}."
                )
            else:
                QMessageBox.critical(self.iface.mainWindow(), "QGIS Ledger", "Errore durante il rollback del progetto.")
            return

        layer_name = info["layer_name"]
        target = None
        for lid, layer in QgsProject.instance().mapLayers().items():
            if layer.name() == layer_name: # Handle both Vector and Raster
                target = layer
                break

        if not target:
            # Attempt auto-restore if file_path is known
            known_path = info.get("file_path")
            clean_path = known_path
            
            if known_path:
                # Handle GeoPackage/SQLite URIs (e.g. path/to.gpkg|layername=my_layer)
                if "|" in known_path:
                    clean_path = known_path.split("|")[0]
                
                # For Rasters, known_path historically held just the backup filename
                if info.get("commit_type") == "RASTER" and not os.path.isabs(known_path):
                    clean_path = os.path.join(self.ledger.history_dir(), "raster", known_path)
                    known_path = clean_path  # Load directly from backup if original is missing

            if known_path and os.path.exists(clean_path):
                if info.get("commit_type") == "RASTER":
                    target = self.iface.addRasterLayer(known_path, layer_name)
                else:
                    target = self.iface.addVectorLayer(known_path, layer_name, "ogr")

            # Fallback to manual restore if auto-restore fails
            if not target or not target.isValid():
                target = None
                display_path = known_path if known_path else 'Sconosciuto'
                reply = QMessageBox.question(
                    self.iface.mainWindow(), "QGIS Ledger",
                    f"Il layer '{layer_name}' non è presente e non è stato possibile ripristinarlo automaticamente in:\n{display_path}\nVuoi cercarlo manualmente sul disco?",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    file_path, _ = QFileDialog.getOpenFileName(
                        self.iface.mainWindow(), f"Seleziona il file sorgente per il layer '{layer_name}'",
                        QgsProject.instance().homePath(), "Dati Geografici (*.gpkg *.shp *.tif *.geojson);;Tutti i file (*)"
                    )
                    if file_path:
                        if info.get("commit_type") == "RASTER":
                            target = self.iface.addRasterLayer(file_path, layer_name)
                        else:
                            target = self.iface.addVectorLayer(file_path, layer_name, "ogr")
                            
                        if not target or not target.isValid():
                            QMessageBox.warning(self.iface.mainWindow(), "QGIS Ledger", "Impossibile caricare il layer selezionato.")
                            return
                    else:
                        return
                else:
                    return

        reply = QMessageBox.warning(
            self.iface.mainWindow(), "QGIS Ledger — Rollback",
            f"\u26A0 ATTENZIONE: Stai per ripristinare il layer "
            f"'{layer_name}' al commit #{commit_id}\n"
            f"({info['timestamp']} di {info['user_name']})\n\n"
            f"Questa operazione sovrascriverà tutte le feature attuali.\n"
            f"Vuoi procedere?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # First create a safety commit of current state
        safety_msg = f"[AUTO] Backup prima di rollback al commit #{commit_id}"
        if info.get("commit_type") == "RASTER":
            self.ledger.create_raster_commit(target, safety_msg, LedgerSettings.user_name())
        else:
            self.ledger.create_commit(target, safety_msg, LedgerSettings.user_name())

        success = self.ledger.rollback_to(target, commit_id)
        if success:
            # Create a new commit for the rollback state
            rollback_msg = f"Rollback al commit #{commit_id}"
            if info.get("commit_type") == "RASTER":
                self.ledger.create_raster_commit(target, rollback_msg, LedgerSettings.user_name())
            else:
                self.ledger.create_commit(target, rollback_msg, LedgerSettings.user_name())
                
            QMessageBox.information(
                self.iface.mainWindow(), "QGIS Ledger — Rollback Completato ✅",
                f"Rollback completato con successo!\n"
                f"Il layer '{layer_name}' è stato ripristinato allo stato del commit #{commit_id}.\n\n"
                f"⚠️ IMPORTANTE: Salva il progetto QGIS ora (Ctrl+S) per rendere permanente il ripristino!"
            )
            self.timeline_panel.refresh()
        else:
            QMessageBox.critical(
                self.iface.mainWindow(), "QGIS Ledger",
                "Errore durante il rollback."
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
                "Serve almeno 2 commit per calcolare il diff."
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
        dlg.exec_()
        self.timeline_panel.refresh()

    def _on_diff_dialog(self):
        """Open a dialog to select two commits for visual diff."""
        if not self.ledger.is_connected():
            QMessageBox.warning(
                self.iface.mainWindow(), "QGIS Ledger",
                "Nessun database di QGIS Ledger aperto."
            )
            return

        history = self.ledger.get_history()
        if len(history) < 2:
            QMessageBox.information(
                self.iface.mainWindow(), "QGIS Ledger",
                "Serve almeno 2 commit per calcolare il diff."
            )
            return

        dlg = _DiffDialog(history, self.iface.mainWindow())
        if dlg.exec_() == QDialog.Accepted:
            old_id, new_id = dlg.get_selection()
            if old_id and new_id and old_id != new_id:
                self.diff_engine.clear_diff()
                added, removed, modified = self.diff_engine.compute_diff(
                    min(old_id, new_id), max(old_id, new_id)
                )
                layer_name = self.ledger.get_commit_info(old_id).get("layer_name", "Sconosciuto")
                res_dlg = _DiffResultDialog(
                    min(old_id, new_id), max(old_id, new_id), layer_name,
                    added, removed, modified, self.ledger, self.iface.mainWindow()
                )
                res_dlg.exec_()
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
                "Nessun registro attivo in questo progetto."
            )
            return
        
        dlg = _HistoryBrowserDialog(self, self.ledger, self.iface.mainWindow())
        dlg.exec_()

    def _on_settings(self):
        dlg = SettingsDialog(self.iface.mainWindow())
        dlg.exec_()

    def _on_info(self):
        """Show About dialog with plugin version and website info."""
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
                name = cfg.get("general", "name", fallback=name).replace("_", " ").title()
                version = cfg.get("general", "version", fallback=version)
                author = cfg.get("general", "author", fallback=author)
                email = cfg.get("general", "email", fallback=email)
                homepage = cfg.get("general", "homepage", fallback=homepage)
                description = cfg.get("general", "description", fallback=description)

        # Build rich HTML content
        plugin_logo_path = os.path.join(plugin_dir, "logoplugin.jpg")
        plugin_logo_url = f"file:///{os.path.abspath(plugin_logo_path).replace(os.sep, '/')}"
        
        author_logo_path = os.path.join(plugin_dir, "sinocloud-logo.png")
        author_logo_url = f"file:///{os.path.abspath(author_logo_path).replace(os.sep, '/')}"
        
        info_html = (
            f'<div style="text-align:center;padding:10px;">'
            f'<img src="{plugin_logo_url}" width="140" style="margin-bottom:10px; border-radius: 6px;"/><br>'
            f'<h2 style="color:#3498db;margin-bottom:2px;">\U0001F6E1\uFE0F {name}</h2>'
            f'<p style="color:#95a5a6;font-size:12px;margin-top:0;">'
            f'Intelligent Versioning for QGIS</p>'
            f'<hr style="border:1px solid #34495e;"/>'
            f'<table style="margin:auto;font-size:13px;">'
            f'<tr><td style="padding:4px 12px;color:#bdc3c7;"><b>Versione:</b></td>'
            f'<td style="padding:4px 12px;color:#2ecc71;font-weight:bold;">{version}</td></tr>'
            f'<tr><td style="padding:4px 12px;color:#bdc3c7;"><b>Autore:</b></td>'
            f'<td style="padding:4px 12px;color:#ecf0f1;">'
            f'<img src="{author_logo_url}" height="18" style="vertical-align:middle; margin-right:6px;"/>{author}</td></tr>'
        )
        if email:
            info_html += (
                f'<tr><td style="padding:4px 12px;color:#bdc3c7;"><b>Email:</b></td>'
                f'<td style="padding:4px 12px;"><a href="mailto:{email}" '
                f'style="color:#3498db;">{email}</a></td></tr>'
            )
        if homepage:
            info_html += (
                f'<tr><td style="padding:4px 12px;color:#bdc3c7;"><b>Sito Web:</b></td>'
                f'<td style="padding:4px 12px;"><a href="{homepage}" '
                f'style="color:#3498db;">{homepage}</a></td></tr>'
            )
        info_html += (
            f'</table>'
            f'<hr style="border:1px solid #34495e;"/>'
            f'<p style="color:#bdc3c7;font-size:11px;padding:4px 16px;">{description}</p>'
            f'</div>'
        )

        dlg = QDialog(self.iface.mainWindow())
        dlg.setWindowTitle("QGIS Ledger — Info & Attività")
        dlg.setMinimumWidth(500)
        dlg.setMinimumHeight(350)
        dlg.setStyleSheet(
            "QDialog{background:#2c3e50;}"
            "QLabel{color:#ecf0f1;}"
        )
        layout = QVBoxLayout(dlg)
        
        tabs = QTabWidget()
        tabs.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #34495e; background: #2c3e50; }"
            "QTabBar::tab { background: #34495e; color: #ecf0f1; padding: 6px 12px; margin-right: 2px; border-top-left-radius: 4px; border-top-right-radius: 4px; }"
            "QTabBar::tab:selected { background: #3498db; font-weight: bold; }"
            "QTabBar::tab:hover { background: #2980b9; }"
        )
        layout.addWidget(tabs)
        
        # Tab 1: Info
        tab_info = QWidget()
        lay_info = QVBoxLayout(tab_info)
        lbl = QLabel(info_html)
        lbl.setOpenExternalLinks(True)
        lbl.setWordWrap(True)
        lay_info.addWidget(lbl)
        tabs.addTab(tab_info, "\u2139\uFE0F Info Plugin")
        
        # Tab 2: Attività (Alerts)
        tab_activity = QWidget()
        lay_act = QVBoxLayout(tab_activity)
        
        if not self.ledger.is_connected():
            lbl_conn = QLabel("⚠️ Database chiuso. Apri/salva il progetto per vedere l'attività.")
            lbl_conn.setAlignment(Qt.AlignCenter)
            lay_act.addWidget(lbl_conn)
        else:
            history = self.ledger.get_history()
            me = LedgerSettings.user_name()
            my_machine = platform.node() if hasattr(platform, 'node') else ""
            
            others_commits = [
                c for c in history 
                if c["user_name"] != me or (my_machine and c.get("machine", "") != my_machine)
            ]
            
            if not others_commits:
                lbl_no_act = QLabel("Nessuna modifica recente da altri mod_user o postazioni.")
                lbl_no_act.setAlignment(Qt.AlignCenter)
                lbl_no_act.setStyleSheet("color: #7f8c8d; font-style: italic;")
                lay_act.addWidget(lbl_no_act)
            else:
                lbl_act_title = QLabel(f"Trovate {len(others_commits)} modifiche da mod_user/altre postazioni:")
                lbl_act_title.setStyleSheet("font-weight: bold; margin-bottom: 5px;")
                lay_act.addWidget(lbl_act_title)
                
                table = QTableWidget(len(others_commits), 4)
                table.setHorizontalHeaderLabels(["Data", "Utente", "Postazione", "Layer modified"])
                table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
                table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
                table.setEditTriggers(QTableWidget.NoEditTriggers)
                table.setSelectionBehavior(QTableWidget.SelectRows)
                table.setStyleSheet(
                    "QTableWidget { background: #34495e; color: #ecf0f1; border: none; gridline-color: #2c3e50; }"
                    "QHeaderView::section { background: #2980b9; color: white; padding: 4px; border: 1px solid #2c3e50; font-weight: bold; }"
                )
                
                for r, c in enumerate(others_commits):
                    # date format YYYY-MM-DD HH:MM
                    date_str = c["timestamp"][:16].replace("T", " ")
                    item_date = QTableWidgetItem(date_str)
                    item_user = QTableWidgetItem(c["user_name"])
                    item_mach = QTableWidgetItem(c.get("machine", "Sconosciuto"))
                    item_layer = QTableWidgetItem(c["layer_name"])
                    
                    table.setItem(r, 0, item_date)
                    table.setItem(r, 1, item_user)
                    table.setItem(r, 2, item_mach)
                    table.setItem(r, 3, item_layer)
                
                lay_act.addWidget(table)
                
        tabs.addTab(tab_activity, "🔔 Notifiche mod_user")

        btn_close = QPushButton("Chiudi")
        btn_close.setStyleSheet(
            "QPushButton{background:#3498db;color:white;border:none;"
            "border-radius:4px;padding:8px 24px;font-weight:bold;}"
            "QPushButton:hover{background:#2980b9;}"
        )
        btn_close.clicked.connect(dlg.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignCenter)

        dlg.exec_()

    def _on_sync(self):
        """Check for external changes to the database."""
        if not self.ledger.is_connected():
            QMessageBox.warning(
                self.iface.mainWindow(), "QGIS Ledger",
                "Nessun database di QGIS Ledger aperto."
            )
            return

        if self.sync.check_for_updates():
            self.status_led.set_status(StatusLED.MODIFIED)
            QMessageBox.information(
                self.iface.mainWindow(), "QGIS Ledger",
                "Modifiche esterne rilevate nel database.\n"
                "La timeline è stata aggiornata."
            )
            self.timeline_panel.refresh()
        else:
            self.iface.messageBar().pushInfo(
                "QGIS Ledger", "Nessuna modifica esterna rilevata."
            )

    def _toggle_main_panel(self, checked: bool):
        """Show or hide the unified main panel (Timeline + Nextcloud)."""
        if not self.main_panel:
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
                self.tab_widget.setCurrentIndex(0) # Switch to Timeline
                self.timeline_panel.populate_layers()

    def _check_sync(self):
        """Periodic check for external database changes."""
        if self.sync.is_watching() and self.sync.check_for_updates():
            self.status_led.set_status(StatusLED.MODIFIED)

    def _toggle_autosave(self, checked: bool):
        """Start or stop the auto-save timer."""
        if checked:
            interval_min = LedgerSettings.autosave_interval()
            self._autosave_timer = QTimer()
            self._autosave_timer.timeout.connect(self._do_autosave)
            self._autosave_timer.start(interval_min * 60 * 1000)
            self.iface.messageBar().pushInfo(
                "QGIS Ledger — Auto-Save ⏱️",
                f"Auto-Save attivato! Salvataggio automatico ogni {interval_min} minuti."
            )
        else:
            if self._autosave_timer:
                self._autosave_timer.stop()
                self._autosave_timer = None
            self.iface.messageBar().pushInfo(
                "QGIS Ledger — Auto-Save ⏱️",
                "Auto-Save disattivato."
            )

    def _do_autosave(self):
        """Timer callback: auto-commit all modified layers and save the project."""
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
            self.iface.messageBar().pushInfo(
                "QGIS Ledger — Auto-Save ⏱️ ✅",
                f"Auto-Save completato: {committed} layer committati e progetto salvato."
            )
            self.status_led.set_status(StatusLED.SYNCED)
            self.timeline_panel.populate_layers()
        else:
            self.iface.messageBar().pushInfo(
                "QGIS Ledger — Auto-Save ⏱️",
                "Auto-Save completato: nessuna modifica rilevata. Progetto salvato."
            )


# ====================================================================== #
# Diff selection dialog
# ====================================================================== #

class _DiffDialog(QDialog):
    """Simple dialog to select two commits for comparison."""

    def __init__(self, history, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QGIS Ledger — Seleziona Commit per Diff")
        self.setMinimumWidth(500)
        self.history = history
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        lbl = QLabel(
            "<b>Seleziona due versioni da confrontare:</b>"
        )
        lbl.setStyleSheet("color:#ecf0f1;font-size:13px;padding:6px;")
        layout.addWidget(lbl)

        # Commit A (old)
        row_a = QHBoxLayout()
        row_a.addWidget(QLabel("Versione A (vecchia):"))
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
        row_b.addWidget(QLabel("Versione B (nuova):"))
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
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setStyleSheet(
            "QDialog{background:#2c3e50;}"
            "QLabel{color:#ecf0f1;}"
            "QComboBox{background:#34495e;color:#ecf0f1;"
            "border:1px solid #636e72;border-radius:4px;padding:4px;}"
        )

    def get_selection(self):
        return (
            self.cmb_a.currentData(),
            self.cmb_b.currentData(),
        )


class _DiffResultDialog(QDialog):
    """Dialog showing diff results with Extract and Replace actions."""
    
    def __init__(self, old_id, new_id, layer_name, added, removed, modified, ledger, parent=None):
        super().__init__(parent)
        self.old_id = old_id
        self.new_id = new_id
        self.layer_name = layer_name
        self.added = added
        self.removed = removed
        self.modified = modified
        self.ledger = ledger
        self.setWindowTitle("QGIS Ledger — Risultati Diff")
        self.setMinimumWidth(400)
        self._build_ui()
        
    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        lbl_title = QLabel(f"<b>Diff tra commit #{self.old_id} e #{self.new_id}</b><br/>Layer: <i>{self.layer_name}</i>")
        layout.addWidget(lbl_title)
        
        lbl_stats = QLabel(
            f"<ul>"
            f"<li>\U0001F7E2 <b>Aggiunte:</b> {self.added}</li>"
            f"<li>\U0001F534 <b>Rimosse:</b> {self.removed}</li>"
            f"<li>\U0001F7E0 <b>Modificate:</b> {self.modified}</li>"
            f"</ul>"
            f"<i>I layer temporanei per visualizzare queste differenze sono stati aggiunti alla mappa.</i>"
        )
        layout.addWidget(lbl_stats)
        
        # Action Buttons
        layout.addSpacing(10)
        lbl_actions = QLabel("<b>Azioni rapide sulla vecchia versione (#{}):</b>".format(self.old_id))
        layout.addWidget(lbl_actions)
        
        btn_layout = QHBoxLayout()
        
        btn_extract = QPushButton("\U0001F4E5 Estrai Versione")
        btn_extract.setToolTip("Salva la vecchia versione come un nuovo file sul disco")
        btn_extract.setStyleSheet("padding: 8px; font-weight: bold;")
        btn_extract.clicked.connect(self._on_extract)
        btn_layout.addWidget(btn_extract)
        
        btn_replace = QPushButton("\U0001F504 Sostituisci corrente")
        btn_replace.setToolTip("Esegui un Rollback immediato a questa vecchia versione")
        btn_replace.setStyleSheet("padding: 8px; font-weight: bold; color: #c0392b;")
        btn_replace.clicked.connect(self._on_replace)
        btn_layout.addWidget(btn_replace)
        
        layout.addLayout(btn_layout)
        
        layout.addSpacing(10)
        btn_close = QPushButton("Chiudi finestra")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)

    def _on_extract(self):
        """Export the old snapshot to a standard Geopackage."""
        snap = self.ledger.get_snapshot_features(self.old_id)
        if not snap:
            QMessageBox.warning(self, "QGIS Ledger", "Impossibile caricare snapshot.")
            return
            
        filename, _ = QFileDialog.getSaveFileName(
            self, "Estrai Versione come GeoPackage", 
            f"{self.layer_name}_v{self.old_id}.gpkg", 
            "GeoPackage (*.gpkg)"
        )
        if not filename: return
        
        # Find original layer logic to duplicate structure
        target = None
        for lid, layer in QgsProject.instance().mapLayers().items():
            if layer.name() == self.layer_name and layer.type() == layer.VectorLayer:
                target = layer
                break
                
        if not target:
            QMessageBox.warning(self, "QGIS Ledger", "Sorgente originaria non trovata. Impossibile copiare schema.")
            return

        from qgis.core import QgsVectorFileWriter, QgsCoordinateReferenceSystem
        # Save exact layer with current snapshot features
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = f"{self.layer_name}_v{self.old_id}"
        
        # We write to a temporary memory layer first
        from qgis.core import QgsVectorLayer
        temp_vl = QgsVectorLayer(target.source().split("?")[0], "temp", "memory")
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
                if idx >= 0: feat.setAttribute(idx, val)
            feats.append(feat)
            
        temp_pr.addFeatures(feats)
        
        # Now write out
        result = QgsVectorFileWriter.writeAsVectorFormatV3(
            temp_vl, filename, QgsProject.instance().transformContext(), options
        )
        err = result[0] if isinstance(result, tuple) else result
        
        if err == QgsVectorFileWriter.NoError:
            QMessageBox.information(self, "QGIS Ledger", f"Versione estratta e salvata in:\n{filename}")
            self.accept()
        else:
            QMessageBox.critical(self, "QGIS Ledger", f"Errore scrittura:\n{error_msg}")

    def _on_replace(self):
        """Invoke rollback."""
        reply = QMessageBox.warning(
            self, "QGIS Ledger — Sostituisci",
            f"Vuoi davvero sovrascrivere lo stato corrente del layer '{self.layer_name}' "
            f"con il layout del commit #{self.old_id}?\n\nQuesta operazione è irreversibile.",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            target = None
            for lid, layer in QgsProject.instance().mapLayers().items():
                if layer.name() == self.layer_name and layer.type() == layer.VectorLayer:
                    target = layer
                    break

            if not target:
                # PHASE 13: Layer not in map. Auto-restore from known path or extract from DB to temp file.
                info = self.ledger.get_commit_info(self.old_id)
                known_path = info.get("file_path")
                import os
                from qgis.utils import iface
                
                if known_path and os.path.exists(known_path):
                    target = iface.addVectorLayer(known_path, self.layer_name, "ogr")
                
                if not target or not target.isValid():
                    # Fallback Extraction
                    import tempfile
                    from qgis.core import QgsVectorLayer, QgsFeature, QgsGeometry, QgsVectorFileWriter, QgsFields, QgsField, QgsWkbTypes
                    from qgis.PyQt.QtCore import QVariant
                    
                    temp_dir = tempfile.gettempdir()
                    filename = os.path.join(temp_dir, f"{self.layer_name}_restored.gpkg")
                    
                    snap = self.ledger.get_snapshot_features(self.old_id)
                    if not snap:
                        QMessageBox.warning(self, "QGIS Ledger", "Sorgente non trovata e snapshot DB vuoto.")
                        return
                    
                    fields = QgsFields()
                    if len(snap) > 0:
                        for k, v in snap[0]["attributes"].items():
                            if isinstance(v, int): fields.append(QgsField(k, QVariant.Int))
                            elif isinstance(v, float): fields.append(QgsField(k, QVariant.Double))
                            else: fields.append(QgsField(k, QVariant.String))
                            
                    geom_type_str = "Polygon"
                    for item in snap:
                        if item["geometry"]:
                            wkb = QgsGeometry.fromWkt(item["geometry"]).wkbType()
                            if QgsWkbTypes.geometryType(wkb) == QgsWkbTypes.PointGeometry: geom_type_str = "Point"
                            elif QgsWkbTypes.geometryType(wkb) == QgsWkbTypes.LineGeometry: geom_type_str = "LineString"
                            break
                    
                    temp_vl = QgsVectorLayer(f"{geom_type_str}?crs=EPSG:4326", "temp", "memory")
                    temp_pr = temp_vl.dataProvider()
                    temp_pr.addAttributes(fields)
                    temp_vl.updateFields()
                    
                    feats = []
                    for item in snap:
                        feat = QgsFeature(temp_vl.fields())
                        if item["geometry"]: feat.setGeometry(QgsGeometry.fromWkt(item["geometry"]))
                        for fname, val in item["attributes"].items():
                            idx = temp_vl.fields().lookupField(fname)
                            if idx >= 0: feat.setAttribute(idx, val)
                        feats.append(feat)
                    
                    temp_pr.addFeatures(feats)
                    
                    options = QgsVectorFileWriter.SaveVectorOptions()
                    options.driverName = "GPKG"
                    options.layerName = self.layer_name
                    result = QgsVectorFileWriter.writeAsVectorFormatV3(temp_vl, filename, QgsProject.instance().transformContext(), options)
                    err = result[0] if isinstance(result, tuple) else result
                    
                    if err == QgsVectorFileWriter.NoError:
                        target = iface.addVectorLayer(filename, self.layer_name, "ogr")
                        QMessageBox.information(self, "QGIS Ledger — Ripristino dal DB ✅",
                            f"Layer '{self.layer_name}' ricostruito dai dati storici del database e caricato in mappa.\n\n"
                            f"⚠️ IMPORTANTE: Salva il progetto QGIS ora (Ctrl+S) per rendere permanente il ripristino!")
                    else:
                        QMessageBox.warning(self, "QGIS Ledger", "Errore nella ricostruzione del layer dal database.")
                        return

            if target and target.isValid():
                success = self.ledger.rollback_to(target, self.old_id)
                if success:
                    user = LedgerSettings.user_name()
                    self.ledger.create_commit(target, f"Sostituito con '#{self.old_id}' da Diff", user)
                    QMessageBox.information(self, "QGIS Ledger — Sostituzione Completata ✅",
                        f"Il layer '{self.layer_name}' è stato aggiornato allo stato del commit #{self.old_id}.\n\n"
                        f"⚠️ IMPORTANTE: Salva il progetto QGIS ora (Ctrl+S) per rendere permanente la sostituzione!"
                    )
                    self.accept()
                else:
                    QMessageBox.critical(self, "QGIS Ledger", "Errore durante rollback.")
            else:
                QMessageBox.warning(self, "QGIS Ledger", "Layer non trovato nel progetto attuale.")

class _HistoryBrowserDialog(QDialog):
    """Dialog to list all historical files and allow extraction or map loading."""
    def __init__(self, plugin, ledger, parent=None):
        super().__init__(parent)
        self.plugin = plugin
        self.ledger = ledger
        self.setWindowTitle("QGIS Ledger — Esplora Storico File")
        self.resize(700, 450)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMaximizeButtonHint)
        self._build_ui()
        self._load_data()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        
        lbl_info = QLabel("<b>Archivio Completo File Storici</b><br>Seleziona un salvataggio dal passato per estrarlo sul tuo computer o caricarlo in mappa.")
        layout.addWidget(lbl_info)
        
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels([
            "ID", "Tipo", "Nome", "Data", "Utente", "Path Originale"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.table)
        
        # Action Buttons
        btn_layout = QHBoxLayout()
        
        self.btn_extract = QPushButton("⬇️ Estrai File / Salva con nome...")
        self.btn_extract.setStyleSheet("padding: 6px; font-weight: bold;")
        self.btn_extract.clicked.connect(self._on_extract)
        btn_layout.addWidget(self.btn_extract)
        
        self.btn_load = QPushButton("🗺️ Carica in QGIS come Layer isolato")
        self.btn_load.setStyleSheet("padding: 6px; font-weight: bold; color: #27ae60;")
        self.btn_load.clicked.connect(self._on_load_map)
        btn_layout.addWidget(self.btn_load)
        
        btn_layout.addStretch()
        
        btn_close = QPushButton("Chiudi")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        
        layout.addLayout(btn_layout)

    def _load_data(self):
        history = self.ledger.get_history(None)
        self.table.setRowCount(len(history))
        for row, commit in enumerate(history):
            self.table.setItem(row, 0, QTableWidgetItem(f"#{commit['id']}"))
            self.table.item(row, 0).setData(Qt.UserRole, commit)
            
            self.table.setItem(row, 1, QTableWidgetItem(commit.get('commit_type', 'VECTOR')))
            self.table.setItem(row, 2, QTableWidgetItem(commit['layer_name']))
            self.table.setItem(row, 3, QTableWidgetItem(commit['timestamp']))
            self.table.setItem(row, 4, QTableWidgetItem(commit['user_name']))
            self.table.setItem(row, 5, QTableWidgetItem(commit.get('file_path', 'N/D')))

    def get_selected_commit(self):
        sel = self.table.selectedItems()
        if not sel: return None
        return self.table.item(sel[0].row(), 0).data(Qt.UserRole)

    def _on_extract(self):
        commit = self.get_selected_commit()
        if not commit: return
        
        cid = commit['id']
        ctype = commit.get('commit_type', 'VECTOR')
        name = commit['layer_name']
        
        if ctype == 'PROJECT':
            out, _ = QFileDialog.getSaveFileName(
                self, "Estrai Progetto Self-Contained in GeoPackage",
                f"{name}_v{cid}.gpkg", "GeoPackage (*.gpkg)"
            )
            if not out:
                return
            
            # Delega l'estrazione alla classe principale del plugin
            self.plugin.export_project_to_gpkg(cid, commit['timestamp'], out, parent_widget=self)
                
        elif ctype == 'RASTER':
            import shutil
            import glob
            import os
            
            base = os.path.join(self.ledger.history_dir(), "raster", f"commit_{cid}_*")
            files = glob.glob(base)
            if not files:
                QMessageBox.warning(self, "QGIS Ledger", "File raster storicizzato non trovato.")
                return
                
            src = files[0]
            ext = os.path.splitext(src)[1]
            out, _ = QFileDialog.getSaveFileName(self, "Estrai Raster", f"{name}_v{cid}{ext}", f"Raster (*{ext})")
            if out:
                shutil.copy2(src, out)
                QMessageBox.information(self, "QGIS Ledger — Estrazione Raster ✅",
                    f"Il file raster del commit #{cid} è stato estratto con successo in:\n{out}\n\n"
                    f"💡 Puoi caricarlo in QGIS con Layer > Aggiungi Layer Raster.")
                
        elif ctype == 'VECTOR':
            # Needs to extract from DB snapshot
            snap = self.ledger.get_snapshot_features(cid)
            if not snap:
                QMessageBox.warning(self, "QGIS Ledger", "Impossibile caricare snapshot.")
                return
                
            out, _ = QFileDialog.getSaveFileName(self, "Estrai Vettore come GeoPackage", f"{name}_v{cid}.gpkg", "GeoPackage (*.gpkg)")
            if not out: return
            
            from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsVectorFileWriter, QgsFields, QgsField, QgsWkbTypes
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
                    if isinstance(v, int): fields.append(QgsField(k, QVariant.Int))
                    elif isinstance(v, float): fields.append(QgsField(k, QVariant.Double))
                    else: fields.append(QgsField(k, QVariant.String))
                    
            geom_type_str = "Polygon"
            for item in snap:
                if item["geometry"]:
                    wkb = QgsGeometry.fromWkt(item["geometry"]).wkbType()
                    if QgsWkbTypes.geometryType(wkb) == QgsWkbTypes.PointGeometry: geom_type_str = "Point"
                    elif QgsWkbTypes.geometryType(wkb) == QgsWkbTypes.LineGeometry: geom_type_str = "LineString"
                    break
                    
            temp_vl = QgsVectorLayer(f"{geom_type_str}?crs=EPSG:4326", "temp", "memory")
            temp_pr = temp_vl.dataProvider()
            temp_pr.addAttributes(fields)
            temp_vl.updateFields()
            
            feats = []
            for item in snap:
                feat = QgsFeature(temp_vl.fields())
                if item["geometry"]: feat.setGeometry(QgsGeometry.fromWkt(item["geometry"]))
                for fname, val in item["attributes"].items():
                    idx = temp_vl.fields().lookupField(fname)
                    if idx >= 0: feat.setAttribute(idx, val)
                feats.append(feat)
                
            temp_pr.addFeatures(feats)
            
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "GPKG"
            options.layerName = f"{name}_v{cid}"
            result = QgsVectorFileWriter.writeAsVectorFormatV3(temp_vl, out, QgsProject.instance().transformContext(), options)
            err = result[0] if isinstance(result, tuple) else result
            if err == QgsVectorFileWriter.NoError:
                QMessageBox.information(self, "QGIS Ledger — Estrazione Vettore ✅",
                    f"Il vettore '{name}' del commit #{cid} è stato estratto con successo in:\n{out}\n\n"
                    f"💡 Puoi caricarlo in QGIS con Layer > Aggiungi Layer Vettoriale.")
            else:
                QMessageBox.critical(self, "QGIS Ledger", f"Errore scrittura:\n{msg}")

    def _on_load_map(self):
        commit = self.get_selected_commit()
        if not commit: return
        
        cid = commit['id']
        ctype = commit.get('commit_type', 'VECTOR')
        name = commit['layer_name']
        
        if ctype == 'PROJECT':
            QMessageBox.warning(self, "QGIS Ledger", "Impossibile caricare un intero Progetto come singolo Layer. Usa la funzione Estrai.")
            return
            
        elif ctype == 'RASTER':
            import glob
            import os
            from qgis.utils import iface
            
            base = os.path.join(self.ledger.history_dir(), "raster", f"commit_{cid}_*")
            files = glob.glob(base)
            if not files:
                QMessageBox.warning(self, "QGIS Ledger", "File raster storicizzato non trovato.")
                return
            src = files[0]
            iface.addRasterLayer(src, f"{name} (v{cid})")
            QMessageBox.information(self, "QGIS Ledger — Raster Caricato ✅",
                f"Il raster '{name}' (versione #{cid}) è stato aggiunto alla mappa come layer isolato.\n\n"
                f"💡 Ricorda: salva il progetto QGIS (Ctrl+S) se vuoi conservare questo layer nella sessione.")
            
        elif ctype == 'VECTOR':
            import os
            from qgis.utils import iface
            
            snap = self.ledger.get_snapshot_features(cid)
            if not snap:
                QMessageBox.warning(self, "QGIS Ledger", "Impossibile caricare snapshot.")
                return
                
            import tempfile
            from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsGeometry, QgsVectorFileWriter, QgsField, QgsFields, QgsWkbTypes
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
                    if isinstance(v, int): fields.append(QgsField(k, QVariant.Int))
                    elif isinstance(v, float): fields.append(QgsField(k, QVariant.Double))
                    else: fields.append(QgsField(k, QVariant.String))
                    
            geom_type_str = "Polygon"
            for item in snap:
                if item["geometry"]:
                    wkb = QgsGeometry.fromWkt(item["geometry"]).wkbType()
                    if QgsWkbTypes.geometryType(wkb) == QgsWkbTypes.PointGeometry: geom_type_str = "Point"
                    elif QgsWkbTypes.geometryType(wkb) == QgsWkbTypes.LineGeometry: geom_type_str = "LineString"
                    break
                
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "GPKG"
            options.layerName = f"{name}_v{cid}"
            
            temp_vl = QgsVectorLayer(f"{geom_type_str}?crs=EPSG:4326", "temp", "memory")
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
                    if idx >= 0: feat.setAttribute(idx, val)
                feats.append(feat)
                
            temp_pr.addFeatures(feats)
            result = QgsVectorFileWriter.writeAsVectorFormatV3(temp_vl, filename, QgsProject.instance().transformContext(), options)
            err = result[0] if isinstance(result, tuple) else result
            
            if err == QgsVectorFileWriter.NoError:
                iface.addVectorLayer(filename, f"{name} (v{cid})", "ogr")
                QMessageBox.information(self, "QGIS Ledger — Vettore Caricato ✅",
                    f"Il vettore '{name}' (versione #{cid}) è stato caricato in mappa come layer temporaneo (estratto dal DB).\n\n"
                    f"💡 Ricorda: salva il progetto QGIS (Ctrl+S) se vuoi conservare questo layer nella sessione.")
            else:
                QMessageBox.critical(self, "QGIS Ledger", "Errore nell'estrazione del vettore per il caricamento.")
