<template>
  <div class="space-y-3">
    <div class="grid grid-cols-2 gap-3">
      <div><label :class="lbl">Portprofil</label>
        <select v-model="cfg.profile_id" :class="inp" @change="applyProfile">
          <option :value="null">— eigene Werte —</option>
          <option v-for="p in profiles" :key="p.id" :value="p.id">{{ p.name }} ({{ p.text }})</option>
        </select></div>
      <div><label :class="lbl">Modus</label>
        <select v-model="cfg.port_mode" :class="inp" @change="cfg.profile_id = null">
          <option value="">nicht dokumentiert</option><option value="access">Access</option><option value="trunk">Trunk</option>
        </select></div>
    </div>
    <div v-if="cfg.port_mode === 'access'" class="grid grid-cols-2 gap-3">
      <div><label :class="lbl">Access-VLAN</label><input v-model.number="cfg.access_vid" type="number" min="1" max="4094" :class="inp" :list="listId" @input="cfg.profile_id = null" /></div>
      <div><label :class="lbl">Voice-VLAN (optional)</label><input v-model.number="cfg.voice_vid" type="number" min="1" max="4094" :class="inp" :list="listId" @input="cfg.profile_id = null" /></div>
    </div>
    <div v-if="cfg.port_mode === 'trunk'" class="grid grid-cols-2 gap-3">
      <div><label :class="lbl">Erlaubte VLANs (leer = alle)</label><input v-model="cfg.allowed_vids" :class="inp" placeholder="z. B. 10,20,40-45" @input="cfg.profile_id = null" /></div>
      <div><label :class="lbl">Native-VLAN (optional)</label><input v-model.number="cfg.native_vid" type="number" min="1" max="4094" :class="inp" :list="listId" @input="cfg.profile_id = null" /></div>
    </div>
    <datalist :id="listId"><option v-for="v in vlans" :key="v.id" :value="v.vid">{{ v.name }}</option></datalist>
    <p class="text-xs text-slate-400">Nur Dokumentation – Portwerk konfiguriert keine Switches.</p>
  </div>
</template>

<script setup>
import { inp, lbl } from '../ui.js'

/** Eingabe einer Port-Konfiguration (VLAN/Profil). ``cfg`` wird direkt bearbeitet. */
const props = defineProps({ cfg: { type: Object, required: true }, profiles: { type: Array, default: () => [] }, vlans: { type: Array, default: () => [] } })
const listId = `vlans-${Math.random().toString(36).slice(2, 8)}`

function applyProfile() {
  const p = props.profiles.find(x => x.id === props.cfg.profile_id)
  if (!p) return
  Object.assign(props.cfg, { port_mode: p.port_mode, access_vid: p.access_vid, voice_vid: p.voice_vid, native_vid: p.native_vid, allowed_vids: p.allowed_vids, profile_id: p.id })
}
</script>
