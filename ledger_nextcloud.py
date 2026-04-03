# -*- coding: utf-8 -*-
"""
ledger_nextcloud.py — Nextcloud File Browser Panel

Fornisce un pannello dock integrato nel plugin QGIS Ledger che permette
di navigare, creare cartelle, rinominare, eliminare, caricare e scaricare
file direttamente dal server Nextcloud configurato nelle impostazioni,
usando il protocollo WebDAV standard (nessuna dipendenza esterna).
"""

import os
import urllib.request
import urllib.parse
import urllib.error
import http.client
import ssl
import base64
import xml.etree.ElementTree as ET
from datetime import datetime
import json

from qgis.PyQt.QtCore import Qt, QThread, pyqtSignal, QRunnable, QThreadPool, QObject
from qgis.PyQt.QtGui import QIcon, QColor, QFont
from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTreeWidget, QTreeWidgetItem,
    QLineEdit, QMessageBox, QInputDialog, QFileDialog,
    QProgressBar, QSizePolicy, QToolBar, QAction,
    QFrame, QSplitter, QMenu,
)

# ========================================================================= #
# Qt5 / Qt6 compatibility shims
# ========================================================================= #
try:
    # Qt6 / PyQt6 (QGIS 4)
    from qgis.PyQt.QtWidgets import QAbstractItemView
    _Qt_UserRole          = Qt.ItemDataRole.UserRole
    _Qt_CustomCtxMenu     = Qt.ContextMenuPolicy.CustomContextMenu
    _Qt_CopyAction        = Qt.DropAction.CopyAction
    _DragDropMode         = QAbstractItemView.DragDropMode.DragDrop
    _SingleSelection      = QAbstractItemView.SelectionMode.SingleSelection
    _QMB_Yes              = QMessageBox.StandardButton.Yes
    _QMB_No               = QMessageBox.StandardButton.No
except AttributeError:
    # Qt5 / PyQt5 (QGIS 3)
    from qgis.PyQt.QtWidgets import QAbstractItemView
    _Qt_UserRole          = Qt.UserRole
    _Qt_CustomCtxMenu     = Qt.CustomContextMenu
    _Qt_CopyAction        = Qt.CopyAction
    _DragDropMode         = QAbstractItemView.DragDrop
    _SingleSelection      = QAbstractItemView.SingleSelection
    _QMB_Yes              = QMessageBox.Yes
    _QMB_No               = QMessageBox.No

# ========================================================================= #
# WebDAV Namespace
# ========================================================================= #

DAV_NS = "DAV:"


# ========================================================================= #
# NextcloudClient — pure-stdlib WebDAV client
# ========================================================================= #

class NextcloudClient:
    """
    Thin WebDAV client for Nextcloud using only Python's standard library.
    All methods raise RuntimeError on failure with a human-readable message.
    """

    def __init__(self, server: str, username: str, password: str, remote_folder: str = "/"):
        # Normalise server URL
        self.server = server.rstrip("/")
        self.username = username
        self.password = password

        # Build WebDAV base path: /remote.php/dav/files/<user>/<folder>
        # Strip leading slash from remote_folder for the path join
        folder = remote_folder.strip("/")
        user_encoded = urllib.parse.quote(username, safe="")
        if folder:
            self.webdav_base = f"/remote.php/dav/files/{user_encoded}/{folder}"
        else:
            self.webdav_base = f"/remote.php/dav/files/{user_encoded}"

        # Build auth header
        creds = base64.b64encode(f"{username}:{password}".encode()).decode()
        self.auth_header = f"Basic {creds}"

        # SSL context: try to be permissive for self-signed certs
        self._ssl_ctx = ssl.create_default_context()
        self._ssl_ctx.check_hostname = False
        self._ssl_ctx.verify_mode = ssl.CERT_NONE

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _build_url(self, path: str) -> str:
        """Combine the WebDAV base with a relative path."""
        path = path.lstrip("/")
        if path:
            return f"{self.server}{self.webdav_base}/{path}"
        return f"{self.server}{self.webdav_base}"

    def _make_connection(self):
        """Return an HTTPConnection or HTTPSConnection based on server URL."""
        parsed = urllib.parse.urlparse(self.server)
        host = parsed.hostname
        port = parsed.port
        if parsed.scheme == "https":
            conn = http.client.HTTPSConnection(host, port or 443, context=self._ssl_ctx, timeout=15)
        else:
            conn = http.client.HTTPConnection(host, port or 80, timeout=15)
        return conn

    def _request(self, method: str, url: str, headers: dict = None, body=None):
        """
        Low-level HTTP request. Returns (status, reason, response_body_bytes).
        Raises RuntimeError on network errors.
        """
        parsed = urllib.parse.urlparse(url)
        path = parsed.path
        if parsed.query:
            path += "?" + parsed.query

        h = {
            "Authorization": self.auth_header,
            "User-Agent": "QGIS-Ledger-NextcloudBrowser/2.5",
        }
        if headers:
            h.update(headers)

        try:
            conn = self._make_connection()
            conn.request(method, path, body=body, headers=h)
            resp = conn.getresponse()
            data = resp.read()
            conn.close()
            return resp.status, resp.reason, data
        except Exception as e:
            raise RuntimeError(f"Errore di rete [{method} {url}]: {e}")

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def test_connection(self) -> tuple:
        """
        Test the connection. Returns (success: bool, message: str).
        """
        try:
            status, reason, _ = self._request("PROPFIND", self._build_url(""), {
                "Depth": "0",
                "Content-Type": "application/xml; charset=utf-8",
            }, body=b'<?xml version="1.0"?><D:propfind xmlns:D="DAV:"><D:prop><D:displayname/></D:prop></D:propfind>')

            if status in (200, 207):
                return True, "Connessione avvenuta con successo!"
            elif status == 401:
                return False, "Credenziali non valide (401 Unauthorized)."
            elif status == 404:
                return False, "Cartella remota non trovata (404). Controlla il percorso nelle impostazioni."
            else:
                return False, f"Risposta inattesa dal server: {status} {reason}"
        except RuntimeError as e:
            return False, str(e)

    def list_directory(self, remote_path: str = "") -> list:
        """
        PROPFIND on remote_path. Returns list of dicts:
        {name, href, is_dir, size, modified, full_path}
        The first entry (the directory itself) is excluded.
        """
        url = self._build_url(remote_path)
        body = b"""<?xml version="1.0"?>
<D:propfind xmlns:D="DAV:">
  <D:prop>
    <D:displayname/>
    <D:getcontentlength/>
    <D:getlastmodified/>
    <D:resourcetype/>
  </D:prop>
</D:propfind>"""
        status, reason, data = self._request("PROPFIND", url, {
            "Depth": "1",
            "Content-Type": "application/xml; charset=utf-8",
        }, body=body)

        if status not in (200, 207):
            raise RuntimeError(f"Impossibile listare la cartella '{remote_path}': {status} {reason}")

        return self._parse_propfind(data, url)

    def _parse_propfind(self, xml_data: bytes, request_url: str) -> list:
        """Parse PROPFIND XML response. Skip the first entry (the requested folder itself)."""
        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError as e:
            raise RuntimeError(f"Errore nel parsing della risposta WebDAV: {e}")

        results = []
        first = True
        for response in root.findall(f"{{{DAV_NS}}}response"):
            href_el = response.find(f"{{{DAV_NS}}}href")
            if href_el is None:
                continue
            href = href_el.text or ""

            propstat = response.find(f"{{{DAV_NS}}}propstat")
            if propstat is None:
                continue
            prop = propstat.find(f"{{{DAV_NS}}}prop")
            if prop is None:
                continue

            # Detect if directory
            resourcetype = prop.find(f"{{{DAV_NS}}}resourcetype")
            is_dir = False
            if resourcetype is not None:
                is_dir = resourcetype.find(f"{{{DAV_NS}}}collection") is not None

            # Name
            displayname_el = prop.find(f"{{{DAV_NS}}}displayname")
            if displayname_el is not None and displayname_el.text:
                name = displayname_el.text
            else:
                # Extract from href
                name = urllib.parse.unquote(href.rstrip("/").split("/")[-1])

            # Size
            size_el = prop.find(f"{{{DAV_NS}}}getcontentlength")
            size = int(size_el.text) if size_el is not None and size_el.text else 0

            # Modified
            mod_el = prop.find(f"{{{DAV_NS}}}getlastmodified")
            modified = mod_el.text if mod_el is not None else ""

            full_path = urllib.parse.unquote(href)

            if first:
                first = False
                continue  # skip self-entry

            if not name:
                continue

            results.append({
                "name": name,
                "href": href,
                "full_path": full_path,
                "is_dir": is_dir,
                "size": size,
                "modified": modified,
            })

        # Directories first, then files, both alphabetical
        results.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return results

    def make_directory(self, remote_path: str):
        """Create a directory at remote_path (MKCOL)."""
        url = self._build_url(remote_path)
        status, reason, _ = self._request("MKCOL", url)
        if status not in (200, 201):
            raise RuntimeError(f"Impossibile creare la cartella '{remote_path}': {status} {reason}")

    def delete(self, remote_path: str):
        """Delete a file or directory at remote_path."""
        url = self._build_url(remote_path)
        status, reason, _ = self._request("DELETE", url)
        if status not in (200, 204):
            raise RuntimeError(f"Impossibile eliminare '{remote_path}': {status} {reason}")

    def move(self, old_remote_path: str, new_remote_path: str):
        """Move/rename a file or directory (MOVE)."""
        src_url = self._build_url(old_remote_path)
        dst_url = self._build_url(new_remote_path)
        status, reason, _ = self._request("MOVE", src_url, {
            "Destination": dst_url,
            "Overwrite": "F",
        })
        if status not in (200, 201, 204):
            raise RuntimeError(f"Impossibile spostare/rinominare '{old_remote_path}' → '{new_remote_path}': {status} {reason}")

    def upload(self, remote_path: str, local_path: str):
        """Upload a local file to remote_path (PUT)."""
        with open(local_path, "rb") as f:
            data = f.read()
        url = self._build_url(remote_path)
        status, reason, _ = self._request("PUT", url, {
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(data)),
        }, body=data)
        if status not in (200, 201, 204):
            raise RuntimeError(f"Impossibile caricare '{local_path}': {status} {reason}")

    def download(self, remote_path: str, local_path: str):
        """Download remote_path to a local file (GET)."""
        url = self._build_url(remote_path)
        status, reason, data = self._request("GET", url)
        if status != 200:
            raise RuntimeError(f"Impossibile scaricare '{remote_path}': {status} {reason}")
        with open(local_path, "wb") as f:
            f.write(data)


# ========================================================================= #
# GenericWebDAVClient — works with ANY standard WebDAV server
# Compatible with: Box.com, ownCloud, Koofr, pCloud, Hetzner Storage Box,
#                  any NAS (Synology, QNAP, TrueNAS), Apache/Nginx WebDAV, …
# Configuration: just base_url + username + password. No app registration.
# ========================================================================= #

class GenericWebDAVClient:
    """
    Pure-stdlib WebDAV client for any standards-compliant WebDAV server.
    Accepts a full base URL (e.g. https://dav.box.com/dav or
    https://mynas.local/remote.php/dav/files/user) and Basic Auth credentials.
    Implements the same public interface as NextcloudClient so the rest of the
    plugin can use either interchangeably.
    """

    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password

        creds = base64.b64encode(f"{username}:{password}".encode()).decode()
        self.auth_header = f"Basic {creds}"

        self._ssl_ctx = ssl.create_default_context()
        self._ssl_ctx.check_hostname = False
        self._ssl_ctx.verify_mode = ssl.CERT_NONE

        # Derive webdav_base from base_url for panel navigation compatibility
        parsed = urllib.parse.urlparse(self.base_url)
        self.webdav_base = parsed.path or "/"

    # ── internal ────────────────────────────────────────────────────────── #

    def _build_url(self, path: str) -> str:
        path = path.lstrip("/")
        return f"{self.base_url}/{path}" if path else self.base_url

    def _make_connection(self):
        parsed = urllib.parse.urlparse(self.base_url)
        host = parsed.hostname
        port = parsed.port
        if parsed.scheme == "https":
            return http.client.HTTPSConnection(host, port or 443,
                                               context=self._ssl_ctx, timeout=15)
        return http.client.HTTPConnection(host, port or 80, timeout=15)

    def _request(self, method: str, url: str, headers: dict = None, body=None):
        parsed = urllib.parse.urlparse(url)
        path = parsed.path
        if parsed.query:
            path += "?" + parsed.query
        h = {
            "Authorization": self.auth_header,
            "User-Agent": "QGIS-Ledger-CloudBrowser/3.0",
        }
        if headers:
            h.update(headers)
        try:
            conn = self._make_connection()
            conn.request(method, path, body=body, headers=h)
            resp = conn.getresponse()
            data = resp.read()
            conn.close()
            return resp.status, resp.reason, data
        except Exception as e:
            raise RuntimeError(f"Errore di rete [{method} {url}]: {e}")

    def _parse_propfind(self, xml_data: bytes, request_url: str) -> list:
        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError as e:
            raise RuntimeError(f"Errore parsing WebDAV: {e}")
        results = []
        first = True
        for response in root.findall(f"{{{DAV_NS}}}response"):
            href_el = response.find(f"{{{DAV_NS}}}href")
            if href_el is None:
                continue
            href = href_el.text or ""
            propstat = response.find(f"{{{DAV_NS}}}propstat")
            if propstat is None:
                continue
            prop = propstat.find(f"{{{DAV_NS}}}prop")
            if prop is None:
                continue
            resourcetype = prop.find(f"{{{DAV_NS}}}resourcetype")
            is_dir = resourcetype is not None and \
                     resourcetype.find(f"{{{DAV_NS}}}collection") is not None
            displayname_el = prop.find(f"{{{DAV_NS}}}displayname")
            if displayname_el is not None and displayname_el.text:
                name = displayname_el.text
            else:
                name = urllib.parse.unquote(href.rstrip("/").split("/")[-1])
            size_el = prop.find(f"{{{DAV_NS}}}getcontentlength")
            size = int(size_el.text) if size_el is not None and size_el.text else 0
            mod_el = prop.find(f"{{{DAV_NS}}}getlastmodified")
            modified = mod_el.text if mod_el is not None else ""
            full_path = urllib.parse.unquote(href)
            if first:
                first = False
                continue
            if not name:
                continue
            results.append({
                "name": name, "href": href, "full_path": full_path,
                "is_dir": is_dir, "size": size, "modified": modified,
            })
        results.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return results

    # ── public API (same interface as NextcloudClient) ───────────────────── #

    def test_connection(self) -> tuple:
        try:
            status, reason, _ = self._request("PROPFIND", self.base_url, {
                "Depth": "0",
                "Content-Type": "application/xml; charset=utf-8",
            }, body=b'<?xml version="1.0"?><D:propfind xmlns:D="DAV:"><D:prop><D:displayname/></D:prop></D:propfind>')
            if status in (200, 207):
                return True, "Connessione avvenuta con successo!"
            elif status == 401:
                return False, "Credenziali non valide (401 Unauthorized)."
            elif status == 404:
                return False, "URL WebDAV non trovato (404). Verificare l'indirizzo."
            else:
                return False, f"Risposta inattesa: {status} {reason}"
        except RuntimeError as e:
            return False, str(e)

    def list_directory(self, remote_path: str = "") -> list:
        url = self._build_url(remote_path)
        body = b"""<?xml version="1.0"?>
<D:propfind xmlns:D="DAV:">
  <D:prop>
    <D:displayname/>
    <D:getcontentlength/>
    <D:getlastmodified/>
    <D:resourcetype/>
  </D:prop>
</D:propfind>"""
        status, reason, data = self._request("PROPFIND", url, {
            "Depth": "1",
            "Content-Type": "application/xml; charset=utf-8",
        }, body=body)
        if status not in (200, 207):
            raise RuntimeError(f"Impossibile listare '{remote_path}': {status} {reason}")
        return self._parse_propfind(data, url)

    def make_directory(self, remote_path: str):
        url = self._build_url(remote_path)
        status, reason, _ = self._request("MKCOL", url)
        if status not in (200, 201):
            raise RuntimeError(f"Impossibile creare cartella '{remote_path}': {status} {reason}")

    def delete(self, remote_path: str):
        url = self._build_url(remote_path)
        status, reason, _ = self._request("DELETE", url)
        if status not in (200, 204):
            raise RuntimeError(f"Impossibile eliminare '{remote_path}': {status} {reason}")

    def move(self, old_remote_path: str, new_remote_path: str):
        src_url = self._build_url(old_remote_path)
        dst_url = self._build_url(new_remote_path)
        status, reason, _ = self._request("MOVE", src_url, {
            "Destination": dst_url, "Overwrite": "F",
        })
        if status not in (200, 201, 204):
            raise RuntimeError(f"Impossibile spostare '{old_remote_path}': {status} {reason}")

    def upload(self, remote_path: str, local_path: str):
        with open(local_path, "rb") as f:
            data = f.read()
        url = self._build_url(remote_path)
        status, reason, _ = self._request("PUT", url, {
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(data)),
        }, body=data)
        if status not in (200, 201, 204):
            raise RuntimeError(f"Impossibile caricare '{local_path}': {status} {reason}")

    def download(self, remote_path: str, local_path: str):
        url = self._build_url(remote_path)
        status, reason, data = self._request("GET", url)
        if status != 200:
            raise RuntimeError(f"Impossibile scaricare '{remote_path}': {status} {reason}")
        with open(local_path, "wb") as f:
            f.write(data)


# ========================================================================= #
# DropboxClient — Dropbox API v2 (pure stdlib)
# Auth: Access Token generated from https://www.dropbox.com/developers/apps
# Credentials needed: access_token, remote_folder (optional)
# ========================================================================= #

class DropboxClient:
    """
    Dropbox API v2 client using Bearer token authentication.
    No external dependencies — uses only Python's stdlib http.client.

    To obtain an Access Token:
      1. Go to https://www.dropbox.com/developers/apps
      2. Create or open your app → Settings → OAuth 2 token
      3. Click "Generate" under "Generated access token"
      4. Copy the token into the plugin settings
    """

    _API  = "api.dropboxapi.com"
    _CONT = "content.dropboxapi.com"

    def __init__(self, access_token: str, remote_folder: str = ""):
        self.access_token  = access_token.strip()
        # Normalize folder: must start with "/" or be ""
        rf = remote_folder.strip().strip("/")
        self.remote_folder = f"/{rf}" if rf else ""
        self.webdav_base   = "/"  # compatibility attribute

        self._ssl = ssl.create_default_context()
        self._ssl.check_hostname = False
        self._ssl.verify_mode   = ssl.CERT_NONE

    def _dbx_path(self, path: str) -> str:
        path = path.strip("/")
        if path:
            return f"{self.remote_folder}/{path}"
        return self.remote_folder  # may be "" which Dropbox treats as root

    def _api(self, endpoint: str, body: dict, headers_extra: dict = None) -> dict:
        data = json.dumps(body).encode()
        h = {
            "Authorization":  f"Bearer {self.access_token}",
            "Content-Type":   "application/json",
            "Content-Length": str(len(data)),
        }
        if headers_extra:
            h.update(headers_extra)
        conn = http.client.HTTPSConnection(self._API, 443, context=self._ssl, timeout=30)
        conn.request("POST", f"/2/{endpoint}", body=data, headers=h)
        resp = conn.getresponse()
        raw  = resp.read()
        conn.close()
        if resp.status >= 400:
            raise RuntimeError(f"Dropbox {endpoint} → {resp.status}: {raw.decode('utf-8', errors='replace')[:200]}")
        return json.loads(raw) if raw else {}

    def _content(self, endpoint: str, dbx_arg: dict, file_data: bytes = b"",
                 method: str = "POST") -> bytes:
        h = {
            "Authorization":   f"Bearer {self.access_token}",
            "Content-Type":    "application/octet-stream",
            "Dropbox-API-Arg": json.dumps(dbx_arg),
        }
        conn = http.client.HTTPSConnection(self._CONT, 443, context=self._ssl, timeout=60)
        conn.request(method, f"/2/{endpoint}", body=file_data, headers=h)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        if resp.status >= 400:
            raise RuntimeError(f"Dropbox content/{endpoint} → {resp.status}: {data.decode('utf-8', errors='replace')[:200]}")
        return data

    # ── public API ───────────────────────────────────────────────────────── #

    def test_connection(self) -> tuple:
        try:
            r    = self._api("users/get_current_account", {})
            name = r.get("name", {}).get("display_name", "utente sconosciuto")
            return True, f"✅ Dropbox connesso come: {name}"
        except RuntimeError as e:
            return False, str(e)

    def list_directory(self, remote_path: str = "") -> list:
        dbx = self._dbx_path(remote_path)
        r   = self._api("files/list_folder",
                         {"path": dbx, "recursive": False, "include_deleted": False})
        out = []
        for e in r.get("entries", []):
            out.append({
                "name":      e["name"],
                "href":      e.get("path_lower", ""),
                "full_path": e.get("path_lower", ""),
                "is_dir":    e.get(".tag") == "folder",
                "size":      e.get("size", 0),
                "modified":  e.get("server_modified", ""),
            })
        out.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return out

    def make_directory(self, remote_path: str):
        self._api("files/create_folder_v2",
                  {"path": self._dbx_path(remote_path), "autorename": False})

    def delete(self, remote_path: str):
        self._api("files/delete_v2", {"path": self._dbx_path(remote_path)})

    def move(self, old_path: str, new_path: str):
        self._api("files/move_v2", {
            "from_path": self._dbx_path(old_path),
            "to_path":   self._dbx_path(new_path),
            "autorename": False,
        })

    def upload(self, remote_path: str, local_path: str):
        with open(local_path, "rb") as f:
            data = f.read()
        self._content("files/upload",
                       {"path": self._dbx_path(remote_path), "mode": "overwrite",
                        "autorename": False, "mute": False},
                       file_data=data)

    def download(self, remote_path: str, local_path: str):
        data = self._content("files/download",
                              {"path": self._dbx_path(remote_path)})
        with open(local_path, "wb") as f:
            f.write(data)


# ========================================================================= #
# OneDriveClient — Microsoft Graph API v1.0 (pure stdlib)
# Auth: Bearer Access Token from https://developer.microsoft.com/en-us/graph/graph-explorer
#       or from Azure Portal → your app → Certificates & secrets
# Credentials needed: access_token, remote_folder (optional)
# ========================================================================= #

class OneDriveClient:
    """
    Microsoft OneDrive client via Microsoft Graph REST API v1.0.
    Authenticates with a Bearer Access Token (no external dependencies).

    To obtain an Access Token:
      Option A (quick test):
        1. Go to https://developer.microsoft.com/en-us/graph/graph-explorer
        2. Sign in with your Microsoft account
        3. Click your avatar → "Access token" tab → copy the token
      Option B (production):
        1. Register an app at https://portal.azure.com → Entra ID → App registrations
        2. Generate a client secret → use OAuth2 flows to obtain access_token
    """

    _GRAPH = "graph.microsoft.com"

    def __init__(self, access_token: str, remote_folder: str = ""):
        self.access_token  = access_token.strip()
        self.remote_folder = remote_folder.strip("/")
        self.webdav_base   = "/"

        self._ssl = ssl.create_default_context()
        self._ssl.check_hostname = False
        self._ssl.verify_mode   = ssl.CERT_NONE

    def _graph_path(self, path: str) -> str:
        """Build the full remote path joining base folder and path."""
        parts = [p for p in [self.remote_folder, path.strip("/")] if p]
        return "/".join(parts)

    def _item_url(self, path: str) -> str:
        full = self._graph_path(path)
        if full:
            return f"/v1.0/me/drive/root:/{urllib.parse.quote(full, safe='/')}"
        return "/v1.0/me/drive/root"

    def _req(self, method: str, path: str, body=None,
             content_type: str = "application/json") -> tuple:
        h = {"Authorization": f"Bearer {self.access_token}"}
        body_bytes = None
        if body is not None:
            if isinstance(body, dict):
                body_bytes = json.dumps(body).encode()
                h["Content-Type"] = "application/json"
            else:
                body_bytes = body
                h["Content-Type"] = content_type
        conn = http.client.HTTPSConnection(self._GRAPH, 443, context=self._ssl, timeout=30)
        conn.request(method, path, body=body_bytes, headers=h)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, data

    # ── public API ───────────────────────────────────────────────────────── #

    def test_connection(self) -> tuple:
        try:
            status, data = self._req("GET", "/v1.0/me/drive")
            if status == 200:
                r     = json.loads(data)
                owner = r.get("owner", {}).get("user", {}).get("displayName", "utente")
                quota = r.get("quota", {})
                used  = quota.get("used", 0) // (1024 ** 3)
                total = quota.get("total", 0) // (1024 ** 3)
                return True, f"✅ OneDrive connesso: {owner} ({used}/{total} GB usati)"
            elif status == 401:
                return False, "Token non valido o scaduto (401). Rinnovare il token."
            else:
                return False, f"Errore {status}: {data.decode('utf-8', errors='replace')[:200]}"
        except Exception as e:
            return False, str(e)

    def list_directory(self, remote_path: str = "") -> list:
        base = self._item_url(remote_path)
        # add /children — if path-based url ends with ":" we need ":/children"
        if base.endswith(":"):
            url = base + "/children"
        else:
            url = base + "/children"
        status, data = self._req("GET", url)
        if status == 404:
            return []
        if status != 200:
            raise RuntimeError(f"OneDrive list → {status}: {data.decode('utf-8', errors='replace')[:200]}")
        r = json.loads(data)
        out = []
        for item in r.get("value", []):
            out.append({
                "name":      item["name"],
                "href":      item.get("id", ""),
                "full_path": (remote_path.rstrip("/") + "/" + item["name"]).lstrip("/"),
                "is_dir":    "folder" in item,
                "size":      item.get("size", 0),
                "modified":  item.get("lastModifiedDateTime", ""),
            })
        out.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return out

    def make_directory(self, remote_path: str):
        parts = [p for p in remote_path.strip("/").split("/") if p]
        if not parts:
            return
        folder_name = parts[-1]
        parent_path = "/".join(parts[:-1])
        parent_url  = self._item_url(parent_path)
        if parent_url.endswith(":"):
            url = parent_url + "/children"
        else:
            url = parent_url + "/children"
        body = {"name": folder_name, "folder": {},
                "@microsoft.graph.conflictBehavior": "rename"}
        status, data = self._req("POST", url, body)
        if status not in (200, 201):
            raise RuntimeError(f"OneDrive mkdir → {status}")

    def delete(self, remote_path: str):
        url = self._item_url(remote_path)
        status, _ = self._req("DELETE", url)
        if status not in (200, 204):
            raise RuntimeError(f"OneDrive delete → {status}")

    def move(self, old_path: str, new_path: str):
        url      = self._item_url(old_path)
        new_name = new_path.strip("/").split("/")[-1]
        status, data = self._req("PATCH", url, {"name": new_name})
        if status not in (200, 201):
            raise RuntimeError(f"OneDrive move → {status}")

    def upload(self, remote_path: str, local_path: str):
        url = self._item_url(remote_path)
        if url.endswith(":"):
            url += ":/content"
        else:
            url += ":/content" if not url.endswith("root") else "_tmp_content"
            # simple path: /v1.0/me/drive/root:/path:/content
        # Re-build cleanly
        url = self._item_url(remote_path) + ":/content"
        with open(local_path, "rb") as f:
            data = f.read()
        status, resp = self._req("PUT", url, body=data,
                                  content_type="application/octet-stream")
        if status not in (200, 201):
            raise RuntimeError(f"OneDrive upload → {status}: {resp.decode('utf-8', errors='replace')[:200]}")

    def download(self, remote_path: str, local_path: str):
        url = self._item_url(remote_path) + ":/content"
        status, data = self._req("GET", url)
        if status != 200:
            raise RuntimeError(f"OneDrive download → {status}")
        with open(local_path, "wb") as f:
            f.write(data)


# ========================================================================= #
# GoogleDriveClient — Google Drive API v3 (pure stdlib)
# Auth: OAuth2 Bearer token (Access Token + optional Refresh Token)
# Credentials needed: access_token; optionally client_id, client_secret,
#                     refresh_token for auto-renewal; folder_id for root
# ========================================================================= #

class GoogleDriveClient:
    """
    Google Drive API v3 client. Uses Bearer token with optional auto-refresh.

    To obtain credentials:
      1. Go to https://console.cloud.google.com → Enable "Drive API"
      2. Create OAuth 2.0 credentials (Desktop app) — get client_id and client_secret
      3. Use https://developers.google.com/oauthplayground to generate:
           - Select "Drive API v3 → .../drive"
           - Exchange authorization code for tokens
           - Copy the Access Token and Refresh Token
      Alternatively for a quick test:
         https://developers.google.com/oauthplayground gives a temporary token directly.

    Fields:
      access_token   — Bearer token (may expire after 1 hour)
      refresh_token  — (Optional) used to auto-refresh the access token
      client_id      — (Optional) your app's client ID from Google Cloud Console
      client_secret  — (Optional) your app's client secret
      folder_id      — (Optional) Google Drive folder ID to use as root (default: "root")
    """

    _HOST = "www.googleapis.com"

    def __init__(self, access_token: str, refresh_token: str = "",
                 client_id: str = "", client_secret: str = "",
                 folder_id: str = "root"):
        self._access_token = access_token.strip()
        self.refresh_token  = refresh_token.strip()
        self.client_id      = client_id.strip()
        self.client_secret  = client_secret.strip()
        self.root_folder_id = folder_id.strip() or "root"
        self.webdav_base    = "/"

        self._ssl = ssl.create_default_context()
        self._ssl.check_hostname = False
        self._ssl.verify_mode   = ssl.CERT_NONE

    def _refresh(self):
        if not (self.refresh_token and self.client_id and self.client_secret):
            return
        try:
            body = urllib.parse.urlencode({
                "grant_type":    "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id":     self.client_id,
                "client_secret": self.client_secret,
            }).encode()
            conn = http.client.HTTPSConnection(
                "oauth2.googleapis.com", 443, context=self._ssl, timeout=15)
            conn.request("POST", "/token", body=body,
                          headers={"Content-Type": "application/x-www-form-urlencoded"})
            resp = conn.getresponse()
            r    = json.loads(resp.read())
            conn.close()
            if "access_token" in r:
                self._access_token = r["access_token"]
        except Exception:
            pass

    def _req(self, method: str, path: str, body=None,
             content_type: str = "application/json",
             host: str = None, retry: bool = True) -> tuple:
        h = host or self._HOST
        headers = {"Authorization": f"Bearer {self._access_token}"}
        body_bytes = None
        if body is not None:
            if isinstance(body, dict):
                body_bytes = json.dumps(body).encode()
                headers["Content-Type"] = "application/json"
            else:
                body_bytes = body
                headers["Content-Type"] = content_type
        conn = http.client.HTTPSConnection(h, 443, context=self._ssl, timeout=30)
        conn.request(method, path, body=body_bytes, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        status = resp.status
        conn.close()
        if status == 401 and retry:
            self._refresh()
            return self._req(method, path, body, content_type, host, retry=False)
        return status, data

    def _folder_id(self, path: str) -> str:
        """Return the Google Drive folder ID for a given path string (ID or root)."""
        if not path:
            return self.root_folder_id
        return path.strip("/")  # the panel stores IDs as paths

    # ── public API ───────────────────────────────────────────────────────── #

    def test_connection(self) -> tuple:
        try:
            status, data = self._req("GET", "/drive/v3/about?fields=user,storageQuota")
            if status == 200:
                r     = json.loads(data)
                name  = r.get("user", {}).get("displayName", "utente")
                q     = r.get("storageQuota", {})
                used  = int(q.get("usage", 0)) // (1024 ** 3)
                total = int(q.get("limit", 0)) // (1024 ** 3)
                return True, f"✅ Google Drive connesso: {name} ({used}/{total} GB)"
            elif status == 401:
                return False, "Token non valido o scaduto. Aggiornare l'access token."
            else:
                return False, f"Errore {status}: {data.decode('utf-8', errors='replace')[:200]}"
        except Exception as e:
            return False, str(e)

    def list_directory(self, remote_path: str = "") -> list:
        folder_id = self._folder_id(remote_path) or self.root_folder_id
        q      = f"'{folder_id}' in parents and trashed=false"
        fields = "files(id,name,mimeType,size,modifiedTime)"
        url    = (f"/drive/v3/files"
                  f"?q={urllib.parse.quote(q)}"
                  f"&fields={urllib.parse.quote(fields)}"
                  f"&pageSize=200&orderBy=folder,name")
        status, data = self._req("GET", url)
        if status != 200:
            raise RuntimeError(f"Google Drive list → {status}: "
                                f"{data.decode('utf-8', errors='replace')[:200]}")
        r = json.loads(data)
        out = []
        for f in r.get("files", []):
            is_dir = f.get("mimeType") == "application/vnd.google-apps.folder"
            out.append({
                "name":      f["name"],
                "href":      f["id"],       # GDrive navigation uses file IDs
                "full_path": f["id"],
                "is_dir":    is_dir,
                "size":      int(f.get("size", 0)) if f.get("size") else 0,
                "modified":  f.get("modifiedTime", ""),
            })
        return out

    def make_directory(self, remote_path: str):
        parts  = [p for p in remote_path.strip("/").split("/") if p]
        name   = parts[-1] if parts else "Nuova Cartella"
        parent = parts[-2] if len(parts) > 1 else self.root_folder_id
        body   = {"name": name,
                  "mimeType": "application/vnd.google-apps.folder",
                  "parents": [parent]}
        status, data = self._req("POST", "/drive/v3/files", body)
        if status not in (200, 201):
            raise RuntimeError(f"Google Drive mkdir → {status}")

    def delete(self, remote_path: str):
        file_id = self._folder_id(remote_path)
        status, _ = self._req("DELETE",
                               f"/drive/v3/files/{urllib.parse.quote(file_id)}")
        if status != 204:
            raise RuntimeError(f"Google Drive delete → {status}")

    def move(self, old_path: str, new_path: str):
        file_id  = self._folder_id(old_path)
        new_name = new_path.strip("/").split("/")[-1]
        status, data = self._req(
            "PATCH", f"/drive/v3/files/{urllib.parse.quote(file_id)}",
            {"name": new_name})
        if status != 200:
            raise RuntimeError(f"Google Drive move → {status}")

    def upload(self, remote_path: str, local_path: str):
        with open(local_path, "rb") as fh:
            file_data = fh.read()
        file_name = os.path.basename(local_path)
        # Determine parent folder ID from remote_path
        parts = [p for p in remote_path.strip("/").split("/") if p]
        parent_id = parts[-2] if len(parts) > 1 else self.root_folder_id
        # Simple multipart upload
        boundary  = "qgis_ledger_boundary_gdrive"
        ext       = os.path.splitext(local_path)[1].lower()
        mime_map  = {".gpkg": "application/x-sqlite3",
                     ".qml": "application/xml",
                     ".json": "application/json",
                     ".geojson": "application/geo+json"}
        mime      = mime_map.get(ext, "application/octet-stream")
        meta_json = json.dumps({"name": file_name, "parents": [parent_id]}).encode()
        body = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
            .encode() + meta_json +
            f"\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n"
            .encode() + file_data +
            f"\r\n--{boundary}--".encode()
        )
        ct     = f"multipart/related; boundary={boundary}"
        status, data = self._req(
            "POST", "/upload/drive/v3/files?uploadType=multipart",
            body=body, content_type=ct)
        if status not in (200, 201):
            raise RuntimeError(f"Google Drive upload → {status}: "
                                f"{data.decode('utf-8', errors='replace')[:200]}")

    def download(self, remote_path: str, local_path: str):
        file_id  = self._folder_id(remote_path)
        status, data = self._req(
            "GET", f"/drive/v3/files/{urllib.parse.quote(file_id)}?alt=media")
        if status != 200:
            raise RuntimeError(f"Google Drive download → {status}")
        with open(local_path, "wb") as fh:
            fh.write(data)


# ========================================================================= #
# Background worker for non-blocking operations
# ========================================================================= #

class _WorkerSignals(QObject):
    finished = pyqtSignal(object)   # result data
    error = pyqtSignal(str)         # error message


class _Worker(QRunnable):
    """Generic QRunnable that runs a callable in a thread pool."""

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = _WorkerSignals()

    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))


# ========================================================================= #
# NextcloudBrowserPanel — QDockWidget
# ========================================================================= #

DARK_STYLE = """
QDockWidget {
    background: #1e272e;
    color: #ecf0f1;
    font-size: 13px;
}
QWidget#nc_root {
    background: #1e272e;
}
QTreeWidget {
    background: #2c3e50;
    color: #ecf0f1;
    border: 1px solid #34495e;
    alternate-background-color: #283747;
    gridline-color: #34495e;
    font-size: 12px;
}
QTreeWidget::item:selected {
    background: #2980b9;
    color: #ffffff;
}
QTreeWidget::item:hover {
    background: #3498db;
    color: #ffffff;
}
QHeaderView::section {
    background: #2980b9;
    color: white;
    padding: 4px 6px;
    border: 1px solid #1a5276;
    font-weight: bold;
    font-size: 11px;
}
QLabel {
    color: #ecf0f1;
}
QLineEdit {
    background: #34495e;
    color: #ecf0f1;
    border: 1px solid #2980b9;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 12px;
}
QPushButton {
    background: #2980b9;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 5px 12px;
    font-weight: bold;
    font-size: 12px;
}
QPushButton:hover { background: #3498db; }
QPushButton:pressed { background: #1a638e; }
QPushButton:disabled { background: #636e72; color: #b2bec3; }
QToolBar {
    background: #2c3e50;
    border: none;
    spacing: 3px;
    padding: 3px;
}
QToolBar QToolButton {
    background: transparent;
    color: #ecf0f1;
    border-radius: 4px;
    padding: 4px 6px;
    font-size: 16px;
}
QToolBar QToolButton:hover { background: #34495e; }
QToolBar QToolButton:pressed { background: #2980b9; }
QProgressBar {
    background: #34495e;
    color: white;
    border: 1px solid #2980b9;
    border-radius: 3px;
    text-align: center;
    font-size: 11px;
}
QProgressBar::chunk { background: #2980b9; }
"""


class _DragTreeWidget(QTreeWidget):
    """QTreeWidget che supporta il drag-out di file Nextcloud."""
    layer_dropped = pyqtSignal(str)  # emette l'ID o nome del layer quando viene droppato

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(_DragDropMode)
        self.setSelectionMode(_SingleSelection)

    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat("application/x-vnd.qgis.qgis.uri"):
            event.accept()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat("application/x-vnd.qgis.qgis.uri"):
            event.accept()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        mime = event.mimeData()
        if mime.hasFormat("application/x-vnd.qgis.qgis.uri"):
            raw = bytes(mime.data("application/x-vnd.qgis.qgis.uri"))
            try:
                data = raw.decode("utf-16")
            except UnicodeDecodeError:
                data = raw.decode("utf-8", errors="replace")
            # tipicamente contiene righe col formato: "type:nome:source" o layerID
            if data:
                self.layer_dropped.emit(data)
            event.accept()
        else:
            super().dropEvent(event)

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item:
            return
        data = item.data(0, _Qt_UserRole)
        if not data or data.get("is_dir"):
            return  # non dragare le cartelle
        from qgis.PyQt.QtCore import QMimeData, QByteArray
        mime = QMimeData()
        import json
        payload = json.dumps(data).encode("utf-8")
        mime.setData("application/x-qgis-ledger-nc", QByteArray(payload))
        mime.setText(data.get("name", ""))
        from qgis.PyQt.QtGui import QDrag, QPixmap, QPainter, QColor as QC2
        drag = QDrag(self)
        drag.setMimeData(mime)
        # mini pixmap
        pm = QPixmap(120, 24)
        pm.fill(QC2(52, 73, 94))
        p = QPainter(pm)
        p.setPen(QC2(236, 240, 241))
        p.drawText(4, 16, data.get("name", "file")[:18])
        p.end()
        drag.setPixmap(pm)
        drag.exec(_Qt_CopyAction)


class NextcloudBrowserPanel(QWidget):
    """
    Pannello Widget per la navigazione e gestione dei file Nextcloud/Cloud.

    Operazioni supportate:
      - Naviga cartelle (doppio click o Enter)
      - Torna alla cartella padre (pulsante ⬆)
      - Aggiorna (ricarica la directory corrente)
      - Nuova cartella
      - Rinomina file/cartella
      - Elimina file/cartella
      - Carica file locale → Nextcloud
      - Scarica file da Nextcloud → locale
    """
    # Signal emitted when a layer is successfully loaded from cloud (layer_object, source_name)
    layer_loaded = pyqtSignal(object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NextcloudBrowserPanel")
        self.setMinimumWidth(300)

        # State
        self._client = None
        self._current_path = ""      # relative to webdav_base
        self._history = []           # navigation stack
        self._pool = QThreadPool.globalInstance()

        # Build UI
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        root = QWidget()
        root.setObjectName("nc_root")
        root.setStyleSheet(DARK_STYLE)
        main_layout.addWidget(root)
        
        self._build_ui(root)

    # ------------------------------------------------------------------ #
    # UI Construction
    # ------------------------------------------------------------------ #

    def _build_ui(self, root: QWidget):
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(4, 4, 4, 4)
        main_layout.setSpacing(4)

        # ── Toolbar ──────────────────────────────────────────────────── #
        tb = QToolBar()
        tb.setIconSize(tb.iconSize())
        tb.setMovable(False)
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)

        self.act_refresh = QAction("🔄 Aggiorna", root)
        self.act_refresh.setToolTip("Aggiorna la cartella corrente")
        self.act_refresh.triggered.connect(self._refresh)
        tb.addAction(self.act_refresh)

        self.act_up = QAction("⬆️ Su", root)
        self.act_up.setToolTip("Vai alla cartella superiore")
        self.act_up.triggered.connect(self._go_up)
        tb.addAction(self.act_up)

        tb.addSeparator()

        self.act_mkdir = QAction("📁 Nuova", root)
        self.act_mkdir.setToolTip("Nuova cartella")
        self.act_mkdir.triggered.connect(self._on_mkdir)
        tb.addAction(self.act_mkdir)

        self.act_rename = QAction("✏️ Rinomina", root)
        self.act_rename.setToolTip("Rinomina elemento selezionato")
        self.act_rename.triggered.connect(self._on_rename)
        tb.addAction(self.act_rename)

        self.act_delete = QAction("🗑️ Elimina", root)
        self.act_delete.setToolTip("Elimina elemento selezionato")
        self.act_delete.triggered.connect(self._on_delete)
        tb.addAction(self.act_delete)

        tb.addSeparator()

        self.act_upload = QAction("⬆ Upload", root)
        self.act_upload.setToolTip("Carica file locale su Cloud")
        self.act_upload.triggered.connect(self._on_upload)
        tb.addAction(self.act_upload)

        self.act_download = QAction("⬇ Download", root)
        self.act_download.setToolTip("Scarica file selezionato dal Cloud in locale")
        self.act_download.triggered.connect(self._on_download)
        tb.addAction(self.act_download)

        main_layout.addWidget(tb)

        # ── Path bar ─────────────────────────────────────────────────── #
        path_row = QHBoxLayout()
        path_row.setSpacing(4)
        lbl_path = QLabel("📂")
        lbl_path.setFixedWidth(20)
        path_row.addWidget(lbl_path)

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("/")
        self.path_edit.setReadOnly(True)
        self.path_edit.setToolTip("Percorso corrente nella cartella Nextcloud")
        path_row.addWidget(self.path_edit)
        main_layout.addLayout(path_row)

        # ── File tree (con supporto Drag) ────────────────────────────── #
        self.tree = _DragTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Nome", "Dimensione", "Modificato"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setContextMenuPolicy(_Qt_CustomCtxMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setDefaultSectionSize(120)
        self.tree.setColumnWidth(0, 220)
        self.tree.setColumnWidth(1, 80)
        main_layout.addWidget(self.tree, stretch=1)

        # ── Progress bar ─────────────────────────────────────────────── #
        self.progress = QProgressBar()
        self.progress.setMaximum(0)   # indeterminate
        self.progress.setFixedHeight(6)
        self.progress.setTextVisible(False)
        self.progress.hide()
        main_layout.addWidget(self.progress)

        # ── Status label ─────────────────────────────────────────────── #
        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        self.lbl_status.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        main_layout.addWidget(self.lbl_status)

    # ------------------------------------------------------------------ #
    # Public: trigger connection from plugin
    # ------------------------------------------------------------------ #

    def connect_cloud(self, client):
        """
        (Re-)create the connection using any CloudBackend-compatible client
        (NextcloudClient, GenericWebDAVClient, etc.) and load the root.
        Called by the plugin whenever the panel becomes visible.
        """
        if client is None:
            self._show_not_configured()
            return
        self._client = client
        self._current_path = ""
        self._history.clear()
        self._refresh()

    def connect_nextcloud(self, server: str, username: str, password: str, remote_folder: str):
        """
        Legacy compatibility shim — creates a NextcloudClient and delegates to connect_cloud.
        """
        if not server or not username:
            self._show_not_configured()
            return
        self.connect_cloud(NextcloudClient(server, username, password, remote_folder))

    # ------------------------------------------------------------------ #
    # Navigation
    # ------------------------------------------------------------------ #

    def _refresh(self):
        if self._client is None:
            self._show_not_configured()
            return
        self._set_busy(True)
        worker = _Worker(self._client.list_directory, self._current_path)
        worker.signals.finished.connect(self._on_list_done)
        worker.signals.error.connect(self._on_error)
        self._pool.start(worker)

    def _on_list_done(self, items: list):
        self._set_busy(False)
        self.tree.clear()
        display_path = "/" + self._current_path if self._current_path else "/"
        self.path_edit.setText(display_path)

        for item_data in items:
            row = QTreeWidgetItem()
            icon = "📁" if item_data["is_dir"] else "📄"
            row.setText(0, f"{icon}  {item_data['name']}")
            row.setData(0, _Qt_UserRole, item_data)

            # Size
            if item_data["is_dir"]:
                row.setText(1, "")
            else:
                row.setText(1, self._format_size(item_data["size"]))
                row.setForeground(1, QColor("#bdc3c7"))

            # Modified date — parse RFC 2822
            mod_str = item_data.get("modified", "")
            row.setText(2, self._format_date(mod_str))
            row.setForeground(2, QColor("#bdc3c7"))

            if item_data["is_dir"]:
                row.setForeground(0, QColor("#3498db"))
                font = row.font(0)
                font.setBold(True)
                row.setFont(0, font)

            self.tree.addTopLevelItem(row)

        n = len(items)
        self.lbl_status.setText(f"{n} element{'i' if n != 1 else 'o'} — {display_path}")

    def _go_up(self):
        if self._current_path:
            parts = self._current_path.rstrip("/").split("/")
            self._current_path = "/".join(parts[:-1])
            self._refresh()

    def _navigate_into(self, item_data: dict):
        """Navigate into a folder."""
        # Compute new relative path from href
        # href is the full WebDAV path; we strip the webdav_base prefix
        href = urllib.parse.unquote(item_data["href"].rstrip("/"))
        base = self._client.webdav_base
        if href.startswith(base):
            rel = href[len(base):].lstrip("/")
        else:
            # fallback: append name
            name = item_data["name"]
            rel = (self._current_path + "/" + name).lstrip("/")
        self._history.append(self._current_path)
        self._current_path = rel
        self._refresh()

    def _on_item_double_clicked(self, item: QTreeWidgetItem, col: int):
        data = item.data(0, _Qt_UserRole)
        if not data:
            return
        if data["is_dir"]:
            self._navigate_into(data)
        else:
            self._auto_download_and_load(data)

    def _get_workspace_dir(self) -> str:
        """Restituisce (e crea) la cartella locale di workspace per il percorso corrente."""
        base = os.path.join(os.path.expanduser("~"), "QGIS_Cloud_Workspace")
        clean_rel = self._current_path.strip("/")
        full_path = os.path.join(base, clean_rel) if clean_rel else base
        os.makedirs(full_path, exist_ok=True)
        return full_path

    def _auto_download_and_load(self, data: dict):
        name = data["name"]
        ext = os.path.splitext(name)[1].lower()
        gis_extensions = {".shp", ".gpkg", ".sqlite", ".db", ".tif", ".tiff", ".geojson", ".kml", ".qgz", ".qgs", ".dxf", ".csv"}

        if ext not in gis_extensions:
            # Fallback a un download semplice
            reply = QMessageBox.question(
                self, "Scarica file", f"Questo file ('{name}') non sembra un layer supportato per l'import automatico.\nVuoi scaricarlo comunque?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                self._on_download()
            return

        target_dir = self._get_workspace_dir()
        files_to_download = [name]

        # Logica speciale: per gli shapefile, cerchiamo di scaricare anche i file correlati presenti nella stessa cartella remota
        if ext == ".shp":
            base_name = os.path.splitext(name)[0]
            root = self.tree.invisibleRootItem()
            related_exts = {".dbf", ".shx", ".prj", ".cpg", ".qix", ".sbn", ".sbx"}
            for i in range(root.childCount()):
                child_data = root.child(i).data(0, _Qt_UserRole)
                if child_data and not child_data["is_dir"]:
                    c_name = child_data["name"]
                    c_base, c_ext = os.path.splitext(c_name)
                    if c_base == base_name and c_ext.lower() in related_exts:
                        files_to_download.append(c_name)

        # Se il file è un progetto .qgz, cerchiamo anche il suo database ledger e il file qgd
        if ext in {".qgz", ".qgs"}:
            base_name = name  # QGIS Ledger DB base name is usually progetto.qgz.ledger.db
            root = self.tree.invisibleRootItem()
            for i in range(root.childCount()):
                child_data = root.child(i).data(0, _Qt_UserRole)
                if child_data and not child_data["is_dir"]:
                    c_name = child_data["name"]
                    if c_name == f"{name}.ledger.db" or c_name == f"{name}.ledger.db-shm" or c_name == f"{name}.ledger.db-wal" or c_name == f"{base_name}~":
                        files_to_download.append(c_name)

        self._set_busy(True)
        self.lbl_status.setText(f"⬇️ Check-out Cloud in corso...")

        worker = _Worker(self._download_sync_files, files_to_download, target_dir)
        worker.signals.finished.connect(lambda res: self._on_auto_load_done(res[0], res[1]))
        worker.signals.error.connect(self._on_error)
        self._pool.start(worker)

    def _download_sync_files(self, file_names: list, target_dir: str):
        # Scarica la lista di file in modo sequenziale
        for fname in file_names:
            remote = (self._current_path + "/" + fname).lstrip("/")
            local = os.path.join(target_dir, fname)
            # Evita di riscaricare file enormi se non sono cambiati? (Per ora scarichiamo sempre l'ultima versione)
            self._client.download(remote, local)
        return target_dir, file_names[0]

    def _on_auto_load_done(self, target_dir: str, primary_file: str):
        self._set_busy(False)
        self.lbl_status.setText(f"✅ Check-out completato. Importo in QGIS...")
        local_path = os.path.join(target_dir, primary_file)
        
        from qgis.utils import iface
        from qgis.core import QgsProject

        ext = os.path.splitext(primary_file)[1].lower()
        if ext in {".qgz", ".qgs"}:
            # Se è un progetto, chiedi se vuole salvarlo prima di aprirlo
            reply = QMessageBox.question(
                self, "Cloud Checkout",
                f"Progetto estratto in:\n{target_dir}\n\nAprire questo progetto in QGIS?\n(Le eventuali modifiche al progetto attuale andranno perse se non salvate).",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                iface.addProject(local_path)
                QgsProject.instance().writeEntry("QGIS_Ledger", "cloud_sync_path", (self._current_path + "/" + primary_file).lstrip("/"))
                QgsProject.instance().writeEntry("QGIS_Ledger", "cloud_sync_workspace", target_dir)
                QMessageBox.information(
                    self, "Progetto Cloud",
                    "Progetto collegato correttamente a Nextcloud.\nOgni commit verrà ora spinto anche in Cloud!"
                )
        else:
            # È un layer
            layer = None
            if ext in {".shp", ".gpkg", ".sqlite", ".db", ".geojson", ".kml", ".csv", ".dxf"}:
                layer = iface.addVectorLayer(local_path, primary_file, "ogr")
            elif ext in {".tif", ".tiff"}:
                layer = iface.addRasterLayer(local_path, primary_file)

            if not layer or not layer.isValid():
                QMessageBox.warning(self, "QGIS Ledger", f"Impossibile caricare il layer in QGIS:\n{local_path}")
            else:
                self.layer_loaded.emit(layer, primary_file)
                QMessageBox.information(
                    self, "Workspace Cloud Sincronizzato",
                    f"Il layer è stato estratto nel workspace locale:\n{target_dir}\n\nQGIS Ledger ora traccerà correttamente questo layer!"
                )
        self.lbl_status.setText(f"✅ Pronto.")

    # ------------------------------------------------------------------ #
    # CRUD Actions
    # ------------------------------------------------------------------ #

    def _get_selected_data(self):
        sel = self.tree.selectedItems()
        if not sel:
            return None
        return sel[0].data(0, _Qt_UserRole)

    def _on_mkdir(self):
        if not self._client:
            return
        name, ok = QInputDialog.getText(
            self, "Nuova Cartella", "Nome della nuova cartella:",
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        remote = (self._current_path + "/" + name).lstrip("/")
        self._set_busy(True)
        worker = _Worker(self._client.make_directory, remote)
        worker.signals.finished.connect(lambda _: (self._set_busy(False), self._refresh()))
        worker.signals.error.connect(self._on_error)
        self._pool.start(worker)

    def _on_rename(self):
        if not self._client:
            return
        data = self._get_selected_data()
        if not data:
            QMessageBox.information(self, "Nextcloud", "Seleziona un elemento per rinominarlo.")
            return
        old_name = data["name"]
        new_name, ok = QInputDialog.getText(
            self, "Rinomina", f"Nuovo nome per '{old_name}':", text=old_name
        )
        if not ok or not new_name.strip() or new_name.strip() == old_name:
            return
        new_name = new_name.strip()
        parent_path = self._current_path
        old_remote = (parent_path + "/" + old_name).lstrip("/")
        new_remote = (parent_path + "/" + new_name).lstrip("/")
        self._set_busy(True)
        worker = _Worker(self._client.move, old_remote, new_remote)
        worker.signals.finished.connect(lambda _: (self._set_busy(False), self._refresh()))
        worker.signals.error.connect(self._on_error)
        self._pool.start(worker)

    def _on_delete(self):
        if not self._client:
            return
        data = self._get_selected_data()
        if not data:
            QMessageBox.information(self, "Nextcloud", "Seleziona un elemento da eliminare.")
            return
        tipo = "cartella" if data["is_dir"] else "file"
        extra = "\n⚠️ Verrà eliminato l'intero contenuto della cartella!" if data["is_dir"] else ""
        reply = QMessageBox.question(
            self, "Conferma Eliminazione",
            f"Sei sicuro di voler eliminare {tipo} '{data['name']}'?" + extra,
            _QMB_Yes | _QMB_No, _QMB_No
        )
        if reply != _QMB_Yes:
            return
        remote = (self._current_path + "/" + data["name"]).lstrip("/")
        self._set_busy(True)
        worker = _Worker(self._client.delete, remote)
        worker.signals.finished.connect(lambda _: (self._set_busy(False), self._refresh()))
        worker.signals.error.connect(self._on_error)
        self._pool.start(worker)

    def _on_upload(self):
        if not self._client:
            return
        local_paths, _ = QFileDialog.getOpenFileNames(
            self, "Seleziona file da caricare su Nextcloud", "", "Tutti i file (*)"
        )
        if not local_paths:
            return
        for local_path in local_paths:
            name = os.path.basename(local_path)
            remote = (self._current_path + "/" + name).lstrip("/")
            self._set_busy(True)
            self.lbl_status.setText(f"⬆️ Caricamento di '{name}'…")
            worker = _Worker(self._client.upload, remote, local_path)
            worker.signals.finished.connect(lambda _, n=name: self._on_upload_done(n))
            worker.signals.error.connect(self._on_error)
            self._pool.start(worker)

    def _on_upload_done(self, name: str):
        self._set_busy(False)
        self.lbl_status.setText(f"✅ '{name}' caricato con successo.")
        self._refresh()

    def _on_download(self):
        if not self._client:
            return
        data = self._get_selected_data()
        if not data:
            QMessageBox.information(self, "Nextcloud", "Seleziona un file da scaricare.")
            return
        if data["is_dir"]:
            QMessageBox.warning(self, "Nextcloud", "Non è possibile scaricare una cartella intera.\nSeleziona un singolo file.")
            return
        name = data["name"]
        local_path, _ = QFileDialog.getSaveFileName(
            self, "Salva file scaricato", name, "Tutti i file (*)"
        )
        if not local_path:
            return
        remote = (self._current_path + "/" + name).lstrip("/")
        self._set_busy(True)
        self.lbl_status.setText(f"⬇️ Download di '{name}'…")
        worker = _Worker(self._client.download, remote, local_path)
        worker.signals.finished.connect(lambda _: self._on_download_done(local_path, name))
        worker.signals.error.connect(self._on_error)
        self._pool.start(worker)

    def _on_download_done(self, local_path: str, name: str):
        self._set_busy(False)
        self.lbl_status.setText(f"✅ '{name}' scaricato in: {local_path}")
        QMessageBox.information(
            self, "Nextcloud — Download Completato ✅",
            f"File '{name}' scaricato con successo in:\n{local_path}"
        )

    # ------------------------------------------------------------------ #
    # Context menu
    # ------------------------------------------------------------------ #

    def _on_context_menu(self, pos):
        data = self._get_selected_data()
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu{background:#2c3e50;color:#ecf0f1;border:1px solid #34495e;}"
            "QMenu::item:selected{background:#3498db;}"
        )
        if data:
            if not data["is_dir"]:
                menu.addAction("⬇️  Scarica file", self._on_download)
            menu.addAction("✏️  Rinomina", self._on_rename)
            menu.addAction("🗑️  Elimina", self._on_delete)
            menu.addSeparator()
        menu.addAction("📁  Nuova cartella", self._on_mkdir)
        menu.addAction("⬆️  Carica file", self._on_upload)
        menu.addSeparator()
        menu.addAction("🔄  Aggiorna", self._refresh)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _set_busy(self, busy: bool):
        if busy:
            self.progress.show()
        else:
            self.progress.hide()
        for act in [self.act_mkdir, self.act_rename, self.act_delete,
                    self.act_upload, self.act_download, self.act_refresh]:
            act.setEnabled(not busy)

    def _on_error(self, msg: str):
        self._set_busy(False)
        self.lbl_status.setText(f"❌ {msg}")
        QMessageBox.critical(self, "Nextcloud — Errore", msg)

    def _show_not_configured(self):
        self.tree.clear()
        self.path_edit.setText("")
        self.lbl_status.setText(
            "⚠️ Nextcloud non configurato.\n"
            "Vai in ⚙ Settings → Tipo Archiviazione: Nextcloud\n"
            "e inserisci Server URL, Utente e Password."
        )

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024*1024):.1f} MB"
        return f"{size_bytes / (1024**3):.2f} GB"

    @staticmethod
    def _format_date(rfc2822: str) -> str:
        """Parse RFC 2822 date string to a human-readable format."""
        if not rfc2822:
            return ""
        try:
            import email.utils
            ts = email.utils.parsedate_to_datetime(rfc2822)
            return ts.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return rfc2822[:16] if len(rfc2822) >= 16 else rfc2822
