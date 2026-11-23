<template>
  <div class="space-y-5 max-w-5xl">
    <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">VLANs & Portprofile</h1>
    <p class="text-sm text-slate-500 dark:text-slate-400">
      Nur Dokumentation – Portwerk konfiguriert keine Switches. Am Port legst du VLAN bzw. Profil auf der Geräteseite fest („VLAN“ in der Portzeile);
      im Ablauf gibt es die Auftragsaktion <b>Port umkonfigurieren</b> und eine Ziel-Konfiguration bei „herstellen“/„umstecken“.
    </p>
    <p v-if="err" class="text-sm text-red-500">{{ err }}</p>

    <!-- VLAN-Katalog -->
    <section :class="card" class="p-4 space-y-3">
      <div class="flex items-center justify-between gap-3 flex-wrap">
        <h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200">VLAN-Katalog</h2>
        <select v-model="siteFilter" :class="inp" class="!w-56 !py-1.5" @change="loadVlans">
          <option :value="null">alle Standorte</option>
          <option v-for="s in sites" :key="s.id" :value="s.id">{{ s.code }} · {{ s.name }}</option>
        </select>
      </div>
      <table class="w-full text-sm">
        <thead><tr class="bg-slate-50 dark:bg-slate-700/40"><th :class="th" class="w-20">VLAN</th><th :class="th">Name</th><th :class="th">Gilt für</th>
          <th :class="th">Notiz</th><th :class="th">Ports</th><th v-if="canWrite" :class="th"></th></tr></thead>
        <tbody>
          <template v-for="v in vlans" :key="v.id">
            <tr class="border-t border-slate-100 dark:border-slate-700">
              <td :class="td" class="font-mono">{{ v.vid }}</td>
              <td :class="td">{{ v.name }}</td>
              <td :class="td" class="text-slate-500">{{ v.site_code || 'alle Standorte' }}</td>
              <td :class="td" class="text-slate-500 text-xs">{{ v.note }}</td>
              <td :class="td"><button v-if="v.ports" :class="btnLink" @click="toggleUsage(v)">{{ v.ports }} {{ usage[v.id] ? '▾' : '▸' }}</button><span v-else class="text-slate-400">0</span></td>
              <td v-if="canWrite" :class="td" class="text-right whitespace-nowrap">
                <button :class="btnLink" @click="editVlan(v)">Bearbeiten</button><button :class="btnDanger" class="ml-3" @click="removeVlan(v)">Löschen</button></td>
            </tr>
            <tr v-if="usage[v.id]"><td :colspan="canWrite ? 6 : 5" class="px-3 pb-2 text-xs">
              <router-link v-for="u in usage[v.id]" :key="u.port_id" :to="`/devices/${u.device_id}`" class="inline-block mr-3 font-mono text-ks-600 dark:text-ks-400 hover:underline">
                {{ u.hostname }}:{{ u.port }} <span class="text-slate-400">({{ u.as.join('/') }})</span></router-link></td></tr>
          </template>
        </tbody>
      </table>
      <p v-if="!vlans.length" class="text-sm text-slate-400">Noch keine VLANs.</p>
      <form v-if="canWrite" class="flex flex-wrap items-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-700" @submit.prevent="saveVlan">
        <div><label :class="lbl">VLAN-ID</label><input v-model.number="vf.vid" type="number" min="1" max="4094" required :class="inp" class="!w-24" /></div>
        <div><label :class="lbl">Name</label><input v-model="vf.name" required :class="inp" class="!w-44" /></div>
        <div><label :class="lbl">Gilt für</label><select v-model="vf.site_id" :class="inp" class="!w-48">
          <option :value="null">alle Standorte</option><option v-for="s in sites" :key="s.id" :value="s.id">{{ s.code }}</option></select></div>
        <div class="flex-1 min-w-[10rem]"><label :class="lbl">Notiz</label><input v-model="vf.note" :class="inp" /></div>
        <button :class="btnPrimary">{{ vf.id ? 'Speichern' : 'Hinzufügen' }}</button>
        <button v-if="vf.id" type="button" :class="btnGhost" @click="resetVlan">Abbrechen</button>
      </form>
    </section>

    <!-- Portprofile -->
    <section :class="card" class="p-4 space-y-3">
      <h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200">Portprofile</h2>
      <table class="w-full text-sm">
        <thead><tr class="bg-slate-50 dark:bg-slate-700/40"><th :class="th">Name</th><th :class="th">Konfiguration</th><th :class="th">Notiz</th>
          <th :class="th">Ports</th><th v-if="canAdmin" :class="th"></th></tr></thead>
        <tbody>
          <tr v-for="p in profiles" :key="p.id" class="border-t border-slate-100 dark:border-slate-700">
            <td :class="td" class="font-medium">{{ p.name }}</td><td :class="td" class="font-mono text-xs">{{ p.text }}</td>
            <td :class="td" class="text-xs text-slate-500">{{ p.note }}</td><td :class="td">{{ p.ports }}</td>
            <td v-if="canAdmin" :class="td" class="text-right whitespace-nowrap">
              <button :class="btnLink" @click="editProfile(p)">Bearbeiten</button><button :class="btnDanger" class="ml-3" @click="removeProfile(p)">Löschen</button></td>
          </tr>
        </tbody>
      </table>
      <p v-if="!profiles.length" class="text-sm text-slate-400">Noch keine Profile – z. B. „Büro-PC“ (Access 10 + Voice 30), „Drucker“, „Access Point“ (Trunk).</p>
      <form v-if="canAdmin" class="space-y-3 pt-2 border-t border-slate-100 dark:border-slate-700" @submit.prevent="saveProfile">
        <div class="grid sm:grid-cols-3 gap-3">
          <div><label :class="lbl">Name</label><input v-model="pf.name" required :class="inp" /></div>
          <div><label :class="lbl">Modus</label><select v-model="pf.port_mode" :class="inp"><option value="access">Access</option><option value="trunk">Trunk</option></select></div>
          <div><label :class="lbl">Notiz</label><input v-model="pf.note" :class="inp" /></div>
        </div>
        <div v-if="pf.port_mode === 'access'" class="grid sm:grid-cols-3 gap-3">
          <div><label :class="lbl">Access-VLAN</label><input v-model.number="pf.access_vid" type="number" min="1" max="4094" :class="inp" /></div>
          <div><label :class="lbl">Voice-VLAN (optional)</label><input v-model.number="pf.voice_vid" type="number" min="1" max="4094" :class="inp" /></div>
        </div>
        <div v-else class="grid sm:grid-cols-3 gap-3">
          <div><label :class="lbl">Erlaubte VLANs (leer = alle)</label><input v-model="pf.allowed_vids" :class="inp" placeholder="10,20,40-45" /></div>
          <div><label :class="lbl">Native-VLAN (optional)</label><input v-model.number="pf.native_vid" type="number" min="1" max="4094" :class="inp" /></div>
        </div>
        <div class="flex gap-2"><button :class="btnPrimary">{{ pf.id ? 'Speichern' : 'Profil anlegen' }}</button>
          <button v-if="pf.id" type="button" :class="btnGhost" @click="resetProfile">Abbrechen</button></div>
        <p class="text-xs text-slate-400">Ein geändertes Profil ändert keine Ports – umkonfiguriert wird über einen Auftrag.</p>
      </form>
    </section>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { api, errText, canWriteMaster, isAdmin } from '../api.js'
import { inp, lbl, card, th, td, btnPrimary, btnGhost, btnLink, btnDanger } from '../ui.js'

const canWrite = canWriteMaster(), canAdmin = isAdmin()
const sites = ref([]), vlans = ref([]), profiles = ref([]), usage = ref({}), err = ref(''), siteFilter = ref(null)
const VF = { id: null, vid: null, name: '', site_id: null, note: '' }
const PF = { id: null, name: '', port_mode: 'access', access_vid: null, voice_vid: null, native_vid: null, allowed_vids: '', note: '' }
const vf = reactive({ ...VF }), pf = reactive({ ...PF })
const blank = v => (v === '' ? null : v)

async function loadVlans() { try { vlans.value = await api.vlans({ site_id: siteFilter.value || undefined }); usage.value = {} } catch (e) { err.value = errText(e) } }
async function loadProfiles() { try { profiles.value = await api.portProfiles() } catch (e) { err.value = errText(e) } }
async function run(fn) { err.value = ''; try { await fn() } catch (e) { err.value = errText(e) } }

const resetVlan = () => Object.assign(vf, VF)
const editVlan = v => Object.assign(vf, { id: v.id, vid: v.vid, name: v.name, site_id: v.site_id, note: v.note })
const saveVlan = () => run(async () => {
  const body = { vid: vf.vid, name: vf.name.trim(), site_id: vf.site_id, note: vf.note }
  vf.id ? await api.updateVlan(vf.id, body) : await api.createVlan(body)
  resetVlan(); await loadVlans()
})
const removeVlan = v => confirm(`VLAN ${v.vid} „${v.name}“ löschen? Ports behalten die VLAN-Nummer.`) && run(async () => { await api.deleteVlan(v.id); await loadVlans() })
async function toggleUsage(v) {
  if (usage.value[v.id]) { const u = { ...usage.value }; delete u[v.id]; usage.value = u; return }
  await run(async () => { usage.value = { ...usage.value, [v.id]: await api.vlanUsage({ vid: v.vid, site_id: v.site_id || undefined }) } })
}

const resetProfile = () => Object.assign(pf, PF)
const editProfile = p => Object.assign(pf, { ...PF, ...p })
const saveProfile = () => run(async () => {
  const body = { name: pf.name.trim(), port_mode: pf.port_mode, access_vid: blank(pf.access_vid), voice_vid: blank(pf.voice_vid),
                 native_vid: blank(pf.native_vid), allowed_vids: pf.allowed_vids || '', note: pf.note }
  pf.id ? await api.updateProfile(pf.id, body) : await api.createProfile(body)
  resetProfile(); await loadProfiles()
})
const removeProfile = p => confirm(`Profil „${p.name}“ löschen? Ports behalten ihre Werte.`) && run(async () => { await api.deleteProfile(p.id); await loadProfiles() })

onMounted(async () => { try { sites.value = await api.sites() } catch {} ; loadVlans(); loadProfiles() })
</script>
