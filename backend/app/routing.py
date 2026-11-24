"""Autorouting: von einem Quellport (z. B. NIC eines neuen Servers) zu einem Zielport (z. B. Switchport) die fehlenden Patchungen finden.

Vorhandene Verkabelung ist fest und kostenlos: dokumentierte Kabel und die Durchschleifung vorn ↔ hinten an Patchfeldern und Dosen
(= „Stationen“, höchstens ``MAX_STATIONS`` auf einem Weg, z. B. Patchfeld → Dose → Patchfeld). Neu geplant werden nur **Patchkabel**:

* von der Quelle zu einem freien Patchfeld-Port,
* zwischen zwei freien Patchfeld-Ports (Rangierung, nur wenn nötig),
* von einem freien Patchfeld-Port zum Zielport – oder gar nicht, wenn der Zielport schon an die Strecke angeschlossen ist.
  Quelle → Ziel direkt (ohne Patchfeld) gibt es nur, wenn beide im selben Rack stehen.

Ein neues Patchkabel verbindet nur Ports **im selben Raum** (nächster Raum über der Location, sonst die übergeordnete Location; im selben Rack
ist es günstiger als zwischen Racks). Frei heißt: kein Kabel, nicht reserviert, nicht von einem offenen Auftrag verplant, Gerät nicht außer Betrieb.
Gesucht wird nach (Zahl neuer Patchkabel, davon zwischen Racks, Stationen, Teilstücke); Alternativen unterscheiden sich in den neuen Patchkabeln.
"""
from __future__ import annotations

import heapq
import itertools
from typing import Optional

from . import db, reservations
from .compare import THROUGH_TYPES

MAX_STATIONS = 3
MAX_CORDS = 3
FIBER = {"LWL", "SFP", "SFP+", "SFP28", "QSFP"}
CORD_STATIONS = ("patchpanel",)                   # neue Patchkabel enden nur an Patchfeldern (Dosen sind Festverkabelung)
SQL_CHUNK = 400


def medium_group(m: str) -> str:
    return "fiber" if m in FIBER else "copper" if m == "RJ45" else "other"


def compatible(m1: str, m2: str) -> bool:
    g1, g2 = medium_group(m1), medium_group(m2)
    return g1 == "other" or g2 == "other" or g1 == g2


def _chunks(ids: list, n: int = SQL_CHUNK):
    for i in range(0, len(ids), n):
        yield ids[i:i + n]


class World:
    """Der Bestand eines Standorts als Graph (Ports, Kabel, Durchschleifungen) mit den freien Ports."""

    def __init__(self, site_id: int, exclude_workorder: Optional[int] = None):
        self.site_id = site_id
        self.locs = {r["id"]: r for r in db.rows("SELECT id, parent_id, kind, name FROM locations WHERE site_id = ?", (site_id,))}
        self.dev = {r["id"]: r for r in db.rows(
            "SELECT d.id, d.hostname, d.type, d.status, d.location_id FROM devices d JOIN locations l ON l.id = d.location_id WHERE l.site_id = ?", (site_id,))}
        self.port = {r["id"]: r for r in db.rows(
            """SELECT p.id, p.name, p.medium, p.peer_port_id, p.device_id FROM ports p JOIN devices d ON d.id = p.device_id
               JOIN locations l ON l.id = d.location_id WHERE l.site_id = ?""", (site_id,))}
        self.cable: dict[int, int] = {}
        for r in db.rows("""SELECT c.port_a_id AS a, c.port_b_id AS b FROM cables c JOIN ports p ON p.id = c.port_a_id JOIN devices d ON d.id = p.device_id
                            JOIN locations l ON l.id = d.location_id WHERE l.site_id = ?""", (site_id,)):
            self.cable[r["a"]], self.cable[r["b"]] = r["b"], r["a"]
        self.peer: dict[int, int] = {}
        for p in self.port.values():
            if p["peer_port_id"]:
                self.peer[p["id"]], self.peer[p["peer_port_id"]] = p["peer_port_id"], p["id"]
        self.exclude = exclude_workorder
        self._blocked: dict[int, bool] = {}

    # -- Eigenschaften ----------------------------------------------------------
    def label(self, pid: int) -> str:
        p = self.port.get(pid)
        return f"{self.dev[p['device_id']]['hostname']}:{p['name']}" if p and p["device_id"] in self.dev else str(pid)

    def device_of(self, pid: int) -> Optional[dict]:
        p = self.port.get(pid)
        return self.dev.get(p["device_id"]) if p else None

    def is_station(self, pid: int) -> bool:
        d = self.device_of(pid)
        return bool(d and d["type"] in THROUGH_TYPES)

    def zone(self, location_id: Optional[int]) -> Optional[int]:
        """„Raum“ einer Location: nächster Raum darüber (oder sie selbst), sonst die übergeordnete Location, sonst sie selbst."""
        cur, guard = self.locs.get(location_id), 0
        while cur and guard < 20:
            if cur["kind"] == "room":
                return cur["id"]
            cur, guard = self.locs.get(cur["parent_id"]), guard + 1
        loc = self.locs.get(location_id)
        return (loc["parent_id"] or loc["id"]) if loc else None

    def load_blocked(self, ids: list[int]) -> None:
        """Reservierte und verplante Ports unter ``ids`` vormerken (in Blöcken, damit SQLite-Grenzen nie greifen)."""
        todo = [i for i in ids if i not in self._blocked]
        for chunk in _chunks(todo):
            res, plan = reservations.active(chunk), reservations.planned(chunk, self.exclude)
            for i in chunk:
                self._blocked[i] = i in res or i in plan

    def free(self, pid: int) -> bool:
        d = self.device_of(pid)
        return pid not in self.cable and not self._blocked.get(pid, False) and bool(d) and d["status"] != "retired"


def _src_zone(w: World, src: dict) -> Optional[int]:
    return w.zone(src["location_id"])


def find_routes(w: World, src: dict, target_id: int, limit: int = 3) -> list[dict]:
    """Bis zu ``limit`` Wege von ``src`` zum Zielport.

    ``src``: ``{"port_id": int | None, "location_id": int, "medium": str, "label": str}`` – ``port_id`` ist leer, wenn das Gerät erst angelegt wird (virtueller Quellport)."""
    tgt = w.port.get(target_id)
    if not tgt:
        return []
    s_id = src["port_id"]
    stations = [p for p in w.port.values() if w.is_station(p["id"])]
    w.load_blocked([p["id"] for p in stations] + [target_id] + ([s_id] if s_id else []))
    zone_src, zone_tgt = w.zone(src["location_id"]), w.zone(w.device_of(target_id)["location_id"])
    # freie Patchfeld-Ports mit Gegenseite je Raum (Kandidaten für neue Patchkabel)
    cand: dict[Optional[int], list[int]] = {}
    for p in stations:
        d = w.dev[p["device_id"]]
        if d["type"] in CORD_STATIONS and w.free(p["id"]) and p["id"] in w.peer and d["status"] != "retired":
            cand.setdefault(w.zone(d["location_id"]), []).append(p["id"])
    tgt_free = w.free(target_id)

    def loc_of(pid: Optional[int]) -> Optional[int]:
        return src["location_id"] if pid is None else w.device_of(pid)["location_id"]

    def med_of(pid: Optional[int]) -> str:
        return src["medium"] if pid is None else w.port[pid]["medium"]

    banned: set[frozenset] = set()
    routes: list[dict] = []
    for _ in range(limit):
        best = None
        for max_cords in range(1, MAX_CORDS + 1):
            best = _search(w, s_id, src, target_id, tgt, cand, tgt_free, zone_src, zone_tgt, max_cords, banned, loc_of, med_of)
            if best:
                break
        if not best:
            break
        cords = [(c["a"], c["b"]) for c in best["cords"]]
        key = frozenset(frozenset(c) for c in cords)
        routes.append(best)
        banned.add(key)
        if len(routes) >= limit:
            break
    return routes


def _search(w, s_id, src, target_id, tgt, cand, tgt_free, zone_src, zone_tgt, max_cords, banned, loc_of, med_of) -> Optional[dict]:
    """Dijkstra über Zustände (Port, Patchkabel, Stationen, letzte Kante). Kosten: (Patchkabel, davon zwischen Racks, Stationen, Teilstücke).

    Letzte Kante: ``start`` · ``cable`` (an einer Station angekommen → weiter durch die Station) · ``peer`` (hinten angekommen → weiter per Kabel
    oder, wenn dort noch nichts angeschlossen ist, mit einem neuen Patchkabel) · ``cord`` (an einem neuen Patchkabel angekommen → durch die Station)."""
    tgt_loc = w.device_of(target_id)["location_id"]
    start = (s_id, 0, 0, "start")
    counter = itertools.count()
    heap = [((0, 0, 0, 0), next(counter), start)]
    seen: dict = {start: (0, 0, 0, 0)}
    prev: dict = {}
    while heap:
        cost, _, st = heapq.heappop(heap)
        if seen.get(st) != cost:
            continue
        u, cords, stat, last = st
        if u is not None and u == target_id:
            route = _build(w, st, prev, src, loc_of)
            if frozenset(frozenset((c["a"], c["b"])) for c in route["cords"]) not in banned:
                return route
            continue
        steps = []                                                     # (neuer Zustand, Zusatzkosten, Kante)
        if last in ("cable", "cord"):                                  # an einer Station angekommen: durch die Station
            if u in w.peer and stat < MAX_STATIONS:
                steps.append(((w.peer[u], cords, stat + 1, "peer"), (0, 0, 1, 1), ("peer", u, w.peer[u])))
        else:                                                          # start / peer: vorhandenes Kabel oder neues Patchkabel
            if u is not None and u in w.cable:
                v = w.cable[u]
                if v in w.port and (v == target_id or w.is_station(v)):
                    steps.append(((v, cords, stat, "cable"), (0, 0, 0, 1), ("cable", u, v)))
            elif cords < max_cords and (u is None or u == s_id or (w.is_station(u) and w.dev[w.port[u]["device_id"]]["type"] in CORD_STATIONS and w.free(u))):
                zone_u = w.zone(loc_of(u))
                targets: list[int] = []
                direct_ok = u != s_id and not (u is None) or loc_of(u) == tgt_loc           # Quelle → Ziel direkt nur im selben Rack, sonst über Patchfelder
                if tgt_free and zone_u == zone_tgt and direct_ok and compatible(med_of(u), tgt["medium"]) and (u is None or w.port[u]["device_id"] != tgt["device_id"]):
                    targets.append(target_id)
                if cords + 1 < max_cords or not tgt_free:               # nach diesem Kabel bleibt noch eins für den Zielport (falls es eins braucht)
                    for v in cand.get(zone_u, ()):
                        if v == u or not compatible(med_of(u), w.port[v]["medium"]) or (u is not None and w.port[v]["device_id"] == w.port[u]["device_id"]):
                            continue
                        targets.append(v)
                for v in targets:
                    cross = 0 if loc_of(u) == w.device_of(v)["location_id"] else 1
                    steps.append(((v, cords + 1, stat, "cord" if v != target_id else "cable"), (1, cross, 0, 1), ("cord", u, v)))
        for nst, add, edge in steps:
            ncost = tuple(x + y for x, y in zip(cost, add))
            if nst not in seen or ncost < seen[nst]:
                seen[nst] = ncost
                prev[nst] = (st, edge)
                heapq.heappush(heap, (ncost, next(counter), nst))
    return None


def _build(w: World, goal, prev, src, loc_of) -> dict:
    edges, st = [], goal
    while st in prev:
        st, edge = prev[st]
        edges.append(edge)
    edges.reverse()
    name = lambda pid: src["label"] if pid is None else w.label(pid)                 # noqa: E731
    steps, cords = [], []
    for kind, a, b in edges:
        if kind == "cord":
            cross = loc_of(a) != w.device_of(b)["location_id"]
            cords.append({"a": a, "b": b, "a_label": name(a), "b_label": name(b), "between_racks": cross,
                          "distance_label": "zwischen Racks im Raum" if cross else "im selben Rack"})
            steps.append({"type": "cord", "from": name(a), "to": name(b), "text": "neues Patchkabel" + (" (zwischen Racks)" if cross else "")})
        elif kind == "cable":
            steps.append({"type": "cable", "from": name(a), "to": name(b), "text": "vorhandenes Kabel"})
        else:
            steps.append({"type": "station", "from": name(a), "to": name(b), "text": "Durchschleifung (" + w.device_of(a)["hostname"] + ")"})
    n_st = sum(1 for s in steps if s["type"] == "station")
    n_ca = sum(1 for s in steps if s["type"] == "cable")
    summary = f"{len(cords)} neue(s) Patchkabel" + (f", {n_st} Station(en)" if n_st else "") + (f", {n_ca} vorhandene(s) Kabel" if n_ca else "")
    return {"cords": cords, "steps": steps, "stations": n_st, "existing_cables": n_ca, "summary": summary,
            "between_racks": sum(1 for c in cords if c["between_racks"])}


def explain_none(w: World, src: dict, target_id: int) -> str:
    """Warum es keinen Weg gibt (für die Meldung an den Benutzer)."""
    tgt_dev = w.device_of(target_id)
    if target_id in w.cable and w.cable[target_id] not in w.port:
        return "Der Zielport ist mit einem Gerät an einem anderen Standort verbunden."
    zone_s, zone_t = w.zone(src["location_id"]), w.zone(tgt_dev["location_id"])
    free_s = [p for p in w.port.values() if w.is_station(p["id"]) and w.dev[p["device_id"]]["type"] in CORD_STATIONS and w.free(p["id"]) and p["id"] in w.peer
              and w.zone(w.dev[p["device_id"]]["location_id"]) == zone_s]
    if not free_s and zone_s != zone_t:
        return "Im Raum des Quellgeräts gibt es keinen freien Patchfeld-Port (mit dokumentierter Gegenseite)."
    if w.free(target_id) and zone_s != zone_t:
        free_t = [p for p in w.port.values() if w.is_station(p["id"]) and w.dev[p["device_id"]]["type"] in CORD_STATIONS and w.free(p["id"])
                  and w.zone(w.dev[p["device_id"]]["location_id"]) == zone_t]
        if not free_t:
            return "Im Raum des Zielgeräts gibt es keinen freien Patchfeld-Port."
    return ("Keine durchgängige dokumentierte Verbindung zwischen den beiden Räumen gefunden (Patchfelder/Dosen/Trunks) – "
            "oder der Weg wäre länger als {} Stationen bzw. {} neue Patchkabel.".format(MAX_STATIONS, MAX_CORDS))
