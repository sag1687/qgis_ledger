# -*- coding: utf-8 -*-
"""
ledger_timeline.py — Timeline Side Panel

Vertical timeline widget (GitKraken-style) that displays commit nodes.
Click a node to enter read-only preview of that version on the map.
"""

from qgis.PyQt.QtCore import Qt, pyqtSignal, QSize, QRectF, QPointF
from qgis.PyQt.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont, QFontMetrics,
    QLinearGradient, QPainterPath, QIcon,
)
from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QScrollArea, QLabel, QPushButton, QComboBox,
    QFrame, QSizePolicy, QMessageBox, QToolButton,
    QInputDialog,
)

from qgis.core import QgsProject, QgsVectorLayer, QgsRasterLayer


# ====================================================================== #
# CommitNode — a single commit in the timeline
# ====================================================================== #

class CommitNode(QFrame):
    """Clickable widget representing one commit in the timeline."""

    selected = pyqtSignal(int)          # commit_id
    rollback_requested = pyqtSignal(int)
    diff_requested = pyqtSignal(int)

    _TYPE_COLORS = {
        "first":  QColor(52, 152, 219),    # Blue
        "normal": QColor(46, 204, 113),    # Green
        "latest": QColor(155, 89, 182),    # Purple
    }

    def __init__(self, commit_data: dict, node_type: str = "normal",
                 parent=None):
        super().__init__(parent)
        self.commit_data = commit_data
        self.commit_id = commit_data["id"]
        self._node_type = node_type
        self._is_selected = False
        self._build_ui()

    def _build_ui(self):
        self.setFrameShape(QFrame.NoFrame)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(80)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        main = QHBoxLayout(self)
        main.setContentsMargins(4, 4, 4, 4)
        main.setSpacing(8)

        # Left: colored dot + line
        self.dot_widget = _DotWidget(
            self._TYPE_COLORS.get(self._node_type,
                                  self._TYPE_COLORS["normal"]),
            parent=self,
        )
        main.addWidget(self.dot_widget)

        # Right: info
        info = QVBoxLayout()
        info.setSpacing(2)

        # Header: commit hash-ish + user
        hdr = QHBoxLayout()
        ctype = self.commit_data.get("commit_type", "VECTOR")
        
        type_icon = "\U0001F4CD" # Vector pin
        if ctype == "PROJECT": type_icon = "\U0001F4BE"
        elif ctype == "RASTER": type_icon = "\U0001F5BE"
        
        lbl_id = QLabel(f"<b>#{self.commit_id}</b> {type_icon} {ctype}")
        lbl_id.setStyleSheet("color: #ecf0f1; font-size: 11px;")
        hdr.addWidget(lbl_id)

        lbl_user = QLabel(f"{self.commit_data['user_name']}@"
                          f"{self.commit_data.get('machine', '?')}")
        lbl_user.setStyleSheet("color: #95a5a6; font-size: 10px;")
        hdr.addWidget(lbl_user)
        hdr.addStretch()
        info.addLayout(hdr)

        # Message
        lbl_msg = QLabel(self.commit_data.get("message", ""))
        lbl_msg.setWordWrap(True)
        lbl_msg.setStyleSheet("color: #bdc3c7; font-size: 11px;")
        info.addWidget(lbl_msg)

        # Footer: timestamp + feature count
        footer = QHBoxLayout()
        ts = self.commit_data.get("timestamp", "")
        lbl_ts = QLabel(f"\U0001F552 {ts}")
        lbl_ts.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        footer.addWidget(lbl_ts)

        fc = self.commit_data.get("feat_count", 0)
        ctype = self.commit_data.get("commit_type", "VECTOR")
        if ctype == "PROJECT":
            txt = "\U0001F4BE Progetto intero"
        elif ctype == "RASTER":
            txt = f"\U0001F5BE Raster ({fc} file)"
        else:
            txt = f"\u2B22 {fc} features"
            
        lbl_fc = QLabel(txt)
        lbl_fc.setStyleSheet("color: #7f8c8d; font-size: 10px;")
        footer.addWidget(lbl_fc)
        footer.addStretch()

        # Action buttons
        btn_preview = QToolButton()
        btn_preview.setText("\U0001F441")
        btn_preview.setToolTip("Preview questa versione")
        btn_preview.setStyleSheet(
            "QToolButton{background:transparent;border:none;font-size:14px;}"
            "QToolButton:hover{background:#34495e;border-radius:3px;}"
        )
        btn_preview.clicked.connect(
            lambda: self.selected.emit(self.commit_id))
        footer.addWidget(btn_preview)

        btn_rollback = QToolButton()
        btn_rollback.setText("\u21A9")
        btn_rollback.setToolTip("Rollback a questa versione")
        btn_rollback.setStyleSheet(
            "QToolButton{background:transparent;border:none;font-size:14px;}"
            "QToolButton:hover{background:#c0392b;border-radius:3px;}"
        )
        btn_rollback.clicked.connect(
            lambda: self.rollback_requested.emit(self.commit_id))
        footer.addWidget(btn_rollback)

        btn_diff = QToolButton()
        btn_diff.setText("\u0394")
        btn_diff.setToolTip("Diff da questa versione")
        btn_diff.setStyleSheet(
            "QToolButton{background:transparent;border:none;font-size:14px;"
            "font-weight:bold;}"
            "QToolButton:hover{background:#2980b9;border-radius:3px;}"
        )
        btn_diff.clicked.connect(
            lambda: self.diff_requested.emit(self.commit_id))
        footer.addWidget(btn_diff)

        btn_map = QToolButton()
        btn_map.setText("🖼️")
        btn_map.setToolTip("Vedi Mappa (Screenshot)")
        btn_map.setStyleSheet(
            "QToolButton{background:transparent;border:none;font-size:14px;}"
            "QToolButton:hover{background:#f39c12;border-radius:3px;}"
        )
        btn_map.clicked.connect(self._open_screenshot)
        footer.addWidget(btn_map)
        
        if ctype != "VECTOR":
            btn_diff.setEnabled(False)
            btn_diff.setToolTip("Diff visuale non disponibile (solo Vettori)")
            btn_preview.setEnabled(False)
            btn_preview.setToolTip("Anteprima non disponibile per questo tipo. Usa Rollback \u21A9")

        info.addLayout(footer)
        main.addLayout(info, stretch=1)

        self._apply_style(False)

    def _apply_style(self, selected: bool):
        self._is_selected = selected
        if selected:
            self.setStyleSheet(
                "CommitNode{background-color:#2c3e50;"
                "border:1px solid #3498db;border-radius:6px;}"
            )
        else:
            self.setStyleSheet(
                "CommitNode{background-color:#1e272e;"
                "border:1px solid #2d3436;border-radius:6px;}"
                "CommitNode:hover{background-color:#2c3e50;"
                "border:1px solid #636e72;}"
            )

    def set_selected(self, sel: bool):
        self._apply_style(sel)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.selected.emit(self.commit_id)

    def _open_screenshot(self):
        """Open the saved map screenshot if it exists."""
        from qgis.core import QgsProject
        import os
        from qgis.PyQt.QtGui import QDesktopServices
        from qgis.PyQt.QtCore import QUrl
        
        proj_path = QgsProject.instance().fileName()
        if not proj_path: return
        
        folder = os.path.join(os.path.dirname(proj_path), ".ledger_history", "screenshots")
        path = os.path.join(folder, f"commit_{self.commit_id}.png")
        
        if os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.information(self, "QGIS Ledger", "Screenshot non disponibile per questa versione.")


class _DotWidget(QWidget):
    """Small widget that draws a colored dot with vertical connecting line."""

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedWidth(20)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = self.height()
        cx = 10

        # Vertical line
        p.setPen(QPen(QColor(100, 100, 100), 2))
        p.drawLine(cx, 0, cx, h)

        # Dot
        p.setPen(QPen(self._color.darker(120), 2))
        p.setBrush(QBrush(self._color))
        p.drawEllipse(QPointF(cx, h / 2), 6, 6)
        p.end()


# ====================================================================== #
# TimelinePanel — the main dock widget
# ====================================================================== #

class TimelinePanel(QWidget):
    """Vertical timeline widget, similar to GitKraken."""

    # Signals the plugin can connect to
    preview_requested = pyqtSignal(int)        # commit_id
    rollback_requested = pyqtSignal(int)       # commit_id
    diff_requested = pyqtSignal(int)           # commit_id
    commit_requested = pyqtSignal()

    def __init__(self, ledger, parent=None):
        super().__init__(parent)
        self.ledger = ledger
        self.setMinimumWidth(320)
        self._selected_commit = None
        self._nodes = []
        self._build_ui()

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # -- Header ---------------------------------------------------- #
        header = QHBoxLayout()

        lbl_title = QLabel("<b style='color:#ecf0f1;font-size:14px;'>"
                           "\U0001F553 Timeline QGIS Ledger</b>")
        header.addWidget(lbl_title)
        header.addStretch()

        self.cmb_layer = QComboBox()
        self.cmb_layer.setMinimumWidth(140)
        self.cmb_layer.setStyleSheet(
            "QComboBox{background:#2c3e50;color:#ecf0f1;border:1px solid "
            "#34495e;border-radius:4px;padding:3px 6px;}"
        )
        self.cmb_layer.currentTextChanged.connect(self.refresh)
        header.addWidget(self.cmb_layer)

        layout.addLayout(header)

        # -- Commit button --------------------------------------------- #
        self.btn_commit = QPushButton("\u2795  Nuovo Commit")
        self.btn_commit.setStyleSheet(
            "QPushButton{background:#27ae60;color:white;border:none;"
            "border-radius:5px;padding:8px 14px;font-weight:bold;"
            "font-size:12px;}"
            "QPushButton:hover{background:#2ecc71;}"
            "QPushButton:pressed{background:#1e8449;}"
        )
        self.btn_commit.clicked.connect(self.commit_requested.emit)
        layout.addWidget(self.btn_commit)

        # -- Scrollable timeline --------------------------------------- #
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(
            "QScrollArea{background:#1e272e;border:none;}"
            "QScrollBar:vertical{background:#2d3436;width:8px;"
            "border-radius:4px;}"
            "QScrollBar::handle:vertical{background:#636e72;"
            "border-radius:4px;}"
        )

        self.timeline_widget = QWidget()
        self.timeline_layout = QVBoxLayout(self.timeline_widget)
        self.timeline_layout.setContentsMargins(0, 0, 0, 0)
        self.timeline_layout.setSpacing(4)
        self.timeline_layout.addStretch()

        self.scroll.setWidget(self.timeline_widget)
        layout.addWidget(self.scroll, stretch=1)

        # -- Info label ------------------------------------------------ #
        self.lbl_info = QLabel("")
        self.lbl_info.setStyleSheet(
            "color:#7f8c8d;font-size:10px;padding:2px;"
        )
        layout.addWidget(self.lbl_info)

        container.setStyleSheet("background-color:#1e272e;")
        main_layout.addWidget(container)

    # ------------------------------------------------------------------ #
    # Refresh
    # ------------------------------------------------------------------ #

    def populate_layers(self):
        """Fill the layer combo box with project filter and layers."""
        self.cmb_layer.blockSignals(True)
        current = self.cmb_layer.currentData()
        self.cmb_layer.clear()
        self.cmb_layer.addItem("-- Tutta la cronologia --", None)
        self.cmb_layer.addItem("📦 Solo versioni Progetto QGIS", "[Project State]")
        
        for lid, layer in QgsProject.instance().mapLayers().items():
            if isinstance(layer, (QgsVectorLayer, QgsRasterLayer)):
                # Icon depending on type could be added here, but keep it simple
                self.cmb_layer.addItem(f"Livello: {layer.name()}", layer.name())
                
        # Restore selection if still valid
        idx = self.cmb_layer.findData(current)
        if idx >= 0:
            self.cmb_layer.setCurrentIndex(idx)
        self.cmb_layer.blockSignals(False)
        self.refresh()

    def refresh(self, *_):
        """Rebuild the timeline nodes from the ledger."""
        # Clear existing nodes
        for node in self._nodes:
            node.setParent(None)
            node.deleteLater()
        self._nodes.clear()

        if not self.ledger.is_connected():
            self.lbl_info.setText("Nessun database di QGIS Ledger aperto.")
            return

        layer_filter = self.cmb_layer.currentData()

        history = self.ledger.get_history(layer_filter)
        if not history:
            self.lbl_info.setText("Nessun commit trovato.")
            return

        self.lbl_info.setText(f"{len(history)} commit trovati")

        # Insert before the stretch
        for i, commit in enumerate(history):
            if i == 0:
                ntype = "latest"
            elif i == len(history) - 1:
                ntype = "first"
            else:
                ntype = "normal"

            node = CommitNode(commit, ntype)
            node.selected.connect(self._on_node_selected)
            node.rollback_requested.connect(self.rollback_requested.emit)
            node.diff_requested.connect(self.diff_requested.emit)
            self._nodes.append(node)

            # Insert before the stretch (which is the last item)
            self.timeline_layout.insertWidget(
                self.timeline_layout.count() - 1, node
            )

    def _on_node_selected(self, commit_id: int):
        self._selected_commit = commit_id
        for node in self._nodes:
            node.set_selected(node.commit_id == commit_id)
        self.preview_requested.emit(commit_id)
