"""Konstanten und Eingabemodelle der API."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

DEVICE_TYPES = ("switch", "router", "firewall", "ap", "server", "patchpanel", "outlet", "endpoint",
                "pdu", "ups", "timeserver", "media_converter", "cable_mgmt", "blank_panel", "shelf",
                "plc", "hmi", "io_module", "drive", "gateway", "power_supply", "other")
DEVICE_STATUS = ("planned", "active", "retired")
LOCATION_KINDS = ("building", "floor", "room", "machine", "vehicle", "rack", "wallrack", "cabinet")
CONTAINER_KINDS = ("rack", "wallrack", "cabinet")             # nehmen Geräte auf und können eine HE-Teilung (rack_units) haben
PORT_MEDIA = ("RJ45", "SFP", "SFP+", "SFP28", "QSFP", "LWL", "BNC", "RJ11", "RS232", "RS485",
              "C13", "C14", "Schuko", "other")
SOURCES = ("manual", "csv", "json", "api", "checkmk", "openplan")
CABLE_CATEGORIES = ("copper", "fiber", "power", "coax", "serial", "telco", "other")


class SiteIn(BaseModel):
    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=120)
    address: str = ""
    note: str = ""


class LocationIn(BaseModel):
    site_id: int
    parent_id: Optional[int] = None
    kind: str = "room"
    name: str = Field(min_length=1, max_length=120)
    rack_units: Optional[int] = Field(default=None, ge=1, le=100)
    note: str = ""
    ident: str = Field(default="", max_length=80)    # Anlagen-/Maschinennummer, Kennzeichen, Schrankbezeichnung


class MoveIn(BaseModel):
    site_id: int
    parent_id: Optional[int] = None


class DeviceIn(BaseModel):
    hostname: str = Field(min_length=1, max_length=120)
    type: str = "switch"
    vendor: str = ""
    model: str = ""
    serial: str = ""
    mgmt_ip: str = ""
    location_id: Optional[int] = None
    rack_position: Optional[int] = Field(default=None, ge=1, le=100)
    height_u: int = Field(default=1, ge=1, le=50)
    status: str = "active"
    note: str = ""
    model_id: Optional[int] = None              # Katalogmodell; beim Update nur geändert, wenn mitgesendet
    apply_model_ports: bool = False             # nur beim Anlegen: Ports aus der Vorlage des Modells erzeugen
    mount_side: str = "both"                    # front | rear | both – beim Update nur geändert, wenn mitgesendet
    orientation: str = "horizontal"             # horizontal (19 Zoll, HE) | vertical (hochkant im Seitenkanal)
    side_slot: str = ""                         # bei vertical: left | right


class PortIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    idx: Optional[int] = None
    medium: str = "RJ45"
    speed_mbps: Optional[int] = Field(default=None, ge=0)
    description: str = ""
    admin_status: str = ""
    oper_status: str = ""


class PortBulkIn(BaseModel):
    """Mehrere Ports anlegen. dual=True legt je einen Vorder- und Rückseiten-Port an und setzt automatisch den Peer."""
    prefix: str = Field(min_length=1, max_length=48)
    start: int = Field(default=1, ge=0)
    count: int = Field(ge=1, le=512)
    medium: str = "RJ45"
    speed_mbps: Optional[int] = Field(default=None, ge=0)
    dual: bool = False
    back_suffix: str = Field(default="-back", max_length=16)


class PeerIn(BaseModel):
    peer_port_id: Optional[int] = None          # None = Durchschleifung lösen


class CableIn(BaseModel):
    port_b_id: Optional[int] = None             # None = Kabel/Verbindung lösen
    cable_label: str = ""
    cable_type: str = "other"
    fiber_count: Optional[int] = Field(default=None, ge=1)
    length_m: Optional[float] = Field(default=None, ge=0)
    color: str = ""
    installed_at: Optional[str] = None          # ISO-Datum YYYY-MM-DD
    measurement_ref: str = ""
    measurement_ok: Optional[bool] = None       # None=nicht gemessen, True=bestanden, False=nicht bestanden
    note: str = ""


WORKORDER_STATUSES = ("draft", "submitted", "approved", "rejected", "in_progress", "done", "confirmed", "rework")
WORKITEM_ACTIONS   = ("connect", "disconnect", "move", "install_device", "remove_device", "wan_activate", "wan_change", "wan_terminate")
MOUNT_SIDES        = ("front", "rear", "both")                      # Einbauseite im Rack
ORIENTATIONS       = ("horizontal", "vertical", "din_rail")          # 19 Zoll (HE), hochkant im Seitenkanal oder Hutschiene/Montageplatte (ohne HE-Raster)
SIDE_SLOTS         = ("", "left", "right")
PASSIVE_TYPES      = ("cable_mgmt", "blank_panel", "shelf")          # Platzhalter ohne Ports: belegen nur Rackplatz
WORKITEM_STATUSES  = ("open", "done", "deviation")
PRIORITIES         = ("low", "normal", "high", "critical")


class WorkOrderIn(BaseModel):
    title:           str = Field(min_length=1, max_length=200)
    description:     str = ""
    priority:        str = "normal"
    location_id:     Optional[int] = None
    planned_from:    Optional[str] = None   # YYYY-MM-DD
    planned_to:      Optional[str] = None
    note:            str = ""
    openplan_project: str = ""
    openplan_task:   str = ""
    openplan_link:   str = ""


class WorkItemIn(BaseModel):
    action:       str = "connect"           # connect | disconnect | move | install_device | remove_device
    device_id:    Optional[int] = None      # bei install_device / remove_device
    wan_link_id:  Optional[int] = None      # bei wan_activate / wan_change / wan_terminate
    wan_patch:    dict = {}                 # bei wan_change: neue Werte (Bandbreite, Provider, Vertragsende …)
    remove_old:   bool = False              # belegten Port: alten Patch per Rückbau-Auftrag entfernen (statt Fehler)
    port_a_id:    Optional[int] = None
    port_b_id:    Optional[int] = None
    old_port_b_id: Optional[int] = None     # nur bei move: alter Zielport
    cable_label:  str = ""
    cable_type:   str = "other"
    fiber_count:  Optional[int] = Field(default=None, ge=1)
    length_m:     Optional[float] = Field(default=None, ge=0)
    color:        str = ""
    note:         str = ""
    idx:          int = 0


class WorkItemExec(BaseModel):
    """Techniker hakt eine Position ab."""
    item_status:    str = "done"            # done | deviation
    deviation_note: str = ""


class ScopeIn(BaseModel):
    role: str
    site_id: int


class UserCreate(BaseModel):
    username: str
    password: str
    roles: list[str] = Field(default_factory=lambda: ["viewer"])   # globale Rollen (leer = nur Bereichs-Rechte)
    scopes: list[ScopeIn] = Field(default_factory=list)           # Rollen nur für bestimmte Standorte
    full_name: str = ""
    email: str = ""


class UserUpdate(BaseModel):
    roles: Optional[list[str]] = None
    scopes: Optional[list[ScopeIn]] = None                        # gewünschte Bereichs-Rechte (manuell); ersetzt die bisherigen im eigenen Verwaltungsbereich
    active: Optional[bool] = None
    full_name: Optional[str] = None
    email: Optional[str] = None


class PasswordReset(BaseModel):
    new_password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePassword(BaseModel):
    current_password: str
    new_password: str


class TokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    scope: str = "read"                          # read | write
    expires_days: Optional[int] = Field(default=None, ge=1, le=3650)


class PortGroup(BaseModel):
    """Eine Gruppe gleichartiger Ports in einer Modellvorlage (z. B. 48 x RJ45 oder 24 Patchfeldports dual)."""
    prefix: str = Field(min_length=1, max_length=48)
    start: int = Field(default=1, ge=0)
    count: int = Field(ge=1, le=512)
    medium: str = "RJ45"
    speed_mbps: Optional[int] = Field(default=None, ge=0)
    dual: bool = False
    back_suffix: str = Field(default="-back", max_length=16)


class DeviceModelIn(BaseModel):
    vendor: str = Field(default="", max_length=80)
    model: str = Field(min_length=1, max_length=120)
    type: str = "switch"
    height_u: int = Field(default=1, ge=1, le=50)
    article_no: str = Field(default="", max_length=80)
    description: str = ""
    ports: list[PortGroup] = Field(default_factory=list, max_length=40)
    note: str = ""
    active: bool = True
    mount_side: str = "both"
    orientation: str = "horizontal"
    side_slot: str = ""


class CableTypeIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    category: str = "other"
    count_label: str = Field(default="", max_length=20)
    note: str = Field(default="", max_length=200)
    active: bool = True
    sort: int = Field(default=100, ge=0, le=9999)


class ModelRef(BaseModel):
    model_id: int


class LocNode(BaseModel):
    """Ein Knoten im Strukturbaum des Standort-Assistenten (Gebäude → Etage → Raum → Rack)."""
    kind: str
    name: str = Field(max_length=120)
    rack_units: Optional[int] = Field(default=None, ge=1, le=100)
    note: str = ""
    children: list["LocNode"] = Field(default_factory=list)


LocNode.model_rebuild()


class SiteWizardIn(BaseModel):
    site_id: Optional[int] = None               # vorhandenen Standort ergänzen ...
    site: Optional[SiteIn] = None               # ... oder neuen Standort anlegen
    parent_id: Optional[int] = None             # Struktur unter dieser vorhandenen Location einhängen
    tree: list[LocNode] = Field(default_factory=list)
    dry_run: bool = False


class LdapSettingsIn(BaseModel):
    enabled: Optional[bool] = None
    url: Optional[str] = Field(None, max_length=300)
    base_dn: Optional[str] = Field(None, max_length=500)
    domain: Optional[str] = Field(None, max_length=200)
    bind_dn: Optional[str] = Field(None, max_length=500)
    bind_password: Optional[str] = Field(None, max_length=500)       # leer = unverändert lassen
    clear_bind_password: bool = False
    user_filter: Optional[str] = Field(None, max_length=500)
    ca_pem: Optional[str] = Field(None, max_length=20000)
    required_group: Optional[str] = Field(None, max_length=500)
    group_roles: Optional[dict[str, str]] = None                     # Rolle -> Gruppen-DN (globale Rolle)
    scoped_groups: Optional[list[dict]] = None                       # [{group, role, site_id}]: Rolle nur für einen Standort
    default_role: Optional[str] = Field(None, max_length=20)
    auto_create: Optional[bool] = None
    nested_groups: Optional[bool] = None


class LdapTestIn(BaseModel):
    settings: Optional[LdapSettingsIn] = None                        # ungespeicherte Formularwerte
    username: str = ""
    password: str = ""


class AcmeSettingsIn(BaseModel):
    directory_url: Optional[str] = Field(None, max_length=500)
    domains: Optional[list[str]] = None
    email: Optional[str] = Field(None, max_length=200)
    ca_pem: Optional[str] = Field(None, max_length=20000)
    auto_renew: Optional[bool] = None
    renew_days: Optional[int] = Field(None, ge=1, le=60)


class AcmeFetchCaIn(BaseModel):
    url: str = Field(max_length=500)


class UplinkIn(BaseModel):
    """Verbindung eines Ports des neuen Geräts zu einem vorhandenen Port (z. B. Uplink zum Patchfeld)."""
    port_name: str = Field(min_length=1, max_length=64)           # Port am neuen Gerät
    target_port_id: int
    cable_type: str = "Cat6"
    cable_label: str = ""
    fiber_count: Optional[int] = Field(default=None, ge=1)
    length_m: Optional[float] = Field(default=None, ge=0)
    color: str = ""
    note: str = ""


class DeviceWizardIn(BaseModel):
    """Gerät platzieren: Stammdaten, Position im Rack, Ports aus Katalogmodell oder eigener Vorlage, optional ein Kabel."""
    hostname: str = Field(default="", max_length=120)               # bei Platzhaltern (Kabelführung …) leer = automatischer Name
    type: str = "switch"
    model_id: Optional[int] = None
    vendor: str = ""
    model: str = ""
    height_u: Optional[int] = Field(default=None, ge=1, le=50)      # leer = aus dem Modell, sonst 1
    ports: list[PortGroup] = Field(default_factory=list)            # nur ohne Modell: eigene Portgruppen
    location_id: int
    rack_position: Optional[int] = Field(default=None, ge=1, le=100)
    serial: str = ""
    mgmt_ip: str = ""
    note: str = ""
    status: str = "active"                                         # planned | active (bei mode=workorder immer planned)
    uplink: Optional[UplinkIn] = None
    links: list[UplinkIn] = Field(default_factory=list, max_length=96)   # mehrere Verbindungen auf einmal (z. B. Patchfeld-Ports an Switch-Ports)
    mode: str = "direct"                                           # direct | workorder
    orientation: Optional[str] = None                              # leer = aus dem Modell (sonst horizontal)
    mount_side: Optional[str] = None                               # leer = aus dem Modell (sonst beide Seiten)
    side_slot: Optional[str] = None                                # bei hochkant: left | right
    replace_devices: bool = False                                  # belegte HE: vorhandene Geräte zurückbauen (direkt bzw. per Rückbau-Auftrag)
    remove_old: bool = False                                       # belegter Zielport: alten Patch zurückbauen
    workorder_id: Optional[int] = None                             # vorhandenen Entwurf ergänzen ...
    workorder_title: str = ""                                      # ... oder neuen Auftrag anlegen
    dry_run: bool = False


class CableWizardIn(BaseModel):
    """Zwei Ports mit einem Kabel verbinden (beliebige Kabelart aus dem Katalog: Daten, Glasfaser, Strom, Koax, seriell, Telefon …)."""
    port_a_id: int
    port_b_id: int
    cable_type: str = "Cat6"
    cable_label: str = Field(default="", max_length=120)
    fiber_count: Optional[int] = Field(default=None, ge=1)          # Fasern/Adern/Paare, je nach Kabelart
    length_m: Optional[float] = Field(default=None, ge=0)
    color: str = ""
    installed_at: Optional[str] = None                              # YYYY-MM-DD (nur bei mode=direct)
    note: str = ""
    mode: str = "direct"                                            # direct | workorder
    remove_old: bool = False                                        # belegte Ports: alte Patches zurückbauen
    workorder_id: Optional[int] = None
    workorder_title: str = ""
    dry_run: bool = False


class PortListSpec(BaseModel):
    """Quelle für die Massenverkabelung: die Ports eines Geräts oder aller Geräte einer Location (z. B. alle Datendosen)."""
    device_id: Optional[int] = None
    location_id: Optional[int] = None               # alle Geräte dieser Location und darunter ...
    device_types: list[str] = Field(default_factory=list)   # ... optional nur diese Typen (z. B. ["outlet"])
    side: str = "all"                               # all | front | back (Rückseite = Portname endet auf -back)
    only_free: bool = True
    medium: Optional[str] = None


class BulkPair(BaseModel):
    port_a_id: int
    port_b_id: int
    cable_label: str = Field(default="", max_length=120)


class BulkCablesIn(BaseModel):
    """Viele Kabel auf einmal: als eine Liste (ein Patchauftrag mit vielen Positionen) oder sofort."""
    pairs: list[BulkPair] = Field(min_length=1, max_length=1000)
    cable_type: str = "Cat6A"
    fiber_count: Optional[int] = Field(default=None, ge=1)
    length_m: Optional[float] = Field(default=None, ge=0)
    color: str = ""
    note: str = ""
    mode: str = "workorder"                         # direct | workorder
    remove_old: bool = False                        # belegte Ports: alte Patches zurückbauen
    workorder_id: Optional[int] = None
    workorder_title: str = ""
    dry_run: bool = False


class BulkParseIn(BaseModel):
    text: str = Field(max_length=2_000_000)         # CSV/TSV aus Excel: Gerät A; Port A; Gerät B; Port B; [Kabelnummer]


class MailSettingsIn(BaseModel):
    enabled: Optional[bool] = None
    host: Optional[str] = Field(None, max_length=200)
    port: Optional[int] = Field(None, ge=1, le=65535)
    security: Optional[str] = Field(None, max_length=10)
    username: Optional[str] = Field(None, max_length=200)
    password: Optional[str] = Field(None, max_length=500)           # leer = unverändert lassen
    clear_password: bool = False
    from_addr: Optional[str] = Field(None, max_length=200)
    from_name: Optional[str] = Field(None, max_length=100)
    reply_to: Optional[str] = Field(None, max_length=200)
    public_url: Optional[str] = Field(None, max_length=300)
    allowed_domains: Optional[list[str]] = None


class MailTestIn(BaseModel):
    to: str = Field(max_length=200)


class SendIn(BaseModel):
    user_ids: list[int] = Field(default_factory=list, max_length=50)
    emails: list[str] = Field(default_factory=list, max_length=50)
    message: str = Field(default="", max_length=2000)
    attach_csv: bool = True
    attach_pdf: bool = False                         # Arbeitsanweisung als PDF anhängen (Oberfläche: vorausgewählt)
    include_list: bool = True                        # Positionen im Text der E-Mail auflisten


class PatchlistSendIn(SendIn):
    ids: list[int] = Field(min_length=1, max_length=50)
    group: str = "location"
    only_open: bool = False


class AssignIn(BaseModel):
    user_id: Optional[int] = None                    # None = Zuweisung aufheben
    notify: bool = True
    message: str = Field(default="", max_length=2000)


class OpenPlanSettingsIn(BaseModel):
    enabled: Optional[bool] = None
    base_url: Optional[str] = Field(None, max_length=300)
    token: Optional[str] = Field(None, max_length=300)              # leer = unverändert lassen
    clear_token: bool = False
    default_project_id: Optional[str] = Field(None, max_length=12)
    ca_pem: Optional[str] = Field(None, max_length=20000)
    verify_tls: Optional[bool] = None
    auto_sync: Optional[bool] = None
    own_url: Optional[str] = Field(None, max_length=300)
    webhook_secret: Optional[str] = Field(None, max_length=200)
    clear_webhook_secret: bool = False


class OpenPlanLinkIn(BaseModel):
    project_id: int
    task_id: int


class OpenPlanCreateIn(BaseModel):
    project_id: int
    parent_id: Optional[int] = None                 # unter diesem Vorgang (z. B. „Patchaufträge (aus Portwerk)“)
    name: str = Field(default="", max_length=300)


class OpenPlanBulkIn(BaseModel):
    project_id: int
    parent_id: Optional[int] = None
    workorder_ids: list[int] = Field(min_length=1, max_length=50)


class OpenPlanProjectIn(BaseModel):
    """Neues OpenPlan-Projekt aus der Vorlage „Einbau Patchfelder / Verkabelung“, optional gleich mit Patchaufträgen."""
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    kind: str = "patchpanel"
    members: list[str] = Field(default_factory=list, max_length=30)      # OpenPlan-Benutzernamen (Bearbeiter)
    workorder_ids: list[int] = Field(default_factory=list, max_length=50)
