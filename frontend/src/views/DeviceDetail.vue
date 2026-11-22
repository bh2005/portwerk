<template>
  <div class="max-w-6xl space-y-4">
    <router-link to="/devices" class="text-xs text-ks-600 dark:text-ks-400 hover:underline">← Alle Geräte</router-link>
    <p v-if="error" class="text-sm text-red-500">{{ error }}</p>

    <template v-if="d">
      <div class="flex items-start justify-between">
        <div>
          <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">{{ d.hostname }}</h1>
          <p class="text-xs text-slate-400">{{ typeLabel(d.type) }} · {{ sourceLabel(d.source) }}<span v-if="d.ext_id"> · Quell-ID {{ d.ext_id }}</span></p>
        </div>
        <div class="flex gap-3 items-center">
          <a v-if="checkmkUrl(d)" :href="checkmkUrl(d)" target="_blank" rel="noopener" :class="btnLink">In Checkmk öffnen ↗</a>
          <button v-if="canWrite" :class="btnDanger" @click="removeDevice">Gerät löschen</button>
        </div>
      </div>

      <div :class="card" class="p-4">
        <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-3">Stammdaten</h2>
        <p v-if="msg" class="text-sm mb-2" :class="msgErr ? 'text-red-500' : 'text-green-600 dark:text-green-400'">{{ msg }}</p>
        <div class="grid md:grid-cols-3 gap-3">
          <div><label :class="lbl">Hostname</label><input v-model="form.hostname" :class="inp" :disabled="!canWrite" /></div>
          <div><label :class="lbl">Typ</label><select v-model="form.type" :class="inp" :disabled="!canWrite"><option v-for="[k, l] in DEVICE_TYPES" :key="k" :value="k">{{ l }}</option></select></div>
          <div><label :class="lbl">Status</label><select v-model="form.status" :class="inp" :disabled="!canWrite"><option v-for="[k, l] in DEVICE_STATUS" :key="k" :value="k">{{ l }}</option></select></div>
          <div><label :class="lbl">Hersteller</label><input v-model="form.vendor" :class="inp" :disabled="!canWrite" /></div>
          <div><label :class="lbl">Modell</label><input v-model="form.model" :class="inp" :disabled="!canWrite" /></div>
          <div><label :class="lbl">Seriennummer</label><input v-model="form.serial" :class="inp" :disabled="!canWrite" /></div>
          <div><label :class="lbl">Mgmt-IP</label><input v-model="form.mgmt_ip" :class="inp" :disabled="!canWrite" /></div>
          <div>
            <label :class="lbl">Location <HelpHint text="Raum oder Rack des Geräts. Eine HE-Position ist nur in einem Rack möglich." /></label>
            <select v-model="form.location_id" :class="inp" :disabled="!canWrite"><option :value="null">(keine)</option>
              <option v-for="l in locations" :key="l.id" :value="l.id">{{ l.path }}</option></select>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <div><label :class="lbl">HE-Position</label><input v-model.number="form.rack_position" type="number" min="1" :class="inp" :disabled="!canWrite" /></div>
            <div><label :class="lbl">Höhe (HE)</label><input v-model.number="form.height_u" type="number" min="1" max="50" :class="inp" :disabled="!canWrite" /></div>
            <div><label :class="lbl">Einbau</label><select v-model="form.orientation" :class="inp" :disabled="!canWrite" @change="if (form.orientation === 'vertical') { if (form.mount_side === 'both') form.mount_side = 'rear'; if (!form.side_slot) form.side_slot = 'left' } else form.side_slot = ''"><option value="horizontal">19 Zoll (HE)</option><option value="vertical">Hochkant (Seitenkanal)</option><option value="din_rail">Hutschiene / Montageplatte</option></select></div>
            <div><label :class="lbl">Einbauseite</label><select v-model="form.mount_side" :class="inp" :disabled="!canWrite"><option value="front">Vorderseite</option><option value="rear">Rückseite</option><option v-if="form.orientation === 'horizontal'" value="both">beide Seiten</option></select></div>
            <div v-if="form.orientation === 'vertical'"><label :class="lbl">Seitenkanal</label><select v-model="form.side_slot" :class="inp" :disabled="!canWrite"><option value="left">links</option><option value="right">rechts</option></select></div>
          </div>
          <div class="md:col-span-3"><label :class="lbl">Notiz</label><input v-model="form.note" :class="inp" :disabled="!canWrite" /></div>
        </div>
        <div v-if="canWrite" class="mt-3 text-right"><button :class="btnPrimary" @click="save">Speichern</button></div>
      </div>

      <div :class="card" class="p-4">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Ports ({{ d.ports.length }})</h2>
          <div class="flex gap-2">
            <button v-if="canReserve && picked.size" :class="btnGhost" @click="openReserve">Reservieren ({{ picked.size }})</button>
            <router-link v-if="d.ports.some(p => p.cable)" :to="{ path: '/labels', query: { device: String(d.id) } }" :class="btnGhost">Etiketten</router-link>
            <template v-if="canWrite">
              <button :class="btnGhost" @click="openBulk">Mehrere anlegen</button>
              <button :class="btnGhost" @click="startCable(null)">Kabel-Assistent</button>
              <button :class="btnPrimary" @click="openPort()">+ Port</button>
            </template>
          </div>
        </div>
        <p v-if="!d.ports.length" class="text-sm text-slate-400">Noch keine Ports.</p>
        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead><tr class="bg-slate-50 dark:bg-slate-700/40"><th v-if="canReserve" :class="th" class="w-6"><input type="checkbox" title="alle freien Ports wählen" :checked="picked.size > 0 && picked.size === freePorts.length" @change="toggleAll($event.target.checked)" /></th><th :class="th">Name</th><th :class="th">Medium</th><th :class="th">Geschw.</th><th :class="th">Beschreibung</th>
              <th :class="th">Status</th><th v-if="d.type === 'patchpanel'" :class="th">Gegenseite</th>
              <th :class="th">Verbunden mit</th><th v-if="canWrite" :class="th"></th></tr></thead>
            <tbody>
              <tr v-for="p in d.ports" :key="p.id" class="border-t border-slate-100 dark:border-slate-700">
                <td v-if="canReserve" :class="td"><input v-if="!p.reservation" type="checkbox" :checked="picked.has(p.id)" @change="togglePick(p.id)" /></td>
                <td :class="td" class="font-mono text-xs">{{ p.name }}</td>
                <td :class="td">{{ p.medium }}</td>
                <td :class="td">{{ fmtSpeed(p.speed_mbps) }}</td>
                <td :class="td" class="text-slate-500">{{ p.description || '–' }}</td>
                <td :class="td"><span :class="linkClass(p.oper_status)">{{ p.oper_status || '–' }}</span></td>
                <td v-if="d.type === 'patchpanel'" :class="td" class="text-xs font-mono">{{ p.peer_port_name || (p.peer_port_id ? `#${p.peer_port_id}` : '–') }}</td>
                <td :class="td" class="text-xs">
                  <router-link v-if="p.cable" :to="`/devices/${p.cable.device_id}`"
                    class="text-ks-600 dark:text-ks-400 hover:underline font-mono">
                    {{ p.cable.device_hostname }}:{{ p.cable.port_name }}
                  </router-link>
                  <span v-if="p.cable && p.cable.cable_label" class="ml-1 text-slate-400">({{ p.cable.cable_label }})</span>
                  <span v-if="p.cable && p.cable.measurement_ok === true" class="ml-1 text-green-500" title="Messung bestanden">✓</span>
                  <span v-if="p.cable && p.cable.measurement_ok === false" class="ml-1 text-red-500" title="Messung nicht bestanden">✗</span>
                  <span v-if="!p.cable && !p.reservation && !p.planned" class="text-slate-400">–</span>
                  <span v-if="p.reservation" class="ml-1 inline-block px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
                    :title="`reserviert von ${p.reservation.reserved_by}` + (p.reservation.workorder ? ` für ${p.reservation.workorder.number}` : '')">
                    reserviert: {{ p.reservation.purpose }}<template v-if="p.reservation.until"> (bis {{ fmtDate(p.reservation.until) }})</template>
                    <button v-if="canReserve" class="ml-1 underline" @click="releaseRes(p)">freigeben</button></span>
                  <router-link v-if="p.planned" :to="`/workorders/${p.planned.id}`" class="ml-1 inline-block px-1.5 py-0.5 rounded bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300 hover:underline"
                    :title="p.planned.title">verplant: {{ p.planned.number }}</router-link>
                  <button v-if="p.cable || p.peer_port_id" :class="btnLink" class="ml-2" title="Ganze Strecke über Patchfelder bis zum Endgerät" @click="showPath(p)">Pfad</button>
                  <button :class="btnLink" class="ml-2" title="Frühere Verbindungen dieses Ports" @click="showPortHistory(p)">Historie</button>
                </td>
                <td v-if="canWrite" :class="td" class="text-right whitespace-nowrap">
                  <button :class="btnLink" @click="openPort(p)">Bearbeiten</button>
                  <button v-if="d.type === 'patchpanel'" :class="btnLink" class="ml-3" @click="openPeer(p)">Gegenseite</button>
                  <button :class="btnLink" class="ml-3" @click="openLink(p)">Verbindung</button>
                  <button v-if="!p.cable" :class="btnLink" class="ml-3" @click="startCable(p)">Kabel-Assistent</button>
                  <button :class="btnDanger" class="ml-3" @click="removePort(p)">Löschen</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div ref="histCard" :class="card" class="p-4">
        <div class="flex flex-wrap items-end justify-between gap-3 mb-3">
          <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Verbindungs-Historie<span v-if="hist.port"> – Port {{ hist.port.name }}</span>
          </h2>
          <div class="flex flex-wrap items-end gap-2">
            <div><label :class="lbl">Stand am</label><input v-model="hist.at" type="datetime-local" :class="inp" class="!py-1" @change="loadHistory" /></div>
            <button v-if="hist.at" :class="btnLink" @click="hist.at = ''; loadHistory()">alle Zeitpunkte</button>
            <button v-if="hist.port" :class="btnLink" @click="hist.port = null; loadHistory()">alle Ports</button>
          </div>
        </div>
        <p v-if="hist.error" class="text-sm text-red-500">{{ hist.error }}</p>
        <p v-else-if="!hist.rows.length" class="text-sm text-slate-400">{{ hist.at ? 'Zu diesem Zeitpunkt war nichts verbunden.' : 'Noch keine Verbindungen.' }}</p>
        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead><tr class="bg-slate-50 dark:bg-slate-700/40"><th :class="th">Port</th><th :class="th">Gegenstelle</th><th :class="th">Kabel</th>
              <th :class="th">Von</th><th :class="th">Bis</th><th :class="th">Hergestellt</th><th :class="th">Getrennt</th></tr></thead>
            <tbody>
              <tr v-for="h in hist.rows" :key="h.id" class="border-t border-slate-100 dark:border-slate-700" :class="h.active ? '' : 'text-slate-500'">
                <td :class="td" class="font-mono text-xs">{{ h.local.port_name }}</td>
                <td :class="td" class="font-mono text-xs">
                  <router-link v-if="h.remote.device_id" :to="`/devices/${h.remote.device_id}`" class="text-ks-600 dark:text-ks-400 hover:underline">{{ h.remote.hostname }}:{{ h.remote.port_name }}</router-link>
                  <span v-else :title="'Port existiert nicht mehr'">{{ h.remote.hostname }}:{{ h.remote.port_name }}</span>
                </td>
                <td :class="td" class="text-xs">{{ h.cable_label || '–' }}<span class="text-slate-400"> {{ h.cable_type !== 'other' ? h.cable_type : '' }}</span></td>
                <td :class="td" class="text-xs whitespace-nowrap">{{ fmtTime(h.valid_from) }}</td>
                <td :class="td" class="text-xs whitespace-nowrap">
                  <span v-if="h.active" class="text-green-600 dark:text-green-400 font-medium">steckt</span>
                  <span v-else>{{ fmtTime(h.valid_to) }}</span>
                </td>
                <td :class="td" class="text-xs">
                  <router-link v-if="h.workorder" :to="`/workorders/${h.workorder.id}`" class="text-ks-600 dark:text-ks-400 hover:underline">{{ h.workorder.number }}</router-link>
                  <span v-else>{{ h.created_by || '–' }}</span>
                </td>
                <td :class="td" class="text-xs">
                  <template v-if="!h.active">
                    <router-link v-if="h.ended_workorder" :to="`/workorders/${h.ended_workorder.id}`" class="text-ks-600 dark:text-ks-400 hover:underline">{{ h.ended_workorder.number }}</router-link>
                    <span v-else>{{ h.ended_by || '–' }}</span>
                    <span class="text-slate-400 ml-1">{{ END_REASONS[h.end_reason] || '' }}</span>
                  </template>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <ModalDialog v-if="pathDlg" huge :title="`Pfad ab ${d.hostname}:${pathDlg.port}`" :error="pathDlg.error" @close="pathDlg = null">
      <p v-if="!pathDlg.data && !pathDlg.error" class="text-sm text-slate-400">Verfolge …</p>
      <PathGraphic v-if="pathDlg.data" :path="pathDlg.data" @navigate="pathDlg = null" />
    </ModalDialog>

    <ModalDialog v-if="resForm" title="Ports reservieren" :error="formError" @close="resForm = null">
      <p class="text-sm text-slate-500 mb-3">{{ resForm.names }}</p>
      <div class="grid grid-cols-2 gap-3">
        <div class="col-span-2"><label :class="lbl">Wofür (Projekt, Zweck)</label><input v-model="resForm.purpose" :class="inp" placeholder="z. B. Kamera-Projekt Halle 3" /></div>
        <div><label :class="lbl">Reserviert bis (optional)</label><input v-model="resForm.until" type="date" :class="inp" /></div>
      </div>
      <p class="text-xs text-slate-400 mt-2">Reservierte Ports gelten in Assistenten nicht mehr als frei; wer sie verplanen will, bekommt eine Rückfrage.</p>
      <template #footer>
        <button :class="btnGhost" @click="resForm = null">Abbrechen</button>
        <button :class="btnPrimary" :disabled="!resForm.purpose.trim()" @click="saveReserve">Reservieren</button>
      </template>
    </ModalDialog>

    <ModalDialog v-if="portForm" :title="portForm.id ? 'Port bearbeiten' : 'Neuer Port'" :error="formError" @close="portForm = null">
      <div class="grid grid-cols-2 gap-3">
        <div><label :class="lbl">Name</label><input v-model="portForm.name" :class="inp" /></div>
        <div><label :class="lbl">Medium</label><select v-model="portForm.medium" :class="inp"><option v-for="m in PORT_MEDIA" :key="m">{{ m }}</option></select></div>
        <div><label :class="lbl">Geschwindigkeit (Mbit/s)</label><input v-model.number="portForm.speed_mbps" type="number" min="0" :class="inp" /></div>
        <div><label :class="lbl">Beschreibung</label><input v-model="portForm.description" :class="inp" /></div>
      </div>
      <template #footer>
        <button @click="portForm = null" :class="btnGhost">Abbrechen</button>
        <button @click="savePort" :class="btnPrimary" :disabled="!portForm.name">Speichern</button>
      </template>
    </ModalDialog>

    <ModalDialog v-if="bulk" title="Mehrere Ports anlegen" :error="formError" @close="bulk = null">
      <p class="text-xs text-slate-400 mb-1">Beispiel: Präfix <code>Port </code>, Start 1, Anzahl 24 legt Port 1–24 an.</p>
      <div class="grid grid-cols-3 gap-3">
        <div><label :class="lbl">Präfix</label><input v-model="bulk.prefix" :class="inp" /></div>
        <div><label :class="lbl">Start</label><input v-model.number="bulk.start" type="number" min="0" :class="inp" /></div>
        <div><label :class="lbl">Anzahl</label><input v-model.number="bulk.count" type="number" min="1" max="512" :class="inp" /></div>
        <div><label :class="lbl">Medium</label><select v-model="bulk.medium" :class="inp"><option v-for="m in PORT_MEDIA" :key="m">{{ m }}</option></select></div>
        <div><label :class="lbl">Mbit/s</label><input v-model.number="bulk.speed_mbps" type="number" min="0" :class="inp" /></div>
        <div class="flex flex-col gap-1">
          <label :class="lbl">Dual (Vorder-/Rückseite) <HelpHint text="Legt pro Port-Nummer zwei Ports an (z.B. &#x27;Port 1&#x27; und &#x27;Port 1-back&#x27;) und verbindet sie automatisch als Peer (Durchschleifung). Ideal für Patchfelder und Datendosen." /></label>
          <label class="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" v-model="bulk.dual" class="rounded" />
            Vorder- und Rückseite anlegen
          </label>
        </div>
        <div v-if="bulk.dual"><label :class="lbl">Rückseiten-Suffix</label><input v-model="bulk.back_suffix" :class="inp" placeholder="-back" /></div>
      </div>
      <p v-if="bulk.dual" class="text-xs text-ks-600 dark:text-ks-400 mt-1">
        Legt {{ bulk.count * 2 }} Ports an: z.B. <code>{{ bulk.prefix }}{{ bulk.start }}</code> + <code>{{ bulk.prefix }}{{ bulk.start }}{{ bulk.back_suffix || '-back' }}</code> (automatisch gepeert)
      </p>
      <template #footer>
        <button @click="bulk = null" :class="btnGhost">Abbrechen</button>
        <button @click="saveBulk" :class="btnPrimary" :disabled="!bulk.prefix || !bulk.count">Anlegen</button>
      </template>
    </ModalDialog>

    <ModalDialog v-if="cableForm" :title="`Kabel an ${cableForm.port.name}`" :error="formError" @close="cableForm = null">
      <div class="space-y-4">
        <div class="grid grid-cols-2 gap-3">
          <div class="col-span-2"><label :class="lbl">Zielgerät</label>
            <select v-model="cableForm.deviceId" :class="inp" @change="loadCablePorts">
              <option :value="null">(Verbindung lösen)</option>
              <option v-for="o in cableForm.devices" :key="o.id" :value="o.id">{{ o.hostname }}</option>
            </select>
          </div>
          <div v-if="cableForm.deviceId" class="col-span-2"><label :class="lbl">Zielport</label>
            <select v-model="cableForm.portId" :class="inp">
              <option :value="null">(Port wählen)</option>
              <option v-for="p in cableForm.ports" :key="p.id" :value="p.id">
                {{ p.name }}{{ p.cable ? ` ← belegt: ${p.cable.device_hostname}:${p.cable.port_name}` : '' }}
              </option>
            </select>
          </div>
        </div>
        <hr class="border-slate-200 dark:border-slate-700" />
        <p class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Kabeldetails</p>
        <div class="grid grid-cols-2 gap-3">
          <div><label :class="lbl">Kabelnummer / Label</label>
            <input v-model="cableForm.cable_label" :class="inp" placeholder="z.B. K-EG-001" />
          </div>
          <div><label :class="lbl">Kabeltyp</label>
            <select v-model="cableForm.cable_type" :class="inp">
              <option v-for="t in cableTypes" :key="t.name" :value="t.name">{{ t.name }}</option>
            </select>
          </div>
          <div v-if="countLabel(cableForm.cable_type)">
            <label :class="lbl">{{ countLabel(cableForm.cable_type) }}</label>
            <input v-model.number="cableForm.fiber_count" type="number" min="1" :class="inp" placeholder="z.B. 4" />
          </div>
          <div><label :class="lbl">Länge (m)</label>
            <input v-model.number="cableForm.length_m" type="number" min="0" step="0.5" :class="inp" placeholder="z.B. 15.5" />
          </div>
          <div><label :class="lbl">Farbe</label>
            <input v-model="cableForm.color" :class="inp" placeholder="z.B. blau" />
          </div>
          <div><label :class="lbl">Verlegt am</label>
            <input v-model="cableForm.installed_at" type="date" :class="inp" />
          </div>
        </div>
        <hr class="border-slate-200 dark:border-slate-700" />
        <p class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Messprotokoll</p>
        <div class="grid grid-cols-2 gap-3">
          <div><label :class="lbl">Protokoll-Nr. / Referenz</label>
            <input v-model="cableForm.measurement_ref" :class="inp" placeholder="z.B. FLUKE-2024-001" />
          </div>
          <div><label :class="lbl">Messergebnis</label>
            <select v-model="cableForm.measurement_ok" :class="inp">
              <option :value="null">– nicht gemessen –</option>
              <option :value="true">✓ Bestanden</option>
              <option :value="false">✗ Nicht bestanden</option>
            </select>
          </div>
        </div>
        <div><label :class="lbl">Notiz</label>
          <input v-model="cableForm.note" :class="inp" placeholder="Freitext" />
        </div>
      </div>
      <template #footer>
        <button @click="cableForm = null" :class="btnGhost">Abbrechen</button>
        <button @click="saveCable" :class="btnPrimary" :disabled="cableForm.deviceId !== null && !cableForm.portId">Speichern</button>
      </template>
    </ModalDialog>

    <ModalDialog v-if="peer" :title="`Gegenseite von ${peer.port.name}`" :error="formError" @close="peer = null">
      <p class="text-xs text-slate-400">Beim Patchfeld hängt jeder Port mit seiner Gegenseite (Rückseite/Vorderseite oder zweites Feld) zusammen. Wähle das Gerät und den Port.</p>
      <div><label :class="lbl">Gerät</label>
        <select v-model="peer.deviceId" :class="inp" @change="loadPeerPorts"><option :value="null">(wählen)</option>
          <option v-for="o in peer.devices" :key="o.id" :value="o.id">{{ o.hostname }}</option></select></div>
      <div v-if="peer.deviceId"><label :class="lbl">Port</label>
        <select v-model="peer.portId" :class="inp"><option :value="null">(Verbindung lösen)</option>
          <option v-for="p in peer.ports" :key="p.id" :value="p.id">{{ p.name }}</option></select></div>
      <template #footer>
        <button @click="peer = null" :class="btnGhost">Abbrechen</button>
        <button @click="savePeer" :class="btnPrimary">Speichern</button>
      </template>
    </ModalDialog>
    <CableWizard v-if="cableWiz" :preset-device-id="cableWiz.deviceId" :preset-port-id="cableWiz.portId" @close="cableWiz = null" @done="cableDone" />
  </div>
</template>

<script setup>
import { computed, ref, reactive, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ModalDialog from '../components/ModalDialog.vue'
import CableWizard from '../components/CableWizard.vue'
import PathGraphic from '../components/PathGraphic.vue'
import HelpHint from '../components/HelpHint.vue'
import { cableTypes, countLabel, loadCableTypes } from '../catalog.js'
import { api, errText, conflictOf, canWriteMaster, hasRole } from '../api.js'
import { checkmkUrl, loadCheckmk } from '../checkmk.js'
import { inp, lbl, card, th, td, btnPrimary, btnGhost, btnDanger, btnLink, DEVICE_TYPES, DEVICE_STATUS, PORT_MEDIA,
         typeLabel, sourceLabel, fmtSpeed, fmtTime, linkClass } from '../ui.js'

const route = useRoute(), router = useRouter()
const canWrite = canWriteMaster()
const d = ref(null), locations = ref([])
const form = reactive({})
const error = ref(''), msg = ref(''), msgErr = ref(false), formError = ref('')
const portForm = ref(null), bulk = ref(null), peer = ref(null), cableForm = ref(null)
const cableWiz = ref(null)
const hist = reactive({ rows: [], at: '', port: null, error: '' }), histCard = ref(null)
const canReserve = hasRole('planer'), picked = ref(new Set()), resForm = ref(null), pathDlg = ref(null)
async function showPath(p) {
  pathDlg.value = { port: p.name, data: null, error: '' }
  try { pathDlg.value.data = await api.portPath(p.id) } catch (e) { pathDlg.value.error = errText(e) }
}
const freePorts = computed(() => (d.value?.ports || []).filter(p => !p.reservation))
const fmtDate = s => s ? s.split('-').reverse().join('.') : ''
function togglePick(id) { const s = new Set(picked.value); s.has(id) ? s.delete(id) : s.add(id); picked.value = s }
function toggleAll(on) { picked.value = new Set(on ? freePorts.value.map(p => p.id) : []) }
function openReserve() {
  formError.value = ''
  const names = d.value.ports.filter(p => picked.value.has(p.id)).map(p => p.name)
  resForm.value = { purpose: '', until: '', names: `${d.value.hostname}: ${names.slice(0, 12).join(', ')}${names.length > 12 ? ` … (${names.length})` : ''}` }
}
async function saveReserve() {
  try {
    await api.reservePorts({ port_ids: [...picked.value], purpose: resForm.value.purpose.trim(), until: resForm.value.until || null })
    resForm.value = null; picked.value = new Set(); msgErr.value = false; msg.value = 'Ports reserviert.'; await load()
  } catch (e) { formError.value = errText(e) }
}
async function releaseRes(p) {
  if (!confirm(`Reservierung „${p.reservation.purpose}“ für ${p.name} freigeben?`)) return
  try { await api.releaseReservation(p.reservation.id); await load() } catch (e) { error.value = errText(e) }
}
const END_REASONS = { manual: '(direkt)', workorder: '', wizard: '(Assistent)', retire: '(Rückbau)', '': '(Port/Gerät gelöscht)' }
async function loadHistory() {
  if (!d.value) return
  try {
    const params = hist.port ? { port_id: hist.port.id } : { device_id: d.value.id }
    if (hist.at) params.at = hist.at
    hist.rows = await api.cableHistory(params); hist.error = ''
  } catch (e) { hist.rows = []; hist.error = errText(e) }
}
function showPortHistory(p) { hist.port = p; loadHistory(); histCard.value?.scrollIntoView({ behavior: 'smooth' }) }
function startCable(p) { cableWiz.value = { deviceId: d.value.id, portId: p ? p.id : null } }
async function cableDone(r) { cableWiz.value = null; msgErr.value = false; msg.value = r.workorder ? `Kabel als Position in ${r.workorder.number} angelegt.` : 'Kabel angelegt.'; await load() }

const FIELDS = ['hostname', 'type', 'vendor', 'model', 'serial', 'mgmt_ip', 'location_id', 'rack_position', 'height_u', 'status', 'note', 'mount_side', 'orientation', 'side_slot']

async function load() {
  try {
    d.value = await api.device(route.params.id)
    for (const k of FIELDS) form[k] = d.value[k]
    error.value = ''
    if (hist.port && !d.value.ports.some(p => p.id === hist.port.id)) hist.port = null
    loadHistory()
  } catch (e) { error.value = errText(e, 'Gerät nicht gefunden'); d.value = null }
}

async function save() {
  msg.value = ''
  try {
    const body = { ...form, rack_position: form.rack_position || null, height_u: form.height_u || 1 }
    await api.updateDevice(d.value.id, body)
    msgErr.value = false; msg.value = 'Gespeichert'
    await load()
  } catch (e) { msgErr.value = true; msg.value = errText(e) }
}

async function removeDevice() {
  if (!confirm(`Gerät ${d.value.hostname} mit allen Ports löschen?`)) return
  try { await api.deleteDevice(d.value.id); router.push('/devices') } catch (e) { error.value = errText(e) }
}

function openPort(p) { formError.value = ''; portForm.value = p ? { ...p } : { name: '', medium: 'RJ45', speed_mbps: null, description: '' } }
async function savePort() {
  try {
    const f = { ...portForm.value, speed_mbps: portForm.value.speed_mbps || null }
    f.id ? await api.updatePort(f.id, f) : await api.createPort(d.value.id, f)
    portForm.value = null; await load()
  } catch (e) { formError.value = errText(e) }
}
async function removePort(p) {
  if (!confirm(`Port ${p.name} löschen?`)) return
  try { await api.deletePort(p.id); await load() } catch (e) { error.value = errText(e) }
}

function openBulk() { formError.value = ''; bulk.value = { prefix: '', start: 1, count: 24, medium: 'RJ45', speed_mbps: null, dual: false, back_suffix: '-back' } }
async function saveBulk() {
  try {
    await api.bulkPorts(d.value.id, { ...bulk.value, speed_mbps: bulk.value.speed_mbps || null })
    bulk.value = null; await load()
  } catch (e) { formError.value = errText(e) }
}

function _emptyCable() {
  return { cable_label: '', cable_type: 'other', fiber_count: null, length_m: null,
           color: '', installed_at: null, measurement_ref: '', measurement_ok: null, note: '' }
}
async function openLink(p) {
  formError.value = ''
  const r = await api.devices({ limit: 1000 })
  const devices = r.items.filter(o => o.id !== d.value.id)
  const currentDeviceId = p.cable ? p.cable.device_id : null
  let ports = []
  if (currentDeviceId) {
    const dev = await api.device(currentDeviceId)
    ports = dev.ports.filter(x => x.id !== p.id)
  }
  cableForm.value = {
    port: p, devices, ports,
    deviceId: currentDeviceId,
    portId: p.cable ? p.cable.port_id : null,
    ...(p.cable ? {
      cable_label: p.cable.cable_label, cable_type: p.cable.cable_type || 'other',
      fiber_count: p.cable.fiber_count, length_m: p.cable.length_m, color: p.cable.color,
      installed_at: p.cable.installed_at, measurement_ref: p.cable.measurement_ref,
      measurement_ok: p.cable.measurement_ok, note: p.cable.note,
    } : _emptyCable()),
  }
}
async function loadCablePorts() {
  cableForm.value.portId = null
  if (cableForm.value.deviceId) {
    const dev = await api.device(cableForm.value.deviceId)
    cableForm.value.ports = dev.ports.filter(x => x.id !== cableForm.value.port.id)
  } else {
    cableForm.value.ports = []
  }
}
async function saveCable() {
  try {
    const { port, devices, ports, deviceId, portId, ...cableFields } = cableForm.value
    await api.setCable(port.id, { port_b_id: portId, ...cableFields })
    cableForm.value = null; await load()
  } catch (e) {
    const c = conflictOf(e)
    if (c && c.code === 'port_reserved' && !cableForm.value.use_reserved && confirm(c.message)) { cableForm.value.use_reserved = true; return saveCable() }
    formError.value = errText(e)
  }
}

async function openPeer(p) {
  formError.value = ''
  const r = await api.devices({ type: 'patchpanel', limit: 1000 })
  peer.value = { port: p, devices: r.items, deviceId: null, portId: p.peer_port_id || null, ports: [] }
}
async function loadPeerPorts() {
  peer.value.portId = null
  peer.value.ports = peer.value.deviceId ? (await api.device(peer.value.deviceId)).ports.filter(x => x.id !== peer.value.port.id) : []
}
async function savePeer() {
  try { await api.setPeer(peer.value.port.id, peer.value.portId); peer.value = null; await load() }
  catch (e) { formError.value = errText(e) }
}

onMounted(async () => { loadCableTypes(); loadCheckmk(); try { locations.value = await api.locations() } catch {} ; load() })
watch(() => route.params.id, id => { if (id) { hist.port = null; hist.at = ''; picked.value = new Set(); load() } })
</script>
