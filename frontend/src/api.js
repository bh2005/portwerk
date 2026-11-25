import axios from 'axios'
import { withOffset } from './ui.js'
import { setLang, t, tApi } from './i18n.js'

const TOKEN_KEY = 'opp_auth_token'
const USER_KEY  = 'opp_user'

export function getToken()   { return localStorage.getItem(TOKEN_KEY) || '' }
export function setToken(t)  { localStorage.setItem(TOKEN_KEY, t) }
export function setUser(u)   { localStorage.setItem(USER_KEY, JSON.stringify(u || {})); if (u?.prefs?.lang) setLang(u.prefs.lang) }   // Sprache aus dem Profil
export function getUser()    { try { return JSON.parse(localStorage.getItem(USER_KEY) || '{}') } catch { return {} } }
export function clearToken() { localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(USER_KEY) }
export function isLoggedIn() { return !!getToken() }
/** Persönliche Einstellungen aus „Mein Profil“ (gelten auf allen Geräten). */
export function userPrefs()  { return getUser().prefs || {} }
export function defaultSite() { return userPrefs().default_site_id || null }
const START = { dashboard: '/dashboard', workorders: '/workorders', m: '/m', racks: '/racks', capacity: '/capacity' }
/** Startseite: eigene Wahl, sonst Techniker am Handy die mobile Ansicht, sonst die Übersicht. */
export function startPage() {
  const p = START[userPrefs().start_page]
  if (p) return p
  return window.matchMedia?.('(max-width: 640px)').matches && hasRole('techniker') ? '/m' : '/dashboard'
}
export function isAdmin()    { return (getUser().roles || []).includes('admin') }                       // globaler Administrator
export function isGlobal()   { return (getUser().roles || []).length > 0 }                              // mindestens eine globale Rolle: sieht alles
export function scopesOf()   { return getUser().scopes || [] }                                          // Rollen nur für bestimmte Standorte
export function isSiteAdmin() { return scopesOf().some(s => s.role === 'admin') }                       // Bereichs-Administrator irgendeines Standorts
export function siteAdminIds() { return scopesOf().filter(s => s.role === 'admin').map(s => s.site_id) }
export function canWriteMaster() { return isAdmin() || isSiteAdmin() }                                  // Stammdaten ändern (Server prüft den Standort)
export function canAdministerUsers() { return isAdmin() || isSiteAdmin() }
/** Rolle global oder an irgendeinem Standort – nur für Menüs und Schaltflächen, die Rechte prüft immer der Server. */
export function hasRole(...roles) {
  const r = getUser().roles || []
  return r.includes('admin') || roles.some(x => r.includes(x)) || scopesOf().some(s => s.role === 'admin' || roles.includes(s.role))
}

const http = axios.create({ baseURL: '' })

http.interceptors.request.use(cfg => {
  const t = getToken()
  if (t) cfg.headers['X-Auth-Token'] = t
  return cfg
})

http.interceptors.response.use(r => r, err => {
  const url = err.config?.url || ''
  if (err.response?.status === 401 && getToken() && !url.includes('/auth/login') && !url.includes('/auth/change-password')) {
    clearToken()
    if (location.pathname !== '/login') location.href = '/login'
  }
  return Promise.reject(err)
})

/** Lesbare Fehlermeldung aus einer API-Antwort (FastAPI: detail als Text oder als Liste von Validierungsfehlern). */
export function errText(e, fallback = 'Fehler') {
  const d = e?.response?.data?.detail
  if (typeof d === 'string') return tApi(d)
  if (d && typeof d === 'object' && !Array.isArray(d) && d.message) return tApi(d.message)
  if (Array.isArray(d)) return d.map(x => `${(x.loc || []).slice(1).join('.')}: ${x.msg}`).join('; ')
  return t(fallback)
}

/** Rückfrage-Antwort des Servers („Port belegt“, „HE belegt“): liefert {code, message, conflicts} oder null. */
export function conflictOf(e) {
  const d = e?.response?.data?.detail
  return e?.response?.status === 409 && d && typeof d === 'object' && ['port_busy', 'slot_busy', 'port_reserved'].includes(d.code) ? d : null
}

const get  = (url, params) => http.get(url, { params }).then(r => r.data)
const post = (url, body, cfg) => http.post(url, body, cfg).then(r => r.data)
const put  = (url, body) => http.put(url, body).then(r => r.data)
const del  = url => http.delete(url).then(r => r.data)

export const api = {
  // Anmeldung
  login:          (username, password) => post('/auth/login', { username, password }),
  logout:         () => post('/auth/logout'),
  me:             () => get('/auth/me'),
  live:           () => get('/api/live'),
  setMyNotifications: b => put('/auth/me/notifications', b),
  setMyPreferences: b => put('/auth/me/preferences', b),
  mySessions:       () => get('/auth/me/sessions'),
  logoutOthers:     () => post('/auth/me/logout-others'),
  changePassword: (current_password, new_password) => post('/auth/change-password', { current_password, new_password }),

  // Übersicht
  stats: () => get('/api/stats'),
  capacity:        params => get('/api/capacity', params),
  capacitySummary: () => get('/api/capacity/summary'),
  cleanup:         params => get('/api/cleanup', params),
  cleanupMail:     () => post('/api/cleanup/mail'),

  // Standorte und Locations
  sites:          () => get('/api/sites'),
  createSite:     b => post('/api/sites', b),
  updateSite:     (id, b) => put(`/api/sites/${id}`, b),
  deleteSite:     id => del(`/api/sites/${id}`),
  locations:      site_id => get('/api/locations', site_id ? { site_id } : {}),
  createLocation: b => post('/api/locations', b),
  updateLocation: (id, b) => put(`/api/locations/${id}`, b),
  deleteLocation: id => del(`/api/locations/${id}`),
  moveLocation:   (id, b) => post(`/api/locations/${id}/move`, b),

  // Geräte und Ports
  devices:      params => get('/api/devices', params),
  device:       id => get(`/api/devices/${id}`),
  createDevice: b => post('/api/devices', b),
  updateDevice: (id, b) => put(`/api/devices/${id}`, b),
  deleteDevice: id => del(`/api/devices/${id}`),
  createPort:   (did, b) => post(`/api/devices/${did}/ports`, b),
  bulkPorts:    (did, b) => post(`/api/devices/${did}/ports/bulk`, b),
  updatePort:   (id, b) => put(`/api/ports/${id}`, b),
  deletePort:   id => del(`/api/ports/${id}`),
  setPeer:      (id, peer_port_id) => put(`/api/ports/${id}/peer`, { peer_port_id }),
  setCable:     (id, body) => put(`/api/ports/${id}/cable`, body),
  cables:       params => get('/api/cables', params),
  updateCable:  (id, body) => put(`/api/cables/${id}`, body),
  cableHistory: params => get('/api/cable-history', { ...params, at: withOffset(params?.at) }),
  portPath:     (id, at) => get(`/api/ports/${id}/path`, at ? { at: withOffset(at) } : undefined),
  historySnapshot: params => get('/api/cable-history/snapshot', { ...params, at: withOffset(params.at) }),
  historyDiff:     params => get('/api/cable-history/diff', { ...params, from: withOffset(params.from), to: withOffset(params.to) }),
  reservations:        params => get('/api/reservations', params),
  vlans:            params => get('/api/vlans', params),
  createVlan:       b => post('/api/vlans', b),
  updateVlan:       (id, b) => put(`/api/vlans/${id}`, b),
  deleteVlan:       id => del(`/api/vlans/${id}`),
  vlanUsage:        params => get('/api/vlans/usage', params),
  vlanCompare:      params => get('/api/vlans/compare', params),
  vlanAdopt:        port_ids => post('/api/vlans/compare/adopt', { port_ids }),
  portProfiles:     () => get('/api/port-profiles'),
  createProfile:    b => post('/api/port-profiles', b),
  updateProfile:    (id, b) => put(`/api/port-profiles/${id}`, b),
  deleteProfile:    id => del(`/api/port-profiles/${id}`),
  setPortConfig:    (id, b) => put(`/api/ports/${id}/config`, b),
  portConfigHistory: id => get(`/api/ports/${id}/config-history`),
  reservePorts:        body => post('/api/reservations', body),
  updateReservation:   (id, body) => put(`/api/reservations/${id}`, body),
  releaseReservation:  id => del(`/api/reservations/${id}`),
  releaseReservations: ids => post('/api/reservations/release', { ids }),
  labels:       params => http.get('/api/labels', { params, paramsSerializer: { indexes: null } }).then(r => r.data),
  resolveLabel: params => get('/api/labels/resolve', params),

  // Assistenten
  deviceWizard:     b => post('/api/wizards/device', b),
  cableWizard:      b => post('/api/wizards/cable', b),
  workplaceWizard:  b => post('/api/wizards/workplace', b),
  portList:         spec => post('/api/wizards/port-list', spec),
  bulkCables:       b => post('/api/wizards/bulk-cables', b),
  bulkParse:        text => post('/api/wizards/bulk-cables/parse', { text }),
  bulkItems:        (wid, b) => post(`/api/workorders/${wid}/items/bulk`, b),
  exportWorkorder:  id => http.get(`/api/workorders/${id}/export`, { responseType: 'blob' }).then(r => r.data),
  workorderPdf:     id => http.get(`/api/workorders/${id}/pdf`, { params: { base: location.origin }, responseType: 'blob' }).then(r => r.data),
  patchlistPdf:     (ids, group, only_open) => http.get('/api/patchlists/pdf', { params: { ids, group, only_open }, responseType: 'blob' }).then(r => r.data),
  patchlist:        (ids, group, only_open) => get('/api/patchlists', { ids, group, only_open }),
  patchlistExport:  (ids, group, only_open) => http.get('/api/patchlists/export', { params: { ids, group, only_open }, responseType: 'blob' }).then(r => r.data),
  rackSlots:        (locationId, height_u, extra = {}) => get(`/api/wizards/rack-slots/${locationId}`, { height_u, ...extra }),
  siteWizard:       b => post('/api/wizards/site', b),

  // Katalog: Kabelarten und Gerätemodelle
  cableTypes:       all => get('/api/cable-types', all ? { all: true } : {}),
  createCableType:  b => post('/api/cable-types', b),
  updateCableType:  (id, b) => put(`/api/cable-types/${id}`, b),
  deleteCableType:  id => del(`/api/cable-types/${id}`),
  deviceModels:     params => get('/api/device-models', params),
  createModel:      b => post('/api/device-models', b),
  updateModel:      (id, b) => put(`/api/device-models/${id}`, b),
  deleteModel:      id => del(`/api/device-models/${id}`),
  portsFromModel:   (did, model_id) => post(`/api/devices/${did}/ports/from-model`, { model_id }),

  // WAN-Verbindungen
  search:         q => get('/api/search', { q }),
  checkmkLink:    () => get('/api/integrations/checkmk'),
  saveCheckmkLink: b => put('/api/admin/checkmk', b),
  compare:        params => get('/api/compare', params),
  releases:       () => get('/api/releases'),
  checkmkApi:     () => get('/api/admin/checkmk-api'),
  saveCheckmkApi: b => put('/api/admin/checkmk-api', b),
  testCheckmkApi: () => post('/api/admin/checkmk-api/test', {}),
  checkmkStatus:  () => get('/api/checkmk/status'),
  checkmkHost:    name => get('/api/checkmk/host', { name }),
  checkmkFolders: () => get('/api/checkmk/folders'),
  checkmkPending: () => get('/api/checkmk/pending'),
  checkmkActivate: () => post('/api/checkmk/activate', {}),
  checkmkCreateHost: b => post('/api/checkmk/hosts', b),
  adoptDevice:    b => post('/api/compare/adopt-device', b),
  moveCableEnd:   (cableId, b) => post(`/api/cables/${cableId}/move-end`, b),
  routePlan:      b => post('/api/routing/plan', b),
  insertStation:  (cableId, b) => post(`/api/cables/${cableId}/insert-station`, b),
  removeStation:  b => post('/api/stations/remove', b),
  adoptConnection: portId => post('/api/compare/adopt', { port_id: portId }),
  wanMeta:        () => get('/api/wan/meta'),
  wanLinks:       params => get('/api/wan', params),
  wanLink:        id => get(`/api/wan/${id}`),
  createWan:      b => post('/api/wan', b),
  updateWan:      (id, b) => put(`/api/wan/${id}`, b),
  deleteWan:      id => del(`/api/wan/${id}`),

  // Patchaufträge
  workorders:        params => get('/api/workorders', params),
  workorder:         id => get(`/api/workorders/${id}`),
  createWorkorder:   b => post('/api/workorders', b),
  updateWorkorder:   (id, b) => put(`/api/workorders/${id}`, b),
  deleteWorkorder:   id => del(`/api/workorders/${id}`),
  workorderTransition: (id, action, overrideReason) => post(`/api/workorders/${id}/transition/${action}`, overrideReason ? { override_reason: overrideReason } : undefined),
  workorderItems:    id => get(`/api/workorders/${id}/items`),
  addWorkitem:       (wid, b) => post(`/api/workorders/${wid}/items`, b),
  updateWorkitem:    (wid, iid, b) => put(`/api/workorders/${wid}/items/${iid}`, b),
  deleteWorkitem:    (wid, iid) => del(`/api/workorders/${wid}/items/${iid}`),
  executeWorkitem:   (wid, iid, b) => post(`/api/workorders/${wid}/items/${iid}/execute`, b),
  reopenWorkitem:    (wid, iid) => post(`/api/workorders/${wid}/items/${iid}/reopen`),
  verifyWorkorder:   id => post(`/api/workorders/${id}/verify`),

  // Import
  importFields:   () => get('/api/import/fields'),
  csvPreview:     (file, kind) => { const f = new FormData(); f.append('file', file); f.append('kind', kind); return post('/api/import/csv/preview', f) },
  csvImport:      (file, kind, mapping, opts) => {
    const f = new FormData()
    f.append('file', file); f.append('kind', kind); f.append('mapping', JSON.stringify(mapping || {}))
    f.append('dry_run', String(opts.dry_run)); f.append('atomic', String(opts.atomic)); f.append('create_locations', String(opts.create_locations))
    return post('/api/import/csv', f)
  },
  jsonImport:     b => post('/api/import/json', b),
  importRuns:     () => get('/api/import/runs'),

  // Verwaltung
  users:          () => get('/api/users'),
  createUser:     b => post('/api/users', b),
  updateUser:     (id, b) => put(`/api/users/${id}`, b),
  deleteUser:     id => del(`/api/users/${id}`),
  resetPassword:  (id, new_password) => post(`/api/users/${id}/reset-password`, { new_password }),
  revokeSessions: id => post(`/api/users/${id}/revoke-sessions`),
  tokens:         () => get('/api/tokens'),
  createToken:    b => post('/api/tokens', b),
  revokeToken:    id => del(`/api/tokens/${id}`),
  audit:          params => get('/api/audit', params),
  auditFacets:    () => get('/api/audit/facets'),
  ldapSettings:     () => get('/api/admin/ldap'),
  saveLdapSettings: b => put('/api/admin/ldap', b),
  testLdap:         (settings, username, password) => post('/api/admin/ldap/test', { settings, username, password }),
  openplanSettings:     () => get('/api/admin/openplan'),
  saveOpenplanSettings: b => put('/api/admin/openplan', b),
  testOpenplan:         () => post('/api/admin/openplan/test'),
  syncOpenplanAbsences: () => post('/api/admin/openplan/absences/sync'),
  openplanStatus:       () => get('/api/openplan/status'),
  openplanProjects:     () => get('/api/openplan/projects'),
  openplanTasks:        (pid, q) => get(`/api/openplan/projects/${pid}/tasks`, q ? { q } : {}),
  openplanLink:         (wid, b) => post(`/api/workorders/${wid}/openplan/link`, b),
  openplanCreate:       (wid, b) => post(`/api/workorders/${wid}/openplan/create`, b),
  openplanSync:         wid => post(`/api/workorders/${wid}/openplan/sync`),
  openplanUnlink:       wid => del(`/api/workorders/${wid}/openplan`),
  openplanOrders:       b => post('/api/openplan/orders', b),
  openplanProject:      b => post('/api/openplan/projects', b),
  openplanDevices:      pid => get(`/api/openplan/projects/${pid}/devices`),
  importOpenplanDevices: (pid, items) => post(`/api/openplan/projects/${pid}/devices`, { items }),
  mailSettings:     () => get('/api/admin/mail'),
  saveMailSettings: b => put('/api/admin/mail', b),
  testMail:         to => post('/api/admin/mail/test', { to }),
  directoryUsers:   wid => get('/api/directory/users', wid ? { workorder_id: wid } : {}),
  myAbsences:       () => get('/auth/me/absences'),
  addMyAbsence:     b => post('/auth/me/absences', b),
  deleteMyAbsence:  id => del(`/auth/me/absences/${id}`),
  userAbsences:     uid => get(`/api/users/${uid}/absences`),
  addUserAbsence:   (uid, b) => post(`/api/users/${uid}/absences`, b),
  deleteUserAbsence: (uid, id) => del(`/api/users/${uid}/absences/${id}`),
  myDeputy:         () => get('/auth/me/deputy'),
  setMyDeputy:      deputy_id => put('/auth/me/deputy', { deputy_id }),
  userDeputy:       uid => get(`/api/users/${uid}/deputy`),
  setUserDeputy:    (uid, deputy_id) => put(`/api/users/${uid}/deputy`, { deputy_id }),
  sendWorkorder:    (id, b) => post(`/api/workorders/${id}/send`, b),
  sendPatchlist:    b => post('/api/patchlists/send', b),
  assignWorkorder:  (id, b) => post(`/api/workorders/${id}/assign`, b),
  tls:              () => get('/api/admin/tls'),
  saveTls:          b => put('/api/admin/tls', b),
  fetchTlsCa:       url => post('/api/admin/tls/fetch-ca', { url }),
  issueTls:         () => post('/api/admin/tls/issue'),
  tlsCert:          () => http.get('/api/admin/tls/cert', { responseType: 'blob' }).then(r => r.data),
  backups:            () => get('/api/admin/backups'),
  createBackup:       () => post('/api/admin/backups'),
  saveBackupSettings: b => put('/api/admin/backups/settings', b),
  deleteBackup:       name => del(`/api/admin/backups/${encodeURIComponent(name)}`),
  downloadBackup:     name => http.get(`/api/admin/backups/${encodeURIComponent(name)}/download`, { responseType: 'blob' }).then(r => r.data),
  backupTargets:      () => get('/api/admin/backups/targets'),
  createBackupTarget: b => post('/api/admin/backups/targets', b),
  updateBackupTarget: (id, b) => put(`/api/admin/backups/targets/${id}`, b),
  deleteBackupTarget: id => del(`/api/admin/backups/targets/${id}`),
  testBackupTarget:   id => post(`/api/admin/backups/targets/${id}/test`, {}),
  backupTargetItems:  id => get(`/api/admin/backups/targets/${id}/items`),
  restoreFromBackupTarget: (id, name) => post(`/api/admin/backups/targets/${id}/restore`, { name, confirm: true }),
  pushBackup:         name => post(`/api/admin/backups/${encodeURIComponent(name)}/push`, {}),
  restoreBackup:      name => post(`/api/admin/backups/${encodeURIComponent(name)}/restore`, { confirm: true }),
  restoreBackupUpload: file => { const f = new FormData(); f.append('file', file); return post('/api/admin/backups/restore-upload', f, { params: { confirm: true } }) },
}
