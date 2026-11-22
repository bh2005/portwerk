<template>
  <div v-if="open" class="fixed inset-0 z-50 bg-black flex flex-col">
    <video ref="video" class="flex-1 w-full object-cover" playsinline muted></video>
    <div class="absolute inset-x-0 top-1/2 -translate-y-1/2 mx-auto w-64 h-64 border-4 border-white/80 rounded-2xl pointer-events-none"></div>
    <p class="absolute top-4 inset-x-0 text-center text-white text-sm px-4">{{ error || 'Kabeletikett in den Rahmen halten …' }}</p>
    <button class="absolute bottom-6 left-1/2 -translate-x-1/2 bg-white text-slate-900 font-semibold text-lg px-8 py-3 rounded-full" @click="close">Abbrechen</button>
  </div>
</template>

<script setup>
/** QR-Scanner über die Kamera (BarcodeDetector – Chrome/Edge auf Android). Nur in sicherem Kontext (HTTPS oder localhost).
 *  Wo es das nicht gibt (z. B. iPhone), scannt die Kamera-App den Code und öffnet die Adresse direkt. */
import { nextTick, onBeforeUnmount, ref } from 'vue'

const emit = defineEmits(['result'])
const open = ref(false), error = ref(''), video = ref(null)
let stream = null, timer = null

const supported = typeof window !== 'undefined' && window.isSecureContext && 'BarcodeDetector' in window && !!navigator.mediaDevices?.getUserMedia
defineExpose({ supported, start })

async function start() {
  error.value = ''; open.value = true
  await nextTick()
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false })
    video.value.srcObject = stream
    await video.value.play()
    const detector = new window.BarcodeDetector({ formats: ['qr_code'] })
    timer = setInterval(async () => {
      try {
        const codes = await detector.detect(video.value)
        if (codes.length) { const v = codes[0].rawValue; close(); emit('result', v) }
      } catch { /* nächster Versuch */ }
    }, 250)
  } catch (e) { error.value = 'Kamera nicht verfügbar: ' + (e?.message || e) }
}
function close() {
  clearInterval(timer); timer = null
  stream?.getTracks().forEach(t => t.stop()); stream = null
  open.value = false
}
onBeforeUnmount(close)
</script>
