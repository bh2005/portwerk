<template>
  <div class="max-w-4xl flex gap-8">
    <nav class="hidden md:block w-44 flex-shrink-0 sticky top-0 self-start text-sm">
      <h2 class="text-xs font-semibold uppercase tracking-wide text-slate-400 mb-2">{{ $t('Inhalt') }}</h2>
      <a v-for="s in sections" :key="s.id" :href="`#${s.id}`" @click.prevent="jump(s.id)"
        class="block py-1 text-slate-600 dark:text-slate-300 hover:text-ks-600 dark:hover:text-ks-400">{{ s.title }}</a>
    </nav>
    <div class="flex-1 min-w-0 space-y-6">
      <h1 class="text-lg font-semibold text-slate-800 dark:text-slate-100">{{ $t('Handbuch') }}</h1>
      <p v-if="lang === 'en'" class="text-sm rounded-lg px-3 py-2 bg-amber-50 text-amber-800 dark:bg-amber-900/30 dark:text-amber-200">The manual is currently only available in German.</p>
      <section v-for="s in sections" :id="s.id" :key="s.id" :class="card" class="p-5">
        <h2 class="text-base font-semibold text-slate-800 dark:text-slate-100 mb-2">{{ s.title }}</h2>
        <div class="manual" v-html="s.html"></div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { lang } from '../i18n.js'
import { sections } from '../content/helpContent.js'
import { card } from '../ui.js'

function jump(id) { document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
</script>

<style>
.manual { font-size: 14px; line-height: 1.65; color: #334155; }
.manual p { margin: 0 0 10px; }
.manual h3 { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: #64748b; margin: 14px 0 6px; }
.manual ul { list-style: disc; padding-left: 20px; margin: 0 0 10px; }
.manual ol { list-style: decimal; padding-left: 20px; margin: 0 0 10px; }
.manual li { margin-bottom: 4px; }
.manual table { border-collapse: collapse; margin: 0 0 10px; font-size: 13px; }
.manual th, .manual td { border: 1px solid #e2e8f0; padding: 5px 10px; text-align: left; }
.manual th { background: #f1f5f9; }
.manual code { background: #f1f5f9; padding: 1px 5px; border-radius: 3px; font-size: 12px; font-family: ui-monospace, monospace; color: #6366f1; }
.dark .manual { color: #cbd5e1; }
.dark .manual h3 { color: #94a3b8; }
.dark .manual th, .dark .manual td { border-color: #475569; }
.dark .manual th { background: #334155; }
.dark .manual code { background: #334155; color: #a5b4fc; }
</style>
