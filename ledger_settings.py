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

from qgis.PyQt.QtCore import QSettings
from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QCheckBox,
    QGroupBox,
    QDialogButtonBox,
    QComboBox,
    QSpinBox,
    QScrollArea,
    QWidget,
    QTabWidget,
)
from qgis.PyQt.QtGui import QIcon
import os
from .ledger_i18n import tr, set_language


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

    @staticmethod
    def compact_toolbar():
        """Compact toolbar mode: show only the Command Center icon.

        Default ON: the toolbar shows a single button (the Command
        Center); every other command is reachable from that window.
        """
        val = LedgerSettings.get("compact_toolbar", "true")
        return not (val == "false" or val is False)

    @staticmethod
    def language():
        return LedgerSettings.get("language", "it")

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

    @staticmethod
    def verify_ssl():
        """Verify TLS certificates for Nextcloud/WebDAV (default ON).

        Disable only for self-hosted servers with self-signed
        certificates. Public cloud APIs always verify regardless.
        """
        val = LedgerSettings.get("verify_ssl", "true")
        return not (val == "false" or val is False)

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
                verify_ssl=LedgerSettings.verify_ssl(),
            )
        elif rtype == "generic_webdav":
            from .ledger_nextcloud import GenericWebDAVClient
            return GenericWebDAVClient(
                LedgerSettings.webdav_url(),
                LedgerSettings.webdav_user(),
                LedgerSettings.webdav_password(),
                verify_ssl=LedgerSettings.verify_ssl(),
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

    def __init__(self, info_widget=None, parent=None):
        self.info_widget = info_widget
        super().__init__(parent)
        self.setWindowTitle(tr("QGIS Ledger — Impostazioni"))
        self.setMinimumWidth(560)
        self.setMinimumHeight(500)
        self._build_ui()
        self._load()
        self._toggle_cloud_fields()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        tabs = QTabWidget()
        main_layout.addWidget(tabs)
        tab_settings = QWidget()
        outer = QVBoxLayout(tab_settings)

        # Scroll area for long content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner_widget = QWidget()
        layout = QVBoxLayout(inner_widget)
        scroll.setWidget(inner_widget)
        outer.addWidget(scroll)

        # -- General --------------------------------------------------- #
        grp_general = QGroupBox(tr("Generale"))
        form = QFormLayout()

        self.txt_user = QLineEdit()
        self.txt_user.setPlaceholderText(tr("Nome utente (default: login OS)"))
        form.addRow(tr("Nome Utente:"), self.txt_user)

        self.chk_auto = QCheckBox(
            tr("Commit automatico al salvataggio del layer"))
        form.addRow(self.chk_auto)

        # Language combo
        self.cmb_lang = QComboBox()
        # Add items with icons assuming icons are in the main plugin folder
        base_dir = os.path.dirname(__file__)
        icon_it = QIcon(os.path.join(base_dir, "ITALIA.png"))
        icon_en = QIcon(os.path.join(base_dir, "REGNOUNITO.png"))
        icon_fr = QIcon(os.path.join(base_dir, "France.png"))
        icon_pt = QIcon(os.path.join(base_dir, "Flag_of_Brazil.svg.png"))
        icon_zh = QIcon(os.path.join(base_dir, "Singapore.png"))
        icon_de = QIcon(os.path.join(base_dir, "DE.png"))
        icon_hi = QIcon(os.path.join(base_dir, "india.png"))

        self.cmb_lang.addItem(icon_it, "Italiano", "it")
        self.cmb_lang.addItem(icon_en, "English", "en")
        self.cmb_lang.addItem(icon_fr, "Français", "fr")
        self.cmb_lang.addItem(icon_de, "Deutsch", "de")
        self.cmb_lang.addItem(icon_pt, "Português (Brasil)", "pt-BR")
        self.cmb_lang.addItem(icon_zh, "中文 (Singapore)", "zh-SG")
        self.cmb_lang.addItem(icon_hi, "हिन्दी (India)", "hi-IN")
        form.addRow(tr("Lingua / Language:"), self.cmb_lang)

        grp_general.setLayout(form)
        layout.addWidget(grp_general)

        # -- Auto-Save ------------------------------------------------- #
        grp_timer = QGroupBox(tr("Auto-Save Automatico"))
        form_timer = QFormLayout()
        self.spn_interval = QSpinBox()
        self.spn_interval.setRange(1, 120)
        self.spn_interval.setSuffix(" min")
        form_timer.addRow(tr("Intervallo Auto-Save:"), self.spn_interval)
        grp_timer.setLayout(form_timer)
        layout.addWidget(grp_timer)

        # -- Cloud ----------------------------------------------------- #
        grp_cloud = QGroupBox(tr("Archiviazione Cloud"))
        form_cloud = QFormLayout()

        self.cmb_cloud_type = QComboBox()
        self.cmb_cloud_type.addItem("Locale / Rete LAN", "locale")
        self.cmb_cloud_type.addItem(
            "☁ Nextcloud / ownCloud (WebDAV)", "webdav")
        self.cmb_cloud_type.addItem(
            "☁ WebDAV Generico (Box · Koofr · pCloud · NAS…)",
            "generic_webdav")
        self.cmb_cloud_type.addItem("☁ Dropbox (API v2)", "dropbox")
        self.cmb_cloud_type.addItem(
            "☁ OneDrive / SharePoint (Graph)", "onedrive")
        self.cmb_cloud_type.addItem("☁ Google Drive (API v3)", "google_drive")
        self.cmb_cloud_type.currentIndexChanged.connect(
            self._toggle_cloud_fields)
        form_cloud.addRow(tr("Tipo Archiviazione:"), self.cmb_cloud_type)

        # ── Locale ────────────────────────────────────────────────────── #
        self.txt_remote_path = QLineEdit()
        self.txt_remote_path.setPlaceholderText(
            tr("Percorso (Opzionale: di default salva nel progetto)"))
        self.lbl_remote_path = QLabel(tr("Cartella Locale/LAN (Overwrite):"))

        self.lbl_locale_info = QLabel(
            tr("<i>Nota: Di default tutte le versioni e le estrazioni vengono salvate<br>"  # noqa: E501
               "nella cartella nascosta <code>.ledger_history</code> creata a fianco del tuo<br>"  # noqa: E501
               "progetto <code>.qgz</code>. Se lavori in rete LAN, lo storico resterà<br>"  # noqa: E501
               "condiviso con il progetto. Compila questo campo solo se desideri<br>"  # noqa: E501
               "forzare il salvataggio in un percorso diverso.</i>")
        )
        self.lbl_locale_info.setStyleSheet("color: #8a97a5; font-size: 11px;")

        form_cloud.addRow(self.lbl_remote_path, self.txt_remote_path)
        form_cloud.addRow("", self.lbl_locale_info)

        # ── Nextcloud ─────────────────────────────────────────────────── #
        self.txt_nc_server = QLineEdit()
        self.txt_nc_server.setPlaceholderText("https://nextcloud.example.com")
        self.lbl_nc_server = QLabel("Server URL:")
        form_cloud.addRow(self.lbl_nc_server, self.txt_nc_server)

        self.txt_nc_folder = QLineEdit()
        self.txt_nc_folder.setPlaceholderText("/QGIS_Projects/")
        self.lbl_nc_folder = QLabel(tr("Cartella Remota:"))
        form_cloud.addRow(self.lbl_nc_folder, self.txt_nc_folder)

        self.txt_nc_user = QLineEdit()
        self.txt_nc_user.setPlaceholderText(tr("Utente Nextcloud"))
        self.lbl_nc_user = QLabel("Utente:")
        form_cloud.addRow(self.lbl_nc_user, self.txt_nc_user)

        self.txt_nc_pwd = QLineEdit()
        self.txt_nc_pwd.setEchoMode(
            getattr(
                getattr(
                    QLineEdit,
                    "EchoMode",
                    QLineEdit),
                "Password"))
        self.txt_nc_pwd.setPlaceholderText(tr("Password / App Token"))
        self.lbl_nc_pwd = QLabel("Password:")
        form_cloud.addRow(self.lbl_nc_pwd, self.txt_nc_pwd)

        self.chk_verify_ssl = QCheckBox(
            tr("Verifica certificati SSL (disattivare solo per server "
               "self-hosted con certificato self-signed)"))
        self.chk_verify_ssl.setChecked(True)
        form_cloud.addRow(self.chk_verify_ssl)

        # ── Generic WebDAV ────────────────────────────────────────────── #
        self.txt_dav_url = QLineEdit()
        self.txt_dav_url.setPlaceholderText(
            "https://dav.box.com/dav  |  https://mynas.local/webdav")
        self.lbl_dav_url = QLabel("URL WebDAV:")
        form_cloud.addRow(self.lbl_dav_url, self.txt_dav_url)

        self.txt_dav_user = QLineEdit()
        self.txt_dav_user.setPlaceholderText(tr("Nome utente"))
        self.lbl_dav_user = QLabel("Utente:")
        form_cloud.addRow(self.lbl_dav_user, self.txt_dav_user)

        self.txt_dav_pwd = QLineEdit()
        self.txt_dav_pwd.setEchoMode(
            getattr(
                getattr(
                    QLineEdit,
                    "EchoMode",
                    QLineEdit),
                "Password"))
        self.txt_dav_pwd.setPlaceholderText(tr("Password"))
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
        self.txt_dbx_token.setEchoMode(
            getattr(
                getattr(
                    QLineEdit,
                    "EchoMode",
                    QLineEdit),
                "Password"))
        self.txt_dbx_token.setPlaceholderText(
            tr("Access Token da dropbox.com/developers/apps"))
        self.lbl_dbx_token = QLabel("Access Token:")
        form_cloud.addRow(self.lbl_dbx_token, self.txt_dbx_token)

        self.txt_dbx_folder = QLineEdit()
        self.txt_dbx_folder.setPlaceholderText(tr("/QGIS  (vuoto = root)"))
        self.lbl_dbx_folder = QLabel(tr("Cartella Remota:"))
        form_cloud.addRow(self.lbl_dbx_folder, self.txt_dbx_folder)

        self.lbl_dbx_info = QLabel(
            "💡 Come ottenere il token:\n"
            "   dropbox.com/developers/apps → Crea app → Settings → OAuth 2 → Generate")  # noqa: E501
        self.lbl_dbx_info.setStyleSheet("color:#666;font-size:11px;")
        form_cloud.addRow(self.lbl_dbx_info)

        # ── OneDrive ──────────────────────────────────────────────────── #
        self.txt_od_token = QLineEdit()
        self.txt_od_token.setEchoMode(
            getattr(
                getattr(
                    QLineEdit,
                    "EchoMode",
                    QLineEdit),
                "Password"))
        self.txt_od_token.setPlaceholderText(
            tr("Access Token da Graph Explorer / Azure Portal"))
        self.lbl_od_token = QLabel("Access Token:")
        form_cloud.addRow(self.lbl_od_token, self.txt_od_token)

        self.txt_od_folder = QLineEdit()
        self.txt_od_folder.setPlaceholderText(
            tr("QGIS/Progetti  (vuoto = root)"))
        self.lbl_od_folder = QLabel(tr("Cartella Remota:"))
        form_cloud.addRow(self.lbl_od_folder, self.txt_od_folder)

        self.lbl_od_info = QLabel(
            "💡 Come ottenere il token:\n"
            "   developer.microsoft.com/graph/graph-explorer → Accedi → Avatar → Access Token")  # noqa: E501
        self.lbl_od_info.setStyleSheet("color:#666;font-size:11px;")
        form_cloud.addRow(self.lbl_od_info)

        # ── Google Drive ──────────────────────────────────────────────── #
        self.txt_gd_access = QLineEdit()
        self.txt_gd_access.setEchoMode(
            getattr(
                getattr(
                    QLineEdit,
                    "EchoMode",
                    QLineEdit),
                "Password"))
        self.txt_gd_access.setPlaceholderText(
            tr("Access Token (scade dopo ~1 ora)"))
        self.lbl_gd_access = QLabel("Access Token:*")
        form_cloud.addRow(self.lbl_gd_access, self.txt_gd_access)

        self.txt_gd_refresh = QLineEdit()
        self.txt_gd_refresh.setEchoMode(
            getattr(
                getattr(
                    QLineEdit,
                    "EchoMode",
                    QLineEdit),
                "Password"))
        self.txt_gd_refresh.setPlaceholderText(
            tr("Refresh Token (opzionale, per auto-rinnovo)"))
        self.lbl_gd_refresh = QLabel("Refresh Token:")
        form_cloud.addRow(self.lbl_gd_refresh, self.txt_gd_refresh)

        self.txt_gd_client_id = QLineEdit()
        self.txt_gd_client_id.setPlaceholderText(
            tr("Client ID (da Google Cloud Console, opzionale)"))
        self.lbl_gd_client_id = QLabel("Client ID:")
        form_cloud.addRow(self.lbl_gd_client_id, self.txt_gd_client_id)

        self.txt_gd_client_secret = QLineEdit()
        self.txt_gd_client_secret.setEchoMode(
            getattr(
                getattr(
                    QLineEdit,
                    "EchoMode",
                    QLineEdit),
                "Password"))
        self.txt_gd_client_secret.setPlaceholderText(
            tr("Client Secret (opzionale)"))
        self.lbl_gd_client_secret = QLabel("Client Secret:")
        form_cloud.addRow(self.lbl_gd_client_secret, self.txt_gd_client_secret)

        self.txt_gd_folder_id = QLineEdit()
        self.txt_gd_folder_id.setPlaceholderText(
            tr("ID cartella Drive (vuoto = root)"))
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
        tabs.addTab(tab_settings, "⚙️ " + tr("Impostazioni"))
        if self.info_widget:
            for i in range(self.info_widget.count()):
                tabs.addTab(
                    self.info_widget.widget(i),
                    self.info_widget.tabText(i))

        main_layout.addWidget(QDialogButtonBox(
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
                "Cancel"),
            accepted=self._save_and_close,
            rejected=self.reject,
        ))

    def _load(self):
        self.txt_user.setText(LedgerSettings.user_name())
        self.chk_auto.setChecked(LedgerSettings.auto_commit())
        self.spn_interval.setValue(LedgerSettings.autosave_interval())

        lang = LedgerSettings.language()
        idx_lang = self.cmb_lang.findData(lang)
        if idx_lang >= 0:
            self.cmb_lang.setCurrentIndex(idx_lang)

        idx = self.cmb_cloud_type.findData(LedgerSettings.remote_type())
        if idx >= 0:
            self.cmb_cloud_type.setCurrentIndex(idx)

        self.txt_remote_path.setText(LedgerSettings.remote_path())

        self.chk_verify_ssl.setChecked(LedgerSettings.verify_ssl())

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
        self.txt_gd_client_secret.setText(
            LedgerSettings.gdrive_client_secret())
        self.txt_gd_folder_id.setText(LedgerSettings.gdrive_folder_id())

    def _toggle_cloud_fields(self):
        ctype = self.cmb_cloud_type.currentData()

        locale_fields = [self.txt_remote_path, self.lbl_remote_path]
        nc_fields = [self.txt_nc_server, self.lbl_nc_server,
                     self.txt_nc_folder, self.lbl_nc_folder,
                     self.txt_nc_user, self.lbl_nc_user,
                     self.txt_nc_pwd, self.lbl_nc_pwd]
        dav_fields = [self.txt_dav_url, self.lbl_dav_url,
                      self.txt_dav_user, self.lbl_dav_user,
                      self.txt_dav_pwd, self.lbl_dav_pwd,
                      self.lbl_dav_info]
        dbx_fields = [self.txt_dbx_token, self.lbl_dbx_token,
                      self.txt_dbx_folder, self.lbl_dbx_folder,
                      self.lbl_dbx_info]
        od_fields = [self.txt_od_token, self.lbl_od_token,
                     self.txt_od_folder, self.lbl_od_folder,
                     self.lbl_od_info]
        gd_fields = [self.txt_gd_access, self.lbl_gd_access,
                     self.txt_gd_refresh, self.lbl_gd_refresh,
                     self.txt_gd_client_id, self.lbl_gd_client_id,
                     self.txt_gd_client_secret, self.lbl_gd_client_secret,
                     self.txt_gd_folder_id, self.lbl_gd_folder_id,
                     self.lbl_gd_info]

        visibility = {
            "locale": (locale_fields, [nc_fields, dav_fields, dbx_fields, od_fields, gd_fields]),  # noqa: E501
            "webdav": (nc_fields, [locale_fields, dav_fields, dbx_fields, od_fields, gd_fields]),  # noqa: E501
            "generic_webdav": (dav_fields, [locale_fields, nc_fields, dbx_fields, od_fields, gd_fields]),  # noqa: E501
            "dropbox": (dbx_fields, [locale_fields, nc_fields, dav_fields, od_fields, gd_fields]),  # noqa: E501
            "onedrive": (od_fields, [locale_fields, nc_fields, dav_fields, dbx_fields, gd_fields]),  # noqa: E501
            "google_drive": (gd_fields, [locale_fields, nc_fields, dav_fields, dbx_fields, od_fields]),  # noqa: E501
        }
        show_list, hide_groups = visibility.get(ctype, ([], []))
        for w in show_list:
            w.setVisible(True)
        for group in hide_groups:
            for w in group:
                w.setVisible(False)
        # SSL verification opt-out applies only to self-hosted servers
        self.chk_verify_ssl.setVisible(
            ctype in ("webdav", "generic_webdav"))

    def _save_and_close(self):
        old_lang = LedgerSettings.get("language", "it")
        selected_lang = self.cmb_lang.currentData()
        LedgerSettings.set("language", selected_lang)
        # Apply language live
        set_language(selected_lang)

        if old_lang != selected_lang:
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.information(self, tr("QGIS Ledger"), tr(
                "Lingua aggiornata con successo! Riavvia QGIS se alcune parti dell'interfaccia non risultano tradotte."))  # noqa: E501

        LedgerSettings.set("user_name", self.txt_user.text().strip())
        LedgerSettings.set(
            "auto_commit",
            "true" if self.chk_auto.isChecked() else "false")
        LedgerSettings.set("autosave_interval", self.spn_interval.value())

        LedgerSettings.set("remote_type", self.cmb_cloud_type.currentData())
        LedgerSettings.set("remote_path", self.txt_remote_path.text().strip())

        LedgerSettings.set(
            "verify_ssl",
            "true" if self.chk_verify_ssl.isChecked() else "false")

        LedgerSettings.set(
            "nextcloud_server",
            self.txt_nc_server.text().strip())
        LedgerSettings.set(
            "nextcloud_folder",
            self.txt_nc_folder.text().strip())
        LedgerSettings.set("nextcloud_user", self.txt_nc_user.text().strip())
        LedgerSettings.set(
            "nextcloud_password",
            self.txt_nc_pwd.text().strip())

        LedgerSettings.set("webdav_url", self.txt_dav_url.text().strip())
        LedgerSettings.set("webdav_user", self.txt_dav_user.text().strip())
        LedgerSettings.set("webdav_password", self.txt_dav_pwd.text().strip())

        LedgerSettings.set("dropbox_token", self.txt_dbx_token.text().strip())
        LedgerSettings.set(
            "dropbox_folder",
            self.txt_dbx_folder.text().strip())

        LedgerSettings.set("onedrive_token", self.txt_od_token.text().strip())
        LedgerSettings.set(
            "onedrive_folder",
            self.txt_od_folder.text().strip())

        LedgerSettings.set(
            "gdrive_access_token",
            self.txt_gd_access.text().strip())
        LedgerSettings.set(
            "gdrive_refresh_token",
            self.txt_gd_refresh.text().strip())
        LedgerSettings.set(
            "gdrive_client_id",
            self.txt_gd_client_id.text().strip())
        LedgerSettings.set(
            "gdrive_client_secret",
            self.txt_gd_client_secret.text().strip())
        LedgerSettings.set("gdrive_folder_id",
                           self.txt_gd_folder_id.text().strip() or "root")

        self.accept()
