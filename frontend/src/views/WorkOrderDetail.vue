<template>
  <div class="max-w-5xl space-y-5" v-if="wo">
    <!-- Kopfzeile -->
    <div class="flex items-start justify-between gap-4 flex-wrap">
      <div>
        <div class="flex items-center gap-3">
          <button class="text-sm text-slate-400 hover:text-ks-600 dark:hover:text-ks-400" @click="$router.push('/workorders')">← Aufträge</button>
          <span class="font-mono font-semibold text-ks-700 dark:text-ks-400 text-lg">{{ wo.number }}</span>
          <span :class="statusClass(wo.status)" class="px-2 py-0.5 rounded-full text-xs font-medium">{{ wo.status_label }}</span>
          <span :class="prioClass(wo.priority)" class="text-xs font-medium">{{ prioLabel(wo.priority) }}</span>
        </div>
        <h1 class="text-xl font-semibold text-slate-800 dark:text-slate-100 mt-1">{{ wo.title }}</h1>
        <p v-if="wo.description" class="text-sm text-slate-500 dark:text-slate-400 mt-0.5">{{ wo.description }}</p>
      </div>
      <div class="flex gap-2 flex-wrap">
        <button v-if="canSend" :class="btnGhost" @click="sendOpen = true">Senden …</button>
        <button v-if="canAssign" :class="btnGhost" @click="openAssign">Zuweisen …</button>
        <button v-if="canEdit" :class="btnGhost" @click="openEdit">Bearbeiten</button>
        <template v-for="btn in actionButtons" :key="btn.action">
          <button :class="btn.danger ? btnDanger2 : btnPrimary" @click="doTransition(btn.action)" :disabled="transitioning">
            {{ btn.label }}
          </button>
        </template>
      </div>
    </div>

    <!-- Metadaten -->
    <div :class="card" class="p-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
      <div><span :class="metaLbl">Zugewiesen an</span><span class="text-slate-700 dark:text-slate-200">{{ wo.assigned_to ? (wo.assigned_to.full_name || wo.assigned_to.username) : '–' }}</span></div>
      <div><span :class="metaLbl">Erstellt von</span><span class="text-slate-700 dark:text-slate-200">{{ wo.created_by }}</span></div>
      <div><span :class="metaLbl">Erstellt am</span><span class="text-slate-700 dark:text-slate-200">{{ fmtTime(wo.created_at) }}</span></div>
      <div v-if="wo.planned_from"><span :class="metaLbl">Geplant von</span><span class="text-slate-700 dark:text-slate-200">{{ wo.planned_from }}</span></div>
      <div v-if="wo.planned_to"><span :class="metaLbl">Geplant bis</span><span class="text-slate-700 dark:text-slate-200">{{ wo.planned_to }}</span></div>
      <div v-if="wo.location"><span :class="metaLbl">Standort</span><span class="text-slate-700 dark:text-slate-200">{{ wo.location.name }}</span></div>
      <div v-if="wo.note"><span :class="metaLbl">Notiz</span><span class="text-slate-700 dark:text-slate-200">{{ wo.note }}</span></div>
      <div v-for="[k, l] in ACTOR_FIELDS.filter(([k]) => wo[k])" :key="k"><span :class="metaLbl">{{ l }}</span><span class="text-slate-700 dark:text-slate-200">{{ wo[k] }}</span></div>
      <div v-if="wo.four_eyes_override && wo.four_eyes_override.length" class="col-span-2 md:col-span-4">
        <span :class="metaLbl">Vier-Augen-Prinzip übersteuert</span>
        <span v-for="o in wo.four_eyes_override" :key="o" class="block text-amber-700 dark:text-amber-400">{{ o }}</span>
      </div>
    </div>

    <!-- OpenPlan -->
    <div v-if="ops.enabled && canAssign" :class="card" class="p-4 print:hidden">
      <div class="flex items-center justify-between gap-3 flex-wrap">
        <h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200">OpenPlan</h2>
        <div class="flex gap-3 items-center">
          <template v-if="wo.openplan.linked">
            <button :class="btnLink" :disabled="opBusy" @click="syncOp">Jetzt abgleichen</button>
            <button :class="btnDanger" :disabled="opBusy" @click="unlinkOp">Trennen</button>
          </template>
          <button v-else :class="btnGhost" @click="opDialog = true">Mit OpenPlan verbinden …</button>
        </div>
      </div>
      <p v-if="!wo.openplan.linked" class="text-sm text-slate-400 mt-1">Noch nicht verknüpft. Für den Auftrag kann eine Aufgabe im OpenPlan-Projektplan angelegt oder eine vorhandene verknüpft werden – Status und Fortschritt werden dann automatisch abgeglichen.</p>
      <div v-else class="mt-2 text-sm space-y-1">
        <div class="flex items-center gap-2 flex-wrap">
          <a v-if="wo.openplan.link" :href="wo.openplan.link" target="_blank" rel="noopener" class="text-ks-600 dark:text-ks-400 hover:underline">Aufgabe in OpenPlan öffnen ↗</a>
          <span class="text-slate-400">·</span>
          <span class="px-2 py-0.5 rounded-full text-xs font-medium" :class="opClass(wo.openplan.status)">{{ opLabel(wo.openplan.status) }}<template v-if="wo.openplan.percent != null"> · {{ Math.round(wo.openplan.percent) }} %</template></span>
          <span v-if="wo.openplan.synced_at" class="text-xs text-slate-400">abgeglichen {{ fmtTime(wo.openplan.synced_at) }}</span>
        </div>
        <p v-if="wo.openplan.error" class="text-xs text-red-500">Letzter Abgleich fehlgeschlagen: {{ wo.openplan.error }}</p>
      </div>
    </div>
    <OpenPlanDialog v-if="opDialog" :wo="wo" @close="opDialog = false" @done="r => { wo = r; opDialog = false; note = 'Mit OpenPlan verknüpft.' }" />

    <!-- Abhängigkeiten (Rückbau vor Einbau) -->
    <div v-if="wo.depends_on" class="rounded-lg border p-3 text-sm"
      :class="wo.depends_on.blocking ? 'border-amber-300 bg-amber-50 text-amber-900 dark:bg-amber-900/20 dark:border-amber-700 dark:text-amber-200' : 'border-green-300 bg-green-50 text-green-800 dark:bg-green-900/20 dark:border-green-700 dark:text-green-300'">
      <template v-if="wo.depends_on.blocking">⚠ Dieser Auftrag kann erst starten, wenn der Rückbau
        <router-link :to="`/workorders/${wo.depends_on.id}`" class="font-mono font-semibold underline">{{ wo.depends_on.number }}</router-link>
        bestätigt ist (aktuell: {{ wo.depends_on.status_label }}).</template>
      <template v-else>✓ Voraussetzung
        <router-link :to="`/workorders/${wo.depends_on.id}`" class="font-mono font-semibold underline">{{ wo.depends_on.number }}</router-link> ist bestätigt.</template>
    </div>
    <div v-if="wo.required_by.length" class="rounded-lg border border-slate-200 dark:border-slate-700 p-3 text-sm text-slate-600 dark:text-slate-300">
      Dieser Rückbau ist Voraussetzung für
      <router-link v-for="r in wo.required_by" :key="r.id" :to="`/workorders/${r.id}`" class="font-mono font-semibold text-ks-600 dark:text-ks-400 underline mr-2">{{ r.number }}</router-link>
      – erst nach seiner Bestätigung können diese Aufträge starten.
    </div>

    <!-- Fortschritt -->
    <div :class="card" class="p-4">
      <div class="flex gap-1 items-center flex-wrap">
        <template v-for="(step, i) in STEPS" :key="step.s">
          <div class="flex items-center gap-1">
            <span :class="[
              'px-2.5 py-1 rounded-full text-xs font-medium transition-colors',
              wo.status === step.s ? statusClass(step.s) :
              STEP_IDX[wo.status] > i ? 'bg-green-50 text-green-600 dark:bg-green-900/20 dark:text-green-400 opacity-70' :
              'bg-slate-100 text-slate-400 dark:bg-slate-700 dark:text-slate-500'
            ]">{{ step.l }}</span>
            <span v-if="i < STEPS.length-1" class="text-slate-300 dark:text-slate-600 text-xs">→</span>
          </div>
        </template>
      </div>
    </div>

    <!-- Positionen -->
    <div :class="card" class="overflow-hidden print:shadow-none">
      <div class="flex items-center justify-between px-4 py-3 border-b border-slate-100 dark:border-slate-700">
        <h2 class="text-sm font-semibold text-slate-700 dark:text-slate-200">Positionen ({{ wo.items.length }})</h2>
        <button v-if="canEditItems" :class="btnPrimary" class="text-xs px-3 py-1.5" @click="openAddItem">+ Position</button>
      </div>
      <!-- Arbeitsliste: Fortschritt, Filter, Sammelaktionen, Export -->
      <div v-if="wo.items.length" class="px-4 py-2 border-b border-slate-100 dark:border-slate-700 flex items-center gap-3 flex-wrap text-sm print:hidden">
        <span class="text-slate-500 whitespace-nowrap">{{ wo.progress.done }} / {{ wo.progress.total }} erledigt<template v-if="wo.progress.deviation"> · {{ wo.progress.deviation }} Abweichung</template></span>
        <span class="w-32 h-1.5 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden"><span class="block h-full bg-green-500" :style="{ width: (100 * wo.progress.done / Math.max(1, wo.progress.total)) + '%' }"></span></span>
        <select v-model="itemFilter" :class="inp" class="!w-32 !py-1 !text-xs"><option value="all">alle</option><option value="open">offen</option><option value="done">erledigt</option><option value="deviation">Abweichung</option></select>
        <template v-if="selectable">
          <span class="text-slate-400">|</span><span class="text-slate-500">{{ picked.size }} gewählt</span>
          <button v-if="canBulkExec" :class="btnPrimary" class="!py-1 !px-3 !text-xs" :disabled="!picked.size || saving" @click="bulk('execute')">Auswahl abhaken</button>
          <button v-if="canBulkExec" :class="btnGhost" class="!py-1 !px-3 !text-xs" :disabled="!picked.size || saving" @click="bulk('deviation')">Abweichung …</button>
          <button v-if="canBulkExec" :class="btnGhost" class="!py-1 !px-3 !text-xs" :disabled="!picked.size || saving" @click="bulk('reopen')">Zurücksetzen</button>
          <button v-if="canBulkExec" :class="btnLink" @click="pickOpen">alle offenen wählen</button>
          <button v-if="canEditItems" :class="btnDanger" :disabled="!picked.size || saving" @click="bulk('delete')">Auswahl löschen</button>
        </template>
        <span class="flex-1"></span>
        <button :class="btnLink" @click="exportList">Arbeitsliste (CSV)</button>
        <router-link :to="{ path: '/patchlist', query: { ids: String(wo.id) } }" :class="btnLink">Patchliste / Druck</router-link>
      </div>
      <p v-if="!wo.items.length" class="p-6 text-sm text-slate-400">Noch keine Positionen. Füge Verbindungen hinzu, die hergestellt oder getrennt werden sollen.</p>
      <table v-else class="w-full text-sm">
        <thead class="bg-slate-50 dark:bg-slate-700/50">
          <tr>
            <th v-if="selectable" :class="th" class="w-8"><input type="checkbox" :checked="allPicked" title="alle sichtbaren wählen" @change="pickAll" /></th>
            <th :class="th">Aktion</th>
            <th :class="th">Port A</th>
            <th :class="th">Port B</th>
            <th :class="th">Kabel</th>
            <th :class="th">Status</th>
            <th :class="th"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in shownItems" :key="item.id" class="border-t border-slate-100 dark:border-slate-700">
            <td v-if="selectable" :class="td"><input type="checkbox" :checked="picked.has(item.id)" @change="pick(item.id)" /></td>
            <td :class="td"><span :class="actionClass(item.action)" class="text-xs font-medium">{{ actionLabel(item.action) }}</span></td>
            <td :class="td" class="font-mono text-xs">
              <router-link v-if="item.wan" :to="`/wan?id=${item.wan.id}`" class="text-ks-600 dark:text-ks-400 hover:underline">WAN {{ item.wan.name }}</router-link>
              <router-link v-else-if="item.device" :to="`/devices/${item.device.id}`" class="text-ks-600 dark:text-ks-400 hover:underline">{{ item.device.hostname }}</router-link>
              <span v-else-if="item.port_a" class="text-slate-700 dark:text-slate-200">{{ item.port_a.device_hostname }}:{{ item.port_a.name }}</span>
              <span v-else class="text-slate-400">–</span>
            </td>
            <td :class="td" class="font-mono text-xs">
              <template v-if="item.wan"><span class="text-slate-500">{{ item.wan.site_b || '–' }}</span>
                <span v-if="Object.keys(item.wan_patch || {}).length" class="block text-amber-600">→ {{ patchText(item.wan_patch) }}</span></template>
              <span v-else-if="item.port_b" class="text-slate-700 dark:text-slate-200">{{ item.port_b.device_hostname }}:{{ item.port_b.name }}</span>
              <span v-else class="text-slate-400">–</span>
              <span v-if="item.old_port_b" class="text-slate-400 ml-1">(war: {{ item.old_port_b.device_hostname }}:{{ item.old_port_b.name }})</span>
            </td>
            <td :class="td" class="text-xs text-slate-500">
              <span v-if="item.cable_label" class="font-mono text-slate-700 dark:text-slate-200">{{ item.cable_label }}</span>
              <span v-if="item.cable_type !== 'other'" class="ml-1 text-slate-400">{{ item.cable_type }}</span>
              <span v-if="item.length_m" class="ml-1 text-slate-400">{{ item.length_m }}m</span>
            </td>
            <td :class="td">
              <span :class="itemStatusClass(item.item_status)" class="px-2 py-0.5 rounded-full text-xs font-medium">
                {{ itemStatusLabel(item.item_status) }}
              </span>
              <span v-if="item.deviation_note" class="ml-1 text-xs text-orange-500" :title="item.deviation_note">⚠</span>
            </td>
            <td :class="td" class="text-right whitespace-nowrap">
              <button v-if="canEditItems" :class="btnDanger" @click="deleteItem(item)" class="mr-1">Löschen</button>
              <button v-if="canExecuteItem(item)" :class="btnLink" @click="openExecItem(item)">Abhaken</button>
              <button v-if="canReopenItem(item)" :class="btnLink" @click="reopenItem(item)">Zurücksetzen</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p v-if="err" class="text-sm text-red-500">{{ err }}</p>
    <p v-if="note" class="text-sm text-green-600">{{ note }}</p>

    <SendDialog v-if="sendOpen" :title="`Auftrag ${wo.number} senden`" :workorder-id="wo.id" :submit="b => api.sendWorkorder(wo.id, b)" @close="sendOpen = false" />

    <ModalDialog v-if="assignForm" :title="`${wo.number} zuweisen`" :error="assignErr" @close="assignForm = null">
      <div><label :class="lbl">Benutzer</label>
        <select v-model="assignForm.user_id" :class="inp"><option :value="null">(niemand – Zuweisung aufheben)</option>
          <option v-for="u in assignUsers" :key="u.id" :value="u.id">{{ u.full_name || u.username }} ({{ u.username }}){{ u.has_email ? '' : ' – keine E-Mail' }}</option></select>
        <p class="text-[11px] text-slate-400 mt-1">Der Auftrag erscheint beim Benutzer unter „Meine Aufgaben“. Es werden nur Benutzer angeboten, die ihn sehen dürfen.</p></div>
      <label class="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300"><input type="checkbox" v-model="assignForm.notify" /> per E-Mail benachrichtigen</label>
      <div v-if="assignForm.notify"><label :class="lbl">Nachricht (optional)</label><textarea v-model="assignForm.message" rows="2" :class="inp"></textarea></div>
      <template #footer>
        <button :class="btnGhost" @click="assignForm = null">Abbrechen</button>
        <button :class="btnPrimary" :disabled="saving" @click="saveAssign">Speichern</button>
      </template>
    </ModalDialog>

    <!-- Dialog: Auftrag bearbeiten -->
    <Teleport to="body">
      <div v-if="editDialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" @click.self="editDialog=false">
        <div :class="card" class="w-full max-w-lg p-6 space-y-4">
          <h2 class="font-semibold text-slate-800 dark:text-slate-100">Auftrag bearbeiten</h2>
          <div><label :class="lbl">Titel *</label><input v-model="editForm.title" :class="inp" /></div>
          <div><label :class="lbl">Beschreibung</label><textarea v-model="editForm.description" :class="inp" rows="3" /></div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label :class="lbl">Priorität</label>
              <select v-model="editForm.priority" :class="inp">
                <option v-for="[v, l] in PRIO_OPTIONS" :key="v" :value="v">{{ l }}</option>
              </select>
            </div>
            <div><label :class="lbl">Von</label><input v-model="editForm.planned_from" type="date" :class="inp" /></div>
          </div>
          <div><label :class="lbl">Bis</label><input v-model="editForm.planned_to" type="date" :class="inp" /></div>
          <div><label :class="lbl">Notiz</label><textarea v-model="editForm.note" :class="inp" rows="2" /></div>
          <p v-if="dialogErr" class="text-sm text-red-500">{{ dialogErr }}</p>
          <div class="flex justify-end gap-2">
            <button :class="btnGhost" @click="editDialog=false">Abbrechen</button>
            <button :class="btnPrimary" @click="saveEdit" :disabled="saving">{{ saving ? '…' : 'Speichern' }}</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Dialog: Position hinzufügen/bearbeiten -->
    <Teleport to="body">
      <div v-if="itemDialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" @click.self="itemDialog=false">
        <div :class="card" class="w-full max-w-xl p-6 space-y-4">
          <h2 class="font-semibold text-slate-800 dark:text-slate-100">Position</h2>
          <div>
            <label :class="lbl">Aktion</label>
            <select v-model="itemForm.action" :class="inp">
              <option value="connect">Verbindung herstellen</option>
              <option value="disconnect">Verbindung trennen</option>
              <option value="move">Verbindung umstecken</option>
              <option value="install_device">Gerät einbauen (vorhandenes, geplantes Gerät)</option>
              <option value="remove_device">Gerät zurückbauen</option>
              <option value="wan_activate">WAN-Verbindung in Betrieb nehmen</option>
              <option value="wan_terminate">WAN-Verbindung kündigen</option>
            </select>
          </div>
          <div v-if="isWanAction(itemForm.action)">
            <label :class="lbl">WAN-Verbindung</label>
            <select v-model="itemForm.wan_link_id" :class="inp"><option :value="null" disabled>wählen …</option>
              <option v-for="l in wanChoices" :key="l.id" :value="l.id">{{ l.name }} · {{ l.site_a }} ↔ {{ l.site_b || '–' }} ({{ l.status_label }})</option></select>
            <p class="text-xs text-slate-400 mt-1">Der Status der Verbindung ändert sich beim Bestätigen des Auftrags. Änderungen (z. B. Bandbreite) legst du im Menü „WAN“ über „Ändern per Auftrag“ an.</p>
          </div>
          <div v-else-if="isDeviceAction(itemForm.action)">
            <label :class="lbl">Gerät</label>
            <select v-model="itemForm.device_id" :class="inp"><option :value="null" disabled>wählen …</option>
              <option v-for="d in deviceChoices" :key="d.id" :value="d.id">{{ d.hostname }} · {{ d.location_path || 'ohne Location' }} ({{ d.status }})</option></select>
            <p class="text-xs text-slate-400 mt-1">Beim Zurückbauen werden alle Kabel des Geräts getrennt, es wird „außer Betrieb“ gesetzt und seine HE wird frei.</p>
          </div>
          <div v-else class="grid grid-cols-2 gap-3">
            <div>
              <label :class="lbl">Port A (Gerät:Port-ID)</label>
              <input v-model.number="itemForm.port_a_id" type="number" :class="inp" placeholder="Port-ID" />
            </div>
            <div>
              <label :class="lbl">{{ itemForm.action === 'move' ? 'Neuer Port B' : 'Port B' }}</label>
              <input v-model.number="itemForm.port_b_id" type="number" :class="inp" placeholder="Port-ID" />
            </div>
          </div>
          <div v-if="itemForm.action === 'move'">
            <label :class="lbl">Alter Port B (bisherige Verbindung)</label>
            <input v-model.number="itemForm.old_port_b_id" type="number" :class="inp" placeholder="Port-ID" />
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div><label :class="lbl">Kabelnummer</label><input v-model="itemForm.cable_label" :class="inp" /></div>
            <div>
              <label :class="lbl">Kabeltyp</label>
              <select v-model="itemForm.cable_type" :class="inp">
                <option v-for="t in cableTypes" :key="t.name" :value="t.name">{{ t.name }}</option>
              </select>
            </div>
          </div>
          <div class="grid grid-cols-3 gap-3">
            <div><label :class="lbl">Länge (m)</label><input v-model.number="itemForm.length_m" type="number" step="0.1" :class="inp" /></div>
            <div v-if="countLabel(itemForm.cable_type)"><label :class="lbl">{{ countLabel(itemForm.cable_type) }}</label><input v-model.number="itemForm.fiber_count" type="number" :class="inp" /></div>
            <div><label :class="lbl">Farbe</label><input v-model="itemForm.color" :class="inp" /></div>
          </div>
          <div><label :class="lbl">Notiz</label><input v-model="itemForm.note" :class="inp" /></div>
          <p v-if="dialogErr" class="text-sm text-red-500">{{ dialogErr }}</p>
          <div class="flex justify-end gap-2">
            <button :class="btnGhost" @click="itemDialog=false">Abbrechen</button>
            <button :class="btnPrimary" @click="saveItem" :disabled="saving">{{ saving ? '…' : 'Speichern' }}</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Dialog: Abhaken -->
    <Teleport to="body">
      <div v-if="execDialog" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40" @click.self="execDialog=false">
        <div :class="card" class="w-full max-w-md p-6 space-y-4">
          <h2 class="font-semibold text-slate-800 dark:text-slate-100">Position abhaken</h2>
          <p class="text-sm text-slate-600 dark:text-slate-300">
            <template v-if="execItem?.wan"><span class="font-mono">{{ execItem.wan.name }}</span> {{ actionLabel(execItem.action) }}</template>
            <template v-else-if="execItem?.device"><span class="font-mono">{{ execItem.device.hostname }}</span> {{ actionLabel(execItem.action) }}</template>
            <template v-else>
              <span class="font-mono">{{ execItem?.port_a?.device_hostname }}:{{ execItem?.port_a?.name }}</span>
              {{ actionLabel(execItem?.action) }}
              <span class="font-mono">{{ execItem?.port_b?.device_hostname }}:{{ execItem?.port_b?.name }}</span>
            </template>
          </p>
          <div>
            <label :class="lbl">Ergebnis</label>
            <select v-model="execForm.item_status" :class="inp">
              <option value="done">Erledigt</option>
              <option value="deviation">Abweichung</option>
            </select>
          </div>
          <div v-if="execForm.item_status === 'deviation'">
            <label :class="lbl">Abweichungsnotiz *</label>
            <textarea v-model="execForm.deviation_note" :class="inp" rows="2" placeholder="Was war anders?" />
          </div>
          <p v-if="dialogErr" class="text-sm text-red-500">{{ dialogErr }}</p>
          <div class="flex justify-end gap-2">
            <button :class="btnGhost" @click="execDialog=false">Abbrechen</button>
            <button :class="btnPrimary" @click="saveExec" :disabled="saving">{{ saving ? '…' : 'Bestätigen' }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>

  <div v-else-if="loading" class="text-sm text-slate-400 p-8">Lade…</div>
  <div v-else class="text-sm text-red-500 p-8">{{ err }}</div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import ModalDialog from '../components/ModalDialog.vue'
import SendDialog from '../components/SendDialog.vue'
import OpenPlanDialog from '../components/OpenPlanDialog.vue'
import { api, errText, conflictOf, hasRole, isAdmin } from '../api.js'
import { card, inp, lbl, th, td, btnPrimary, btnGhost, btnDanger, btnLink, fmtTime } from '../ui.js'
import { cableTypes, countLabel, loadCableTypes } from '../catalog.js'

const route = useRoute()
const wo = ref(null), loading = ref(true), err = ref(''), transitioning = ref(false), saving = ref(false)
const editDialog = ref(false), itemDialog = ref(false), execDialog = ref(false)
const dialogErr = ref('')
const editForm = ref({})
const itemForm = ref({})
const execForm = ref({ item_status: 'done', deviation_note: '' })
const execItem = ref(null)
const editingItemId = ref(null)

const STEPS = [
  {s:'draft',l:'Entwurf'},{s:'submitted',l:'Eingereicht'},{s:'approved',l:'Freigegeben'},
  {s:'in_progress',l:'In Ausführung'},{s:'done',l:'Ausgeführt'},{s:'confirmed',l:'Bestätigt'},
]
const STEP_IDX = Object.fromEntries(STEPS.map((s, i) => [s.s, i]))
const PRIO_OPTIONS = [['low','Niedrig'],['normal','Normal'],['high','Hoch'],['critical','Kritisch']]
const metaLbl = 'block text-xs text-slate-400 uppercase tracking-wide mb-0.5'
const btnDanger2 = 'bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors shadow-sm'

const ACTION_BUTTONS = {
  draft:       [{action:'submit',   label:'Einreichen',       roles:['planer']}],
  submitted:   [{action:'approve',  label:'Freigeben',        roles:['freigeber']},
                {action:'reject',   label:'Ablehnen',         danger:true, roles:['freigeber']}],
  approved:    [{action:'start',    label:'Ausführung starten', roles:['techniker']}],
  in_progress: [{action:'finish',   label:'Ausführung abschließen', roles:['techniker']}],
  done:        [{action:'confirm',  label:'Bestätigen & anwenden', roles:['freigeber']},
                {action:'rework',   label:'Nacharbeit', danger:true, roles:['freigeber']}],
  rework:      [{action:'start',    label:'Ausführung starten', roles:['techniker']}],
}

const actionButtons = computed(() => {
  if (!wo.value) return []
  return (ACTION_BUTTONS[wo.value.status] || []).filter(b =>
    isAdmin() || hasRole(...b.roles)
  )
})
const canEdit = computed(() => wo.value && ['draft','rework'].includes(wo.value.status) && (isAdmin() || hasRole('planer')))
const canEditItems = computed(() => wo.value && ['draft','rework'].includes(wo.value.status) && (isAdmin() || hasRole('planer')))
const canExecuteItem = item => wo.value?.status === 'in_progress' && item.item_status === 'open' && (isAdmin() || hasRole('techniker'))
const canReopenItem = item => wo.value?.status === 'in_progress' && item.item_status !== 'open' && (isAdmin() || hasRole('techniker'))

const statusClass = s => ({
  draft:'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300',
  submitted:'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  approved:'bg-cyan-100 text-cyan-700 dark:bg-cyan-900/40 dark:text-cyan-300',
  rejected:'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  in_progress:'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  done:'bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300',
  confirmed:'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300',
  rework:'bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300',
}[s] || 'bg-slate-100 text-slate-500')

const prioClass = p => ({ low:'text-slate-400', normal:'text-slate-600 dark:text-slate-300',
  high:'text-amber-600 dark:text-amber-400', critical:'text-red-600 dark:text-red-400 font-semibold' }[p] || '')
const prioLabel = p => ({ low:'Niedrig', normal:'Normal', high:'Hoch', critical:'Kritisch' }[p] || p)
const actionLabel = a => ({ connect:'→ herstellen', disconnect:'✕ trennen', move:'↔ umstecken', install_device:'＋ Gerät einbauen', remove_device:'✕ Gerät zurückbauen',
  wan_activate:'🌐 WAN in Betrieb nehmen', wan_change:'🌐 WAN ändern', wan_terminate:'🌐 WAN kündigen' }[a] || a)
const WAN_LABELS = { name: 'Name', technology: 'Technik', provider: 'Provider', circuit_id: 'Leitungs-ID', bandwidth_down: 'Down Mbit/s', bandwidth_up: 'Up Mbit/s',
  contract_number: 'Vertrag', contract_start: 'Vertragsbeginn', contract_end: 'Vertragsende', notice_days: 'Kündigungsfrist (Tage)', monthly_cost: 'Kosten/Monat',
  contact: 'Kontakt', note: 'Notiz', remote_label: 'Gegenstelle', site_b_id: 'Standort B', port_a_id: 'Port A', port_b_id: 'Port B' }
const patchText = p => Object.entries(p).map(([k, v]) => `${WAN_LABELS[k] || k}: ${v ?? '–'}`).join(', ')
const actionClass = a => ({ connect:'text-green-700 dark:text-green-400', disconnect:'text-red-600 dark:text-red-400',
  move:'text-blue-600 dark:text-blue-400', install_device:'text-green-700 dark:text-green-400', remove_device:'text-red-600 dark:text-red-400',
  wan_activate:'text-green-700 dark:text-green-400', wan_change:'text-blue-600 dark:text-blue-400', wan_terminate:'text-red-600 dark:text-red-400' }[a] || '')
const isWanAction = a => a.startsWith('wan_')
const wanChoices = ref([])
const isDeviceAction = a => a === 'install_device' || a === 'remove_device'
const deviceChoices = ref([])
const ops = ref({ enabled: false }), opDialog = ref(false), opBusy = ref(false)
const OP_LABELS = { open: 'offen', in_progress: 'in Arbeit', blocked: 'blockiert', done: 'erledigt' }
const opLabel = s => OP_LABELS[s] || s || 'noch nicht abgeglichen'
const opClass = s => ({ open: 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300', in_progress: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  blocked: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300', done: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300' }[s] || 'bg-slate-100 text-slate-500')
async function syncOp() {
  opBusy.value = true; err.value = ''
  try { const r = await api.openplanSync(wo.value.id); wo.value = r; note.value = r.sync?.synced ? 'Mit OpenPlan abgeglichen.' : '' ; if (r.sync && !r.sync.synced) err.value = r.sync.error || 'Abgleich fehlgeschlagen' }
  catch (e) { err.value = errText(e) } finally { opBusy.value = false }
}
async function unlinkOp() {
  if (!confirm('Verknüpfung mit OpenPlan aufheben? Die Aufgabe in OpenPlan bleibt bestehen.')) return
  opBusy.value = true
  try { wo.value = await api.openplanUnlink(wo.value.id); note.value = 'Verknüpfung aufgehoben.' } catch (e) { err.value = errText(e) } finally { opBusy.value = false }
}
const sendOpen = ref(false), assignForm = ref(null), assignUsers = ref([]), assignErr = ref(''), note = ref('')
const canSend = hasRole('planer', 'freigeber', 'techniker')
const canAssign = hasRole('planer', 'freigeber')
async function openAssign() {
  assignErr.value = ''
  try { assignUsers.value = await api.directoryUsers(wo.value.id) } catch (e) { err.value = errText(e); return }
  assignForm.value = { user_id: wo.value.assigned_to?.id ?? null, notify: true, message: '' }
}
async function saveAssign() {
  saving.value = true; assignErr.value = ''
  try {
    const r = await api.assignWorkorder(wo.value.id, assignForm.value)
    wo.value = r; assignForm.value = null
    note.value = r.notified ? 'Zugewiesen und per E-Mail benachrichtigt.' : (r.notify_note || (r.assigned_to ? 'Zugewiesen.' : 'Zuweisung aufgehoben.'))
  } catch (e) { assignErr.value = errText(e) } finally { saving.value = false }
}
const itemFilter = ref('all'), picked = ref(new Set())
const canBulkExec = computed(() => wo.value?.status === 'in_progress' && (isAdmin() || hasRole('techniker')))
const selectable = computed(() => canBulkExec.value || canEditItems.value)
const shownItems = computed(() => (wo.value?.items || []).filter(i => itemFilter.value === 'all' || i.item_status === itemFilter.value))
const allPicked = computed(() => !!shownItems.value.length && shownItems.value.every(i => picked.value.has(i.id)))
function pick(id) { const s = new Set(picked.value); s.has(id) ? s.delete(id) : s.add(id); picked.value = s }
function pickAll() { picked.value = allPicked.value ? new Set() : new Set(shownItems.value.map(i => i.id)) }
function pickOpen() { picked.value = new Set((wo.value.items || []).filter(i => i.item_status === 'open').map(i => i.id)) }
async function bulk(kind) {
  if (!picked.value.size) return
  let body = { ids: [...picked.value] }
  if (kind === 'delete') { if (!confirm(`${picked.value.size} Position(en) löschen?`)) return; body.action = 'delete' }
  else if (kind === 'reopen') body.action = 'reopen'
  else if (kind === 'deviation') {
    const n = prompt('Abweichung – was war anders?'); if (!n || !n.trim()) return
    Object.assign(body, { action: 'execute', item_status: 'deviation', deviation_note: n.trim() })
  } else Object.assign(body, { action: 'execute', item_status: 'done' })
  saving.value = true
  try { wo.value = await api.bulkItems(wo.value.id, body); picked.value = new Set(); err.value = '' } catch (e) { err.value = errText(e) } finally { saving.value = false }
}
async function exportList() {
  try {
    const blob = await api.exportWorkorder(wo.value.id)
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `${wo.value.number}-arbeitsliste.csv`; a.click(); URL.revokeObjectURL(a.href)
  } catch (e) { err.value = errText(e) }
}
const itemStatusLabel = s => ({ open:'offen', done:'erledigt', deviation:'Abweichung' }[s] || s)
const itemStatusClass = s => ({ open:'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400',
  done:'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  deviation:'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400' }[s] || '')

async function load() {
  try {
    wo.value = await api.workorder(route.params.id)
    err.value = ''
  } catch (e) { err.value = errText(e) }
  finally { loading.value = false }
}

const ACTOR_FIELDS = [['submitted_by', 'Eingereicht von'], ['approved_by', 'Freigegeben von'], ['finished_by', 'Ausgeführt von'], ['confirmed_by', 'Bestätigt von']]

async function doTransition(action, overrideReason) {
  transitioning.value = true
  try {
    wo.value = await api.workorderTransition(wo.value.id, action, overrideReason)
    err.value = ''
  } catch (e) {
    const d = e?.response?.data?.detail
    if (e?.response?.status === 409 && d?.code === 'four_eyes' && d.can_override && !overrideReason) {
      const reason = prompt(`${d.message}\n\nBegründung für die Ausnahme (wird im Audit-Log und am Auftrag vermerkt):`)
      transitioning.value = false
      if (reason && reason.trim()) return doTransition(action, reason.trim())
      err.value = d.message
      return
    }
    err.value = errText(e)
  }
  finally { transitioning.value = false }
}

function openEdit() {
  editForm.value = { ...wo.value, location_id: wo.value.location?.id }
  dialogErr.value = ''
  editDialog.value = true
}

async function saveEdit() {
  if (!editForm.value.title.trim()) { dialogErr.value = 'Titel ist erforderlich'; return }
  saving.value = true
  try {
    wo.value = await api.updateWorkorder(wo.value.id, editForm.value)
    editDialog.value = false
  } catch (e) { dialogErr.value = errText(e) }
  finally { saving.value = false }
}

function openAddItem() {
  editingItemId.value = null
  api.wanLinks().then(l => { wanChoices.value = l.filter(x => x.status !== 'terminated') }).catch(() => {})
  itemForm.value = { action:'connect', device_id: null, wan_link_id: null, remove_old: false, port_a_id: null, port_b_id: null, old_port_b_id: null,
    cable_label:'', cable_type:'Cat6', fiber_count: null, length_m: null, color:'', note:'', idx: wo.value.items.length }
  dialogErr.value = ''
  itemDialog.value = true
}

async function saveItem() {
  saving.value = true
  try {
    if (editingItemId.value) {
      const updated = await api.updateWorkitem(wo.value.id, editingItemId.value, itemForm.value)
      const idx = wo.value.items.findIndex(i => i.id === editingItemId.value)
      if (idx >= 0) wo.value.items[idx] = updated
    } else {
      const item = await api.addWorkitem(wo.value.id, itemForm.value)
      wo.value.items.push(item)
    }
    itemDialog.value = false
  } catch (e) {
    const c = conflictOf(e)
    if (c && !itemForm.value.remove_old && confirm(`${c.message}`)) {          // „Alten Patch zurückbauen?“ -> Ja: Rückbau-Auftrag wird automatisch angelegt
      itemForm.value.remove_old = true
      saving.value = false
      return saveItem().then(() => load())
    }
    dialogErr.value = errText(e)
  }
  finally { saving.value = false }
}

async function deleteItem(item) {
  if (!confirm(`Position löschen?`)) return
  try {
    await api.deleteWorkitem(wo.value.id, item.id)
    wo.value.items = wo.value.items.filter(i => i.id !== item.id)
  } catch (e) { err.value = errText(e) }
}

function openExecItem(item) {
  execItem.value = item
  execForm.value = { item_status: 'done', deviation_note: '' }
  dialogErr.value = ''
  execDialog.value = true
}

async function saveExec() {
  if (execForm.value.item_status === 'deviation' && !execForm.value.deviation_note.trim()) {
    dialogErr.value = 'Bitte Abweichungsnotiz eingeben'; return
  }
  saving.value = true
  try {
    const updated = await api.executeWorkitem(wo.value.id, execItem.value.id, execForm.value)
    const idx = wo.value.items.findIndex(i => i.id === execItem.value.id)
    if (idx >= 0) wo.value.items[idx] = updated
    execDialog.value = false
  } catch (e) { dialogErr.value = errText(e) }
  finally { saving.value = false }
}

async function reopenItem(item) {
  try {
    const updated = await api.reopenWorkitem(wo.value.id, item.id)
    const idx = wo.value.items.findIndex(i => i.id === item.id)
    if (idx >= 0) wo.value.items[idx] = updated
  } catch (e) { err.value = errText(e) }
}

async function loadDevices() {
  try { deviceChoices.value = (await api.devices({ limit: 1000 })).items.filter(d => d.status !== 'retired') } catch {}
}
onMounted(() => { loadCableTypes(); load(); loadDevices(); api.openplanStatus().then(s => { ops.value = s }).catch(() => {}) })
</script>
