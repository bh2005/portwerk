import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import LoginView from './views/LoginView.vue'
import Dashboard from './views/Dashboard.vue'
import Sites from './views/Sites.vue'
import Wan from './views/Wan.vue'
import Compare from './views/Compare.vue'
import Devices from './views/Devices.vue'
import DeviceDetail from './views/DeviceDetail.vue'
import Racks from './views/Racks.vue'
import ImportView from './views/ImportView.vue'
import Admin from './views/Admin.vue'
import Help from './views/Help.vue'
import Catalog from './views/Catalog.vue'
import WorkOrderList from './views/WorkOrderList.vue'
import WorkOrderDetail from './views/WorkOrderDetail.vue'
import PatchList from './views/PatchList.vue'
import LabelPrint from './views/LabelPrint.vue'
import CableLookup from './views/CableLookup.vue'
import Reservations from './views/Reservations.vue'
import Capacity from './views/Capacity.vue'
import TimeTravel from './views/TimeTravel.vue'
import VlanAdmin from './views/VlanAdmin.vue'
import MobileHome from './views/mobile/MobileHome.vue'
import MobileOrder from './views/mobile/MobileOrder.vue'
import { isLoggedIn, isAdmin, canAdministerUsers, startPage } from './api.js'
import { helpContext } from './content/helpContext.js'
import './style.css'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/',            redirect: () => startPage() },
    { path: '/login',       component: LoginView, meta: { public: true } },
    { path: '/dashboard',   component: Dashboard },
    { path: '/sites',       component: Sites },
    { path: '/devices',     component: Devices },
    { path: '/devices/:id', component: DeviceDetail },
    { path: '/racks',       component: Racks },
    { path: '/wan',         component: Wan },
    { path: '/compare',     component: Compare },
    { path: '/catalog',     component: Catalog },
    { path: '/workorders',    component: WorkOrderList },
    { path: '/workorders/:id', component: WorkOrderDetail },
    { path: '/patchlist',   component: PatchList },
    { path: '/labels',      component: LabelPrint },
    { path: '/reservations', component: Reservations },
    { path: '/capacity',    component: Capacity },
    { path: '/timetravel',  component: TimeTravel },
    { path: '/vlans',       component: VlanAdmin },
    { path: '/q/k/:label',  component: CableLookup, meta: { bare: true } },   // Ziel der QR-Codes auf Kabeletiketten (meist am Handy)
    { path: '/q/c/:id',     component: CableLookup, meta: { bare: true } },
    { path: '/m',           component: MobileHome, meta: { bare: true } },    // Techniker-Ansicht fürs Handy
    { path: '/m/wo/:id',    component: MobileOrder, meta: { bare: true } },
    { path: '/import',      component: ImportView, meta: { admin: true } },
    { path: '/admin',       component: Admin, meta: { userAdmin: true } },
    { path: '/handbuch',    component: Help },
  ],
})

router.beforeEach(to => {
  if (!to.meta.public && !isLoggedIn()) return { path: '/login', query: { redirect: to.fullPath } }
  if (to.meta.admin && !isAdmin()) return { path: '/dashboard' }
  if (to.meta.userAdmin && !canAdministerUsers()) return { path: '/dashboard' }
})

router.afterEach(() => { helpContext.value = '' })

createApp(App).use(router).mount('#app')
