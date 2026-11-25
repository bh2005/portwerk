<template>
  <div class="space-y-4">
    <div class="print:hidden space-y-4">
      <div class="flex items-center justify-between gap-3 flex-wrap">
        <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">{{ $t('Kabeletiketten') + ' ' }}<span class="text-sm font-normal text-slate-400">{{ source }}</span></h1>
        <div class="flex gap-2">
          <button :class="btnGhost" @click="$router.back()">{{ $t('Zurück') }}</button>
          <button :class="btnPrimary" :disabled="!sheets.length" @click="print">{{ $t('Drucken') }}</button>
        </div>
      </div>
      <p v-if="err" class="text-sm text-red-500 dark:text-red-400">{{ err }}</p>

      <div :class="card" class="p-4 grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
        <div class="md:col-span-2"><label :class="lbl">{{ $t('Format') }}</label>
          <select v-model="fmtKey" :class="inp"><option v-for="(f, k) in FORMATS" :key="k" :value="k">{{ f.name }}</option></select></div>
        <div v-if="fmt.sheet"><label :class="lbl">{{ $t('Startposition auf dem Bogen') }}</label>
          <input v-model.number="skip" type="number" min="1" :max="fmt.cols * fmt.rows" :class="inp" /></div>
        <label class="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200"><input v-model="perEnd" type="checkbox" />{{ ' ' + $t('je Kabelende ein Etikett') }}</label>
        <p class="md:col-span-4 text-xs text-slate-400">
          {{ $t('{n} Etiketten', { n: labels.length }) }}<span v-if="missing"> · {{ $t('{n} Position(en) ohne Kabelnummer – ohne QR-Code (Nummer im Auftrag vergeben)', { n: missing }) }}</span>{{ $t('. Beim Drucken „Tatsächliche Größe“ bzw. Skalierung 100 % und keine Ränder wählen. Der QR-Code führt nach dem Scannen zu dieser Portwerk-Instanz ({base}).', { base }) }}
        </p>
      </div>
    </div>

    <p v-if="!loading && !labels.length" class="text-sm text-slate-400 print:hidden">{{ $t('Keine Kabel für Etiketten gefunden.') }}</p>

    <div class="label-preview" :style="{ '--zoom': fmt.sheet ? 0.6 : 1.6 }">
      <div v-for="(page, pi) in sheets" :key="pi" class="label-page" :style="pageStyle">
        <div v-for="(l, i) in page" :key="i" class="label" :style="labelStyle">
          <template v-if="l">
            <div v-if="l.qr_svg" class="label-qr" :style="qrStyle" v-html="l.qr_svg"></div>
            <div class="label-text">
              <div class="label-nr" :style="{ fontSize: fit(l.cable_label || '—', 0.24, 5, 0.62) }">{{ l.cable_label || '—' }}</div>
              <div class="label-line" :style="{ fontSize: fit(lineOf(l), 0.14, 3.4) }"><b>{{ l.here.hostname }}</b> {{ l.here.port }}</div>
              <div class="label-line" :style="{ fontSize: fit(lineOf(l), 0.14, 3.4) }">→ <b>{{ l.there.hostname }}</b> {{ l.there.port }}</div>
              <div v-if="fmt.h >= 19 && l.meta" class="label-line label-meta" :style="{ fontSize: fit(l.meta, 0.1, 2.4) }">{{ l.meta }}</div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { t } from '../i18n.js'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api, errText } from '../api.js'
import { inp, lbl, card, btnPrimary, btnGhost } from '../ui.js'

// Maße in mm. Bandetiketten: eine Seite je Etikett; Bögen: Raster auf A4.
const FORMATS = {
  tape24: { name: 'Band 24 mm (z. B. Brother P-touch), 70 mm lang', w: 70, h: 24 },
  tape12: { name: 'Band 12 mm (z. B. Brother P-touch), 60 mm lang', w: 60, h: 12 },
  dymo19: { name: 'Band 19 mm (z. B. Dymo), 64 mm lang', w: 64, h: 19 },
  a4_48:  { name: 'A4-Bogen 48,5 × 25,4 mm, 4 × 10 (z. B. Zweckform 3657)', w: 48.5, h: 25.4, qr: 16, sheet: true, cols: 4, rows: 10, top: 21.5, left: 8 },
  a4_70:  { name: 'A4-Bogen 70 × 37 mm, 3 × 8 (z. B. Zweckform 3474)', w: 70, h: 37, sheet: true, cols: 3, rows: 8, top: 0.5, left: 0 },
}
const KEY = 'portwerk_label_format'

const route = useRoute()
const raw = ref([]), err = ref(''), loading = ref(true)
const fmtKey = ref(localStorage.getItem(KEY) in FORMATS ? localStorage.getItem(KEY) : 'tape24')
const perEnd = ref(true), skip = ref(1)
const fmt = computed(() => FORMATS[fmtKey.value])
const base = location.origin
const source = computed(() => route.query.workorder ? t('aus Patchauftrag') : route.query.device ? t('eines Geräts') : '')
watch(fmtKey, k => { localStorage.setItem(KEY, k); skip.value = 1 })

const meta = l => [l.cable_type !== 'other' ? l.cable_type : '', l.length_m ? `${l.length_m} m` : '', l.color].filter(Boolean).join(' · ')
const labels = computed(() => raw.value.flatMap(l => {
  const one = { ...l, here: l.a, there: l.b, meta: meta(l) }
  return perEnd.value ? [one, { ...l, here: l.b, there: l.a, meta: meta(l) }] : [one]
}))
const missing = computed(() => raw.value.filter(l => !l.qr_svg).length)

const sheets = computed(() => {
  if (!labels.value.length) return []
  if (!fmt.value.sheet) return labels.value.map(l => [l])
  const per = fmt.value.cols * fmt.value.rows
  const list = [...Array(Math.min(Math.max(skip.value || 1, 1), per) - 1).fill(null), ...labels.value]
  const pages = []
  for (let i = 0; i < list.length; i += per) pages.push(list.slice(i, i + per))
  return pages
})

const mm = v => `${v}mm`
const pad = computed(() => Math.max(1, fmt.value.h * 0.08))
const qrSize = computed(() => fmt.value.qr || fmt.value.h - 2 * pad.value)       // QR-Kantenlänge (schmale Formate: kleiner, mehr Platz für Text)
const textWidth = computed(() => fmt.value.w - qrSize.value - 3 * pad.value)       // Etikett minus QR-Code und Abstände
const lineOf = l => {                                                              // längere der beiden Endpunkt-Zeilen bestimmt die Größe
  const t = e => `${e.hostname} ${e.port}`
  return `→ ${t(l.here).length >= t(l.there).length ? t(l.here) : t(l.there)}`
}
/** Schriftgröße in mm: höchstens Anteil der Etikettenhöhe bzw. ``max``, sonst so klein, dass der Text in die Breite passt (≥ 1,5 mm). */
const fit = (text, ofHeight, max, charWidth = 0.56) =>
  mm(Math.max(1.5, Math.min(fmt.value.h * ofHeight, max, textWidth.value / (Math.max(text.length, 4) * charWidth))).toFixed(2))
const qrStyle = computed(() => ({ width: mm(qrSize.value), height: mm(qrSize.value) }))
const pageStyle = computed(() => fmt.value.sheet
  ? { width: '210mm', height: '297mm', paddingTop: mm(fmt.value.top), paddingLeft: mm(fmt.value.left), display: 'grid',
      gridTemplateColumns: `repeat(${fmt.value.cols}, ${fmt.value.w}mm)`, gridAutoRows: mm(fmt.value.h), alignContent: 'start' }
  : { width: mm(fmt.value.w), height: mm(fmt.value.h) })
const labelStyle = computed(() => ({ width: mm(fmt.value.w), height: mm(fmt.value.h), padding: mm(pad.value), gap: mm(pad.value) }))

// Seitengröße für den Druck: als eigenes <style>, weil @page nicht per Inline-Stil geht
let pageCss
function applyPageCss() {
  if (!pageCss) { pageCss = document.createElement('style'); document.head.appendChild(pageCss) }
  pageCss.textContent = fmt.value.sheet ? '@page { size: A4; margin: 0 }' : `@page { size: ${fmt.value.w}mm ${fmt.value.h}mm; margin: 0 }`
}
watch(fmtKey, applyPageCss)
const print = () => { applyPageCss(); window.print() }

async function load() {
  loading.value = true
  try {
    const q = route.query, params = { base }
    if (q.workorder) params.workorder_id = q.workorder
    if (q.device) params.device_id = q.device
    if (q.cables) params.cable_ids = String(q.cables).split(',').filter(Boolean)
    raw.value = await api.labels(params)
    err.value = ''
  } catch (e) { err.value = errText(e) } finally { loading.value = false }
}

onMounted(() => { applyPageCss(); load() })
onBeforeUnmount(() => pageCss?.remove())
</script>

<style scoped>
.label-page { box-sizing: border-box; background: white; color: black; overflow: hidden; }
.label { box-sizing: border-box; display: flex; align-items: center; overflow: hidden; background: white; color: black;
         font-family: ui-sans-serif, system-ui, sans-serif; line-height: 1.15; }
.label-qr { flex: none; }
.label-qr :deep(svg) { width: 100%; height: 100%; display: block; }
.label-text { min-width: 0; flex: 1; }
.label-nr { font-weight: 700; font-family: ui-monospace, monospace; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.label-line { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.label-meta { color: #444; }
@media screen {
  .label-preview { display: flex; flex-wrap: wrap; gap: 12px; zoom: var(--zoom); }
  .label-page { outline: 1px solid #cbd5e1; }
  .label-page .label { outline: 1px dashed #e2e8f0; }
}
@media print {
  :global(html), :global(body) { background: white !important; margin: 0 !important; padding: 0 !important; }
  .label-preview { margin: 0 !important; }
  .label-page { break-after: page; }
  .label-page:last-child { break-after: auto; }
}
</style>
