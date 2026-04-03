# -*- coding: utf-8 -*-
"""
ledger_diff.py — Visual Diff Engine

Computes symmetric difference between two commit snapshots and creates
temporary memory layers on the map with appropriate styling:
  - Red (semi-transparent)    → Removed features
  - Green (semi-transparent)  → Added features
  - Orange + direction arrow  → Modified/moved features
"""

from qgis.core import (
    QgsProject,
    QgsVectorLayer,
    QgsFeature,
    QgsGeometry,
    QgsField,
    QgsFields,
    QgsSymbol,
    QgsSimpleFillSymbolLayer,
    QgsSimpleLineSymbolLayer,
    QgsMarkerLineSymbolLayer,
    QgsArrowSymbolLayer,
    QgsSingleSymbolRenderer,
    QgsWkbTypes,
    QgsPointXY,
)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor


class LedgerDiff:
    """Visual Diff Engine — creates colored memory layers showing changes."""

    # Group name in the layer tree
    GROUP_NAME = "QGIS Ledger Diff"

    def __init__(self, ledger):
        self.ledger = ledger
        self._diff_layers = []

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def compute_diff(self, commit_id_old: int, commit_id_new: int,
                     layer_name: str = None):
        """Compare two snapshots and add diff layers to the map.

        Returns (added_count, removed_count, modified_count).
        """
        self.clear_diff()

        snap_old = {
            s["fid"]: s for s in self.ledger.get_snapshot_features(commit_id_old)
        }
        snap_new = {
            s["fid"]: s for s in self.ledger.get_snapshot_features(commit_id_new)
        }

        old_fids = set(snap_old.keys())
        new_fids = set(snap_new.keys())

        added_fids = new_fids - old_fids
        removed_fids = old_fids - new_fids
        common_fids = old_fids & new_fids

        modified = []
        for fid in common_fids:
            old = snap_old[fid]
            new = snap_new[fid]
            if (old["geometry"] != new["geometry"] or
                    old["attributes"] != new["attributes"]):
                modified.append((fid, old, new))

        # Detect geometry type from snapshots
        geom_type = self._detect_geom_type(snap_old, snap_new)

        # Create diff layers
        info_old = self.ledger.get_commit_info(commit_id_old)
        info_new = self.ledger.get_commit_info(commit_id_new)
        suffix = (f" (#{commit_id_old} vs #{commit_id_new})")

        if added_fids:
            self._create_diff_layer(
                [snap_new[f] for f in added_fids],
                "Aggiunte" + suffix,
                QColor(46, 204, 113, 120),     # Green
                QColor(39, 174, 96),
                geom_type,
            )

        if removed_fids:
            self._create_diff_layer(
                [snap_old[f] for f in removed_fids],
                "Rimosse" + suffix,
                QColor(231, 76, 60, 120),      # Red
                QColor(192, 57, 43),
                geom_type,
            )

        if modified:
            self._create_modified_layers(modified, suffix, geom_type)

        return len(added_fids), len(removed_fids), len(modified)

    def clear_diff(self):
        """Remove all diff layers from the map."""
        project = QgsProject.instance()
        for lid in self._diff_layers:
            layer = project.mapLayer(lid)
            if layer:
                project.removeMapLayer(lid)
        self._diff_layers.clear()

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _detect_geom_type(self, snap_a, snap_b):
        """Guess the geometry type from snapshot data."""
        for snap in (snap_a, snap_b):
            for item in snap.values():
                wkt = item.get("geometry")
                if wkt:
                    g = QgsGeometry.fromWkt(wkt)
                    if not g.isEmpty():
                        wkb = g.wkbType()
                        if QgsWkbTypes.geometryType(wkb) == QgsWkbTypes.PolygonGeometry:
                            return "Polygon"
                        elif QgsWkbTypes.geometryType(wkb) == QgsWkbTypes.LineGeometry:
                            return "LineString"
                        else:
                            return "Point"
        return "Polygon"

    def _create_diff_layer(self, features_data, name, fill_color,
                           stroke_color, geom_type):
        """Create a styled memory layer for a set of features."""
        uri = f"{geom_type}?crs=EPSG:4326"
        vl = QgsVectorLayer(uri, name, "memory")
        pr = vl.dataProvider()

        # Add common fields
        pr.addAttributes([
            QgsField("fid_orig", QVariant.Int),
            QgsField("diff_type", QVariant.String),
        ])
        vl.updateFields()

        feats = []
        for item in features_data:
            f = QgsFeature(vl.fields())
            if item["geometry"]:
                f.setGeometry(QgsGeometry.fromWkt(item["geometry"]))
            f.setAttribute("fid_orig", item["fid"])
            feats.append(f)

        pr.addFeatures(feats)
        vl.updateExtents()

        # Style
        symbol = QgsSymbol.defaultSymbol(vl.geometryType())
        if symbol:
            symbol.setColor(fill_color)
            if symbol.symbolLayerCount() > 0:
                sl = symbol.symbolLayer(0)
                if hasattr(sl, 'setStrokeColor'):
                    sl.setStrokeColor(stroke_color)
                if hasattr(sl, 'setStrokeWidth'):
                    sl.setStrokeWidth(0.8)
            vl.setRenderer(QgsSingleSymbolRenderer(symbol))

        QgsProject.instance().addMapLayer(vl, True)
        self._diff_layers.append(vl.id())

    def _create_modified_layers(self, modified_list, suffix, geom_type):
        """Create a single layer for modified features showing their new state."""

        # Modified geometry in orange
        uri = f"{geom_type}?crs=EPSG:4326"
        vl_mod = QgsVectorLayer(uri, "Modificate" + suffix, "memory")
        pr_mod = vl_mod.dataProvider()
        pr_mod.addAttributes([
            QgsField("fid_orig", QVariant.Int),
            QgsField("diff_type", QVariant.String),
        ])
        vl_mod.updateFields()

        feats_mod = []

        for fid, old, new in modified_list:
            # New feature state
            f_new = QgsFeature(vl_mod.fields())
            if new["geometry"]:
                f_new.setGeometry(QgsGeometry.fromWkt(new["geometry"]))
            f_new.setAttribute("fid_orig", fid)
            f_new.setAttribute("diff_type", "MODIFIED")
            feats_mod.append(f_new)

        pr_mod.addFeatures(feats_mod)
        vl_mod.updateExtents()

        # Style: bright orange semi-transparent
        color_mod = QColor(243, 156, 18, 140)
        sym_mod = QgsSymbol.defaultSymbol(vl_mod.geometryType())
        if sym_mod:
            sym_mod.setColor(color_mod)
            if sym_mod.symbolLayerCount() > 0:
                sl = sym_mod.symbolLayer(0)
                if hasattr(sl, 'setStrokeColor'):
                    sl.setStrokeColor(QColor(211, 84, 0))
                if hasattr(sl, 'setStrokeWidth'):
                    sl.setStrokeWidth(0.8)
            vl_mod.setRenderer(QgsSingleSymbolRenderer(sym_mod))

        project = QgsProject.instance()
        project.addMapLayer(vl_mod, True)
        self._diff_layers.append(vl_mod.id())
