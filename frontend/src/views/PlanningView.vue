<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSharedPlanning } from '../composables/planningContext'
import { isTerminalTask } from '../api/planning'
import Timeline from '../components/Timeline.vue'

const planning = useSharedPlanning()
const { task, trip, taskId, reading, connectionError } = planning
const route = useRoute()
const router = useRouter()

const terminal = computed(() => !!task.value && isTerminalTask(task.value.status))
const doneTrip = computed(() => !!trip.value?.plan && terminal.value && task.value?.status !== 'failed')
const restoring = computed(() => !!taskId.value && !task.value && reading.value)
const money = (value: string) => new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(Number(value))
const request = computed(() => trip.value?.request || null)

function goDetail() {
  const id = trip.value?.trip_id || String(route.query.trip_id || '')
  if (id) void router.push({ name: 'trip-detail', params: { tripId: id } })
}
function goChat() { void router.push('/plan/chat') }
function retryConnect() { if (taskId.value) void planning.readTask(taskId.value) }

onMounted(() => {
  const routeTaskId = typeof route.query.task_id === 'string' ? route.query.task_id : null
  const routeTripId = typeof route.query.trip_id === 'string' ? route.query.trip_id : null
  if (routeTaskId) void planning.readTask(routeTaskId)
  else if (routeTripId) void planning.openTrip(routeTripId)
})
</script>

<template>
  <main id="main-content" class="plan-page">
    <div class="plan-header">
      <div>
        <span class="eyebrow">生成中</span>
        <h1 v-if="request">{{ request.destination ? `为 ${request.destination} 排好每一天` : '正在为你规划行程' }}</h1>
        <h1 v-else>正在为你规划行程</h1>
        <p v-if="request">{{ request.origin }} → {{ request.destination }} · {{ request.start_date }} 至 {{ request.end_date }} · {{ request.travelers }} 人</p>
        <p v-else>下面的每一步都来自真实服务调用；生成后行程会自动保存在本机。</p>
      </div>
      <RouterLink class="secondary-link" to="/plan/chat">← 修改需求</RouterLink>
    </div>

    <Timeline v-if="task || restoring" :task="task" />

    <section v-if="!task && !restoring" class="empty-card">
      <h2>还没有进行中的规划</h2>
      <p>去对话里把想去的城市与日期告诉我们，行程就会在这里一步步生成。</p>
      <button type="button" class="primary-button empty-cta" @click="goChat"><span>开始规划</span><span aria-hidden="true">→</span></button>
      <RouterLink class="secondary-link" to="/trips">或者查看我的行程</RouterLink>
    </section>

    <div v-if="connectionError && taskId" class="state-note error" role="alert">
      <strong>{{ connectionError.message }}</strong>
      <button type="button" class="text-button" @click="retryConnect">重试连接</button>
    </div>

    <section v-if="doneTrip && trip" class="result-card">
      <span class="mark" aria-hidden="true">✓</span>
      <div>
        <span class="eyebrow">{{ task?.status === 'degraded' ? '行程已生成 · 部分信息待确认' : '行程已生成' }}</span>
        <h2>{{ trip.plan?.title }}</h2>
        <p>{{ trip.plan?.summary }}</p>
        <p class="result-meta">{{ trip.request.destination }} · {{ trip.request.start_date }} — {{ trip.request.end_date }} · {{ trip.request.travelers }} 人 · 预算 {{ money(trip.request.budget_total) }}</p>
      </div>
      <button type="button" class="primary-button result-cta" @click="goDetail"><span>查看完整行程</span><span aria-hidden="true">→</span></button>
    </section>

    <section v-if="task?.status === 'failed'" class="state-note error">
      <strong>本次没能顺利排好行程</strong>
      <p>{{ task.message || '请返回对话调整需求后重试；也欢迎在我的行程中查看历史记录。' }}</p>
      <button type="button" class="primary-button result-cta" @click="goChat"><span>返回对话调整</span><span aria-hidden="true">→</span></button>
    </section>
  </main>
</template>

<style scoped>
.plan-page { max-width: 900px; margin: 0 auto; padding: 36px 24px 72px; }
.plan-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 24px; }
.plan-header h1 { font-size: 27px; font-weight: 500; margin: 8px 0 6px; line-height: 1.45; }
.plan-header p { margin: 0; color: var(--muted); font-size: 14px; }
.secondary-link { color: var(--green); font-size: 13px; text-decoration: none; border-bottom: 1px solid #c3d2bd; white-space: nowrap; }
.empty-card { text-align: center; padding: 60px 24px; background: var(--surface); border: 1px dashed #d5dfd1; border-radius: 20px; }
.empty-card h2 { font-weight: 500; font-size: 22px; margin: 0 0 10px; }
.empty-card p { color: var(--muted); font-size: 14px; margin: 0 0 22px; }
.empty-cta { width: auto; margin: 0 auto 18px; padding: 11px 22px; }
.state-note { margin-top: 18px; padding: 18px 22px; border-radius: 14px; border: 1px solid #ecd2b8; background: #fff6eb; color: #8f4426; font-size: 14px; }
.state-note.error strong { font-weight: 500; }
.state-note p { margin: 6px 0 12px; font-size: 13px; }
.text-button { background: none; border: none; color: var(--green); font-size: 13px; }
.result-card { margin-top: 22px; display: grid; grid-template-columns: auto 1fr auto; gap: 18px; align-items: center; background: var(--surface); border: 1px solid #dfe7d6; border-radius: 20px; padding: 26px 28px; }
.result-card .mark { width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center; background: #e2efe0; color: #35633c; font-size: 16px; }
.result-card h2 { font-size: 21px; font-weight: 500; margin: 6px 0 6px; }
.result-card p { margin: 0; font-size: 13px; color: var(--muted); line-height: 1.7; }
.result-meta { margin-top: 6px; }
.result-cta { width: auto; margin-top: 0; min-height: 46px; padding: 10px 20px; }
@media (max-width: 640px) { .result-card { grid-template-columns: auto 1fr; } .result-cta { grid-column: 1 / -1; } }
</style>
