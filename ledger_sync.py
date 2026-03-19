# -*- coding: utf-8 -*-
"""
ledger_sync.py — Network Sync Module (Stub for Phase 4)

Monitors shared folders for changes to the .ledger.db file made by
other users, using the `watchdog` library (when available).
"""

import os
import time


class NetworkSync:
    """Network synchronization manager.

    Stub implementation for Phase 4.
    When fully implemented, this will use `watchdog` to monitor a
    shared folder for changes to .ledger.db by other users.
    """

    def __init__(self):
        self._watching = False
        self._watch_path = None
        self._last_mtime = None

    def is_available(self):
        """Check if watchdog library is installed."""
        try:
            import watchdog  # noqa: F401
            return True
        except ImportError:
            return False

    def start_watching(self, db_path: str):
        """Start monitoring the .ledger.db file for external changes.

        Stub: records the current mtime for future comparison.
        """
        if not db_path or not os.path.exists(db_path):
            return False
        self._watch_path = db_path
        self._last_mtime = os.path.getmtime(db_path)
        self._watching = True
        return True

    def stop_watching(self):
        """Stop monitoring."""
        self._watching = False
        self._watch_path = None

    def check_for_updates(self) -> bool:
        """Check if the database was modified externally.

        Returns True if changes were detected.
        """
        if not self._watching or not self._watch_path:
            return False
        try:
            current_mtime = os.path.getmtime(self._watch_path)
            if current_mtime > self._last_mtime:
                self._last_mtime = current_mtime
                return True
        except OSError:
            pass
        return False

    def is_watching(self):
        return self._watching
