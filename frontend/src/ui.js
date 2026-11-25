// Gemeinsame Tailwind-Klassen und Beschriftungen (damit alle Seiten gleich aussehen).
import { locale, t } from './i18n.js'

export const inp = 'w-full bg-slate-50 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-800 dark:text-slate-100 focus:outline-none focus:border-ks-500 transition-colors disabled:opacity-60'
export const lbl = 'block text-xs font-medium text-slate-400 uppercase tracking-wide mb-1'
export const card = 'bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-sm'
export const btnPrimary = 'bg-ks-600 hover:bg-ks-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors shadow-sm'
export const btnGhost = 'bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 disabled:opacity-50 text-slate-700 dark:text-slate-200 text-sm font-medium px-4 py-2 rounded-lg transition-colors'
export const btnDanger = 'text-xs text-red-500 hover:text-red-700 hover:underline'
export const btnLink = 'text-xs text-ks-600 dark:text-ks-400 hover:underline'
export const th = 'px-3 py-2 text-left text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400'
export const td = 'px-3 py-2'

export const DEVICE_TYPES = [
  ['switch', 'Switch'], ['router', 'Router'], ['firewall', 'Firewall'], ['ap', 'Access Point'], ['server', 'Server'],
  ['patchpanel', 'Patchfeld'], ['outlet', 'Dose'], ['endpoint', 'Endgerät'], ['pdu', 'Steckdosenleiste (PDU)'], ['ups', 'USV'],
  ['timeserver', 'Zeitserver / Funkuhr'], ['media_converter', 'Medienkonverter'],
  ['cable_mgmt', 'Kabelführung'], ['blank_panel', 'Blindblende'], ['shelf', 'Fachboden'],
  ['plc', 'SPS / Steuerung'], ['hmi', 'Bedienpanel (HMI)'], ['io_module', 'I/O-Modul'], ['drive', 'Antrieb / Umrichter'], ['gateway', 'Gateway / Modem'],
  ['power_supply', 'Netzteil'], ['other', 'Sonstiges'],
]
export const PASSIVE_TYPES = ['cable_mgmt', 'blank_panel', 'shelf']      // Platzhalter ohne Ports: belegen nur Rackplatz
export const MOUNT_SIDES = [['front', 'Vorderseite'], ['rear', 'Rückseite'], ['both', 'beide Seiten (durchgehend)']]
export const SIDE_SLOTS = [['left', 'links'], ['right', 'rechts']]
export const mountLabel = k => t((MOUNT_SIDES.find(x => x[0] === k) || [k, k])[1])
export const DEVICE_STATUS = [['planned', 'geplant'], ['active', 'aktiv'], ['retired', 'außer Betrieb']]
export const LOCATION_KINDS = [['building', 'Gebäude'], ['floor', 'Etage'], ['room', 'Raum'], ['machine', 'Anlage/Maschine'], ['vehicle', 'Mobile Maschine'],
  ['rack', 'Rack'], ['wallrack', 'Wandgehäuse'], ['cabinet', 'Schaltschrank']]
export const CONTAINER_KINDS = ['rack', 'wallrack', 'cabinet']                 // nehmen Geräte auf, können eine HE-Teilung haben
export const PLACE_KINDS = ['room', 'machine', 'vehicle', 'rack', 'wallrack', 'cabinet']   // Orte, an denen Geräte stehen können
export const MOVABLE_KINDS = ['vehicle', 'machine', 'cabinet', 'wallrack', 'rack']        // lassen sich an einen anderen Standort verlegen
export const PORT_MEDIA = ['RJ45', 'SFP', 'SFP+', 'SFP28', 'QSFP', 'LWL', 'BNC', 'RJ11', 'RS232', 'RS485', 'C13', 'C14', 'Schuko', 'other']
export const CABLE_CATEGORIES = [['copper', 'Kupfer (Daten)'], ['fiber', 'Glasfaser'], ['power', 'Strom'], ['coax', 'Koax'], ['serial', 'Seriell / Signal'], ['telco', 'Telefon'], ['other', 'Sonstiges']]
// Welche Port-Medien zu welcher Kabelkategorie passen (spiegelt den Server; „other“ passt immer, Abweichungen sind nur ein Hinweis)
export const CATEGORY_MEDIA = {
  copper: ['RJ45', 'SFP', 'SFP+', 'SFP28', 'QSFP'], fiber: ['LWL', 'SFP', 'SFP+', 'SFP28', 'QSFP'], power: ['C13', 'C14', 'Schuko'],
  coax: ['BNC'], serial: ['RS232', 'RS485', 'RJ45', 'RJ11'], telco: ['RJ11', 'RJ45'],
}
export const SOURCES = [['manual', 'manuell'], ['csv', 'CSV'], ['json', 'JSON'], ['api', 'API'], ['checkmk', 'Checkmk'], ['openplan', 'OpenPlan']]
export const ROLES = [
  ['admin', 'Administrator', 'darf alles'], ['planer', 'Planer', 'erstellt und reicht Patchaufträge ein'],
  ['freigeber', 'Freigeber', 'gibt Aufträge frei oder lehnt sie ab'], ['techniker', 'Techniker', 'führt Aufträge aus'],
  ['viewer', 'Betrachter', 'darf nur lesen'],
]

const labelOf = (list, key) => t((list.find(x => x[0] === key) || [key, key])[1])        // Beschriftungen in der eingestellten Sprache
export const typeLabel = k => labelOf(DEVICE_TYPES, k)
export const statusLabel = k => labelOf(DEVICE_STATUS, k)
export const kindLabel = k => labelOf(LOCATION_KINDS, k)
export const sourceLabel = k => labelOf(SOURCES, k)
export const roleLabel = k => labelOf(ROLES, k)

export const statusClass = s => ({
  active:  'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  planned: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  retired: 'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400',
}[s] || 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300')

export const linkClass = s => ({
  up:   'text-green-600 dark:text-green-400',
  down: 'text-slate-400',
}[s] || 'text-slate-500')

/** Wert eines <input type="datetime-local"> (Ortszeit des Browsers) als ISO mit Zeitzone – der Server läuft ggf. in UTC. */
export function withOffset(v) {
  if (!v) return v
  const d = new Date(v.length === 10 ? `${v}T23:59:59` : v)
  if (isNaN(d)) return v
  const p = n => String(Math.trunc(Math.abs(n))).padStart(2, '0'), off = -d.getTimezoneOffset()
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}${off >= 0 ? '+' : '-'}${p(off / 60)}:${p(off % 60)}`
}
export function fmtTime(ts) { return ts ? new Date(ts * 1000).toLocaleString(locale()) : '–' }
export function fmtSpeed(m) { return !m ? '–' : (m >= 1000 ? `${m / 1000} Gbit/s` : `${m} Mbit/s`) }
