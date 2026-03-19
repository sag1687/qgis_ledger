# -*- coding: utf-8 -*-
"""
ledger_ledger.py — Transaction Ledger

SQLite-based engine that records every modification with granular change tracking:
Who, What, When, Why. Stores both full snapshots and per-feature diffs.
"""

import os
import json
import sqlite3
import getpass
import platform
from datetime import datetime

from qgis.core import (
    QgsProject,
    QgsFeature,
    QgsGeometry,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QVariant


class LedgerDB:
    """Transaction Ledger — the heart of QGIS Ledger."""

    def __init__(self):
        self._conn = None
        self._db_path = None

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #

    @staticmethod
    def _project_dir():
        path = QgsProject.instance().fileName()
        return os.path.dirname(path) if path else None

    def history_dir(self):
        d = self._project_dir()
        if not d:
            return None
        return os.path.join(d, ".ledger_history")

    def db_path(self):
        h = self.history_dir()
        if not h:
            return None
        os.makedirs(h, exist_ok=True)
        for sub in ("project", "vector", "raster"):
            os.makedirs(os.path.join(h, sub), exist_ok=True)
        return os.path.join(h, "ledger.db")

    def connect(self):
        path = self.db_path()
        if not path:
            return False
        self._db_path = path
        self._conn = sqlite3.connect(path)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._create_tables()
        return True

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def is_connected(self):
        return self._conn is not None

    # ------------------------------------------------------------------ #
    # Schema
    # ------------------------------------------------------------------ #

    def _create_tables(self):
        c = self._conn.cursor()

        # -- Commits --------------------------------------------------- #
        c.execute("""
            CREATE TABLE IF NOT EXISTS ledger_commits (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                layer_name  TEXT    NOT NULL,
                layer_id    TEXT,
                user_name   TEXT    NOT NULL,
                machine     TEXT    NOT NULL,
                message     TEXT    NOT NULL,
                timestamp   TEXT    NOT NULL,
                feat_count  INTEGER NOT NULL DEFAULT 0,
                commit_type TEXT    NOT NULL DEFAULT 'VECTOR',
                file_path   TEXT,
                parent_id   INTEGER,
                FOREIGN KEY (parent_id) REFERENCES ledger_commits(id)
            );
        """)

        # -- Full snapshots -------------------------------------------- #
        c.execute("""
            CREATE TABLE IF NOT EXISTS ledger_snapshots (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                commit_id   INTEGER NOT NULL,
                fid         INTEGER NOT NULL,
                geometry    TEXT,
                attributes  TEXT,
                FOREIGN KEY (commit_id) REFERENCES ledger_commits(id)
                    ON DELETE CASCADE
            );
        """)

        # -- Granular changes ------------------------------------------ #
        c.execute("""
            CREATE TABLE IF NOT EXISTS ledger_changes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                commit_id   INTEGER NOT NULL,
                fid         INTEGER NOT NULL,
                change_type TEXT    NOT NULL,
                old_geom    TEXT,
                new_geom    TEXT,
                old_attrs   TEXT,
                new_attrs   TEXT,
                FOREIGN KEY (commit_id) REFERENCES ledger_commits(id)
                    ON DELETE CASCADE
            );
        """)

        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_snap_commit
            ON ledger_snapshots(commit_id);
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_chg_commit
            ON ledger_changes(commit_id);
        """)
        
        # Upgrade schema for older DBs
        try:
            c.execute("ALTER TABLE ledger_commits ADD COLUMN style_qml TEXT;")
        except sqlite3.OperationalError:
            pass

        self._conn.commit()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    @staticmethod
    def _make_path_relative(filepath: str) -> str:
        """Convert absolute path to a relative token to survive cross-OS/Nextcloud moves."""
        if not filepath:
            return filepath
        proj_dir = LedgerDB._project_dir()
        if not proj_dir:
            return filepath
        
        pd_forward = proj_dir.replace("\\", "/")
        pd_back = proj_dir.replace("/", "\\")
        
        res = filepath
        if pd_forward in res:
            res = res.replace(pd_forward, "{PROJECT_DIR}")
        elif pd_back in res:
            res = res.replace(pd_back, "{PROJECT_DIR}")
            
        return res

    @staticmethod
    def _make_path_absolute(filepath: str) -> str:
        """Convert a relative token back to the current machine's absolute path."""
        if not filepath:
            return filepath
        if "{PROJECT_DIR}" not in filepath:
            return filepath
            
        proj_dir = LedgerDB._project_dir()
        if not proj_dir:
            return filepath
            
        # Standardize to forward slash for QGIS sources, even on Windows
        pd_forward = proj_dir.replace("\\", "/")
        return filepath.replace("{PROJECT_DIR}", pd_forward)

    @staticmethod
    def _serialize_attrs(feat, fields):
        """Serialize feature attributes to a JSON-safe dict."""
        attrs = {}
        for i, field in enumerate(fields):
            val = feat.attribute(i)
            if val is None or (isinstance(val, QVariant) and val.isNull()):
                attrs[field.name()] = None
            else:
                try:
                    json.dumps(val)
                    attrs[field.name()] = val
                except (TypeError, ValueError):
                    attrs[field.name()] = str(val)
        return attrs

    @staticmethod
    def _features_dict(layer):
        """Return {fid: {geometry_wkt, attributes}} for all features."""
        result = {}
        fields = layer.fields()
        for feat in layer.getFeatures():
            geom = feat.geometry().asWkt() if feat.hasGeometry() else None
            attrs = LedgerDB._serialize_attrs(feat, fields)
            result[feat.id()] = {"geometry": geom, "attributes": attrs}
        return result

    # ------------------------------------------------------------------ #
    # Public API — Commit
    # ------------------------------------------------------------------ #

    def _get_layer_style(self, layer) -> str:
        """Helper to get layer style as QML string."""
        if not layer: return None
        import tempfile
        tmp = tempfile.NamedTemporaryFile(suffix=".qml", delete=False)
        tmp.close()
        try:
            layer.saveNamedStyle(tmp.name)
            with open(tmp.name, "r", encoding="utf-8") as f:
                style = f.read()
            return style
        except Exception:
            return None
        finally:
            if os.path.exists(tmp.name):
                os.remove(tmp.name)

    def _insert_commit_record(self, layer_name, layer_id, message, user, feat_count, commit_type="VECTOR", file_path=None, style_qml=None):
        user = user or getpass.getuser()
        machine = platform.node()
        ts = datetime.now().isoformat(timespec="seconds")
        prev_commit = self._latest_commit_id(layer_name)

        c = self._conn.cursor()
        
        rel_file_path = self._make_path_relative(file_path)
        
        c.execute(
            "INSERT INTO ledger_commits "
            "(layer_name, layer_id, user_name, machine, message, "
            " timestamp, feat_count, commit_type, file_path, parent_id, style_qml) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (layer_name, layer_id, user, machine, message,
             ts, feat_count, commit_type, rel_file_path, prev_commit, style_qml),
        )
        return c.lastrowid, prev_commit

    def create_commit(self, layer: QgsVectorLayer, message: str,
                      user: str = None) -> int:
        """Record the current state of *layer* as a new commit.

        Stores both a full snapshot AND granular changes compared to the
        previous commit on the same layer.

        Returns the commit id or -1 on failure.
        """
        if not self._conn:
            return -1

        fields = layer.fields()
        current = self._features_dict(layer)
        style_str = self._get_layer_style(layer)

        commit_id, prev_commit = self._insert_commit_record(
            layer.name(), layer.id(), message, user, layer.featureCount(), "VECTOR", layer.source(), style_str
        )
        c = self._conn.cursor()

        # Store full snapshot
        for fid, data in current.items():
            c.execute(
                "INSERT INTO ledger_snapshots "
                "(commit_id, fid, geometry, attributes) VALUES (?,?,?,?)",
                (commit_id, fid, data["geometry"],
                 json.dumps(data["attributes"])),
            )

        # Compute and store granular changes
        if prev_commit:
            prev_features = {
                s["fid"]: s
                for s in self.get_snapshot_features(prev_commit)
            }
        else:
            prev_features = {}

        prev_fids = set(prev_features.keys())
        curr_fids = set(current.keys())

        # ADDED features
        for fid in curr_fids - prev_fids:
            c.execute(
                "INSERT INTO ledger_changes "
                "(commit_id, fid, change_type, new_geom, new_attrs) "
                "VALUES (?,?,?,?,?)",
                (commit_id, fid, "ADD",
                 current[fid]["geometry"],
                 json.dumps(current[fid]["attributes"])),
            )

        # DELETED features
        for fid in prev_fids - curr_fids:
            c.execute(
                "INSERT INTO ledger_changes "
                "(commit_id, fid, change_type, old_geom, old_attrs) "
                "VALUES (?,?,?,?,?)",
                (commit_id, fid, "DELETE",
                 prev_features[fid]["geometry"],
                 json.dumps(prev_features[fid]["attributes"])),
            )

        # MODIFIED features
        for fid in curr_fids & prev_fids:
            old = prev_features[fid]
            new = current[fid]
            geom_changed = old["geometry"] != new["geometry"]
            attrs_changed = old["attributes"] != new["attributes"]
            if geom_changed or attrs_changed:
                c.execute(
                    "INSERT INTO ledger_changes "
                    "(commit_id, fid, change_type, "
                    " old_geom, new_geom, old_attrs, new_attrs) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (commit_id, fid, "MODIFY",
                     old["geometry"], new["geometry"],
                     json.dumps(old["attributes"]),
                     json.dumps(new["attributes"])),
                )

        self._conn.commit()
        return commit_id

    def create_project_commit(self, message: str, user: str = None) -> int:
        """Commit the entire QGIS project file (.qgz)."""
        if not self._conn:
            return -1
        
        proj_path = QgsProject.instance().fileName()
        if not proj_path:
            return -1
            
        # Ensure project is saved before committing
        QgsProject.instance().write()
        
        commit_id, _ = self._insert_commit_record(
            layer_name="[Project State]", 
            layer_id="project", 
            message=message, 
            user=user, 
            feat_count=0, 
            commit_type="PROJECT"
        )
        
        # Copy file physical
        ext = os.path.splitext(proj_path)[1]
        dest_name = f"commit_{commit_id}{ext}"
        dest_path = os.path.join(self.history_dir(), "project", dest_name)
        
        import shutil
        shutil.copy2(proj_path, dest_path)
        
        # Update db with file_path
        c = self._conn.cursor()
        c.execute("UPDATE ledger_commits SET file_path=? WHERE id=?", (dest_name, commit_id))
        self._conn.commit()
        return commit_id

    def create_raster_commit(self, layer, message: str, user: str = None) -> int:
        """Commit a physical copy of a Raster layer (.tif)."""
        if not self._conn:
            return -1
            
        src_path = layer.source()
        if not os.path.isfile(src_path):
            return -1
            
        style_str = self._get_layer_style(layer)
            
        commit_id, _ = self._insert_commit_record(
            layer_name=layer.name(), 
            layer_id=layer.id(), 
            message=message, 
            user=user, 
            feat_count=1,
            commit_type="RASTER",
            style_qml=style_str
        )
        
        ext = os.path.splitext(src_path)[1]
        dest_name = f"commit_{commit_id}_{layer.name()}{ext}"
        dest_path = os.path.join(self.history_dir(), "raster", dest_name)
        
        import shutil
        shutil.copy2(src_path, dest_path)
        
        c = self._conn.cursor()
        c.execute("UPDATE ledger_commits SET file_path=? WHERE id=?", (dest_name, commit_id))
        self._conn.commit()
        return commit_id

    # ------------------------------------------------------------------ #
    # Public API — History / Read
    # ------------------------------------------------------------------ #

    def _latest_commit_id(self, layer_name: str):
        c = self._conn.cursor()
        c.execute(
            "SELECT id FROM ledger_commits WHERE layer_name=? "
            "ORDER BY id DESC LIMIT 1",
            (layer_name,),
        )
        row = c.fetchone()
        return row[0] if row else None

    def get_history(self, layer_name: str = None) -> list:
        """Return list of commit dicts, newest first."""
        if not self._conn:
            return []
        c = self._conn.cursor()
        base = (
            "SELECT id, layer_name, layer_id, user_name, machine, "
            "message, timestamp, feat_count, commit_type, file_path, parent_id "
            "FROM ledger_commits "
        )
        if layer_name:
            c.execute(base + "WHERE layer_name=? ORDER BY id DESC",
                      (layer_name,))
        else:
            c.execute(base + "ORDER BY id DESC")
        cols = [
            "id", "layer_name", "layer_id", "user_name", "machine",
            "message", "timestamp", "feat_count", "commit_type", "file_path", "parent_id", "style_qml"
        ]
        
        results = []
        for row in c.fetchall():
            d = dict(zip(cols, row))
            d["file_path"] = self._make_path_absolute(d.get("file_path"))
            results.append(d)
        return results

    def get_commit_info(self, commit_id: int) -> dict:
        if not self._conn:
            return {}
        c = self._conn.cursor()
        c.execute(
            "SELECT id, layer_name, layer_id, user_name, machine, "
            "message, timestamp, feat_count, commit_type, file_path, parent_id "
            "FROM ledger_commits WHERE id=?",
            (commit_id,),
        )
        row = c.fetchone()
        if not row:
            return {}
        cols = [
            "id", "layer_name", "layer_id", "user_name", "machine",
            "message", "timestamp", "feat_count", "commit_type", "file_path", "parent_id", "style_qml"
        ]
        res = dict(zip(cols, row))
        res["file_path"] = self._make_path_absolute(res.get("file_path"))
        return res

    def get_snapshot_features(self, commit_id: int) -> list:
        """Return [{fid, geometry, attributes}, ...] for a commit."""
        if not self._conn:
            return []
        c = self._conn.cursor()
        c.execute(
            "SELECT fid, geometry, attributes FROM ledger_snapshots "
            "WHERE commit_id=?",
            (commit_id,),
        )
        return [
            {
                "fid": fid,
                "geometry": geom,
                "attributes": json.loads(attrs) if attrs else {},
            }
            for fid, geom, attrs in c.fetchall()
        ]

    def get_changes(self, commit_id: int) -> list:
        """Return granular changes for a commit.

        Each item: {fid, change_type, old_geom, new_geom,
                     old_attrs, new_attrs}
        """
        if not self._conn:
            return []
        c = self._conn.cursor()
        c.execute(
            "SELECT fid, change_type, old_geom, new_geom, "
            "old_attrs, new_attrs FROM ledger_changes WHERE commit_id=?",
            (commit_id,),
        )
        return [
            {
                "fid": fid,
                "change_type": ct,
                "old_geom": og,
                "new_geom": ng,
                "old_attrs": json.loads(oa) if oa else {},
                "new_attrs": json.loads(na) if na else {},
            }
            for fid, ct, og, ng, oa, na in c.fetchall()
        ]

    # ------------------------------------------------------------------ #
    # Public API — Rollback
    # ------------------------------------------------------------------ #

    def rollback_to(self, layer_or_project, commit_id: int) -> bool:
        """Replace all features in *layer* with the snapshot at *commit_id* or restore project/raster.

        Returns True on success.
        """
        info = self.get_commit_info(commit_id)
        if not info:
            return False
            
        ctype = info.get("commit_type", "VECTOR")
        
        if ctype == "PROJECT":
            if not info.get("file_path"): return False
            src = os.path.join(self.history_dir(), "project", info["file_path"])
            proj_path = QgsProject.instance().fileName()
            import shutil
            shutil.copy2(src, proj_path)
            # Instruct QGIS to reload
            QgsProject.instance().read(proj_path)
            return True
            
        elif ctype == "RASTER":
            if not info.get("file_path"): return False
            src = os.path.join(self.history_dir(), "raster", info["file_path"])
            if hasattr(layer_or_project, 'source'):
                target_path = layer_or_project.source()
                import shutil
                shutil.copy2(src, target_path)
                
                # Restore style if available
                if info.get("style_qml"):
                    import tempfile
                    tmp = tempfile.NamedTemporaryFile(suffix=".qml", mode="w", encoding="utf-8", delete=False)
                    tmp.write(info["style_qml"])
                    tmp.close()
                    layer_or_project.loadNamedStyle(tmp.name)
                    os.remove(tmp.name)
                
                layer_or_project.dataProvider().reloadData()
                layer_or_project.triggerRepaint()
            return True

        # Normal VECTOR rollback
        layer = layer_or_project
        snap = self.get_snapshot_features(commit_id)
        if snap is None:
            return False

        was_editing = layer.isEditable()
        if not was_editing:
            layer.startEditing()

        # Delete current features
        fids = [f.id() for f in layer.getFeatures()]
        layer.deleteFeatures(fids)

        # Re-add from snapshot
        fields = layer.fields()
        for item in snap:
            feat = QgsFeature(fields)
            if item["geometry"]:
                feat.setGeometry(QgsGeometry.fromWkt(item["geometry"]))
            for fname, val in item["attributes"].items():
                idx = fields.lookupField(fname)
                if idx >= 0:
                    feat.setAttribute(idx, val)
            layer.addFeature(feat)

        if not was_editing:
            layer.commitChanges()
            
        # Restore style if available
        if info.get("style_qml"):
            import tempfile
            tmp = tempfile.NamedTemporaryFile(suffix=".qml", mode="w", encoding="utf-8", delete=False)
            tmp.write(info["style_qml"])
            tmp.close()
            layer.loadNamedStyle(tmp.name)
            os.remove(tmp.name)

        layer.triggerRepaint()
        return True

    # ------------------------------------------------------------------ #
    # Public API — Delete
    # ------------------------------------------------------------------ #

    def delete_commit(self, commit_id: int):
        """Delete a commit and its snapshots/changes (CASCADE)."""
        if not self._conn:
            return
        c = self._conn.cursor()
        c.execute("DELETE FROM ledger_snapshots WHERE commit_id=?",
                  (commit_id,))
        c.execute("DELETE FROM ledger_changes WHERE commit_id=?",
                  (commit_id,))
        c.execute("DELETE FROM ledger_commits WHERE id=?", (commit_id,))
        self._conn.commit()

    # ------------------------------------------------------------------ #
    # Report helper
    # ------------------------------------------------------------------ #

    def generate_report_data(self, from_date: str = None,
                             to_date: str = None) -> list:
        """Return commit + change summary data for the report generator."""
        history = self.get_history()
        result = []
        for commit in history:
            ts = commit["timestamp"]
            if from_date and ts < from_date:
                continue
            if to_date and ts > to_date:
                continue
            changes = self.get_changes(commit["id"])
            added = sum(1 for ch in changes if ch["change_type"] == "ADD")
            deleted = sum(1 for ch in changes if ch["change_type"] == "DELETE")
            modified = sum(1 for ch in changes if ch["change_type"] == "MODIFY")
            commit["changes_summary"] = {
                "added": added,
                "deleted": deleted,
                "modified": modified,
                "total": len(changes),
            }
            result.append(commit)
        return result
