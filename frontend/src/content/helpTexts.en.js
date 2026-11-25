// Context help per page (F1 / ?), English. Same keys as helpTexts.js; missing keys fall back to German.
export const T_EN = {
  '/dashboard': `<h2>Overview</h2>
<p>See at a glance what is in the inventory: sites, racks, devices and ports.</p>
<ul><li><b>Devices without location</b> are not yet assigned to a room or rack – they are missing from the rack view.</li>
<li><b>Latest imports</b> shows whether an import was applied or only checked as a dry run.</li></ul>
<p class="help-tip">New here? Create sites first, then import devices (Import).</p>`,

  '/sites': `<h2>Sites</h2>
<p>The location structure is hierarchical: <b>site → building → floor → room → plant/machine → rack / wall cabinet / control cabinet</b>. Any level may be missing.</p>
<ul><li><b>Racks, wall cabinets and control cabinets</b> hold devices and optionally have rack units (U). A control cabinet without U is meant for DIN-rail devices.</li>
<li>A <b>plant/machine</b> is stationary (e.g. press, conveyor) and can contain control cabinets. Devices can also sit directly in the machine.</li>
<li>A <b>mobile machine</b> (e.g. loader) belongs to a site and can be moved to another site with “Move”, together with its cabinet and devices. The change is recorded in the audit log.</li></ul>
<ul><li>Choose a site on the left; its structure appears on the right.</li>
<li>A <b>rack</b> needs the number of rack units (U) so the rack view can show it.</li>
<li>Sites or locations that contain devices cannot be deleted.</li></ul>
<p><b>Wizard: new site</b> guides you through site, structure and check in three steps. “Several …” creates e.g. 10 racks at once with the name pattern <code>Rack {n}</code>. Use “Structure wizard” to extend an existing site.</p>
<p class="help-tip">When importing, a path like <code>SITE-A/Building 1/Room 2/Rack 3</code> is enough – missing levels are created.</p>`,

  '/admin#ldap': `<h2>AD / LDAP</h2>
<p>Here you enable <b>login via Active Directory</b>. The default is <b>off</b>; local accounts always remain as emergency access.</p>
<ul><li><b>Server</b>: prefer ldaps://; several servers provide failover.</li>
<li><b>Check login</b>: either directly as <code>user@domain</code> (enter the domain) or via a service account with a user filter.</li>
<li><b>Roles</b>: one AD group (DN) per role. Roles are recalculated from the groups at every login. Without a matching group the “role without matching group” applies – empty means: no access.</li>
<li><b>Test connection</b> shows step by step what works and lists the groups of the test user – you can copy the DNs directly.</li></ul>
<p class="help-tip">Passwords of AD users are never stored and only changed in the directory.</p>`,

  '/admin#mail': `<h2>Email</h2>
<p>SMTP access for sending orders and patch lists as well as assignment notifications. The default is <b>off</b>.</p>
<ul><li><b>Allowed domains</b> restrict the recipients – recommended so that no order data goes to outside addresses.</li>
<li>The <b>public URL</b> is used for the links in the mails.</li>
<li>“Test message” checks the saved settings. Every sending is recorded in the audit log.</li></ul>`,

  '/admin#openplan': `<h2>OpenPlan</h2>
<p>Integration with the project planning tool OpenPlan (default: <b>off</b>). In OpenPlan, create a service account with an API token (scope write, role editor) and add it to the project as a member.</p>
<ul><li><b>Test connection</b> shows the service account and the visible projects.</li>
<li><b>Sync automatically:</b> every status change and every ticked-off item reports status and progress to the linked task. An OpenPlan outage never disturbs the patch order; “Sync now” catches up.</li>
<li><b>Webhook (optional):</b> OpenPlan reports changes to the task back; the status appears on the order. Secret and address are shown on this page.</li>
<li><b>Absences (optional):</b> imports the personal absences from OpenPlan every hour; the default deputy from the profile applies to them. The OpenPlan API token needs the “Absences” permission.</li></ul>`,

  '/admin#tls': `<h2>Certificate (ACME)</h2>
<p>The app requests its server certificate itself from an ACME CA (e.g. an internal step-ca) and renews it automatically.</p>
<ul><li>Enter the <b>directory URL</b> and <b>domains</b> (recommended: short name, FQDN and IP). The CA validates via HTTP-01 – port 80 must be forwarded to the app.</li>
<li>If the CA uses its <b>own PKI</b>, store the CA chain (root + intermediate) or load it via URL and check the fingerprints.</li>
<li>The <b>HTTPS listener</b> starts as soon as <code>TLS_PORT</code> is set; a renewed certificate is picked up without a restart.</li></ul>`,

  '/compare': `<h2>Target/actual comparison</h2>
<p>Compares the documented cabling (<b>target</b>, also across patch panels and outlets) with the neighbours reported via LLDP/CDP (<b>actual</b>).</p>
<ul><li><b>matches</b> · <b>other port</b> (right device, wrong port) · <b>other device</b> · <b>not seen</b> (documented, but no neighbour reported) · <b>not documented</b> (neighbour seen, no cable recorded).</li>
<li>For “not seen” the date shows since when the connection has been missing (from the first import without it).</li>
<li>The neighbour data comes with the Checkmk import; each import replaces the data of the devices it contains. Plain MAC addresses (phones, cameras) are ignored.</li>
<li><b>Adopt connection</b> documents a seen but undocumented connection as a provisional direct cable; <b>Add to inventory</b> creates an unknown neighbour device.</li>
<li>The chips filter; CSV export for reports.</li></ul>`,

  '/wan': `<h2>WAN connections</h2>
<p>The circuit directory: connections between sites or to the internet with provider, circuit ID, technology, bandwidth and contract.</p>
<ul><li><b>Remote end:</b> one of your own sites or free text (e.g. internet). <b>Ports</b> on a router/firewall are optional; a port belongs to at most one active connection.</li>
<li><b>Changes run as orders:</b> “Activate”, “Change via order” and “Terminate” create a patch order. The status or the new values only apply once the order is confirmed.</li>
<li><b>Edit directly</b> (administrators): for recording existing circuits.</li>
<li>The filter “Contract ends within 90 days” shows termination and renewal dates; CSV export for evaluations.</li></ul>`,

  '/workorders': `<h2>Patch orders</h2>
<p>Changes to cabling and devices run as orders: <b>draft → submit → approve → carry out → confirm</b>. Only the confirmation changes the inventory.</p>
<ul><li>Items: connect, disconnect, re-plug as well as <b>install device</b> and <b>remove device</b>; for WAN connections <b>activate</b>, <b>change</b> and <b>terminate</b>; <b>reconfigure port</b> for VLAN/profile.</li>
<li><b>Occupied port:</b> if a new patch is planned on an occupied port, the interface asks “Remove the old patch?”. On <b>Yes</b> a <b>removal order</b> is created automatically; the new order can only start once the removal has been confirmed.</li>
<li>The same applies to <b>occupied rack units</b>: the old device is removed via a removal order (cables disconnected, status “retired”, U free).</li>
<li><b>Work list:</b> large orders (e.g. from bulk cabling) are a list with one item per cable. Progress, filters and <b>multiple selection</b> (“Tick off selection”, “Deviation …”, “Reset”) make execution easier; “Work list (CSV)” opens directly in Excel.</li>
<li><b>Patch list from several orders:</b> tick orders in the order list and choose “Patch list from selection”. The combined list is sorted by location (rack/room) – so you can work through one room after another – or by order. Ticking off, CSV export and printing (with check boxes for paper) are possible.</li>
<li><b>OpenPlan:</b> if the integration is set up, you link an order to a task in the OpenPlan project plan (create a new one or choose an existing one). Status and progress are transferred automatically; OpenPlan shows the reference <code>portwerk: PA-…</code> with a link back. In the order list, “In OpenPlan …” transfers several orders at once or creates a <b>new project from the template “Patch panel installation / cabling”</b>.</li>
<li><b>Send …</b> sends the order (or a patch list) by email to users and/or any addresses – with a link, item list and the work list as a CSV attachment. Users are only offered if they may see the order.</li>
<li><b>Assign …</b> makes a user responsible; the order appears on their overview under “My tasks” (filter “Assigned to me” in the list). An email can be sent on request.</li>
<li>With permissions for one site only, you only see the orders of your site.</li></ul>`,

  '/catalog': `<h2>Catalogue</h2>
<p>Here you maintain <b>what may be installed</b>: device models and cable types.</p>
<ul><li><b>Device models</b> are templates with vendor, type, height and port layout (e.g. 48× RJ45 + 4× SFP+). The wizards create ports from them automatically.</li>
<li>For <b>patch panels</b> set the port group to “dual”: each port gets a front and rear side, already linked.</li>
<li>Accessories without ports (UPS, radio clock, PDU) also belong in the catalogue.</li></ul>
<p class="help-tip">A model already used by devices can only be deactivated, not deleted.</p>`,

  '/catalog#models': `<h2>Device models</h2>
<p>Templates for switches, patch panels, time servers, PDUs and more. The port layout consists of <b>port groups</b>: prefix (e.g. <code>Gi1/0/</code>), start number, count and medium.</p>
<ul><li>Deactivated models no longer appear in the wizards; existing devices keep the link.</li></ul>`,

  '/catalog#cables': `<h2>Cable types</h2>
<p>Besides Cat and fibre cables, <b>power</b>, <b>coax (RG58 for NTP/DCF)</b>, <b>serial/signal</b> and <b>telephone copper</b> are built in. You can create your own types freely.</p>
<ul><li>The <b>count field</b> (fibres, cores or pairs) appears when recording a cable of this type.</li>
<li>The <b>name</b> cannot be changed because existing cables refer to it. Types no longer needed are deactivated.</li>
<li>Only administrators maintain cable types.</li></ul>`,

  '/devices': `<h2>Devices</h2>
<p>All devices with ports: switches, routers, firewalls, access points, servers, patch panels and outlets.</p>
<ul><li>Filters for search text, type, status, source and site can be combined.</li>
<li><b>Source</b> shows where the device comes from (manual, CSV, Checkmk, OpenPlan …).</li>
<li>Clicking a hostname opens details and ports.</li>
<li><b>From OpenPlan …</b> imports devices from a device rollout in OpenPlan as “planned” (if the integration is active).</li></ul>`,

  '/racks': `<h2>Racks</h2>
<p>Cabinet view with rack units (U). U 1 is at the bottom.</p>
<ul><li>Devices with a rack position are shown in their place, multi-height devices across several U.</li>
<li>Devices in the rack without a rack position are listed below under “Without position”.</li>
<li><b>Clicking a device</b> opens the <b>port usage</b> on the right: for each port, what it is connected to (device:port, cable number, cable type) or “free”. The filter shows only used or free ports.</li>
<li><b>Clicking a free slot</b> asks whether a new device should be placed there – the wizard starts with rack and U preset. Placeholders (cable management, blank panel, shelf) can be planned this way too.</li>
<li>Grey bars are placeholders, orange devices are only “planned”, red bars are PDUs.</li>
<li><b>Front / rear:</b> switch the view at the top right. Devices are mounted at the <i>front</i>, <i>rear</i> or <i>full depth</i> (both sides) – a front-only and a rear-only device may share the same U.</li>
<li><b>Vertical devices</b> (e.g. PDU, vertical cable management) sit in the narrow <b>side channels on the left and right</b> and occupy no 19-inch U. Clicking the channel places one; left/right refer to the view currently shown.</li></ul>
<p class="help-tip">If the chosen U is occupied, the wizard asks whether the old device should be removed. Via a patch order a removal order is created automatically for this.</p>`,

  '/import': `<h2>Import</h2>
<p>Devices and ports can be read in from CSV, JSON or Checkmk. The import only changes devices and ports, never connections.</p>
<ul><li><b>Dry run</b> calculates everything and shows the result without saving.</li>
<li><b>Atomic</b>: if there is an error, nothing is saved.</li>
<li>Repeated imports are safe: devices are recognised by hostname or source ID. Empty fields overwrite nothing, missing ports are not deleted.</li></ul>`,
  '/import#csv': `<h2>CSV import</h2>
<p>Choose a file, map the columns, check the dry run, then import. The mapping is suggested; adjust it if necessary.</p>
<ul><li><b>Devices</b>: required field hostname.</li><li><b>Ports</b>: required fields hostname and port.</li></ul>`,
  '/import#json': `<h2>JSON import</h2>
<p>The API uses the same format (<code>POST /api/import/json</code>) for scripts. An example is shown below the input field.</p>`,
  '/import#checkmk': `<h2>Checkmk import</h2>
<p>The script <code>tools/checkmk_export.py</code> reads the HW/SW inventory from Checkmk and sends it to the API. You need an API token with write access (Administration → API tokens).</p>`,

  '/admin': `<h2>Administration</h2>
<p>Users, API tokens and audit log. Administrators only.</p>`,
  '/admin#users': `<h2>Users and permissions</h2>
<ul><li>Roles can be combined: administrator, planner, approver, technician, viewer.</li>
<li><b>Global roles</b> apply to all sites; anyone who has one sees everything.</li>
<li><b>Permissions per site</b>: a role for one site only (several rows = several sites). Anyone <i>without</i> a global role only sees these sites – including locations, devices, cables and orders.</li>
<li>A <b>site administrator</b> (role administrator at one site) manages the master data and users of their site, but not API tokens, AD, certificate, catalogue or import. They do not lock or delete users who also belong to other sites.</li>
<li>For AD users, roles and site permissions come from the AD groups (tab “AD / LDAP”); they are set anew at every login.</li>
<li>“Absence” enters an absence with deputy for a user (administrators).</li>
<li>“End sessions” logs the user out everywhere.</li>
<li>The last active administrator cannot be removed or demoted.</li></ul>`,
  '/admin#tokens': `<h2>API tokens</h2>
<p>Tokens for scripts and integrations (e.g. Checkmk, OpenPlan). The plain text is shown <b>only once</b> when it is created.</p>
<ul><li><b>read</b>: read only. <b>write</b>: read and write (import).</li></ul>`,
  '/admin#audit': `<h2>Audit log</h2>
<p>Who changed what and when: logins, master data, imports, user and token management.</p>`,

  '/handbuch': `<h2>Manual</h2><p>The manual describes all functions in detail. Use the table of contents to jump to the sections.</p>`,
}

export const DEFAULT_EN = '<h2>Help</h2><p>There is no specific help text for this page. The manual explains all functions.</p>'
