<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError } from '../api/client'
import { getTrip } from '../api/planning'
import { useSharedPlanning } from '../composables/planningContext'
import { setCurrentTrip } from '../stores/currentTrip'
import type { TripDetail } from '../types/planning'
import TripPlan from '../components/TripPlan.vue'

const props = defineProps<{ tripId: string }>()
const planning = useSharedPlanning()
const router = useRouter()
const trip = ref<TripDetail | null>(null)
const error = ref<ApiError | null>(null)
const loading = ref(true)
const deleting = ref(false)
const deleteError = ref('')
let controller: AbortController | undefined
const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api'

async function doDelete() {
  if (!trip.value || deleting.value) return
  if (!window.confirm(`删除「${trip.value.request.destination}」这条行程记录？此操作不可撤销。`)) return
  deleting.value = true
  deleteError.value = ''
  try {
    await planning.removeTrip(trip.value.trip_id)
    await router.push('/trips')
  } catch (caught) {
    deleteError.value = caught instanceof ApiError ? caught.message : '删除失败，请稍后重试。'
  } finally {
    deleting.value = false
  }
}

async function load(id: string) {
  controller?.abort()
  const next = new AbortController()
  controller = next
  loading.value = true
  error.value = null
  try {
    const saved = await getTrip(id, { baseUrl, signal: next.signal })
    if (controller !== next) return
    trip.value = saved
    setCurrentTrip(saved)
  } catch (caught) {
    if (controller !== next) return
    error.value = caught instanceof ApiError ? caught
      : new ApiError({ code: 'UNEXPECTED_ERROR', message: '暂时无法读取行程，请稍后重试。' })
    trip.value = null
    setCurrentTrip(null)
  } finally {
    if (controller === next) loading.value = false
  }
}

watch(() => props.tripId, id => { if (id) void load(id) }, { immediate: true })
onMounted(() => { if (props.tripId) void load(props.tripId) })
onBeforeUnmount(() => {
  controller?.abort()
  setCurrentTrip(null)
})
</script>

<template>
  <main id="main-content" class="detail-page">
    <div class="detail-top">
      <RouterLink class="back-link" to="/trips">← 我的行程</RouterLink>
      <button v-if="trip && !loading && !error" type="button" class="detail-delete" :disabled="deleting" @click="doDelete">
        {{ deleting ? '删除中…' : '删除行程' }}
      </button>
    </div>
    <p v-if="deleteError" class="delete-error" role="alert">{{ deleteError }}</p>

    <div v-if="loading" class="detail-state">正在读取行程…</div>
    <div v-else-if="error" class="detail-state error" role="alert">
      <strong>{{ error.message }}</strong>
      <RouterLink class="back-link" to="/trips">返回我的行程</RouterLink>
    </div>
    <div v-else-if="trip?.plan" class="detail-body">
      <TripPlan :trip="trip" />
    </div>
    <div v-else-if="trip" class="detail-state">这条记录还没有可展示的行程内容。</div>
  </main>
</template>

<style scoped>
.detail-page { max-width: 980px; margin: 0 auto; padding: 22px 24px 80px; }
.detail-top { display: flex; justify-content: space-between; align-items: center; }
.back-link { color: var(--green); font-size: 14px; text-decoration: none; border-bottom: 1px solid #c3d2bd; }
.detail-delete { border: 1px solid #ecd2b8; background: #fff6eb; color: #a34c2a; border-radius: 10px; padding: 7px 14px; font-size: 12px; }
.detail-delete:hover:enabled { background: #fbebdc; }
.delete-error { color: #a34c2a; font-size: 13px; }
.detail-state { text-align: center; padding: 60px 20px; color: var(--muted); }
.detail-state.error strong { display: block; margin-bottom: 14px; color: #8f4426; font-weight: 500; }
.detail-body { margin-top: 18px; }
</style>
