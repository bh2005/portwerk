"""Verbindungs-Historie: Kabel entfernen und dabei festhalten, wer bzw. welcher Auftrag die Verbindung beendet hat.

Beginn und Ende jeder Verbindung schreiben Trigger auf ``cables`` (Migration 0022) – auch ohne diese Funktionen bleibt die Historie
vollständig (z. B. wenn ein Port gelöscht wird). ``remove`` ergänzt nur Wer/Auftrag/Grund.
"""
from __future__ import annotations

import sqlite3
import time
from typing import Optional

from . import db


def remove(where: str, args: tuple, by: str = "", workorder_id: Optional[int] = None, reason: str = "manual",
           c: Optional[sqlite3.Connection] = None) -> int:
    """``DELETE FROM cables WHERE <where>`` mit Vermerk in der Historie; liefert die Zahl der entfernten Kabel.
    ``c``: laufende Transaktion verwenden (sonst eigene)."""
    now = time.time()
    mark = (f"UPDATE cable_history SET valid_to = MAX(valid_from, ?), ended_by = ?, ended_workorder_id = ?, end_reason = ? "
            f"WHERE valid_to IS NULL AND cable_id IN (SELECT id FROM cables WHERE {where})")
    if c is not None:
        c.execute(mark, (now, by, workorder_id, reason, *args))
        return c.execute(f"DELETE FROM cables WHERE {where}", args).rowcount
    with db.transaction() as t:
        t.execute(mark, (now, by, workorder_id, reason, *args))
        return t.execute(f"DELETE FROM cables WHERE {where}", args).rowcount


def remove_at_ports(port_ids, by: str = "", workorder_id: Optional[int] = None, reason: str = "manual",
                    c: Optional[sqlite3.Connection] = None) -> int:
    """Alle Kabel an den angegebenen Ports entfernen."""
    ids = [p for p in port_ids if p]
    if not ids:
        return 0
    ph = ",".join("?" * len(ids))
    return remove(f"port_a_id IN ({ph}) OR port_b_id IN ({ph})", (*ids, *ids), by, workorder_id, reason, c)


def remove_cable(cable_id: int, by: str = "", workorder_id: Optional[int] = None, reason: str = "manual",
                 c: Optional[sqlite3.Connection] = None) -> int:
    return remove("id = ?", (cable_id,), by, workorder_id, reason, c)
