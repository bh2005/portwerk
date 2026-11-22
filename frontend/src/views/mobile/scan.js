/** Gescannten QR-Inhalt in einen Pfad dieser Oberfläche übersetzen (nur bekannte Ziele: Kabeletikett, Auftrag).
 *  Alles andere wird nicht geöffnet (kein Sprung auf fremde Seiten). Liefert z. B. '/q/k/K-0001' oder null. */
export function pathFromScan(text) {
  let u
  try { u = new URL(text, location.origin) } catch { return null }
  const p = u.pathname
  if (/^\/q\/[kc]\/[^/]+$/.test(p) || /^\/(m\/wo|workorders)\/\d+$/.test(p)) return p.replace(/^\/workorders\//, '/m/wo/')
  return null
}

/** Kabelnummer aus einem gescannten Etikett (nur /q/k/<Nummer>), sonst null. */
export function labelFromScan(text) {
  const p = pathFromScan(text)
  const m = p && p.match(/^\/q\/k\/(.+)$/)
  return m ? decodeURIComponent(m[1]) : null
}
