<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { usePlanning } from '../composables/usePlanning'
import type { PlanningTask, TaskStage, TaskStatus } from '../types/planning'
import type { TravelRequest } from '../types/travel'
import TripPlan from './TripPlan.vue'
import AgentOverview from './AgentOverview.vue'

const props = defineProps<{ request: TravelRequest | null }>()
const emit = defineEmits<{ busy: [value: boolean]; task: [value: PlanningTask | null]; submitted: [] }>()
const { taskId, task, trip, submitting, reading, busy, connectionError, submissionError, uncertainSubmission,
  history, historyLoading, historyError, hasMoreHistory, storageAvailable,
  generate, readTask, refreshHistory, openTrip, recoverLatest } = usePlanning()
const consent = ref(false)
const progressElement = ref<HTMLElement | null>(null)
const retryRequest = ref<TravelRequest | null>(null)
const requestToPlan = computed(() => retryRequest.value || props.request)
const statusLabels: Record<TaskStatus, string> = { queued: '等待开始', running: '正在协作规划', ready: '行程已生成', degraded: '已生成，部分信息待确认', failed: '本次规划未完成' }
const stageLabels: Record<TaskStage, string> = { validating: '检查需求', collecting: '查询旅行信息', planning: '编排行程', checking: '校验时间与路线', persisting: '保存结果' }
watch(busy, value => emit('busy', value), { immediate: true })
watch(task, value => emit('task', value), { immediate: true })
watch(() => props.request, () => { consent.value = false; retryRequest.value = null })
watch(taskId, () => { consent.value = false })
watch(submitting, async value => {
  if (!value) return
  await nextTick()
  progressElement.value?.scrollIntoView({ block: 'start', behavior: 'instant' })
})

async function submitPlan() {
  if (!consent.value || !requestToPlan.value || busy.value || reading.value) return
  const request = requestToPlan.value
  const previousTaskId = taskId.value
  consent.value = false
  await generate(request)
  if (taskId.value && taskId.value !== previousTaskId) emit('submitted')
}
function prepareRetry() {
  if (busy.value || !trip.value) return
  retryRequest.value = trip.value.request
  consent.value = false
}
</script>

<template>
  <section class="planning-workspace" aria-label="协作规划与本地行程">
    <div v-if="requestToPlan && !busy" class="planning-confirmation">
      <span class="eyebrow">{{ retryRequest ? '重新规划' : '让计划开始' }}</span>
      <h3>{{ requestToPlan.destination }}，一起把行程安排好。</h3>
      <p v-if="retryRequest" class="retry-summary">{{ requestToPlan.origin }} → {{ requestToPlan.destination }} · {{ requestToPlan.start_date }} 至 {{ requestToPlan.end_date }} · {{ requestToPlan.travelers }} 人</p>
      <label for="confirm-planning" class="planning-consent"><input id="confirm-planning" v-model="consent" type="checkbox" :disabled="submitting || reading" /><span>我确认生成行程：需求与结果将保存在本机；规划时会将必要的位置、日期及偏好发送给模型和旅行数据服务。</span></label>
      <button type="button" class="primary-button" :disabled="!consent || submitting || reading" @click="submitPlan"><span>{{ submitting ? '正在提交…' : task ? '重新生成行程' : '确认并生成行程' }}</span><span aria-hidden="true">→</span></button>
      <p class="planning-note">将发起真实查询和 Agent 协作，可能产生已配置服务的调用费用。</p>
    </div>

    <div ref="progressElement" class="progress-region">
    <div v-if="submitting" class="task-banner" role="status"><strong>正在提交规划任务…</strong><p>任务被接收后将展示真实执行进展。</p></div>
    <div v-if="taskId && !submitting" class="task-banner" :class="{ 'task-failed': task?.status === 'failed', 'task-degraded': task?.status === 'degraded' }" aria-live="polite">
      <div class="task-title"><strong>{{ task ? statusLabels[task.status] : '正在恢复最近任务…' }}</strong><span v-if="task?.status === 'queued' || task?.status === 'running'">{{ stageLabels[task.stage] }}</span></div>
      <p v-if="task?.message">{{ task.message }}</p>
      <p v-else-if="task?.status === 'queued' || task?.status === 'running'">页面每秒读取一次进度。刷新后可继续查看本机保存的任务。</p>
      <p v-if="task?.status === 'failed' && !task.message">未获得可保存的完整行程，请查看 Agent 记录与失败原因后重试。</p>
      <p v-if="task?.error_code" class="task-reference">错误代码：{{ task.error_code }}</p>
      <p class="task-reference">任务编号：{{ taskId }}</p>
      <button v-if="task?.status === 'failed' && trip && !retryRequest" type="button" class="secondary-button" :disabled="reading" @click="prepareRetry">重新规划此行程</button>
      <p v-if="reading && task && ['ready', 'degraded', 'failed'].includes(task.status)" class="planning-note">正在读取本机保存的记录…</p>
    </div>
    <AgentOverview v-if="taskId || submitting" :task="submitting ? null : task" compact />
    </div>

    <div v-if="submissionError" class="planning-error" role="alert"><strong>{{ submissionError.message }}</strong><p v-if="submissionError.requestId">请求编号：{{ submissionError.requestId }}</p><template v-if="uncertainSubmission"><p>提交结果尚未确认。请先读取本地记录，避免重复生成。</p><button type="button" class="secondary-button" :disabled="reading || historyLoading" @click="recoverLatest">恢复最近任务</button></template></div>
    <div v-if="connectionError" class="planning-error" role="alert"><strong>{{ connectionError.message }}</strong><p v-if="connectionError.requestId">请求编号：{{ connectionError.requestId }}</p><p v-if="taskId">连接中断不会取消后台任务。恢复后将继续读取同一任务。</p><button v-if="taskId" type="button" class="secondary-button" :disabled="reading" @click="readTask(taskId)">恢复连接并读取</button><button v-else type="button" class="secondary-button" :disabled="reading || historyLoading" @click="recoverLatest">读取最近任务</button></div>
    <p v-if="!storageAvailable" class="planning-note">浏览器未允许保存任务编号；仍可从下方本地历史恢复查看。</p>

    <TripPlan v-if="trip?.plan && (!task || task.trip_id === trip.trip_id)" :trip="trip" />

    <section class="history-section" aria-labelledby="history-heading">
      <div class="history-heading"><div><span class="eyebrow">留在本机的旅途</span><h3 id="history-heading">最近行程</h3></div><button type="button" class="secondary-button" :disabled="historyLoading" @click="refreshHistory()">{{ historyLoading ? '读取中…' : '刷新历史' }}</button></div>
      <p v-if="historyError" class="history-error" role="alert">{{ historyError.message }}</p>
      <p v-else-if="!history.length && !historyLoading" class="history-empty">还没有保存的行程。确认规划后，任务与结果将记录在这里。</p>
      <ul v-if="history.length" class="history-list"><li v-for="entry in history" :key="entry.trip_id"><button type="button" :disabled="submitting || reading || (busy && !uncertainSubmission)" :aria-current="trip?.trip_id === entry.trip_id ? 'true' : undefined" @click="openTrip(entry.trip_id)"><span class="history-name">{{ entry.destination }}<span>{{ statusLabels[entry.status] }}</span></span><span class="history-date">{{ entry.start_date }} — {{ entry.end_date }} · {{ entry.travelers }} 人</span><span class="history-action">查看记录 ↗</span></button></li></ul>
      <button v-if="hasMoreHistory" type="button" class="secondary-button more-history" :disabled="historyLoading" @click="refreshHistory(true)">查看更多</button>
    </section>
  </section>
</template>

<style scoped>
.planning-workspace { margin-top: 32px; padding: 32px; background: var(--surface); border: 1px solid #e2e7dc; border-radius: 20px; }
.progress-region { scroll-margin-top: 24px; }
.progress-region:empty { display: none; }
.planning-confirmation { padding: 22px; border: 1px solid #cadbc3; border-radius: 12px; background: #f3f7ee; }
.planning-confirmation .primary-button { max-width: 380px; }
.planning-confirmation h3 { margin: 10px 0 16px; font-size: 21px; font-weight: 500; color: #355940; }
.planning-consent { display: flex; align-items: flex-start; gap: 10px; font-size: 13px; line-height: 1.85; color: #536e50; }
.planning-consent input { accent-color: var(--green); flex-shrink: 0; width: 17px; height: 17px; margin: 4px 0 0; }
.planning-note { margin: 12px 0 0; color: var(--muted); font-size: 12px; line-height: 1.8; }
.retry-summary { font-size: 13px; color: var(--muted); }
.task-banner { padding: 20px; border: 1px solid #ccddc5; border-radius: 12px; background: #eff5e9; margin: 22px 0; overflow-wrap: anywhere; }
.task-title { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; color: #355840; }
.task-title strong { font-size: 17px; font-weight: 500; }
.task-title > span { font-size: 12px; color: var(--muted); }
.task-banner p { font-size: 13px; color: var(--muted); margin: 8px 0; }
.task-banner .task-reference { font-size: 11px; }
.task-degraded, .task-failed { border-color: #e4d3b6; background: #faf5e9; }
.task-failed .task-title strong { color: #8f4426; }
.secondary-button { border: 1px solid #d1dccb; border-radius: 8px; background: var(--surface); color: var(--green); min-height: 36px; padding: 6px 12px; font-size: 12px; }
.secondary-button:hover:enabled { background: #edf3e7; }
.secondary-button:disabled { color: #798573; }
.planning-error { padding: 18px; margin: 18px 0; border: 1px solid #e6d0b2; border-radius: 10px; background: #fff6eb; color: #8f4426; font-size: 13px; overflow-wrap: anywhere; }
.planning-error strong { font-weight: 500; }
.planning-error p { margin: 8px 0; font-size: 12px; }
.history-section { border-top: 1px solid var(--line); padding-top: 24px; margin-top: 32px; }
.history-heading { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
.history-heading h3 { font-size: 20px; font-weight: 500; margin: 5px 0 0; }
.history-empty, .history-error { font-size: 13px; color: var(--muted); }
.history-error { color: #8f4426; }
.history-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; list-style: none; padding: 0; margin: 18px 0 0; }
.history-list button { display: block; width: 100%; border: 1px solid var(--line); border-radius: 10px; padding: 15px 16px; background: var(--surface); text-align: left; color: var(--ink); }
.history-list button:hover:enabled, .history-list button[aria-current='true'] { border-color: #95ae8f; background: #f3f6ed; }
.history-list button:disabled { opacity: .65; }
.history-name { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px; font-size: 15px; }
.history-name > span { font-size: 12px; color: #6e7c62; }
.history-date { display: block; color: var(--muted); font-size: 12px; margin-top: 6px; }
.history-action { display: block; font-size: 12px; color: var(--green); margin-top: 10px; }
.more-history { margin-top: 14px; }
@media (max-width: 820px) { .planning-workspace { padding: 24px; } }
@media (max-width: 540px) { .planning-workspace { padding: 22px 20px; border-radius: 16px; } .planning-confirmation { padding: 18px; } .planning-confirmation h3 { font-size: 19px; } .history-list { grid-template-columns: minmax(0, 1fr); } }
</style>
