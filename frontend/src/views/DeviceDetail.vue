<template>
  <div class="max-w-6xl space-y-4">
    <router-link to="/devices" class="text-xs text-ks-600 dark:text-ks-400 hover:underline">{{ $t('← Alle Geräte') }}</router-link>
    <p v-if="error" class="text-sm text-red-500 dark:text-red-400">{{ error }}</p>

    <template v-if="d">
      <div class="flex items-start justify-between">
        <div>
          <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">{{ d.hostname }}</h1>
          <p class="text-xs text-slate-400">{{ typeLabel(d.type) }} · {{ sourceLabel(d.source) }}<span v-if="d.ext_id"> · {{ $t('Quell-ID') }} {{ d.ext_id }}</span></p>
        </div>
        <div class="flex gap-3 items-center">
          <a v-if="checkmkUrl(d)" :href="checkmkUrl(d)" target="_blank" rel="noopener" :class="btnLink">{{ $t('In Checkmk öffnen ↗') }}</a>
          <button v-if="canWrite" :class="btnDanger" @click="removeDevice">{{ $t('Gerät löschen') }}</button>
        </div>
      </div>

      <div :class="card" class="p-4">
        <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 mb-3">{{ $t('Stammdaten') }}</h2>
        <p v-if="msg" class="text-sm mb-2" :class="msgErr ? 'text-red-500' : 'text-green-600 dark:text-green-400'">{{ msg }}</p>
        <div class="grid md:grid-cols-3 gap-3">
          <div><label :class="lbl">{{ $t('Hostname') }}</label><input v-model="form.hostname" :class="inp" :disabled="!canWrite" /></div>
          <div><label :class="lbl">{{ $t('Typ') }}</label><select v-model="form.type" :class="inp" :disabled="!canWrite"><option v-for="[k, l] in DEVICE_TYPES" :key="k" :value="k">{{ $t(l) }}</option></select></div>
          <div><label :class="lbl">{{ $t('Status') }}</label><select v-model="form.status" :class="inp" :disabled="!canWrite"><option v-for="[k, l] in DEVICE_STATUS" :key="k" :value="k">{{ $t(l) }}</option></select></div>
          <div><label :class="lbl">{{ $t('Hersteller') }}</label><input v-model="form.vendor" :class="inp" :disabled="!canWrite" /></div>
          <div><label :class="lbl">{{ $t('Modell') }}</label><input v-model="form.model" :class="inp" :disabled="!canWrite" /></div>
          <div><label :class="lbl">{{ $t('Seriennummer') }}</label><input v-model="form.serial" :class="inp" :disabled="!canWrite" /></div>
          <div><label :class="lbl">{{ $t('Mgmt-IP') }}</label><input v-model="form.mgmt_ip" :class="inp" :disabled="!canWrite" /></div>
          <div>
            <label :class="lbl">{{ $t('Location') + ' ' }}<HelpHint :text="$t('Raum oder Rack des Geräts. Eine HE-Position ist nur in einem Rack möglich.')" /></label>
            <select v-model="form.location_id" :class="inp" :disabled="!canWrite"><option :value="null">{{ $t('(keine)') }}</option>
              <option v-for="l in locations" :key="l.id" :value="l.id">{{ l.path }}</option></select>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <div><label :class="lbl">{{ $t('HE-Position') }}</label><input v-model.number="form.rack_position" type="number" min="1" :class="inp" :disabled="!canWrite" /></div>
            <div><label :class="lbl">{{ $t('Höhe (HE)') }}</label><input v-model.number="form.height_u" type="number" min="1" max="50" :class="inp" :disabled="!canWrite" /></div>
            <div><label :class="lbl">{{ $t('Einbau') }}</label><select v-model="form.orientation" :class="inp" :disabled="!canWrite" @change="if (form.orientation === 'vertical') { if (form.mount_side === 'both') form.mount_side = 'rear'; if (!form.side_slot) form.side_slot = 'left' } else form.side_slot = ''"><option value="horizontal">{{ $t('19 Zoll (HE)') }}</option><option value="vertical">{{ $t('Hochkant (Seitenkanal)') }}</option><option value="din_rail">{{ $t('Hutschiene / Montageplatte') }}</option></select></div>
            <div><label :class="lbl">{{ $t('Einbauseite') }}</label><select v-model="form.mount_side" :class="inp" :disabled="!canWrite"><option value="front">{{ $t('Vorderseite') }}</option><option value="rear">{{ $t('Rückseite') }}</option><option v-if="form.orientation === 'horizontal'" value="both">{{ $t('beide Seiten') }}</option></select></div>
            <div v-if="form.orientation === 'vertical'"><label :class="lbl">{{ $t('Seitenkanal') }}</label><select v-model="form.side_slot" :class="inp" :disabled="!canWrite"><option value="left">{{ $t('links') }}</option><option value="right">{{ $t('rechts') }}</option></select></div>
          </div>
          <div class="md:col-span-3"><label :class="lbl">{{ $t('Notiz') }}</label><input v-model="form.note" :class="inp" :disabled="!canWrite" /></div>
        </div>
        <div v-if="canWrite" class="mt-3 text-right"><button :class="btnPrimary" @click="save">{{ $t('Speichern') }}</button></div>
      </div>

      <div :class="card" class="p-4">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{{ $t('Ports ({n})', { n: d.ports.length }) }}</h2>
          <div class="flex gap-2">
            <button v-if="canReserve && picked.size" :class="btnGhost" @click="openReserve">{{ $t('Reservieren ({n})', { n: picked.size }) }}</button>
            <router-link v-if="d.ports.some(p => p.cable)" :to="{ path: '/labels', query: { device: String(d.id) } }" :class="btnGhost">{{ $t('Etiketten') }}</router-link>
            <template v-if="canWrite">
              <button :class="btnGhost" @click="openBulk">{{ $t('Mehrere anlegen') }}</button>
              <button :class="btnGhost" @click="startCable(null)">{{ $t('Kabel-Assistent') }}</button>
              <button :class="btnPrimary" @click="openPort()">{{ $t('+ Port') }}</button>
            </template>
          </div>
        </div>
        <p v-if="!d.ports.length" class="text-sm text-slate-400">{{ $t('Noch keine Ports.') }}</p>
        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead><tr class="bg-slate-50 dark:bg-slate-700/40"><th v-if="canReserve" :class="th" class="w-6"><input type="checkbox" :title="$t('alle freien Ports wählen')" :checked="picked.size > 0 && picked.size === freePorts.length" @change="toggleAll($event.target.checked)" /></th><th :class="th">{{ $t('Name') }}</th><th :class="th">{{ $t('Medium') }}</th><th :class="th">{{ $t('Geschw.') }}</th><th :class="th">{{ $t('Beschreibung') }}</th>
              <th :class="th">{{ $t('Status') }}</th><th v-if="d.type === 'patchpanel'" :class="th">{{ $t('Gegenseite') }}</th>
              <th :class="th">{{ $t('Verbunden mit') }}</th><th v-if="canWrite" :class="th"></th></tr></thead>
            <tbody>
              <tr v-for="p in d.ports" :key="p.id" class="border-t border-slate-100 dark:border-slate-700">
                <td v-if="canReserve" :class="td"><input v-if="!p.reservation" type="checkbox" :checked="picked.has(p.id)" @change="togglePick(p.id)" /></td>
                <td :class="td" class="font-mono text-xs">{{ p.name }}
                  <span v-if="p.config" class="block font-sans text-[11px] text-indigo-600 dark:text-indigo-400 whitespace-nowrap" :title="p.config.text">{{ shortCfg(p.config) }}</span></td>
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
                  <span v-if="p.cable && p.cable.provisional" class="ml-1 inline-block px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
                    :title="$t('Aus dem Soll/Ist-Abgleich übernommen – Dosen und Patchfelder sind noch nicht dokumentiert')">{{ $t('vorläufig') }}
                    <button v-if="canWrite" class="ml-1 underline" :title="$t('Strecke ist vollständig dokumentiert')" @click="completeCable(p)">{{ $t('vollständig') }}</button></span>
                  <span v-if="p.cable && p.cable.measurement_ok === true" class="ml-1 text-green-500" :title="$t('Messung bestanden')">✓</span>
                  <span v-if="p.cable && p.cable.measurement_ok === false" class="ml-1 text-red-500 dark:text-red-400" :title="$t('Messung nicht bestanden')">✗</span>
                  <span v-if="!p.cable && !p.reservation && !p.planned" class="text-slate-400">–</span>
                  <span v-if="p.reservation" class="ml-1 inline-block px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
                    :title="`reserviert von ${p.reservation.reserved_by}` + (p.reservation.workorder ? ` für ${p.reservation.workorder.number}` : '')">
                    {{ $t('reserviert:') }} {{ p.reservation.purpose }}<template v-if="p.reservation.until"> ({{ $t('bis {d}', { d: fmtDate(p.reservation.until) }) }})</template>
                    <button v-if="canReserve" class="ml-1 underline" @click="releaseRes(p)">{{ $t('freigeben') }}</button></span>
                  <router-link v-if="p.planned" :to="`/workorders/${p.planned.id}`" class="ml-1 inline-block px-1.5 py-0.5 rounded bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-300 hover:underline"
                    :title="p.planned.title">{{ $t('verplant:') }} {{ p.planned.number }}</router-link>
                  <button v-if="p.cable || p.peer_port_id" :class="btnLink" class="ml-2" :title="$t('Ganze Strecke über Patchfelder bis zum Endgerät')" @click="showPath(p)">{{ $t('Pfad') }}</button>
                  <button v-if="canPlan && !p.cable && !['patchpanel', 'outlet'].includes(d.type)" :class="btnLink" class="ml-2" :title="$t('Patchungen zu einem Zielport automatisch planen')" @click="autoRoute = { portId: p.id }">{{ $t('Autorouting') }}</button>
                  <button :class="btnLink" class="ml-2" :title="$t('Frühere Verbindungen dieses Ports')" @click="showPortHistory(p)">{{ $t('Historie') }}</button>
                  <button v-if="['switch', 'router', 'firewall'].includes(d.type) || p.config" :class="btnLink" class="ml-2" :title="$t('VLAN / Portprofil')" @click="openVlan(p)">{{ $t('VLAN') }}</button>
                  <button v-if="d.type === 'outlet' && canPlan && !p.name.toLowerCase().endsWith('-back')" :class="btnLink" class="ml-2"
                    :title="$t('Dose bis zum Switch patchen und VLAN setzen (als Auftrag)')" @click="workplaceFor = { deviceId: d.id, portId: p.id }">{{ $t('Arbeitsplatz') }}</button>
                </td>
                <td v-if="canWrite" :class="td" class="text-right whitespace-nowrap">
                  <button :class="btnLink" @click="openPort(p)">{{ $t('Bearbeiten') }}</button>
                  <button v-if="d.type === 'patchpanel'" :class="btnLink" class="ml-3" @click="openPeer(p)">{{ $t('Gegenseite') }}</button>
                  <button :class="btnLink" class="ml-3" @click="strecke = p" :title="$t('Ganze Strecke ansehen und bearbeiten (Kabel, Zwischenstationen, LLDP-Abgleich)')">{{ $t('Verbindung') }}</button>
                  <button v-if="!p.cable" :class="btnLink" class="ml-3" @click="startCable(p)">{{ $t('Kabel-Assistent') }}</button>
                  <button :class="btnDanger" class="ml-3" @click="removePort(p)">{{ $t('Löschen') }}</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div :class="card" class="px-4 py-3 flex items-center justify-between gap-3">
        <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{{ $t('Verbindungs-Historie') }}</h2>
        <button :class="btnLink" @click="hist.port = null; hist.open = true">{{ $t('alle Ports anzeigen') }}</button>
      </div>
    </template>

    <CableHistoryPanel :open="hist.open" :device-id="d?.id" :port-id="hist.port?.id ?? null" :hostname="d?.hostname || ''" :port-name="hist.port?.name || ''"
                       @close="hist.open = false" @all-ports="hist.port = null" />

    <WorkplaceWizard v-if="workplaceFor" :preset="workplaceFor" @close="workplaceFor = null; load()" />

    <ModalDialog v-if="vlanDlg" wide :title="`VLAN / Portprofil – ${d.hostname}:${vlanDlg.port.name}`" :error="formError" @close="vlanDlg = null">
      <p class="text-sm mb-3"><span class="text-slate-500">{{ $t('Aktuell:') }}</span> <b>{{ vlanDlg.port.config ? vlanDlg.port.config.text : $t('nicht dokumentiert') }}</b></p>
      <template v-if="canWrite">
        <PortConfigFields :cfg="vlanDlg.cfg" :profiles="vlanDlg.profiles" :vlans="vlanDlg.vlans" />
        <p class="text-xs text-slate-400 mt-2">{{ $t('Direkt ändern ist für Administratoren gedacht; im Ablauf über den Auftrag „Port umkonfigurieren“.') }}</p>
      </template>
      <div v-if="vlanDlg.history.length" class="mt-4">
        <div :class="lbl">{{ $t('Historie') }}</div>
        <div v-for="(h, i) in vlanDlg.history" :key="i" class="text-xs py-1 border-t border-slate-100 dark:border-slate-700">
          {{ fmtTime(h.changed_at) }} · {{ h.workorder ? h.workorder.number : h.changed_by }}: <span class="line-through text-slate-400">{{ h.before }}</span> → {{ h.after }}</div>
      </div>
      <template #footer>
        <button :class="btnGhost" @click="vlanDlg = null">{{ canWrite ? $t('Abbrechen') : $t('Schließen') }}</button>
        <button v-if="canWrite" :class="btnPrimary" @click="saveVlan">{{ $t('Speichern') }}</button>
      </template>
    </ModalDialog>

    <ModalDialog v-if="pathDlg" huge :title="`Pfad ab ${d.hostname}:${pathDlg.port}`" :error="pathDlg.error" @close="pathDlg = null">
      <div class="flex items-end gap-2 mb-3">
        <div><label :class="lbl">{{ $t('Stand am (leer = heute)') }}</label><input v-model="pathDlg.at" type="datetime-local" :class="inp" class="!py-1" @change="loadPath" /></div>
        <button v-if="pathDlg.at" :class="btnLink" class="pb-2" @click="pathDlg.at = ''; loadPath()">{{ $t('heute') }}</button>
        <p v-if="pathDlg.data?.at" class="text-xs text-slate-400 pb-2">{{ $t('Verbindungen aus der Historie; Geräte, Orte und Patchfeld-Gegenseiten: heutiger Stand.') }}</p>
      </div>
      <p v-if="!pathDlg.data && !pathDlg.error" class="text-sm text-slate-400">{{ $t('Verfolge …') }}</p>
      <PathGraphic v-if="pathDlg.data" :path="pathDlg.data" @navigate="pathDlg = null" />
    </ModalDialog>

    <ModalDialog v-if="resForm" :title="$t('Ports reservieren')" :error="formError" @close="resForm = null">
      <p class="text-sm text-slate-500 mb-3">{{ resForm.names }}</p>
      <div class="grid grid-cols-2 gap-3">
        <div class="col-span-2"><label :class="lbl">{{ $t('Wofür (Projekt, Zweck)') }}</label><input v-model="resForm.purpose" :class="inp" :placeholder="$t('z. B. Kamera-Projekt Halle 3')" /></div>
        <div><label :class="lbl">{{ $t('Reserviert bis (optional)') }}</label><input v-model="resForm.until" type="date" :class="inp" /></div>
      </div>
      <p class="text-xs text-slate-400 mt-2">{{ $t('Reservierte Ports gelten in Assistenten nicht mehr als frei; wer sie verplanen will, bekommt eine Rückfrage.') }}</p>
      <template #footer>
        <button :class="btnGhost" @click="resForm = null">{{ $t('Abbrechen') }}</button>
        <button :class="btnPrimary" :disabled="!resForm.purpose.trim()" @click="saveReserve">{{ $t('Reservieren') }}</button>
      </template>
    </ModalDialog>

    <ModalDialog v-if="portForm" :title="portForm.id ? $t('Port bearbeiten') : $t('Neuer Port')" :error="formError" @close="portForm = null">
      <div class="grid grid-cols-2 gap-3">
        <div><label :class="lbl">{{ $t('Name') }}</label><input v-model="portForm.name" :class="inp" /></div>
        <div><label :class="lbl">{{ $t('Medium') }}</label><select v-model="portForm.medium" :class="inp"><option v-for="m in PORT_MEDIA" :key="m">{{ m }}</option></select></div>
        <div><label :class="lbl">{{ $t('Geschwindigkeit (Mbit/s)') }}</label><input v-model.number="portForm.speed_mbps" type="number" min="0" :class="inp" /></div>
        <div><label :class="lbl">{{ $t('Beschreibung') }}</label><input v-model="portForm.description" :class="inp" /></div>
      </div>
      <template #footer>
        <button @click="portForm = null" :class="btnGhost">{{ $t('Abbrechen') }}</button>
        <button @click="savePort" :class="btnPrimary" :disabled="!portForm.name">{{ $t('Speichern') }}</button>
      </template>
    </ModalDialog>

    <ModalDialog v-if="bulk" :title="$t('Mehrere Ports anlegen')" :error="formError" @close="bulk = null">
      <p class="text-xs text-slate-400 mb-1">{{ $t('Beispiel: Präfix') + ' ' }}<code>{{ $t('Port') + ' ' }}</code>{{ $t(', Start 1, Anzahl 24 legt Port 1–24 an.') }}</p>
      <div class="grid grid-cols-3 gap-3">
        <div><label :class="lbl">{{ $t('Präfix') }}</label><input v-model="bulk.prefix" :class="inp" /></div>
        <div><label :class="lbl">{{ $t('Start') }}</label><input v-model.number="bulk.start" type="number" min="0" :class="inp" /></div>
        <div><label :class="lbl">{{ $t('Anzahl') }}</label><input v-model.number="bulk.count" type="number" min="1" max="512" :class="inp" /></div>
        <div><label :class="lbl">{{ $t('Medium') }}</label><select v-model="bulk.medium" :class="inp"><option v-for="m in PORT_MEDIA" :key="m">{{ m }}</option></select></div>
        <div><label :class="lbl">{{ $t('Mbit/s') }}</label><input v-model.number="bulk.speed_mbps" type="number" min="0" :class="inp" /></div>
        <div class="flex flex-col gap-1">
          <label :class="lbl">{{ $t('Dual (Vorder-/Rückseite)') + ' ' }}<HelpHint :text="$t('Legt pro Port-Nummer zwei Ports an (z.B. „Port 1“ und „Port 1-back“) und verbindet sie automatisch als Peer (Durchschleifung). Ideal für Patchfelder und Datendosen.')" /></label>
          <label class="flex items-center gap-2 text-sm cursor-pointer">
            <input type="checkbox" v-model="bulk.dual" class="rounded" />
            {{ $t('Vorder- und Rückseite anlegen') }}
          </label>
        </div>
        <div v-if="bulk.dual"><label :class="lbl">{{ $t('Rückseiten-Suffix') }}</label><input v-model="bulk.back_suffix" :class="inp" :placeholder="$t('-back')" /></div>
      </div>
      <p v-if="bulk.dual" class="text-xs text-ks-600 dark:text-ks-400 mt-1">
        {{ $t('Legt {n} Ports an: z. B.', { n: bulk.count * 2 }) + ' ' }}<code>{{ bulk.prefix }}{{ bulk.start }}</code> + <code>{{ bulk.prefix }}{{ bulk.start }}{{ bulk.back_suffix || '-back' }}</code>{{ ' ' + $t('(automatisch gepeert)') }}
      </p>
      <template #footer>
        <button @click="bulk = null" :class="btnGhost">{{ $t('Abbrechen') }}</button>
        <button @click="saveBulk" :class="btnPrimary" :disabled="!bulk.prefix || !bulk.count">{{ $t('Anlegen') }}</button>
      </template>
    </ModalDialog>

    <AutoRouteWizard :open="!!autoRoute" :preset-port-id="autoRoute?.portId ?? null" :preset-device-id="d?.id ?? null" @close="autoRoute = null" @done="load" />
    <PathEditor :open="!!strecke" :port-id="strecke?.id ?? null" @close="strecke = null" @changed="load" />

    <ModalDialog v-if="peer" :title="`Gegenseite von ${peer.port.name}`" :error="formError" @close="peer = null">
      <p class="text-xs text-slate-400">{{ $t('Beim Patchfeld hängt jeder Port mit seiner Gegenseite (Rückseite/Vorderseite oder zweites Feld) zusammen. Wähle das Gerät und den Port.') }}</p>
      <div><label :class="lbl">{{ $t('Gerät') }}</label>
        <select v-model="peer.deviceId" :class="inp" @change="loadPeerPorts"><option :value="null">{{ $t('(wählen)') }}</option>
          <option v-for="o in peer.devices" :key="o.id" :value="o.id">{{ o.hostname }}</option></select></div>
      <div v-if="peer.deviceId"><label :class="lbl">{{ $t('Port') }}</label>
        <select v-model="peer.portId" :class="inp"><option :value="null">{{ $t('(Verbindung lösen)') }}</option>
          <option v-for="p in peer.ports" :key="p.id" :value="p.id">{{ p.name }}</option></select></div>
      <template #footer>
        <button @click="peer = null" :class="btnGhost">{{ $t('Abbrechen') }}</button>
        <button @click="savePeer" :class="btnPrimary">{{ $t('Speichern') }}</button>
      </template>
    </ModalDialog>
    <CableWizard v-if="cableWiz" :preset-device-id="cableWiz.deviceId" :preset-port-id="cableWiz.portId" @close="cableWiz = null" @done="cableDone" />
  </div>
</template>

<script setup>
import { t } from '../i18n.js'
import { computed, ref, reactive, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ModalDialog from '../components/ModalDialog.vue'
import CableWizard from '../components/CableWizard.vue'
import CableHistoryPanel from '../components/CableHistoryPanel.vue'
import PathEditor from '../components/PathEditor.vue'
import AutoRouteWizard from '../components/AutoRouteWizard.vue'
import PathGraphic from '../components/PathGraphic.vue'
import PortConfigFields from '../components/PortConfigFields.vue'
import WorkplaceWizard from '../components/WorkplaceWizard.vue'
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
const portForm = ref(null), bulk = ref(null), peer = ref(null), strecke = ref(null), autoRoute = ref(null)
const cableWiz = ref(null)
const hist = reactive({ open: false, port: null })
const canReserve = hasRole('planer'), picked = ref(new Set()), resForm = ref(null), pathDlg = ref(null)
const vlanDlg = ref(null), workplaceFor = ref(null), canPlan = hasRole('planer')
/** Kurzform für die Port-Tabelle: Profilname bzw. VLAN-Nummern (voller Text im Tooltip). */
const shortCfg = c => c.profile ? c.profile.name
  : c.port_mode === 'access' ? `VLAN ${c.access_vid}${c.voice_vid ? ' + V' + c.voice_vid : ''}` : `Trunk ${c.allowed_vids || 'alle'}`
async function openVlan(p) {
  formError.value = ''
  const c = p.config || {}
  vlanDlg.value = { port: p, cfg: { port_mode: c.port_mode || '', access_vid: c.access_vid ?? null, voice_vid: c.voice_vid ?? null, native_vid: c.native_vid ?? null,
    allowed_vids: c.allowed_vids || '', profile_id: c.profile?.id ?? null }, profiles: [], vlans: [], history: [] }
  try {
    const [profiles, vlans, history] = await Promise.all([api.portProfiles(), api.vlans(), api.portConfigHistory(p.id)])
    Object.assign(vlanDlg.value, { profiles, vlans, history })
  } catch (e) { formError.value = errText(e) }
}
async function saveVlan() {
  const c = vlanDlg.value.cfg, n = v => (v === '' ? null : v)
  try {
    await api.setPortConfig(vlanDlg.value.port.id, { ...c, access_vid: n(c.access_vid), voice_vid: n(c.voice_vid), native_vid: n(c.native_vid) })
    vlanDlg.value = null; msgErr.value = false; msg.value = t('VLAN-Konfiguration gespeichert.'); await load()
  } catch (e) { formError.value = errText(e) }
}
function showPath(p) { pathDlg.value = { port: p.name, portId: p.id, at: '', data: null, error: '' }; loadPath() }
async function loadPath() {
  const dlg = pathDlg.value
  dlg.error = ''
  try { dlg.data = await api.portPath(dlg.portId, dlg.at || undefined) } catch (e) { dlg.error = errText(e) }
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
    resForm.value = null; picked.value = new Set(); msgErr.value = false; msg.value = t('Ports reserviert.'); await load()
  } catch (e) { formError.value = errText(e) }
}
async function releaseRes(p) {
  if (!confirm(t('Reservierung „{p}“ für {port} freigeben?', { p: p.reservation.purpose, port: p.name }))) return
  try { await api.releaseReservation(p.reservation.id); await load() } catch (e) { error.value = errText(e) }
}
function showPortHistory(p) { hist.port = p; hist.open = true }
async function completeCable(p) {
  const c = p.cable
  try {
    await api.updateCable(c.id, { cable_type: c.cable_type, cable_label: c.cable_label, fiber_count: c.fiber_count, length_m: c.length_m, color: c.color,
      installed_at: c.installed_at, measurement_ref: c.measurement_ref, measurement_ok: c.measurement_ok, note: c.note, provisional: false })
    await load()
  } catch (e) { error.value = errText(e) }
}
function startCable(p) { cableWiz.value = { deviceId: d.value.id, portId: p ? p.id : null } }
async function cableDone(r) { cableWiz.value = null; msgErr.value = false; msg.value = r.workorder ? t('Kabel als Position in {n} angelegt.', { n: r.workorder.number }) : t('Kabel angelegt.'); await load() }

const FIELDS = ['hostname', 'type', 'vendor', 'model', 'serial', 'mgmt_ip', 'location_id', 'rack_position', 'height_u', 'status', 'note', 'mount_side', 'orientation', 'side_slot']

async function load() {
  try {
    d.value = await api.device(route.params.id)
    for (const k of FIELDS) form[k] = d.value[k]
    error.value = ''
    if (hist.port && !d.value.ports.some(p => p.id === hist.port.id)) hist.port = null
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
  if (!confirm(t('Gerät {name} mit allen Ports löschen?', { name: d.value.hostname }))) return
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
  if (!confirm(t('Port {name} löschen?', { name: p.name }))) return
  try { await api.deletePort(p.id); await load() } catch (e) { error.value = errText(e) }
}

function openBulk() { formError.value = ''; bulk.value = { prefix: '', start: 1, count: 24, medium: 'RJ45', speed_mbps: null, dual: false, back_suffix: '-back' } }
async function saveBulk() {
  try {
    await api.bulkPorts(d.value.id, { ...bulk.value, speed_mbps: bulk.value.speed_mbps || null })
    bulk.value = null; await load()
  } catch (e) { formError.value = errText(e) }
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
watch(() => route.params.id, id => { if (id) { hist.port = null; hist.open = false; picked.value = new Set(); load() } })
</script>
