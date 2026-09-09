import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'
import PlanChatView from '../views/PlanChatView.vue'
import PlanningView from '../views/PlanningView.vue'
import TripDetailView from '../views/TripDetailView.vue'
import TripsView from '../views/TripsView.vue'
import FlightsView from '../views/FlightsView.vue'

export const router = createRouter({
  history: createWebHistory(),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/plan/chat', name: 'plan-chat', component: PlanChatView },
    { path: '/plan', name: 'plan-progress', component: PlanningView },
    { path: '/trip/:tripId', name: 'trip-detail', component: TripDetailView, props: true },
    { path: '/trips', name: 'trips', component: TripsView },
    { path: '/flights', name: 'flights', component: FlightsView },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

export default router
