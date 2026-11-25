<template>
  <Transition name="help-slide">
    <div v-if="open" class="help-overlay" @click.self="$emit('close')">
      <aside class="help-panel" role="complementary" :aria-label="$t('Hilfe')">
        <div class="help-header">
          <span class="help-title">{{ $t('Hilfe') }}</span>
          <div class="help-header-actions">
            <router-link to="/handbuch" class="help-manual-link" @click="$emit('close')">{{ $t('Handbuch →') }}</router-link>
            <button class="help-close" @click="$emit('close')" :title="$t('Schließen (Esc)')">✕</button>
          </div>
        </div>
        <div class="help-body" v-html="content"></div>
        <div class="help-footer">{{ $t('F1 oder ? zum Öffnen/Schließen') }}</div>
      </aside>
    </div>
  </Transition>
</template>

<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { getHelp } from '../content/helpTexts.js'
import { helpContext } from '../content/helpContext.js'

const props = defineProps({ open: { type: Boolean, default: false } })
const emit  = defineEmits(['close'])

const route   = useRoute()
const content = computed(() => getHelp(route.path, helpContext.value))

function onKey(e) { if (e.key === 'Escape' && props.open) emit('close') }
onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => document.removeEventListener('keydown', onKey))
</script>

<style>
.help-overlay { position: fixed; inset: 0; z-index: 60; background: rgba(0,0,0,.3); }
.help-panel {
  position: fixed; top: 0; right: 0; bottom: 0; width: 380px; max-width: 95vw;
  background: #fff; box-shadow: -4px 0 24px rgba(0,0,0,.15);
  display: flex; flex-direction: column; overflow: hidden;
}
.help-header {
  display: flex; justify-content: space-between; align-items: center; flex-shrink: 0;
  padding: 14px 18px; border-bottom: 1px solid #e2e8f0; background: #f8fafc;
}
.help-title { font-weight: 700; font-size: 15px; color: #1e293b; }
.help-header-actions { display: flex; gap: 8px; align-items: center; }
.help-manual-link { font-size: 12px; color: #3b82f6; text-decoration: none; font-weight: 500; }
.help-manual-link:hover { text-decoration: underline; }
.help-close { background: none; border: none; cursor: pointer; font-size: 16px; color: #64748b; padding: 2px 6px; border-radius: 4px; }
.help-close:hover { background: #f1f5f9; color: #0f172a; }
.help-footer {
  padding: 10px 18px; border-top: 1px solid #e2e8f0; font-size: 11px; color: #94a3b8;
  text-align: center; background: #f8fafc; flex-shrink: 0;
}

/* Inhalt (v-html) */
.help-panel .help-body { flex: 1; overflow-y: auto; padding: 18px; font-size: 13px; line-height: 1.65; color: #334155; }
.help-body h2 { font-size: 16px; font-weight: 700; color: #1e293b; margin: 0 0 12px; }
.help-body h3 { font-size: 13px; font-weight: 700; color: #475569; margin: 14px 0 6px; text-transform: uppercase; letter-spacing: .04em; }
.help-body p  { margin: 0 0 10px; }
.help-body ul { margin: 0 0 10px; padding-left: 18px; list-style: disc; }
.help-body li { margin-bottom: 4px; }
.help-body table { width: 100%; border-collapse: collapse; margin: 0 0 10px; font-size: 12px; }
.help-body th { background: #f1f5f9; padding: 5px 8px; text-align: left; font-weight: 600; border: 1px solid #e2e8f0; }
.help-body td { padding: 5px 8px; border: 1px solid #e2e8f0; vertical-align: top; }
.help-body code { background: #f1f5f9; padding: 1px 5px; border-radius: 3px; font-size: 11.5px; font-family: ui-monospace, monospace; color: #6366f1; }
.help-body hr { border: none; border-top: 1px solid #e2e8f0; margin: 12px 0; }
.help-body .help-tip { background: #eff6ff; border-left: 3px solid #3b82f6; padding: 8px 10px; border-radius: 0 5px 5px 0; font-size: 12px; color: #1e40af; margin: 0; }

/* Dark Mode (Klasse .dark sitzt am App-Wurzelelement) */
.dark .help-panel { background: #1e293b; box-shadow: -4px 0 24px rgba(0,0,0,.5); }
.dark .help-header, .dark .help-footer { background: #0f172a; border-color: #334155; }
.dark .help-title, .dark .help-body h2 { color: #f1f5f9; }
.dark .help-panel .help-body { color: #cbd5e1; }
.dark .help-body h3 { color: #94a3b8; }
.dark .help-close { color: #94a3b8; }
.dark .help-close:hover { background: #334155; color: #f1f5f9; }
.dark .help-body th { background: #334155; border-color: #475569; color: #e2e8f0; }
.dark .help-body td { border-color: #475569; }
.dark .help-body code { background: #334155; color: #a5b4fc; }
.dark .help-body hr { border-color: #334155; }
.dark .help-body .help-tip { background: rgba(59,130,246,.12); color: #93c5fd; }

/* Einfahr-Animation */
.help-slide-enter-active, .help-slide-leave-active { transition: opacity .2s ease; }
.help-slide-enter-active .help-panel, .help-slide-leave-active .help-panel { transition: transform .22s ease; }
.help-slide-enter-from, .help-slide-leave-to { opacity: 0; }
.help-slide-enter-from .help-panel, .help-slide-leave-to .help-panel { transform: translateX(100%); }
</style>
