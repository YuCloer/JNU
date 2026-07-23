import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/upload' },
  { path: '/upload', name: 'Upload', component: () => import('../views/UploadView.vue') },
  { path: '/match', name: 'Match', component: () => import('../views/MatchView.vue') },
  { path: '/interview', name: 'Interview', component: () => import('../views/InterviewView.vue') },
  { path: '/report', name: 'Report', component: () => import('../views/ReportView.vue') },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
