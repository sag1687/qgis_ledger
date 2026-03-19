# -*- coding: utf-8 -*-
"""
ledger_settings.py — Settings Dialog

Simple dialog for configuring the QGIS Ledger plugin:
  - Default user name
  - Auto-commit on save toggle
  - Remote storage configuration (Locale / Nextcloud)
"""

from qgis.PyQt.QtCore import Qt, QSettings
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QCheckBox, QPushButton,
    QGroupBox, QDialogButtonBox, QComboBox, QSpinBox,
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

    # -- Remote Storage ------------------------------------------------ #
    @staticmethod
    def remote_type():
        return LedgerSettings.get("remote_type", "locale")

    @staticmethod
    def remote_path():
        return LedgerSettings.get("remote_path", "")

    # -- Nextcloud Settings -------------------------------------------- #
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
    def autosave_interval():
        """Returns the auto-save interval in minutes (default 5)."""
        val = LedgerSettings.get("autosave_interval", 5)
        try:
            return max(1, int(val))
        except (ValueError, TypeError):
            return 5


class SettingsDialog(QDialog):
    """Settings dialog for QGIS Ledger."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("QGIS QGIS Ledger — Impostazioni")
        self.setMinimumWidth(480)
        self._build_ui()
        self._load()
        self._toggle_cloud_fields()

    def _build_ui(self):
        layout = QVBoxLayout(self)

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

        # -- Auto-Save Timer ------------------------------------------- #
        grp_timer = QGroupBox("Auto-Save Automatico")
        form_timer = QFormLayout()

        self.spn_interval = QSpinBox()
        self.spn_interval.setRange(1, 120)
        self.spn_interval.setSuffix(" min")
        self.spn_interval.setToolTip("Intervallo in minuti tra un salvataggio automatico e l'altro")
        form_timer.addRow("Intervallo Auto-Save:", self.spn_interval)

        grp_timer.setLayout(form_timer)
        layout.addWidget(grp_timer)

        # -- Remote Storage / Cloud ------------------------------------ #
        grp_cloud = QGroupBox("Archiviazione Condivisa / Cloud (Fase Sperimentale)")
        form_cloud = QFormLayout()

        self.cmb_cloud_type = QComboBox()
        self.cmb_cloud_type.addItem("Locale / Rete LAN", "locale")
        self.cmb_cloud_type.addItem("Nextcloud", "webdav")
        # Change UI based on selection
        self.cmb_cloud_type.currentIndexChanged.connect(self._toggle_cloud_fields)
        form_cloud.addRow("Tipo Archiviazione:", self.cmb_cloud_type)

        self.txt_remote_path = QLineEdit()
        self.txt_remote_path.setPlaceholderText("Percorso cartella locale o LAN")
        self.lbl_remote_path = QLabel("Cartella Locale/LAN:")
        form_cloud.addRow(self.lbl_remote_path, self.txt_remote_path)

        self.txt_nc_server = QLineEdit()
        self.txt_nc_server.setPlaceholderText("Es. https://nextcloud.example.com")
        self.lbl_nc_server = QLabel("Nextcloud Server URL:")
        form_cloud.addRow(self.lbl_nc_server, self.txt_nc_server)

        self.txt_nc_folder = QLineEdit()
        self.txt_nc_folder.setPlaceholderText("Es. /QGIS_Projects/")
        self.lbl_nc_folder = QLabel("Nextcloud Cartella Remota:")
        form_cloud.addRow(self.lbl_nc_folder, self.txt_nc_folder)

        self.txt_nc_user = QLineEdit()
        self.txt_nc_user.setPlaceholderText("Utente Nextcloud")
        self.lbl_nc_user = QLabel("Nextcloud Utente:")
        form_cloud.addRow(self.lbl_nc_user, self.txt_nc_user)

        self.txt_nc_pwd = QLineEdit()
        self.txt_nc_pwd.setPlaceholderText("Password App / Token")
        self.txt_nc_pwd.setEchoMode(QLineEdit.Password)
        self.lbl_nc_pwd = QLabel("Nextcloud Password App:")
        form_cloud.addRow(self.lbl_nc_pwd, self.txt_nc_pwd)

        grp_cloud.setLayout(form_cloud)
        layout.addWidget(grp_cloud)

        # -- Buttons --------------------------------------------------- #
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._save_and_close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load(self):
        self.txt_user.setText(LedgerSettings.user_name())
        self.chk_auto.setChecked(LedgerSettings.auto_commit())
        
        # Load remote settings
        idx = self.cmb_cloud_type.findData(LedgerSettings.remote_type())
        if idx >= 0:
            self.cmb_cloud_type.setCurrentIndex(idx)
        self.txt_remote_path.setText(LedgerSettings.remote_path())
        
        # Load nextcloud settings
        self.txt_nc_server.setText(LedgerSettings.nextcloud_server())
        self.txt_nc_folder.setText(LedgerSettings.nextcloud_folder())
        self.txt_nc_user.setText(LedgerSettings.nextcloud_user())
        self.txt_nc_pwd.setText(LedgerSettings.nextcloud_password())
        
        self.spn_interval.setValue(LedgerSettings.autosave_interval())

    def _toggle_cloud_fields(self):
        """Enable/disable and show/hide fields based on cloud type."""
        ctype = self.cmb_cloud_type.currentData()
        is_locale = ctype == "locale"
        is_webdav = ctype == "webdav"
        
        # Toggle Locale fields
        self.txt_remote_path.setVisible(is_locale)
        self.lbl_remote_path.setVisible(is_locale)
        
        # Toggle Nextcloud fields
        self.txt_nc_server.setVisible(is_webdav)
        self.lbl_nc_server.setVisible(is_webdav)
        
        self.txt_nc_folder.setVisible(is_webdav)
        self.lbl_nc_folder.setVisible(is_webdav)
        
        self.txt_nc_user.setVisible(is_webdav)
        self.lbl_nc_user.setVisible(is_webdav)
        
        self.txt_nc_pwd.setVisible(is_webdav)
        self.lbl_nc_pwd.setVisible(is_webdav)

    def _save_and_close(self):
        LedgerSettings.set("user_name", self.txt_user.text().strip() or "")
        LedgerSettings.set("auto_commit",
                          "true" if self.chk_auto.isChecked() else "false")
        
        LedgerSettings.set("remote_type", self.cmb_cloud_type.currentData())
        LedgerSettings.set("remote_path", self.txt_remote_path.text().strip())
        
        LedgerSettings.set("nextcloud_server", self.txt_nc_server.text().strip())
        LedgerSettings.set("nextcloud_folder", self.txt_nc_folder.text().strip())
        LedgerSettings.set("nextcloud_user", self.txt_nc_user.text().strip())
        LedgerSettings.set("nextcloud_password", self.txt_nc_pwd.text().strip())

        LedgerSettings.set("autosave_interval", self.spn_interval.value())
        
        self.accept()
