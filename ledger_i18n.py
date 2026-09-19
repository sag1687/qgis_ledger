# -*- coding: utf-8 -*-
"""
ledger_i18n.py — Dynamic JSON-based Internationalization handling
"""

import os
import json
from qgis.PyQt.QtCore import QSettings, QLocale

_translations = {}
_current_lang = "it"


def init_i18n():
    """Load the translation dict according to user settings or system locale."""  # noqa: E501
    global _translations, _current_lang
    settings = QSettings()
    lang = settings.value("qgis_ledger/language", "it")

    if not lang:
        sys_loc = QLocale.system().name()
        if sys_loc.startswith("it"):
            lang = "it"
        else:
            lang = "en"

    _current_lang = lang
    _translations.clear()

    if lang != "it":
        dict_path = os.path.join(os.path.dirname(
            __file__), "i18n", f"{lang}.json")
        if os.path.exists(dict_path):
            try:
                with open(dict_path, "r", encoding="utf-8") as f:
                    _translations = json.load(f)
            except Exception as e:
                print(f"QGIS Ledger: Error loading translations: {e}")


def tr(text):
    """Translate 'text' to the current language."""
    if _current_lang == "it":
        return text
    return _translations.get(text, text)


def current_language():
    return _current_lang


def set_language(lang_code):
    """Dynamically set the language (e.g. 'it' or 'en') and reload dict."""
    QSettings().setValue("qgis_ledger/language", lang_code)
    init_i18n()
