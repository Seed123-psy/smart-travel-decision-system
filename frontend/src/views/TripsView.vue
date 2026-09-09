<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useSharedPlanning } from '../composables/planningContext'
import { ApiError } from '../api/client'
import { isTerminalTask } from '../api/planning'
import type { TripHistoryItem } from '../types/planning'

const planning = useSharedPlanning()
const { history, historyLoading, historyError, hasMoreHistory, busy, uncertainSubmission, submitting, reading } = planning
const router = useRouter()
const deletingId = ref<string | null>(null)
const actionError = ref('')
const money = (value: string) => new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(Number(value))

const statusText: Record<TripHistoryItem['status'], string> = {
  queued: '排队中', running: '生成中', ready: '已生成', degraded: '部分信息待确认', failed: '规划未完成',
}

async function open(entry: TripHistoryItem) {
  if (busy.value && !uncertainSubmission.value) return
  if (!isTerminalTask(entry.status)) {
    await planning.openTrip(entry.trip_id)
    void router.push('/plan')
  } else {
    void router.push({ name: 'trip-detail', params: { tripId: entry.trip_id } })
  }
}

async function remove(entry: TripHistoryItem) {
  if (busy.value || deletingId.value) return
  if (!isTerminalTask(entry.status)) return
  if (!window.confirm(`删除「${entry.destination}」这条行程记录？此操作不可撤销。`)) return
  deletingId.value = entry.trip_id
  actionError.value = ''
  try {
    await planning.removeTrip(entry.trip_id)
  } catch (caught) {
    actionError.value = caught instanceof ApiError ? caught.message : '删除失败，请稍后重试。'
  } finally {
    deletingId.value = null
  }
}
</script>

<template>
  <main id="main-content" class="trips-page">
    <div class="trips-header">
      <div>
        <span class="eyebrow">留在本机的旅途</span>
        <h1>我的行程</h1>
        <p>确认生成后，行程会保存在本机，随时可以回看。</p>
      </div>
      <RouterLink class="primary-button trips-cta" to="/plan/chat"><span>规划新旅行</span><span aria-hidden="true">→</span></RouterLink>
    </div>

    <div v-if="historyLoading" class="trips-note">正在读取…</div>
    <div v-else-if="historyError" class="trips-note error" role="alert">{{ historyError.message }}</div>
    <div v-else-if="!history.length" class="trips-empty">
      <h2>还没有保存的行程</h2>
      <p>去对话里把目的地与日期告诉行知，生成后会出现在这里。</p>
    </div>

    <p v-if="actionError" class="trips-note error" role="alert">{{ actionError }}</p>
    <ul v-else class="trip-cards">
      <li v-for="entry in history" :key="entry.trip_id" class="trip-row">
        <button type="button" class="trip-open" :disabled="busy && !uncertainSubmission || submitting || reading" @click="open(entry)">
          <span class="trip-name">{{ entry.destination }}<span class="trip-status" :class="`s-${entry.status}`">{{ statusText[entry.status] }}</span></span>
          <span class="trip-meta">{{ entry.start_date }} — {{ entry.end_date }} · {{ entry.travelers }} 人 · 目的地总预算 {{ money(entry.budget_total) }}</span>
          <span class="trip-action">{{ isTerminalTask(entry.status) && entry.status !== 'failed' ? '查看行程 ↗' : entry.status === 'failed' ? '查看记录 ↗' : '查看进展 ↗' }}</span>
        </button>
        <button v-if="isTerminalTask(entry.status)" type="button" class="trip-delete" :disabled="deletingId === entry.trip_id" :aria-label="`删除 ${entry.destination} 行程`" @click="remove(entry)">
          {{ deletingId === entry.trip_id ? '删除中…' : '删除' }}
        </button>
      </li>
    </ul>
    <button v-if="hasMoreHistory" type="button" class="more-button" :disabled="historyLoading" @click="planning.refreshHistory(true)">加载更多</button>
  </main>
</template>

<style scoped>
.trips-page { max-width: 980px; margin: 0 auto; padding: 34px 24px 80px; }
.trips-header { display: flex; align-items: flex-end; justify-content: space-between; gap: 18px; margin-bottom: 26px; }
.trips-header h1 { font-size: 28px; font-weight: 500; margin: 6px 0 4px; }
.trips-header p { margin: 0; color: var(--muted); font-size: 13px; }
.trips-cta { width: auto; margin-top: 0; min-height: 46px; padding: 10px 20px; text-decoration: none; }
.trips-note { padding: 30px; text-align: center; color: var(--muted); }
.trips-note.error { color: #8f4426; }
.trips-empty { text-align: center; padding: 60px 20px; border: 1px dashed #d5dfd1; border-radius: 20px; background: var(--surface); }
.trips-empty h2 { font-weight: 500; font-size: 21px; margin: 0 0 8px; }
.trips-empty p { color: var(--muted); font-size: 14px; margin: 0; }
.trip-cards { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.trip-row { display: flex; align-items: stretch; gap: 8px; }
.trip-row .trip-open { flex: 1; min-width: 0; text-align: left; border: 1px solid var(--line); border-radius: 16px; padding: 20px 22px; background: var(--surface); color: var(--ink); display: flex; flex-direction: column; gap: 8px; }
.trip-row .trip-open:hover:enabled { border-color: #95ae8f; background: #f4f7ef; }
.trip-row .trip-open:disabled { opacity: .65; }
.trip-delete { align-self: center; flex-shrink: 0; border: 1px solid #ecd2b8; background: #fff6eb; color: #a34c2a; border-radius: 10px; padding: 8px 12px; font-size: 12px; }
.trip-delete:hover:enabled { background: #fbebdc; }
.trip-name { display: flex; align-items: center; justify-content: space-between; gap: 10px; font-size: 19px; }
.trip-status { font-size: 12px; font-weight: 400; padding: 2px 10px; border-radius: 20px; border: 1px solid #dce4d5; color: #66785e; }
.trip-status.s-ready { background: #eef4ea; color: #3c633f; border-color: #ccdac5; }
.trip-status.s-running, .trip-status.s-queued { background: #e6f0e4; color: var(--green); border-color: #9fb8a0; }
.trip-status.s-degraded { background: #faf2e5; color: #87622c; border-color: #dfc9a6; }
.trip-status.s-failed { background: #faede4; color: #a34c2a; border-color: #e6c6ad; }
.trip-meta { color: var(--muted); font-size: 13px; }
.trip-action { font-size: 13px; color: var(--green); margin-top: 4px; }
.more-button { display: block; margin: 22px auto 0; border: 1px solid #d1dccb; border-radius: 10px; background: var(--surface); color: var(--green); padding: 10px 18px; font-size: 13px; }
@media (max-width: 640px) { .trip-cards { grid-template-columns: minmax(0, 1fr); } }
</style>
