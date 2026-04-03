# -*- coding: utf-8 -*-
"""
ledger_merge.py — Merge Wizard

Split-screen conflict resolution dialog.
  Left:   Your version (local)
  Right:  Colleague's version (remote/other commit)
  Center: Action buttons to pick which version to keep per feature.
"""

from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QFont
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QPushButton, QLabel, QGroupBox, QMessageBox,
    QDialogButtonBox, QWidget, QFrame, QAbstractItemView,
)

from qgis.core import QgsGeometry


class ConflictItem:
    """Represents a single feature conflict between two versions."""

    def __init__(self, fid, local_geom, local_attrs,
                 remote_geom, remote_attrs, change_type):
        self.fid = fid
        self.local_geom = local_geom      # WKT or None
        self.local_attrs = local_attrs     # dict
        self.remote_geom = remote_geom     # WKT or None
        self.remote_attrs = remote_attrs   # dict
        self.change_type = change_type     # "MODIFY", "ADD", "DELETE"
        self.resolution = None             # "local", "remote", "merge"
        self.merged_geom = None
        self.merged_attrs = None


class MergeWizard(QDialog):
    """Split-screen conflict resolution wizard."""

    merge_completed = pyqtSignal(list)   # emits list of resolved ConflictItems

    def __init__(self, conflicts: list, commit_local: dict,
                 commit_remote: dict, parent=None):
        """
        :param conflicts: list of ConflictItem objects
        :param commit_local: commit info dict (your version)
        :param commit_remote: commit info dict (colleague's version)
        """
        super().__init__(parent)
        self.conflicts = conflicts
        self.commit_local = commit_local
        self.commit_remote = commit_remote
        self.setWindowTitle("QGIS Ledger — Risoluzione Conflitti")
        self.setMinimumSize(1000, 600)
        self._build_ui()
        self._populate()

    # ------------------------------------------------------------------ #
    # UI
    # ------------------------------------------------------------------ #

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # -- Header ---------------------------------------------------- #
        hdr = QLabel(
            f"<b style='font-size:14px;'>\u26A0 {len(self.conflicts)} "
            f"conflitti rilevati</b><br>"
            f"<span style='color:#95a5a6;'>Commit locale: "
            f"#{self.commit_local.get('id', '?')} di "
            f"{self.commit_local.get('user_name', '?')} &nbsp;|&nbsp; "
            f"Commit remoto: #{self.commit_remote.get('id', '?')} di "
            f"{self.commit_remote.get('user_name', '?')}</span>"
        )
        hdr.setStyleSheet("background:#2c3e50;padding:10px;border-radius:6px;"
                          "color:#ecf0f1;")
        layout.addWidget(hdr)

        # -- Splitter: left / center / right --------------------------- #
        splitter = QSplitter(Qt.Horizontal)

        # Left: local version
        self.tbl_local = self._make_table("La Tua Versione (Locale)")
        left_group = self._wrap_table(self.tbl_local, "La Tua Versione",
                                      QColor(52, 152, 219))
        splitter.addWidget(left_group)

        # Center: actions
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(4, 4, 4, 4)
        center_layout.addStretch()

        lbl_actions = QLabel("<b>Azioni</b>")
        lbl_actions.setAlignment(Qt.AlignCenter)
        lbl_actions.setStyleSheet("color:#ecf0f1;font-size:12px;")
        center_layout.addWidget(lbl_actions)

        self.btn_accept_local = QPushButton("\u2190 Accetta Locale")
        self.btn_accept_local.setStyleSheet(
            "QPushButton{background:#2980b9;color:white;border:none;"
            "border-radius:4px;padding:8px;font-weight:bold;}"
            "QPushButton:hover{background:#3498db;}"
        )
        self.btn_accept_local.clicked.connect(
            lambda: self._resolve_selected("local"))
        center_layout.addWidget(self.btn_accept_local)

        self.btn_accept_remote = QPushButton("Accetta Remoto \u2192")
        self.btn_accept_remote.setStyleSheet(
            "QPushButton{background:#e67e22;color:white;border:none;"
            "border-radius:4px;padding:8px;font-weight:bold;}"
            "QPushButton:hover{background:#f39c12;}"
        )
        self.btn_accept_remote.clicked.connect(
            lambda: self._resolve_selected("remote"))
        center_layout.addWidget(self.btn_accept_remote)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#636e72;")
        center_layout.addWidget(sep)

        self.btn_all_local = QPushButton("\u21D0 Tutti Locale")
        self.btn_all_local.setStyleSheet(
            "QPushButton{background:#34495e;color:#bdc3c7;border:none;"
            "border-radius:4px;padding:6px;}"
            "QPushButton:hover{background:#2c3e50;}"
        )
        self.btn_all_local.clicked.connect(lambda: self._resolve_all("local"))
        center_layout.addWidget(self.btn_all_local)

        self.btn_all_remote = QPushButton("Tutti Remoto \u21D2")
        self.btn_all_remote.setStyleSheet(
            "QPushButton{background:#34495e;color:#bdc3c7;border:none;"
            "border-radius:4px;padding:6px;}"
            "QPushButton:hover{background:#2c3e50;}"
        )
        self.btn_all_remote.clicked.connect(
            lambda: self._resolve_all("remote"))
        center_layout.addWidget(self.btn_all_remote)

        center_layout.addStretch()
        splitter.addWidget(center)

        # Right: remote version
        self.tbl_remote = self._make_table("Versione Collega (Remota)")
        right_group = self._wrap_table(self.tbl_remote, "Versione Collega",
                                       QColor(230, 126, 34))
        splitter.addWidget(right_group)

        splitter.setSizes([400, 200, 400])
        layout.addWidget(splitter, stretch=1)

        # -- Resolution status ----------------------------------------- #
        self.lbl_status = QLabel("")
        self.lbl_status.setStyleSheet(
            "color:#95a5a6;font-size:11px;padding:4px;"
        )
        layout.addWidget(self.lbl_status)

        # -- Buttons --------------------------------------------------- #
        buttons = QDialogButtonBox()
        self.btn_apply = buttons.addButton(
            "Applica Risoluzione", QDialogButtonBox.AcceptRole
        )
        self.btn_apply.setStyleSheet(
            "QPushButton{background:#27ae60;color:white;border:none;"
            "border-radius:4px;padding:8px 16px;font-weight:bold;}"
            "QPushButton:hover{background:#2ecc71;}"
        )
        self.btn_apply.setEnabled(False)
        btn_cancel = buttons.addButton(QDialogButtonBox.Cancel)
        btn_cancel.setStyleSheet(
            "QPushButton{background:#c0392b;color:white;border:none;"
            "border-radius:4px;padding:8px 16px;}"
            "QPushButton:hover{background:#e74c3c;}"
        )
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.setStyleSheet("QDialog{background:#1e272e;}")

    def _make_table(self, title):
        tbl = QTableWidget()
        tbl.setColumnCount(4)
        tbl.setHorizontalHeaderLabels(["FID", "Tipo", "Geometria", "Attributi"])
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setAlternatingRowColors(True)
        tbl.setStyleSheet(
            "QTableWidget{background:#2d3436;color:#dfe6e9;"
            "gridline-color:#636e72;border:none;}"
            "QTableWidget::item:selected{background:#34495e;}"
            "QHeaderView::section{background:#2c3e50;color:#ecf0f1;"
            "border:1px solid #34495e;padding:4px;}"
            "QTableWidget::item:alternate{background:#353b48;}"
        )
        return tbl

    def _wrap_table(self, table, title, color):
        grp = QGroupBox(title)
        grp.setStyleSheet(
            f"QGroupBox{{color:{color.name()};border:1px solid {color.name()};"
            f"border-radius:6px;margin-top:10px;padding-top:14px;"
            f"font-weight:bold;}}"
            f"QGroupBox::title{{subcontrol-origin:margin;"
            f"left:10px;padding:0 4px;}}"
        )
        lay = QVBoxLayout(grp)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(table)
        return grp

    # ------------------------------------------------------------------ #
    # Populate
    # ------------------------------------------------------------------ #

    def _populate(self):
        self.tbl_local.setRowCount(len(self.conflicts))
        self.tbl_remote.setRowCount(len(self.conflicts))

        for row, c in enumerate(self.conflicts):
            # Local side
            self.tbl_local.setItem(row, 0, QTableWidgetItem(str(c.fid)))
            self.tbl_local.setItem(row, 1, QTableWidgetItem(c.change_type))
            geom_short = (c.local_geom[:60] + "...") if c.local_geom else "—"
            self.tbl_local.setItem(row, 2, QTableWidgetItem(geom_short))
            attrs_str = ", ".join(
                f"{k}={v}" for k, v in (c.local_attrs or {}).items()
            )
            self.tbl_local.setItem(
                row, 3, QTableWidgetItem(attrs_str[:120] or "—"))

            # Remote side
            self.tbl_remote.setItem(row, 0, QTableWidgetItem(str(c.fid)))
            self.tbl_remote.setItem(row, 1, QTableWidgetItem(c.change_type))
            geom_r = (c.remote_geom[:60] + "...") if c.remote_geom else "—"
            self.tbl_remote.setItem(row, 2, QTableWidgetItem(geom_r))
            attrs_r = ", ".join(
                f"{k}={v}" for k, v in (c.remote_attrs or {}).items()
            )
            self.tbl_remote.setItem(
                row, 3, QTableWidgetItem(attrs_r[:120] or "—"))

        self._update_status()

    # ------------------------------------------------------------------ #
    # Resolution logic
    # ------------------------------------------------------------------ #

    def _selected_rows(self):
        rows = set()
        for idx in self.tbl_local.selectedIndexes():
            rows.add(idx.row())
        for idx in self.tbl_remote.selectedIndexes():
            rows.add(idx.row())
        return sorted(rows)

    def _resolve_selected(self, side: str):
        rows = self._selected_rows()
        if not rows:
            QMessageBox.information(
                self, "QGIS Ledger",
                "Seleziona almeno una riga da risolvere."
            )
            return
        for r in rows:
            self.conflicts[r].resolution = side
            self._highlight_row(r, side)
        self._update_status()

    def _resolve_all(self, side: str):
        for i, c in enumerate(self.conflicts):
            c.resolution = side
            self._highlight_row(i, side)
        self._update_status()

    def _highlight_row(self, row: int, side: str):
        if side == "local":
            color = QColor(52, 152, 219, 60)
        else:
            color = QColor(230, 126, 34, 60)
        for col in range(4):
            item_l = self.tbl_local.item(row, col)
            item_r = self.tbl_remote.item(row, col)
            if item_l:
                item_l.setBackground(color)
            if item_r:
                item_r.setBackground(color)

    def _update_status(self):
        resolved = sum(1 for c in self.conflicts if c.resolution)
        total = len(self.conflicts)
        self.lbl_status.setText(
            f"Risolti: {resolved}/{total}"
        )
        self.btn_apply.setEnabled(resolved == total)

    def _apply(self):
        unresolved = [c for c in self.conflicts if not c.resolution]
        if unresolved:
            QMessageBox.warning(
                self, "QGIS Ledger",
                f"Ci sono ancora {len(unresolved)} conflitti non risolti."
            )
            return
        self.merge_completed.emit(self.conflicts)
        self.accept()

    # ------------------------------------------------------------------ #
    # Static helper to detect conflicts between two snapshots
    # ------------------------------------------------------------------ #

    @staticmethod
    def find_conflicts(snap_local: list, snap_remote: list) -> list:
        """Compare two snapshot feature lists and return ConflictItem list.

        Both inputs are lists from ledger.get_snapshot_features().
        """
        local_map = {s["fid"]: s for s in snap_local}
        remote_map = {s["fid"]: s for s in snap_remote}

        l_fids = set(local_map.keys())
        r_fids = set(remote_map.keys())

        conflicts = []

        # Features modified in both
        for fid in l_fids & r_fids:
            l = local_map[fid]
            r = remote_map[fid]
            if l["geometry"] != r["geometry"] or l["attributes"] != r["attributes"]:
                conflicts.append(ConflictItem(
                    fid=fid,
                    local_geom=l["geometry"],
                    local_attrs=l["attributes"],
                    remote_geom=r["geometry"],
                    remote_attrs=r["attributes"],
                    change_type="MODIFY",
                ))

        # Features only in local (deleted remotely?)
        for fid in l_fids - r_fids:
            l = local_map[fid]
            conflicts.append(ConflictItem(
                fid=fid,
                local_geom=l["geometry"],
                local_attrs=l["attributes"],
                remote_geom=None,
                remote_attrs={},
                change_type="DELETE",
            ))

        # Features only in remote (added remotely)
        for fid in r_fids - l_fids:
            r = remote_map[fid]
            conflicts.append(ConflictItem(
                fid=fid,
                local_geom=None,
                local_attrs={},
                remote_geom=r["geometry"],
                remote_attrs=r["attributes"],
                change_type="ADD",
            ))

        return conflicts
