# -*- coding: utf-8 -*-
"""
ledger_settings.py — Settings Dialog for QGIS Ledger

Cloud storage providers supported:
  - Locale / LAN
  - Nextcloud / ownCloud (WebDAV)
  - WebDAV Generico (Box · Koofr · pCloud · NAS…)
  - Dropbox (API v2 — Access Token)
  - OneDrive / SharePoint (Microsoft Graph API — Access Token)
  - Google Drive (API v3 — Access Token + optional Refresh Token)
"""

from qgis.PyQt.QtCore import Qt, QSettings
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QCheckBox, QPushButton,
    QGroupBox, QDialogButtonBox, QComboBox, QSpinBox, QScrollArea, QWidget,
)


SETTINGS_PREFIX = "qgis_ledger/"


class LedgerSettings:
    """Read / write plugin settings via QSettings."""

    @staticmethod
    def get(key, default=None):
        return QSettings().value(SETTINGS_PREFIX + key, default)

    @staticmethod
    def set(key, value):
        QSettings().setValue(SETTINGS_PREFIX + key, value)

    @staticmethod
    def user_name():
        import getpass
        val = LedgerSettings.get("user_name", "")
        if not val or not str(val).strip():
            return getpass.getuser()
        return str(val).strip()

    @staticmethod
    def auto_commit():
        val = LedgerSettings.get("auto_commit", "false")
        return val == "true" or val is True

    # -- Remote type --------------------------------------------------- #
    @staticmethod
    def remote_type():
        return LedgerSettings.get("remote_type", "locale")

    @staticmethod
    def remote_path():
        return LedgerSettings.get("remote_path", "")

    # -- Nextcloud ----------------------------------------------------- #
    @staticmethod
    def nextcloud_server():
        return LedgerSettings.get("nextcloud_server", "")

    @staticmethod
    def nextcloud_folder():
        return LedgerSettings.get("nextcloud_folder", "")

    @staticmethod
    def nextcloud_user():
        return LedgerSettings.get("nextcloud_user", "")

    @staticmethod
    def nextcloud_password():
        return LedgerSettings.get("nextcloud_password", "")

    # -- Generic WebDAV ------------------------------------------------ #
    @staticmethod
    def webdav_url():
        return LedgerSettings.get("webdav_url", "")

    @staticmethod
    def webdav_user():
        return LedgerSettings.get("webdav_user", "")

    @staticmethod
    def webdav_password():
        return LedgerSettings.get("webdav_password", "")

    # -- Dropbox ------------------------------------------------------- #
    @staticmethod
    def dropbox_token():
        return LedgerSettings.get("dropbox_token", "")

    @staticmethod
    def dropbox_folder():
        return LedgerSettings.get("dropbox_folder", "")

    # -- OneDrive ------------------------------------------------------ #
    @staticmethod
    def onedrive_token():
        return LedgerSettings.get("onedrive_token", "")

    @staticmethod
    def onedrive_folder():
        return LedgerSettings.get("onedrive_folder", "")

    # -- Google Drive -------------------------------------------------- #
    @staticmethod
    def gdrive_access_token():
        return LedgerSettings.get("gdrive_access_token", "")

    @staticmethod
    def gdrive_refresh_token():
        return LedgerSettings.get("gdrive_refresh_token", "")

    @staticmethod
    def gdrive_client_id():
        return LedgerSettings.get("gdrive_client_id", "")

    @staticmethod
    def gdrive_client_secret():
        return LedgerSettings.get("gdrive_client_secret", "")

    @staticmethod
    def gdrive_folder_id():
        return LedgerSettings.get("gdrive_folder_id", "root")

    # -- Auto-save ----------------------------------------------------- #
    @staticmethod
    def autosave_interval():
        val = LedgerSettings.get("autosave_interval", 5)
        try:
            return max(1, int(val))
        except (ValueError, TypeError):
            return 5

    # -- Cloud client factory ------------------------------------------ #
    @staticmethod
    def get_cloud_client():
        """
        Returns the appropriate cloud backend client based on current settings.
        Returns None for locale.
        """
        rtype = LedgerSettings.remote_type()
        if rtype == "webdav":
            from .ledger_nextcloud import NextcloudClient
            return NextcloudClient(
                LedgerSettings.nextcloud_server(),
                LedgerSettings.nextcloud_user(),
                LedgerSettings.nextcloud_password(),
                LedgerSettings.nextcloud_folder(),
            )
        elif rtype == "generic_webdav":
            from .ledger_nextcloud import GenericWebDAVClient
            return GenericWebDAVClient(
                LedgerSettings.webdav_url(),
                LedgerSettings.webdav_user(),
                LedgerSettings.webdav_password(),
            )
        elif rtype == "dropbox":
            from .ledger_nextcloud import DropboxClient
            return DropboxClient(
                LedgerSettings.dropbox_token(),
                LedgerSettings.dropbox_folder(),
            )
        elif rtype == "onedrive":
            from .ledger_nextcloud import OneDriveClient
            return OneDriveClient(
                LedgerSettings.onedrive_token(),
                LedgerSettings.onedrive_folder(),
            )
        elif rtype == "google_drive":
            from .ledger_nextcloud import GoogleDriveClient
            return GoogleDriveClient(
                LedgerSettings.gdrive_access_token(),
                LedgerSettings.gdrive_refresh_token(),
                LedgerSettings.gdrive_client_id(),
                LedgerSettings.gdrive_client_secret(),
                LedgerSettings.gdrive_folder_id(),
            )
        return None


class SettingsDialog(QDialog):
    """Settings dialog for QGIS Ledger."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QGIS Ledger — Impostazioni")
        self.setMinimumWidth(560)
        self.setMinimumHeight(500)
        self._build_ui()
        self._load()
        self._toggle_cloud_fields()

    def _build_ui(self):
        outer = QVBoxLayout(self)

        # Scroll area for long content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner_widget = QWidget()
        layout = QVBoxLayout(inner_widget)
        scroll.setWidget(inner_widget)
        outer.addWidget(scroll)

        # -- General --------------------------------------------------- #
        grp_general = QGroupBox("Generale")
        form = QFormLayout()

        self.txt_user = QLineEdit()
        self.txt_user.setPlaceholderText("Nome utente (default: login OS)")
        form.addRow("Nome Utente:", self.txt_user)

        self.chk_auto = QCheckBox("Commit automatico al salvataggio del layer")
        form.addRow(self.chk_auto)

        grp_general.setLayout(form)
        layout.addWidget(grp_general)

        # -- Auto-Save ------------------------------------------------- #
        grp_timer = QGroupBox("Auto-Save Automatico")
        form_timer = QFormLayout()
        self.spn_interval = QSpinBox()
        self.spn_interval.setRange(1, 120)
        self.spn_interval.setSuffix(" min")
        form_timer.addRow("Intervallo Auto-Save:", self.spn_interval)
        grp_timer.setLayout(form_timer)
        layout.addWidget(grp_timer)

        # -- Cloud ----------------------------------------------------- #
        grp_cloud = QGroupBox("Archiviazione Cloud")
        form_cloud = QFormLayout()

        self.cmb_cloud_type = QComboBox()
        self.cmb_cloud_type.addItem("Locale / Rete LAN",              "locale")
        self.cmb_cloud_type.addItem("☁ Nextcloud / ownCloud (WebDAV)", "webdav")
        self.cmb_cloud_type.addItem("☁ WebDAV Generico (Box · Koofr · pCloud · NAS…)", "generic_webdav")
        self.cmb_cloud_type.addItem("☁ Dropbox (API v2)",             "dropbox")
        self.cmb_cloud_type.addItem("☁ OneDrive / SharePoint (Graph)",  "onedrive")
        self.cmb_cloud_type.addItem("☁ Google Drive (API v3)",        "google_drive")
        self.cmb_cloud_type.currentIndexChanged.connect(self._toggle_cloud_fields)
        form_cloud.addRow("Tipo Archiviazione:", self.cmb_cloud_type)

        # ── Locale ────────────────────────────────────────────────────── #
        self.txt_remote_path = QLineEdit()
        self.txt_remote_path.setPlaceholderText("Percorso (Opzionale: di default salva nel progetto)")
        self.lbl_remote_path = QLabel("Cartella Locale/LAN (Overwrite):")
        
        self.lbl_locale_info = QLabel(
            "<i>Nota: Di default tutte le versioni e le estrazioni vengono salvate<br>"
            "nella cartella nascosta <code>.ledger_history</code> creata a fianco del tuo<br>"
            "progetto <code>.qgz</code>. Se lavori in rete LAN, lo storico resterà<br>"
            "condiviso con il progetto. Compila questo campo solo se desideri<br>"
            "forzare il salvataggio in un percorso diverso.</i>"
        )
        self.lbl_locale_info.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        
        form_cloud.addRow(self.lbl_remote_path, self.txt_remote_path)
        form_cloud.addRow("", self.lbl_locale_info)

        # ── Nextcloud ─────────────────────────────────────────────────── #
        self.txt_nc_server = QLineEdit()
        self.txt_nc_server.setPlaceholderText("https://nextcloud.example.com")
        self.lbl_nc_server = QLabel("Server URL:")
        form_cloud.addRow(self.lbl_nc_server, self.txt_nc_server)

        self.txt_nc_folder = QLineEdit()
        self.txt_nc_folder.setPlaceholderText("/QGIS_Projects/")
        self.lbl_nc_folder = QLabel("Cartella Remota:")
        form_cloud.addRow(self.lbl_nc_folder, self.txt_nc_folder)

        self.txt_nc_user = QLineEdit()
        self.txt_nc_user.setPlaceholderText("Utente Nextcloud")
        self.lbl_nc_user = QLabel("Utente:")
        form_cloud.addRow(self.lbl_nc_user, self.txt_nc_user)

        self.txt_nc_pwd = QLineEdit()
        self.txt_nc_pwd.setEchoMode(QLineEdit.Password)
        self.txt_nc_pwd.setPlaceholderText("Password / App Token")
        self.lbl_nc_pwd = QLabel("Password:")
        form_cloud.addRow(self.lbl_nc_pwd, self.txt_nc_pwd)

        # ── Generic WebDAV ────────────────────────────────────────────── #
        self.txt_dav_url = QLineEdit()
        self.txt_dav_url.setPlaceholderText("https://dav.box.com/dav  |  https://mynas.local/webdav")
        self.lbl_dav_url = QLabel("URL WebDAV:")
        form_cloud.addRow(self.lbl_dav_url, self.txt_dav_url)

        self.txt_dav_user = QLineEdit()
        self.txt_dav_user.setPlaceholderText("Nome utente")
        self.lbl_dav_user = QLabel("Utente:")
        form_cloud.addRow(self.lbl_dav_user, self.txt_dav_user)

        self.txt_dav_pwd = QLineEdit()
        self.txt_dav_pwd.setEchoMode(QLineEdit.Password)
        self.txt_dav_pwd.setPlaceholderText("Password")
        self.lbl_dav_pwd = QLabel("Password:")
        form_cloud.addRow(self.lbl_dav_pwd, self.txt_dav_pwd)

        self.lbl_dav_info = QLabel(
            "💡 Compatibile con: Box.com, Koofr, pCloud, ownCloud,\n"
            "   Hetzner Storage Box, Synology/QNAP/TrueNAS, Apache WebDAV…"
        )
        self.lbl_dav_info.setStyleSheet("color:#666;font-size:11px;")
        form_cloud.addRow(self.lbl_dav_info)

        # ── Dropbox ───────────────────────────────────────────────────── #
        self.txt_dbx_token = QLineEdit()
        self.txt_dbx_token.setEchoMode(QLineEdit.Password)
        self.txt_dbx_token.setPlaceholderText("Access Token da dropbox.com/developers/apps")
        self.lbl_dbx_token = QLabel("Access Token:")
        form_cloud.addRow(self.lbl_dbx_token, self.txt_dbx_token)

        self.txt_dbx_folder = QLineEdit()
        self.txt_dbx_folder.setPlaceholderText("/QGIS  (vuoto = root)")
        self.lbl_dbx_folder = QLabel("Cartella Remota:")
        form_cloud.addRow(self.lbl_dbx_folder, self.txt_dbx_folder)

        self.lbl_dbx_info = QLabel(
            "💡 Come ottenere il token:\n"
            "   dropbox.com/developers/apps → Crea app → Settings → OAuth 2 → Generate"
        )
        self.lbl_dbx_info.setStyleSheet("color:#666;font-size:11px;")
        form_cloud.addRow(self.lbl_dbx_info)

        # ── OneDrive ──────────────────────────────────────────────────── #
        self.txt_od_token = QLineEdit()
        self.txt_od_token.setEchoMode(QLineEdit.Password)
        self.txt_od_token.setPlaceholderText("Access Token da Graph Explorer / Azure Portal")
        self.lbl_od_token = QLabel("Access Token:")
        form_cloud.addRow(self.lbl_od_token, self.txt_od_token)

        self.txt_od_folder = QLineEdit()
        self.txt_od_folder.setPlaceholderText("QGIS/Progetti  (vuoto = root)")
        self.lbl_od_folder = QLabel("Cartella Remota:")
        form_cloud.addRow(self.lbl_od_folder, self.txt_od_folder)

        self.lbl_od_info = QLabel(
            "💡 Come ottenere il token:\n"
            "   developer.microsoft.com/graph/graph-explorer → Accedi → Avatar → Access Token"
        )
        self.lbl_od_info.setStyleSheet("color:#666;font-size:11px;")
        form_cloud.addRow(self.lbl_od_info)

        # ── Google Drive ──────────────────────────────────────────────── #
        self.txt_gd_access = QLineEdit()
        self.txt_gd_access.setEchoMode(QLineEdit.Password)
        self.txt_gd_access.setPlaceholderText("Access Token (scade dopo ~1 ora)")
        self.lbl_gd_access = QLabel("Access Token:*")
        form_cloud.addRow(self.lbl_gd_access, self.txt_gd_access)

        self.txt_gd_refresh = QLineEdit()
        self.txt_gd_refresh.setEchoMode(QLineEdit.Password)
        self.txt_gd_refresh.setPlaceholderText("Refresh Token (opzionale, per auto-rinnovo)")
        self.lbl_gd_refresh = QLabel("Refresh Token:")
        form_cloud.addRow(self.lbl_gd_refresh, self.txt_gd_refresh)

        self.txt_gd_client_id = QLineEdit()
        self.txt_gd_client_id.setPlaceholderText("Client ID (da Google Cloud Console, opzionale)")
        self.lbl_gd_client_id = QLabel("Client ID:")
        form_cloud.addRow(self.lbl_gd_client_id, self.txt_gd_client_id)

        self.txt_gd_client_secret = QLineEdit()
        self.txt_gd_client_secret.setEchoMode(QLineEdit.Password)
        self.txt_gd_client_secret.setPlaceholderText("Client Secret (opzionale)")
        self.lbl_gd_client_secret = QLabel("Client Secret:")
        form_cloud.addRow(self.lbl_gd_client_secret, self.txt_gd_client_secret)

        self.txt_gd_folder_id = QLineEdit()
        self.txt_gd_folder_id.setPlaceholderText("ID cartella Drive (vuoto = root)")
        self.lbl_gd_folder_id = QLabel("Folder ID:")
        form_cloud.addRow(self.lbl_gd_folder_id, self.txt_gd_folder_id)

        self.lbl_gd_info = QLabel(
            "💡 Token rapido: developers.google.com/oauthplayground\n"
            "   → Seleziona Drive API v3 scope → Exchange → copia i token"
        )
        self.lbl_gd_info.setStyleSheet("color:#666;font-size:11px;")
        form_cloud.addRow(self.lbl_gd_info)

        grp_cloud.setLayout(form_cloud)
        layout.addWidget(grp_cloud)

        # -- Buttons --------------------------------------------------- #
        outer.addWidget(QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            accepted=self._save_and_close,
            rejected=self.reject,
        ))

    def _load(self):
        self.txt_user.setText(LedgerSettings.user_name())
        self.chk_auto.setChecked(LedgerSettings.auto_commit())
        self.spn_interval.setValue(LedgerSettings.autosave_interval())

        idx = self.cmb_cloud_type.findData(LedgerSettings.remote_type())
        if idx >= 0:
            self.cmb_cloud_type.setCurrentIndex(idx)

        self.txt_remote_path.setText(LedgerSettings.remote_path())

        self.txt_nc_server.setText(LedgerSettings.nextcloud_server())
        self.txt_nc_folder.setText(LedgerSettings.nextcloud_folder())
        self.txt_nc_user.setText(LedgerSettings.nextcloud_user())
        self.txt_nc_pwd.setText(LedgerSettings.nextcloud_password())

        self.txt_dav_url.setText(LedgerSettings.webdav_url())
        self.txt_dav_user.setText(LedgerSettings.webdav_user())
        self.txt_dav_pwd.setText(LedgerSettings.webdav_password())

        self.txt_dbx_token.setText(LedgerSettings.dropbox_token())
        self.txt_dbx_folder.setText(LedgerSettings.dropbox_folder())

        self.txt_od_token.setText(LedgerSettings.onedrive_token())
        self.txt_od_folder.setText(LedgerSettings.onedrive_folder())

        self.txt_gd_access.setText(LedgerSettings.gdrive_access_token())
        self.txt_gd_refresh.setText(LedgerSettings.gdrive_refresh_token())
        self.txt_gd_client_id.setText(LedgerSettings.gdrive_client_id())
        self.txt_gd_client_secret.setText(LedgerSettings.gdrive_client_secret())
        self.txt_gd_folder_id.setText(LedgerSettings.gdrive_folder_id())

    def _toggle_cloud_fields(self):
        ctype = self.cmb_cloud_type.currentData()

        locale_fields  = [self.txt_remote_path, self.lbl_remote_path]
        nc_fields      = [self.txt_nc_server, self.lbl_nc_server,
                          self.txt_nc_folder, self.lbl_nc_folder,
                          self.txt_nc_user, self.lbl_nc_user,
                          self.txt_nc_pwd, self.lbl_nc_pwd]
        dav_fields     = [self.txt_dav_url, self.lbl_dav_url,
                          self.txt_dav_user, self.lbl_dav_user,
                          self.txt_dav_pwd, self.lbl_dav_pwd,
                          self.lbl_dav_info]
        dbx_fields     = [self.txt_dbx_token, self.lbl_dbx_token,
                          self.txt_dbx_folder, self.lbl_dbx_folder,
                          self.lbl_dbx_info]
        od_fields      = [self.txt_od_token, self.lbl_od_token,
                          self.txt_od_folder, self.lbl_od_folder,
                          self.lbl_od_info]
        gd_fields      = [self.txt_gd_access, self.lbl_gd_access,
                          self.txt_gd_refresh, self.lbl_gd_refresh,
                          self.txt_gd_client_id, self.lbl_gd_client_id,
                          self.txt_gd_client_secret, self.lbl_gd_client_secret,
                          self.txt_gd_folder_id, self.lbl_gd_folder_id,
                          self.lbl_gd_info]

        visibility = {
            "locale":       (locale_fields, [nc_fields, dav_fields, dbx_fields, od_fields, gd_fields]),
            "webdav":       (nc_fields,     [locale_fields, dav_fields, dbx_fields, od_fields, gd_fields]),
            "generic_webdav": (dav_fields,  [locale_fields, nc_fields, dbx_fields, od_fields, gd_fields]),
            "dropbox":      (dbx_fields,    [locale_fields, nc_fields, dav_fields, od_fields, gd_fields]),
            "onedrive":     (od_fields,     [locale_fields, nc_fields, dav_fields, dbx_fields, gd_fields]),
            "google_drive": (gd_fields,     [locale_fields, nc_fields, dav_fields, dbx_fields, od_fields]),
        }
        show_list, hide_groups = visibility.get(ctype, ([], []))
        for w in show_list:
            w.setVisible(True)
        for group in hide_groups:
            for w in group:
                w.setVisible(False)

    def _save_and_close(self):
        LedgerSettings.set("user_name", self.txt_user.text().strip())
        LedgerSettings.set("auto_commit", "true" if self.chk_auto.isChecked() else "false")
        LedgerSettings.set("autosave_interval", self.spn_interval.value())

        LedgerSettings.set("remote_type", self.cmb_cloud_type.currentData())
        LedgerSettings.set("remote_path", self.txt_remote_path.text().strip())

        LedgerSettings.set("nextcloud_server",   self.txt_nc_server.text().strip())
        LedgerSettings.set("nextcloud_folder",   self.txt_nc_folder.text().strip())
        LedgerSettings.set("nextcloud_user",     self.txt_nc_user.text().strip())
        LedgerSettings.set("nextcloud_password", self.txt_nc_pwd.text().strip())

        LedgerSettings.set("webdav_url",      self.txt_dav_url.text().strip())
        LedgerSettings.set("webdav_user",     self.txt_dav_user.text().strip())
        LedgerSettings.set("webdav_password", self.txt_dav_pwd.text().strip())

        LedgerSettings.set("dropbox_token",  self.txt_dbx_token.text().strip())
        LedgerSettings.set("dropbox_folder", self.txt_dbx_folder.text().strip())

        LedgerSettings.set("onedrive_token",  self.txt_od_token.text().strip())
        LedgerSettings.set("onedrive_folder", self.txt_od_folder.text().strip())

        LedgerSettings.set("gdrive_access_token",  self.txt_gd_access.text().strip())
        LedgerSettings.set("gdrive_refresh_token", self.txt_gd_refresh.text().strip())
        LedgerSettings.set("gdrive_client_id",     self.txt_gd_client_id.text().strip())
        LedgerSettings.set("gdrive_client_secret", self.txt_gd_client_secret.text().strip())
        LedgerSettings.set("gdrive_folder_id",     self.txt_gd_folder_id.text().strip() or "root")

        self.accept()
