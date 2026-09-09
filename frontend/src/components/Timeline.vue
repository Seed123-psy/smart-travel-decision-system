<script setup lang="ts">
import { computed } from 'vue'
import type { AgentRun, PlanningTask } from '../types/planning'

const props = defineProps<{ task: PlanningTask | null }>()

const statusHeader = computed(() => {
  const task = props.task
  if (!task) return '正在恢复最近的任务…'
  if (task.status === 'queued') return '任务排队中，即将开始'
  if (task.status === 'ready') return '行程已生成'
  if (task.status === 'degraded') return '已生成，部分信息需出行前确认'
  if (task.status === 'failed') return '本次没能顺利排好'
  switch (task.stage) {
    case 'validating': return '正在检查你的需求'
    case 'collecting': return '正在查找目的地的真实信息'
    case 'planning': return '正在按你的节奏编排每日行程'
    case 'checking': return '正在核对时间衔接与步行路线'
    default: return '正在保存你的行程'
  }
})
const live = computed(() => !!props.task && !['ready', 'degraded', 'failed'].includes(props.task.status))

const latest = computed<AgentRun[]>(() => {
  const runs = props.task?.agents || []
  const byName = new Map<string, AgentRun>()
  for (const run of runs) {
    const existing = byName.get(run.agent_name)
    if (!existing || run.attempt > existing.attempt) byName.set(run.agent_name, run)
  }
  const order = ['attractions', 'hotel', 'weather', 'opening', 'planner']
  return order.map(name => byName.get(name)).filter((run): run is AgentRun => !!run)
})

function count(run: AgentRun): number | null {
  const value = run.summary?.candidate_count
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : null
}
function agentLine(run: AgentRun): string {
  const n = count(run)
  switch (run.agent_name) {
    case 'attractions':
      if (run.status === 'running') return '正在挑选值得一去的景点'
      if (run.status === 'failed') return '候选景点暂时没查到，不会补造结果'
      return n !== null ? `找到 ${n} 个真实候选，价格与营业信息仍待核实` : '已取得候选景点，价格与营业信息仍待核实'
    case 'hotel':
      if (run.status === 'running') return '正在匹配住宿'
      if (run.status === 'skipped') return '当天往返，无需住宿'
      if (run.status === 'failed') return '住宿候选查询未成功'
      if (run.status === 'degraded') return '住宿候选信息不足，请自行核实'
      return n !== null ? `给出 ${n} 个住宿候选，价格与可订状态待确认` : '给出住宿候选，价格与可订状态待确认'
    case 'weather':
      if (run.status === 'running') return '正在查询天气预报'
      if (run.status === 'failed') return '天气预报查询失败'
      if (run.status === 'degraded') return '部分日期暂无可用预报，请临近出发再查'
      return n !== null && n > 0 ? `已拿到行程中 ${n} 天的预报` : '已查询天气预报'
    case 'opening':
      if (run.status === 'running') return '正在核实景点的营业资料'
      if (run.status === 'failed') return '营业资料查询未成功'
      if (run.status === 'degraded') return '部分营业资料未核实，出发前请再确认'
      return n !== null ? `核实了 ${n} 个地点的营业资料，当日开放仍请出发前确认` : '已核实营业资料'
    default:
      if (run.status === 'running') return '正在编排每日行程与衔接'
      if (run.status === 'failed') return '行程编排遇到问题，可调整后重试'
      if (run.status === 'degraded') return '行程已编排，部分衔接信息待确认'
      return '每日行程已编排完成'
  }
}
</script>

<template>
  <section class="timeline" :aria-busy="live" aria-live="polite" aria-label="规划进展">
    <header class="timeline-header" :class="{ live: live, warn: task?.status === 'degraded', fail: task?.status === 'failed' }">
      <span v-if="live" class="pulse" aria-hidden="true"></span>
      <span v-else-if="task?.status === 'ready'" class="mark" aria-hidden="true">✓</span>
      <span v-else-if="task?.status === 'degraded'" class="mark warn-mark" aria-hidden="true">!</span>
      <span v-else-if="task?.status === 'failed'" class="mark fail-mark" aria-hidden="true">✕</span>
      <strong>{{ statusHeader }}</strong>
    </header>

    <ol class="timeline-list">
      <li v-for="(run, index) in latest" :key="`${run.agent_name}-${run.attempt}`"
        :class="['tl-step', `tl-${run.status}`, { done: run.status === 'succeeded', warn: run.status === 'degraded' }]">
        <span class="tl-dot" aria-hidden="true">{{ index + 1 }}</span>
        <div class="tl-body">
          <span class="tl-time">{{ run.started_at ? new Date(run.started_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : '' }}</span>
          <p>{{ agentLine(run) }}</p>
        </div>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.timeline { background: var(--surface); border: 1px solid #e2e7dc; border-radius: 20px; padding: 24px 28px; }
.timeline-header { display: flex; align-items: center; gap: 12px; font-size: 17px; margin-bottom: 8px; }
.timeline-header strong { font-weight: 500; color: var(--ink); }
.timeline-header.live { color: var(--green); }
.pulse { width: 10px; height: 10px; border-radius: 50%; background: #4f8a71; animation: pulse 1.4s ease-in-out infinite; }
@keyframes pulse { 0%, 100% { opacity: .3; } 50% { opacity: 1; } }
.mark { width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; background: #e2efe0; color: #35633c; font-size: 14px; }
.mark.warn-mark { background: #f7ecd8; color: #8a6a2f; }
.mark.fail-mark { background: #fae7da; color: #a34c2a; }
.timeline-list { list-style: none; margin: 14px 0 0; padding: 0; }
.tl-step { display: flex; gap: 14px; position: relative; padding-bottom: 22px; }
.tl-step:not(:last-child)::before { content: ''; position: absolute; left: 15px; top: 32px; bottom: 4px; width: 1px; background: #dbe3d6; }
.tl-step.tl-running .tl-dot { background: #dcebdc; border-color: #729580; color: var(--green); }
.tl-step.tl-succeeded .tl-dot { background: #e8f1e3; border-color: #c4d6bd; color: #4e7a4e; }
.tl-step.tl-failed .tl-dot { background: #fae7da; border-color: #e6c2a9; color: #a34c2a; }
.tl-dot { flex-shrink: 0; width: 30px; height: 30px; border-radius: 50%; border: 1px solid #d9e1d3; display: grid; place-items: center; background: #f4f7f0; font-size: 12px; font-variant-numeric: tabular-nums; color: #82927c; z-index: 1; }
.tl-body { flex: 1; min-width: 0; padding-top: 2px; }
.tl-body p { margin: 0; font-size: 14px; line-height: 1.7; color: var(--ink); }
.tl-step:not(.tl-running) .tl-body p { color: var(--muted); }
.tl-time { font-size: 11px; color: #a7b2a8; display: block; margin-bottom: 3px; }
</style>
