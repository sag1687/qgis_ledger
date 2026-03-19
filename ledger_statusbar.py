# -*- coding: utf-8 -*-
"""
ledger_statusbar.py — Status Bar Panel
"""

from qgis.PyQt.QtCore import Qt, QSize, pyqtSignal
from qgis.PyQt.QtGui import QPainter, QColor, QBrush, QPen, QFont, QFontMetrics
from qgis.PyQt.QtWidgets import QWidget, QHBoxLayout, QLabel

class StatusLED(QWidget):
    """Advanced Status panel for QGIS status bar."""

    SYNCED = "synced"
    MODIFIED = "modified"
    CONFLICT = "conflict"
    DISCONNECTED = "disconnected"

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._status = self.DISCONNECTED
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Apri/Chiudi Timeline QGIS Ledger")
        
        # Build UI layout
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(10)

        # Base style
        self.setStyleSheet("""
            StatusLED {
                background-color: #1e272e;
                border: 1px solid #2d3436;
                border-radius: 4px;
            }
            StatusLED:hover {
                background-color: #2c3e50;
            }
            QLabel {
                color: #7f8c8d;
                font-size: 11px;
                font-weight: bold;
            }
        """)

        # Synced indicator
        self.ind_synced = _SingleDot(QColor(46, 204, 113), "Synced")
        layout.addWidget(self.ind_synced)

        # Modified indicator
        self.ind_modified = _SingleDot(QColor(241, 196, 15), "Modified")
        layout.addWidget(self.ind_modified)

        # Conflict indicator
        self.ind_conflict = _SingleDot(QColor(231, 76, 60), "Conflict")
        layout.addWidget(self.ind_conflict)

        # Logo / Icon on the right
        lbl_logo = QLabel(" ⚑ QGIS Ledger")
        lbl_logo.setStyleSheet("color: #ecf0f1; font-size: 12px;")
        layout.addWidget(lbl_logo)
        
        self.set_status(self.DISCONNECTED)

    def set_status(self, status: str):
        self._status = status
        
        if status == self.DISCONNECTED:
            self.ind_synced.set_active(False)
            self.ind_modified.set_active(False)
            self.ind_conflict.set_active(False)
            self.setToolTip("QGIS Ledger: Nessun progetto aperto")
        elif status == self.SYNCED:
            self.ind_synced.set_active(True)
            self.ind_modified.set_active(False)
            self.ind_conflict.set_active(False)
            self.setToolTip("QGIS Ledger: Sincronizzato con l'ultima versione")
        elif status == self.MODIFIED:
            self.ind_synced.set_active(False)
            self.ind_modified.set_active(True)
            self.ind_conflict.set_active(False)
            self.setToolTip("QGIS Ledger: Modifiche in attesa di commit")
        elif status == self.CONFLICT:
            self.ind_synced.set_active(False)
            self.ind_modified.set_active(False)
            self.ind_conflict.set_active(True)
            self.setToolTip("QGIS Ledger: Conflitti rilevati!")
            
    def status(self):
        return self._status

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()


class _SingleDot(QWidget):
    """A small widget painting a single LED and a text label below it."""
    
    def __init__(self, color: QColor, text: str, parent=None):
        super().__init__(parent)
        self.active_color = color
        self.inactive_color = color.darker(300)
        self.inactive_color.setAlpha(100)
        self.text = text
        self.is_active = False
        
        # Fixed size that accommodates both the dot and the text
        self.setFixedSize(50, 32)
        
    def set_active(self, active: bool):
        self.is_active = active
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        color = self.active_color if self.is_active else self.inactive_color
        
        # Center coordinates for the dot (top half)
        cx, cy = self.width() / 2, 10
        radius = 6

        # Draw outer ring
        painter.setPen(QPen(color.darker(150), 1))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(int(cx - radius), int(cy - radius), radius * 2, radius * 2)

        # Glossy highlight if active
        if self.is_active:
            highlight = QColor(255, 255, 255, 80)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(highlight))
            painter.drawEllipse(int(cx - radius*0.4), int(cy - radius*0.6), int(radius), int(radius*0.8))

        # Draw text centered below the dot
        font = QFont()
        font.setPointSize(8)
        if self.is_active:
            font.setBold(True)
        painter.setFont(font)
        
        if self.is_active:
            painter.setPen(QColor(236, 240, 241))  # Bright text
        else:
            painter.setPen(QColor(127, 140, 141))  # Dim text
            
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(self.text)
        
        text_x = int((self.width() - tw) / 2)
        text_y = int(cy + radius + 10)
        
        painter.drawText(text_x, text_y, self.text)
        painter.end()
