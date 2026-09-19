# -*- coding: utf-8 -*-
"""
ledger_browser.py — QGIS Browser Integration
"""

from qgis.core import QgsDataItemProvider, QgsDataCollectionItem, QgsDataItem, QgsApplication  # noqa: E501
from .ledger_i18n import tr


class LedgerBrowserProvider(QgsDataItemProvider):
    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin

    def name(self):
        return "QGIS_LEDGER_PROVIDER"

    def dataProviderKey(self):
        return "qgis_ledger"

    def capabilities(self):
        try:
            from qgis.core import QgsDataProvider
            return QgsDataProvider.DataCapability.Dir
        except AttributeError:
            return 0

    def createDataItem(self, path, parentItem):
        if path == "":
            return LedgerRootItem(parentItem, "QGIS Ledger", path, self.plugin)
        return None


class LedgerRootItem(QgsDataCollectionItem):
    def __init__(self, parent, name, path, plugin):
        super().__init__(parent, name, path)
        self.plugin = plugin
        icon = QgsApplication.getThemeIcon("/mIconFolder.svg")
        self.setIcon(icon)

    def createChildren(self):
        children = []

        item_local = LedgerActionItem(
            self,
            tr("📂 Esplora Storico Locale"),
            self.path() + "/local",
            lambda: self.plugin._on_browser_dialog(),
            QgsApplication.getThemeIcon("/mActionHistory.svg")
        )
        children.append(item_local)

        item_cloud = LedgerCloudRootItem(
            self,
            tr("☁️ Connessioni Cloud"),
            self.path() + "/cloud",
            self.plugin
        )
        children.append(item_cloud)

        return children


class LedgerCloudRootItem(QgsDataCollectionItem):
    def __init__(self, parent, name, path, plugin):
        super().__init__(parent, name, path)
        self.plugin = plugin
        icon = QgsApplication.getThemeIcon("/mActionOptions.svg")
        self.setIcon(icon)

    def createChildren(self):
        children = []
        providers = [
            (tr("Locale / Rete LAN"), "locale"),
            (tr("Nextcloud / ownCloud"), "webdav"),
            (tr("WebDAV Generico"), "generic_webdav"),
            (tr("Dropbox"), "dropbox"),
            (tr("OneDrive / SharePoint"), "onedrive"),
            (tr("Google Drive"), "google_drive")
        ]
        for display_name, cloud_id in providers:
            item = LedgerActionItem(
                self,
                f"☁ {display_name}",
                self.path() + f"/{cloud_id}",
                lambda cid=cloud_id: self.plugin._connect_and_open_cloud(cid),
                QgsApplication.getThemeIcon("/mActionSharing.svg")
            )
            children.append(item)
        return children


class LedgerActionItem(QgsDataItem):
    def __init__(self, parent, name, path, action_callback, qicon=None):
        super().__init__(QgsDataItem.Type.Custom, parent, name, path)
        self.action_callback = action_callback
        if qicon:
            self.setIcon(qicon)

    def handleDoubleClick(self):
        self.action_callback()
        return True
