# -*- coding: utf-8 -*-
"""
QGIS QGIS Ledger — Intelligent Versioning & Collaboration Plugin
"""


def classFactory(iface):
    """Load the QGIS Ledger plugin class.

    :param iface: A QGIS interface instance.
    :type iface: QgsInterface
    """
    from .ledger_plugin import LedgerPlugin
    return LedgerPlugin(iface)
