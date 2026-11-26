// Manual (English): sections with heading and HTML content (page /handbuch). Same ids as helpContent.js.
export const sectionsEn = [
  { id: 'einstieg', title: 'Getting started', html: `
<p>Portwerk manages the inventory for the cabling: sites, rooms and racks, devices with ports as well as patch panels and outlets. The focus is on <b>planning</b>: changes to the cabling run as orders (plan → approve → carry out → confirm), and the target/actual comparison checks the documentation against LLDP/CDP.</p>
<h3>Typical start</h3>
<ol><li>Under <b>Sites</b>, create sites, buildings, rooms and racks – or let the import create them.</li>
<li>Under <b>Import</b>, read in devices and ports from CSV, JSON or Checkmk.</li>
<li>Under <b>Racks</b>, check the occupancy; under <b>Devices</b>, maintain details and ports.</li>
<li>Plan changes to the cabling as <b>patch orders</b>.</li></ol>` },

  { id: 'bedienung', title: 'Using Portwerk', html: `
<ul><li><b>Help:</b> F1 or ? opens the help for the current page. The question-mark icon next to fields shows a short tip.</li>
<li><b>Dark mode</b> and <b>profile</b> (change password, language, notifications) are at the bottom of the sidebar.</li>
<li>The sidebar can be collapsed via the menu icon.</li>
<li><b>Language:</b> German or English, per user under “My profile → Personal settings”; before logging in via the switch on the login page. Notifications are sent in the recipient’s language; PDFs and CSV lists are created in the language of whoever downloads or sends them.</li>
<li><b>Changes by others:</b> if someone else changes data (or an API token, e.g. the Checkmk import), the notice “… changed data” appears at the top. <b>Reload</b> shows the current state, <b>Hide</b> remembers it until the next change. Nothing is overwritten and no form is changed; only the overview reloads by itself. Your own changes do not trigger a notice.</li></ul>` },

  { id: 'standorte', title: 'Sites and racks', html: `
<p>The structure is hierarchical: <b>site → building → floor → room → rack</b>. Each level is a “location”. Racks have a height in rack units (U).</p>
<p>Sites and locations can only be deleted when they are empty. When importing, a path like <code>SITE-A/Building 1/Room 2/Rack 3</code> is enough; missing levels are created. If only a site code is given, the device ends up in the location “Allgemein” (general).</p>` },

  { id: 'geraete', title: 'Devices and ports', html: `
<p>Device types: switch, router, firewall, access point, server, patch panel, outlet, end device, other (plus industrial and rack accessory types). The status is <i>planned</i>, <i>active</i> or <i>retired</i>.</p>
<ul><li><b>Rack position and height</b> are only possible in a rack. Overlaps and exceeding the rack height are rejected.</li>
<li><b>Ports</b> can be created individually or in bulk (prefix, start, count).</li>
<li><b>Patch panels:</b> each port can be linked to a counterpart (pass-through).</li>
<li><b>Path:</b> “Path” in the port row (or “Show whole path” after scanning a label) shows the complete route as a graphic – switch, patch panels (front ◂ / rear ▸), outlet, end device – with cable number, type, length and colour, location and U, planned changes and reservations. Open ends (e.g. a patch panel without a recorded counterpart) are marked; on end-to-end paths the LLDP/CDP check shows whether the ends really see each other.</li>
<li><b>Mobile technician view</b> (<code>/m</code>, on the phone also via “Mobile view for ticking off” in the order or the QR code of the PDF work instruction): approved and running orders, items by location with rack unit, large “Done”/“Deviation” buttons, start and report finished. “Scan” (Android/Chrome, HTTPS only) jumps to the item with the scanned cable number; on the iPhone use the camera app – the label opens the cable page with “Tick off in the order”.</li>
<li><b>Port reservations:</b> on the device page tick ports → “Reserve” (purpose, optional deadline). Reserved ports and ports that another open order already wants to connect (“planned”) do not count as free in the wizards; anyone using them anyway is asked first – the reservation is released in that case (audit log). A reservation for a specific order is no conflict there and ends when that order is confirmed. Overview under <b>Reservations</b>.</li>
<li><b>My profile</b> (person icon at the bottom of the sidebar): email notifications on/off individually – assignment, status changes of own orders (approved, rejected, rework, confirmed), LLDP deviation for own execution, expiry of own reservations (3 days before), suggested for confirmation (approvers). Also language, default site (pre-fills filters), start page after login and “Log out all others” (e.g. after losing a device). Under <b>Absence and deputy</b> you enter periods with a deputy: your notifications then go to the deputy (if they are entitled – for confirmation suggestions they must be an approver at the site), and they see your orders under “My tasks”. Assignments stay with you; administrators can also enter absences for others. If the OpenPlan sync is enabled, absences entered there appear automatically (note “from OpenPlan”, can only be changed there); your <b>default deputy</b> applies to them. Everything applies on all devices; email sending as a whole is controlled by the administration.</li>
<li><b>Devices from OpenPlan:</b> Devices → “From OpenPlan …” (if the OpenPlan integration is active). Choose a project: Portwerk lists the device tasks of the rollout and maps site (location code or name), location (rack from “Rack / U”, otherwise room), type and catalogue model. Selected devices are created as <b>planned</b> – with ports from the catalogue model and at the rack unit if it is free; if the location is missing, you choose it in the list. An existing device with the same name is only linked. In OpenPlan the task receives the reference “portwerk” to the device; fetching again shows what has already been imported. Allowed for: planners at the site and site administrators.</li>
<li><b>Workplace wizard:</b> on the device page of an outlet “Workplace” (or Patch orders → “+ Workplace”). Portwerk traces the path to the patch panel port where the patch cable is missing, suggests a free switch port (first in the same rack, then nearby, then at the site; not reserved, not planned), takes over profile/VLAN and creates a patch order from it – optionally with the connection of the end device. If the outlet is already connected to the switch, only “Reconfigure port” is created.</li>
<li><b>VLAN / port profile:</b> documentation only – Portwerk does not configure switches. Under <b>VLANs &amp; profiles</b> maintain the VLAN catalogue (per site or for all) and port profiles (e.g. “Office PC”: access 10 + voice 30, “Access point”: trunk). On the port, the device page shows the configuration (“VLAN” in the port row, with history). In the process: order action <b>Reconfigure port</b> or a target configuration for “connect/re-plug” (applies to the switch end by default); it appears in the work instruction, CSV and mobile view and is documented on the port when confirming.</li>
<li><b>VLAN target/actual (Checkmk):</b> Target/actual → tab “VLANs (Checkmk)” compares the documented VLAN configuration with the VLANs from the Checkmk inventory. Checkmk only supplies them for Cisco and only as access VLANs; it does not report trunks and voice VLANs (a documented trunk without a report therefore counts as “plausible”). VLANs reported but not documented can be entered into the documentation with “Adopt actual” – useful for the initial fill.</li>
<li><b>LLDP check of carried-out orders:</b> after every Checkmk import (and with “Check now”) Portwerk compares each ticked-off item with the LLDP/CDP neighbours: for “connect” the path is traced across patch panels to the active devices – does one end see the other? For “disconnect” the old neighbour must no longer be reported. Data only counts if it was reported after ticking off. If everything matches, the order appears as “suggested for confirmation” on the overview (LLDP ✓ in the list), and the approvers receive one email (can be switched off centrally under Administration → Email, personally under “My profile” → Email notifications); confirming remains with the approver (four-eyes principle).</li>
<li><b>Time travel:</b> “Comparison” shows what changed in the cabling between two points in time – new, removed, re-plugged (a port with A before, with B after), only plugged in between – each with who or which order. “As of” lists all connections at a point in time. In the path dialog “As of” shows the route as it was then. Connections are historised; locations and patch panel counterparts are the current state.</li>
<li><b>Clean-up:</b> collects places that should be updated: provisional cables from the target/actual comparison (add outlets/patch panels in the path editor and choose “Path complete”), documented connections that LLDP does not see (possible dead patch; with “missing since” from the first import without the connection and “last seen”, oldest first), expired reservations (deletable together), open orders without changes for X days and planned devices without an order. Global administrators receive a summary by email on Mondays (can be turned off in the profile).</li>
<li><b>Capacity:</b> free, used, planned (open orders) and reserved ports per category (switch ports, patch panel, outlets, PDU) summed up across the locations, plus the free rack units per rack and the largest contiguous free block. Areas below the threshold (default 10 % free) appear as a bottleneck – also as a card on the overview.</li>
<li><b>Work instruction as PDF:</b> “Work instruction (PDF)” in the patch order, “PDF” in the patch list – grouped by location, with check boxes, a field for deviations and a signature as well as a QR code to the order. Orders not yet approved carry the note “do not carry out”. The PDF can be attached when sending by email. It is created in the language of whoever downloads or sends it.</li>
<li><b>Cable labels:</b> “Labels” on the device page or “Cable labels” in the patch order (also before confirmation) – formats for tape (12/19/24 mm) and A4 sheets, optionally one label per cable end. The QR code contains the cable number: after scanning, Portwerk shows where the cable is plugged, whether it is planned and where it was plugged before. Without a cable number there is no QR code for planned items.</li>
<li><b>Connection history</b> (at the bottom of the device page): all current and earlier connections with period, who or which order made and disconnected them. With <b>As of</b> it shows what was plugged at a certain point in time; <b>History</b> in the port row filters on one port. Deleted ports and devices remain with their name of the time.</li></ul>` },

  { id: 'import', title: 'Import', html: `
<p>The import creates and updates devices and ports. It never changes connections.</p>
<h3>Rules</h3>
<ul><li><b>Recognition:</b> via source ID, otherwise via the hostname (case-insensitive). Repeated imports do not create duplicates.</li>
<li><b>Empty fields</b> do not overwrite existing values. <b>Missing ports</b> are not deleted.</li>
<li><b>Dry run</b> shows the result without saving. <b>Atomic</b> saves nothing if there is an error.</li></ul>
<h3>CSV</h3>
<p>Choose a file, map the columns (suggested), dry run, import. Device fields: hostname, type, vendor, model, serial, mgmt_ip, location, status, note, ext_id. Port fields: hostname, port, idx, medium, speed_mbps, description, admin_status, oper_status.</p>
<h3>JSON and API</h3>
<p>The JSON format is identical to the API <code>POST /api/import/json</code>. The button “Insert example” inserts an example.</p>
<h3>Checkmk</h3>
<p>The script <code>tools/checkmk_export.py</code> reads the HW/SW inventory and sends it to <code>POST /api/import/checkmk</code>. It needs an API token with write access. Ethernet interfaces become ports, from 10 Gbit/s with medium SFP+. Loopbacks, VLAN interfaces and tunnels are not imported.</p>` },

  { id: 'verwaltung', title: 'Administration', html: `
<h3>Roles</h3>
<table><tr><th>Role</th><th>May</th></tr>
<tr><td>Administrator</td><td>everything, incl. import and administration</td></tr>
<tr><td>Planner</td><td>maintain master data, plan orders</td></tr>
<tr><td>Approver</td><td>approve orders</td></tr>
<tr><td>Technician</td><td>carry out orders</td></tr>
<tr><td>Viewer</td><td>read only</td></tr></table>
<p>Roles can be combined. The last active administrator cannot be removed.</p>
<h3>Four-eyes principle</h3>
<p>Whoever created or submitted an order may not <b>approve</b> it themselves; whoever carried it out may not <b>confirm</b> it themselves. Rejecting and rework remain allowed. Administrators can override in an emergency with a <b>reason</b> – the exception is recorded in the audit log and on the order.</p>
<h3>Backup</h3>
<p>Administration → <b>Backup</b>: “Back up now” creates a ZIP with the database and server certificate; daily automatically with an adjustable time and retention. External targets (NAS directory, S3, WebDAV, optionally encrypted) receive each backup in addition. Restoring (from the server, a target or a file) replaces the entire inventory – the current state is backed up beforehand, afterwards everyone logs in again. Backups contain password hashes and credentials: keep them confidential.</p>
<h3>API tokens</h3>
<p>Tokens for scripts (prefix <code>opp_</code>). Scope <i>read</i> or <i>write</i>, optionally with expiry. The plain text is shown only once; pass it in the header <code>Authorization: Bearer …</code> or <code>X-Auth-Token</code>.</p>
<h3>Audit log</h3>
<p>Records logins, changes to master data, imports as well as user and token management.</p>` },

  { id: 'assistenten', title: 'Wizards and logic checks', html: `
<p>Wizards guide you step by step through common tasks and show a preview before saving.</p>
<ul><li><b>New site</b> (Sites): site, structure of building → floor → room → rack, check. Everything is saved in one step.</li>
<li><b>Place device</b> (Devices, Racks): model from the catalogue, site and rack position, hostname and data, optionally a cable (e.g. uplink), implementation. Placeholders (cable management, blank panel, shelf) use the same wizard; the hostname is optional there.</li>
<li><b>Bulk cabling</b> (Devices → “Wizard: bulk cabling”): many cables at once. <i>Patch panel ↔ patch panel</i> connects all ports (e.g. rear data centre ↔ rear floor 1); <i>Data outlets → patch panel/switch</i> patches all outlets of a location in order; <i>From list</i> reads an Excel/CSV mapping (device A; port A; device B; port B; cable number). The mapping can be checked beforehand, offset and skipped row by row; cable numbers are generated from a pattern. Result: <b>one patch order with a work list</b> (or everything immediately, atomically). Occupied ports trigger a single question about removal.</li>
<li><b>Autorouting</b> (Racks, port in the device details): from a source port to a target port Portwerk suggests the missing patches – via existing cables, patch panels and outlets – and can create a new device as “planned” at the same time.</li>
<li><b>Quick search:</b> <b>Ctrl+K</b> or <b>/</b> (or the field in the sidebar) opens the search across devices (hostname, IP, serial number, model), sites, locations, WAN connections, patch orders and cable numbers. For devices the site, room/rack and rack unit are shown directly in the hit; Enter opens the rack view with the device highlighted.</li>
<li><b>OpenPlan integration:</b> patch orders become tasks in the OpenPlan project plan (Administration → OpenPlan). Status and progress are synced automatically; several orders can be transferred at once or attached to a new project from the template “Patch panel installation / cabling”.</li>
<li><b>Patch list from several orders:</b> in “Patch orders” tick orders → “Patch list from selection”: one combined work list sorted by location for ticking off, exporting and printing.</li>
<li><b>Install cable</b> (Devices, device view, Racks → free port “connect …”): cable type from the catalogue (data, fibre, <b>power</b>, <b>coax RG58</b> for NTP/DCF, serial, telephone), end A and B, details, implementation. If the port medium does not match the cable type, a note is shown; occupied ports trigger the question about removal.</li>
<li><b>Wall cabinets, control cabinets, machines and loaders:</b> besides racks there are wall cabinets and control cabinets (with or without U), plants/machines and mobile machines. Devices in them are mounted on a <i>DIN rail/mounting plate</i> (no U grid, no collision) or – in housings with U – on 19-inch slots. Typical industrial types (PLC, HMI, I/O module, drive, gateway, power supply) and templates for the DIN rail are in the catalogue.</li>
<li><b>Mounting position:</b> every device has a mounting side (front, rear, full depth) and an orientation: <i>19 inch</i> occupies U, <i>vertical</i> sits in the side channel on the left or right (PDU, vertical cable management) and occupies no U. The collision check takes side and channel into account.</li>
<li><b>Place patch panel</b> (Devices, Racks): template (Cat6A/fibre, 8/12/24 ports, front and rear linked), location, name and <b>port mapping</b>: e.g. front P1–P12 consecutively to switch port 1–12, cable numbers from a pattern (<code>{hostname}-{nn}</code>). Several mappings are possible; occupied target ports trigger the question about removal.</li>
<li><b>Implementation of your choice:</b> “immediately” writes directly to the inventory (administrators), “via patch order” creates the device as <i>planned</i> and turns installation and cables into items of an order.</li></ul>
<h3>Logic checks</h3>
<ul><li><b>Port occupied:</b> the wizard asks whether the old patch should be removed. On “Yes” a <b>removal patch order</b> is created automatically; the new order only starts once it has been confirmed. In “immediately” mode the old patch is removed directly.</li>
<li><b>Rack unit occupied:</b> the same question for the old device. Removed devices remain in the history as “retired”.</li>
<li>Hostnames must be unique; device and rack height are checked as when creating normally.</li></ul>
<h3>Permissions per site</h3>
<p>Users can receive roles for individual sites only and then only see those. Site administrators manage their site including its users. See Administration → Users.</p>` },

  { id: 'ausblick', title: 'Outlook', html: `
<ul><li>Webhooks to other systems (e.g. “order confirmed”, “LLDP deviation”)</li>
<li>VLAN target/actual for trunks, voice VLANs and other vendors</li>
<li>History for device locations and patch panel pairs (time travel with the locations of the time)</li></ul>` },
]
