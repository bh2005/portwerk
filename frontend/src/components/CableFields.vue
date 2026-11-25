<template>
  <div class="space-y-3">
    <div class="grid grid-cols-2 gap-3">
      <div><label :class="lbl">{{ $t('Kabelnummer / Label') }}</label><input v-model="f.cable_label" :class="inp" :placeholder="$t('z.B. K-EG-001')" /></div>
      <div><label :class="lbl">{{ $t('Kabeltyp') }}</label>
        <select v-model="f.cable_type" :class="inp"><option v-for="t in cableTypes" :key="t.name" :value="t.name">{{ t.name }}</option></select></div>
      <div v-if="countLabel(f.cable_type)"><label :class="lbl">{{ countLabel(f.cable_type) }}</label>
        <input v-model.number="f.fiber_count" type="number" min="1" :class="inp" placeholder="z.B. 4" /></div>
      <div><label :class="lbl">{{ $t('Länge (m)') }}</label><input v-model.number="f.length_m" type="number" min="0" step="0.5" :class="inp" placeholder="z.B. 15.5" /></div>
      <div><label :class="lbl">{{ $t('Farbe') }}</label><input v-model="f.color" :class="inp" :placeholder="$t('z.B. blau')" /></div>
      <div><label :class="lbl">{{ $t('Verlegt am') }}</label><input v-model="f.installed_at" type="date" :class="inp" /></div>
    </div>
    <div class="grid grid-cols-2 gap-3">
      <div><label :class="lbl">{{ $t('Messprotokoll (Nr. / Referenz)') }}</label><input v-model="f.measurement_ref" :class="inp" :placeholder="$t('z.B. FLUKE-2024-001')" /></div>
      <div><label :class="lbl">{{ $t('Messergebnis') }}</label>
        <select v-model="f.measurement_ok" :class="inp"><option :value="null">{{ $t('– nicht gemessen –') }}</option><option :value="true">{{ $t('✓ Bestanden') }}</option><option :value="false">{{ $t('✗ Nicht bestanden') }}</option></select></div>
    </div>
    <div><label :class="lbl">{{ $t('Notiz') }}</label><input v-model="f.note" :class="inp" :placeholder="$t('Freitext')" /></div>
    <label v-if="'provisional' in f" class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
      <input v-model="f.provisional" type="checkbox" />{{ ' ' + $t('vorläufig (Strecke noch nicht vollständig dokumentiert)') }}</label>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { cableTypes, countLabel, loadCableTypes } from '../catalog.js'
import { inp, lbl } from '../ui.js'

/** Felder eines Kabels (Label, Typ, Länge, Farbe, Messprotokoll, Notiz). ``modelValue`` ist das Formularobjekt; es wird direkt bearbeitet. */
const props = defineProps({ modelValue: { type: Object, required: true } })
const f = props.modelValue
onMounted(() => loadCableTypes())
</script>
