<template>
  <section class="border border-slate-200 dark:border-slate-700 rounded-xl p-4 space-y-3">
    <div class="flex items-center justify-between gap-3 flex-wrap">
      <h3 class="text-sm font-semibold text-slate-700 dark:text-slate-200">Externe Sicherungsziele</h3>
      <button :class="btnPrimary" @click="openForm()">+ Ziel hinzufügen</button>
    </div>
    <p class="text-xs text-slate-400">Nach jeder Sicherung (automatisch und manuell) werden die aktiven Ziele bedient. Ein Fehler an einem Ziel stört die Sicherung nicht, er steht im Status.
      Verzeichnis (NAS/NFS/SMB, eingehängt), S3 und WebDAV sind möglich. Je Ziel werden automatische Sicherungen nach Anzahl aufbewahrt, manuelle bleiben.</p>
    <p v-if="err" class="text-sm text-red-500 dark:text-red-400">{{ err }}</p>
    <p v-if="msg" class="text-sm text-green-600 dark:text-green-400">{{ msg }}</p>
    <p v-if="!items.length" class="text-sm text-slate-400">Noch kein externes Ziel eingerichtet.</p>
    <div v-else class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead><tr class="bg-slate-50 dark:bg-slate-700/40"><th :class="th">Ziel</th><th :class="th">Typ</th><th :class="th">Ablage</th><th :class="th">Behalten</th><th :class="th">Letzte Übertragung</th><th :class="th"></th></tr></thead>
        <tbody>
          <tr v-for="t in items" :key="t.id" class="border-t border-slate-100 dark:border-slate-700 align-top" :class="t.enabled ? '' : 'opacity-60'">
            <td :class="td"><span class="font-medium text-slate-800 dark:text-slate-100">{{ t.name }}</span>
              <span v-if="!t.enabled" class="ml-1 text-[10px] px-1.5 py-0.5 rounded bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300">aus</span>
              <span v-if="t.encrypt" class="ml-1 text-[10px] px-1.5 py-0.5 rounded bg-indigo-100 dark:bg-indigo-900/40 text-indigo-700 dark:text-indigo-300" title="AES-256-GCM, Passphrase">verschlüsselt</span></td>
            <td :class="td" class="text-xs">{{ t.type_label }}</td>
            <td :class="td" class="text-xs font-mono break-all">{{ where(t) }}</td>
            <td :class="td" class="text-xs whitespace-nowrap">{{ t.keep }} automatische</td>
            <td :class="td" class="text-xs">
              <span v-if="t.last_ok === null" class="text-slate-400">noch nie</span>
              <template v-else>
                <span :class="t.last_ok ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'">{{ t.last_ok ? '✓' : '✗' }} {{ fmtTime(t.last_at) }}</span>
                <div v-if="!t.last_ok" class="text-red-500 break-words max-w-xs dark:text-red-400">{{ t.last_msg }}</div>
                <div v-else class="text-slate-400 font-mono break-all">{{ t.last_name }}</div>
              </template></td>
            <td :class="td" class="text-right whitespace-nowrap">
              <button :class="btnLink" :disabled="!!busy" @click="test(t)">{{ busy === 'test' + t.id ? 'Teste …' : 'Testen' }}</button>
              <button :class="btnLink" class="ml-3" @click="openItems(t)">Sicherungen</button>
              <button :class="btnLink" class="ml-3" @click="openForm(t)">Bearbeiten</button>
              <button :class="btnDanger" class="ml-3" :disabled="!!busy" @click="remove(t)">Entfernen</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Ziel anlegen/bearbeiten -->
    <SidePanel :open="!!form" :title="form?.id ? 'Sicherungsziel bearbeiten' : 'Sicherungsziel hinzufügen'" @close="form = null">
      <template v-if="form">
        <div class="grid grid-cols-2 gap-3">
          <div><label :class="lbl">Typ</label>
            <select v-model="form.type" :class="inp" :disabled="!!form.id"><option v-for="(l, k) in types" :key="k" :value="k">{{ l }}</option></select></div>
          <div><label :class="lbl">Name</label><input v-model="form.name" :class="inp" placeholder="z. B. NAS Rechenzentrum" /></div>
        </div>

        <template v-if="form.type === 'path'">
          <div><label :class="lbl">Verzeichnis im Container</label><input v-model="form.path" :class="inp" placeholder="/backup-extern" />
            <p class="text-xs text-slate-400 mt-1">NAS-Freigaben (NFS/SMB) werden auf dem Docker-Host als Volume eingehängt und hier als Pfad angegeben.</p></div>
          <details class="text-xs text-slate-500"><summary class="cursor-pointer">Beispiel: NFS-Share als Volume (docker-compose.yml)</summary>
            <pre class="mt-2 p-2 rounded bg-slate-100 dark:bg-slate-900 overflow-x-auto">services:
  portwerk:
    volumes:
      - opp-data:/data
      - nas-backup:/backup-extern
volumes:
  opp-data:
  nas-backup:
    driver: local
    driver_opts:
      type: nfs
      o: "addr=nas.example.test,rw,nfsvers=4"
      device: ":/export/portwerk"</pre></details>
        </template>

        <template v-else-if="form.type === 's3'">
          <div><label :class="lbl">Endpunkt</label><input v-model="form.endpoint" :class="inp" placeholder="leer = Amazon S3, sonst z. B. https://minio.example.test:9000" /></div>
          <div class="grid grid-cols-2 gap-3">
            <div><label :class="lbl">Bucket</label><input v-model="form.bucket" :class="inp" /></div>
            <div><label :class="lbl">Region</label><input v-model="form.region" :class="inp" placeholder="us-east-1" /></div>
            <div class="col-span-2"><label :class="lbl">Ordner im Bucket (optional)</label><input v-model="form.prefix" :class="inp" placeholder="portwerk/prod" /></div>
            <div><label :class="lbl">Zugangsschlüssel</label><input v-model="form.access_key" :class="inp" autocomplete="off" /></div>
            <div><label :class="lbl">Secret</label><input v-model="form.secret_key" type="password" :class="inp" autocomplete="new-password" :placeholder="form.secret_key_set ? '(gesetzt – leer = unverändert)' : ''" /></div>
          </div>
          <label v-if="form.endpoint" class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300"><input v-model="form.path_style" type="checkbox" /> Pfad-Stil (<code>host/bucket</code>, bei MinIO und den meisten Eigenbauten nötig)</label>
        </template>

        <template v-else>
          <div><label :class="lbl">WebDAV-Adresse</label><input v-model="form.url" :class="inp" placeholder="https://cloud.example.test/remote.php/dav/files/benutzer" /></div>
          <div class="grid grid-cols-2 gap-3">
            <div><label :class="lbl">Benutzer</label><input v-model="form.user" :class="inp" autocomplete="off" /></div>
            <div><label :class="lbl">Passwort</label><input v-model="form.password" type="password" :class="inp" autocomplete="new-password" :placeholder="form.password_set ? '(gesetzt – leer = unverändert)' : ''" /></div>
            <div class="col-span-2"><label :class="lbl">Ordner (optional)</label><input v-model="form.prefix" :class="inp" placeholder="Sicherungen/portwerk" /></div>
          </div>
        </template>

        <template v-if="form.type !== 'path' && httpsUrl">
          <label class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300"><input v-model="form.verify_tls" type="checkbox" /> Zertifikat prüfen</label>
          <div><label :class="lbl">CA-Zertifikat (PEM, optional)</label><textarea v-model="form.ca_pem" rows="3" :class="inp" class="font-mono text-xs" placeholder="-----BEGIN CERTIFICATE-----"></textarea></div>
        </template>

        <div class="grid grid-cols-2 gap-3">
          <div><label :class="lbl">Automatische aufbewahren</label><input v-model.number="form.keep" type="number" min="1" max="365" :class="inp" /></div>
          <label class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300 mt-6"><input v-model="form.enabled" type="checkbox" /> Ziel aktiv</label>
        </div>

        <div class="rounded-lg border border-slate-200 dark:border-slate-700 p-3 space-y-2">
          <label class="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200"><input v-model="form.encrypt" type="checkbox" /> Vor der Übertragung verschlüsseln (AES-256-GCM)</label>
          <div v-if="form.encrypt"><label :class="lbl">Passphrase</label>
            <input v-model="form.passphrase" type="password" :class="inp" autocomplete="new-password" :placeholder="form.passphrase_set ? '(gesetzt – leer = unverändert)' : ''" />
            <p class="text-xs text-amber-700 dark:text-amber-300 mt-1">Ohne die Passphrase sind die Sicherungen auf dem Ziel nicht lesbar. Sie liegt in der Portwerk-Datenbank (die ihrerseits in der Sicherung steckt) –
              bewahren Sie sie zusätzlich getrennt auf, sonst ist eine Wiederherstellung auf einem neuen Server nicht möglich.</p></div>
          <p v-else class="text-xs text-slate-400">Die Sicherung enthält Passwort-Hashes, Zugangsdaten und das Server-Zertifikat. Ohne Verschlüsselung muss das Ziel entsprechend geschützt sein.</p>
        </div>
        <p v-if="form.error" class="text-sm text-red-500 dark:text-red-400">{{ form.error }}</p>
      </template>
      <template #footer>
        <div class="flex justify-end gap-2"><button :class="btnGhost" @click="form = null">Abbrechen</button>
          <button :class="btnPrimary" :disabled="busy === 'save' || !form?.name?.trim()" @click="save">Speichern</button></div>
      </template>
    </SidePanel>

    <!-- Sicherungen auf dem Ziel -->
    <SidePanel :open="!!remote" :title="remote ? 'Sicherungen auf ' + remote.t.name : ''" @close="remote = null">
      <template v-if="remote">
        <p v-if="remote.error" class="text-sm text-red-500 dark:text-red-400">{{ remote.error }}</p>
        <p v-else-if="remote.loading" class="text-sm text-slate-400">Lade …</p>
        <p v-else-if="!remote.items.length" class="text-sm text-slate-400">Auf diesem Ziel liegt noch keine Sicherung.</p>
        <ul v-else class="space-y-2">
          <li v-for="i in remote.items" :key="i.name" class="rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm">
            <div class="font-mono text-xs break-all">{{ i.name }}</div>
            <div class="text-xs text-slate-500 mt-0.5">{{ i.kind === 'auto' ? 'automatisch' : 'manuell' }} · {{ size(i.size) }}<template v-if="i.modified"> · {{ fmtTime(i.modified) }}</template>
              <span v-if="i.encrypted" class="ml-1 text-indigo-600 dark:text-indigo-400">verschlüsselt</span></div>
            <button :class="btnLink" class="mt-1" :disabled="!!busy" @click="restoreFrom(i)">Wiederherstellen</button>
          </li>
        </ul>
      </template>
    </SidePanel>
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import SidePanel from './SidePanel.vue'
import { api, errText } from '../api.js'
import { inp, lbl, th, td, btnPrimary, btnGhost, btnDanger, btnLink, fmtTime } from '../ui.js'

/** Externe Sicherungsziele (Verzeichnis/NAS, S3, WebDAV): anlegen, testen, Sicherungen ansehen und von dort wiederherstellen. */
const emit = defineEmits(['restored', 'changed'])
const items = ref([]), types = ref({}), err = ref(''), msg = ref(''), busy = ref(''), form = ref(null), remote = ref(null)

const httpsUrl = computed(() => /^https/i.test(form.value?.type === 's3' ? form.value.endpoint || 'https' : form.value?.url || ''))
const size = n => n >= 1024 ** 2 ? `${(n / 1024 ** 2).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`
const where = t => t.type === 'path' ? t.path : t.type === 's3' ? `${t.endpoint || 'Amazon S3'} · ${t.bucket}${t.prefix ? '/' + t.prefix : ''}` : `${t.url}${t.prefix ? '/' + t.prefix : ''}`

async function load() {
  try { const r = await api.backupTargets(); items.value = r.items; types.value = r.types; emit('changed', r.items) } catch (e) { err.value = errText(e) }
}
function openForm(t) {
  form.value = t ? { ...t, secret_key: '', password: '', passphrase: '', error: '' }
    : { type: 'path', name: '', enabled: true, keep: 14, encrypt: false, passphrase: '', verify_tls: true, ca_pem: '', path: '', endpoint: '', region: 'us-east-1', bucket: '', prefix: '',
        access_key: '', secret_key: '', path_style: true, url: '', user: '', password: '', error: '' }
}
async function save() {
  const f = { ...form.value }
  const { id, error, type_label, last_at, last_ok, last_msg, last_name, secret_key_set, password_set, passphrase_set, ...body } = f
  busy.value = 'save'; form.value.error = ''
  try { id ? await api.updateBackupTarget(id, body) : await api.createBackupTarget(body); form.value = null; msg.value = 'Gespeichert.'; await load() }
  catch (e) { form.value.error = errText(e) } finally { busy.value = '' }
}
async function test(t) {
  busy.value = 'test' + t.id; err.value = msg.value = ''
  try { const r = await api.testBackupTarget(t.id); msg.value = `${t.name}: ${r.message}` } catch (e) { err.value = `${t.name}: ${errText(e)}` } finally { busy.value = '' }
}
async function remove(t) {
  if (!confirm(`Sicherungsziel „${t.name}“ entfernen?\n\nBereits abgelegte Sicherungen auf dem Ziel bleiben dort erhalten.`)) return
  try { await api.deleteBackupTarget(t.id); await load() } catch (e) { err.value = errText(e) }
}
async function openItems(t) {
  remote.value = { t, items: [], loading: true, error: '' }
  try { remote.value.items = await api.backupTargetItems(t.id) } catch (e) { remote.value.error = errText(e) } finally { remote.value.loading = false }
}
async function restoreFrom(i) {
  const t = remote.value.t
  if (!confirm(`Sicherung „${i.name}“ von „${t.name}“:\n\nDen GESAMTEN aktuellen Bestand durch diese Sicherung ersetzen?\n\nDer jetzige Stand wird vorher automatisch gesichert. Danach müssen sich alle neu anmelden.`)) return
  busy.value = 'restore'; remote.value.error = ''
  try { emit('restored', await api.restoreFromBackupTarget(t.id, i.name)) } catch (e) { remote.value.error = errText(e); busy.value = '' }
}
onMounted(load)
defineExpose({ load })
</script>
