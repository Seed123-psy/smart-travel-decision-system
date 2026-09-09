<script setup lang="ts">
import { computed } from 'vue'
import { useSharedPlanning } from '../composables/planningContext'
import { currentTrip } from '../stores/currentTrip'
import ServiceReadiness from './ServiceReadiness.vue'
import AgentOverview from './AgentOverview.vue'
import { evidenceDocumentation } from '../api/evidence'
import type { EvidenceRef } from '../types/planning'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()
const planning = useSharedPlanning()
const { task, connectionError } = planning

const trip = computed(() => currentTrip.value || planning.trip.value)
const agents = computed(() => planning.task.value?.agents ?? [])
const text = (value: unknown) => typeof value === 'string' || typeof value === 'number' ? String(value) : ''
const evidenceLabels: Record<string, string> = { verified: '已核实', estimated: '估算', stale: '已过期', unknown: '待核实' }
const evidenceLabel = (source: Record<string, unknown>) => {
  const expiry = typeof source.expires_at === 'string' ? Date.parse(source.expires_at) : NaN
  return Number.isFinite(expiry) && expiry <= Date.now() ? '已过期' : evidenceLabels[text(source.status)] || '待核实'
}
const fetchedAt = (value: unknown) => {
  if (typeof value !== 'string' || Number.isNaN(Date.parse(value))) return ''
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', dateStyle: 'short', timeStyle: 'short' }).format(new Date(value))
}
const resolveRef = (value: EvidenceRef) => typeof value === 'string' ? trip.value?.plan?.evidence.find(entry => entry.id === value) : value
const dayItemSources = computed(() => {
  const plan = trip.value?.plan
  if (!plan) return []
  const entries: { day: string; name: string; refs: EvidenceRef[] }[] = []
  for (const day of plan.days) {
    for (const item of day.items) {
      if (item.evidence_refs.length) entries.push({ day: day.date, name: item.name, refs: item.evidence_refs })
    }
  }
  return entries
})
</script>

<template>
  <div v-if="open" class="dev-backdrop" @click.self="emit('close')">
    <aside class="dev-drawer" role="region" aria-label="调试面板" aria-live="polite">
      <header class="dev-header">
        <div>
          <strong>调试面板</strong>
          <span class="env-badge">本地开发版</span>
        </div>
        <button type="button" class="dev-close" @click="emit('close')" aria-label="关闭调试面板">×</button>
      </header>

      <section class="dev-section" aria-labelledby="svc-title">
        <h3 id="svc-title">服务配置</h3>
        <ServiceReadiness />
      </section>

      <section v-if="trip?.version" class="dev-section" aria-label="行程版本">
        <h3>行程版本</h3>
        <p class="dev-row">version {{ trip.version }} · trip_id <code>{{ trip.trip_id }}</code></p>
        <p v-if="trip.latest_task" class="dev-row">latest_task {{ trip.latest_task.task_id }}（{{ trip.latest_task.status }}）</p>
      </section>

      <section v-if="task || agents.length" class="dev-section" aria-labelledby="task-title">
        <h3 id="task-title">最近任务明细</h3>
        <template v-if="task">
          <p class="dev-row">task_id <code>{{ task.task_id }}</code></p>
          <p class="dev-row">status {{ task.status }} · stage {{ task.stage }}</p>
          <p v-if="task.error_code" class="dev-row">error_code <code>{{ task.error_code }}</code></p>
          <p v-if="task.message" class="dev-row">{{ task.message }}</p>
          <p v-if="connectionError" class="dev-row error">{{ connectionError.message }}</p>
        </template>
        <AgentOverview v-if="agents.length" :task="task" />
        <p v-else class="dev-empty">暂无执行中的任务。</p>
      </section>

      <section v-if="trip?.plan?.evidence?.length" class="dev-section" aria-labelledby="source-title">
        <h3 id="source-title">数据来源</h3>
        <p class="dev-note">保留生成时的查询记录；仅供开发者核对，页面不向游客展示接口细节。</p>
        <ul class="source-list">
          <li v-for="(source, index) in trip.plan.evidence" :key="index">
            <strong>{{ source.source === 'amap' ? '高德地图' : text(source.source) || '来源记录' }}<template v-if="text(source.label)"> · {{ text(source.label) }}</template></strong>
            <span> · {{ evidenceLabel(source) }}</span>
            <template v-if="typeof source === 'object' && source !== null">
              <p v-if="fetchedAt(text((source as Record<string, unknown>).fetched_at))">查询：{{ fetchedAt(text((source as Record<string, unknown>).fetched_at)) }}</p>
              <p v-if="fetchedAt(text((source as Record<string, unknown>).expires_at))">过期：{{ fetchedAt(text((source as Record<string, unknown>).expires_at)) }}</p>
              <p v-if="text((source as Record<string, unknown>).message)">{{ text((source as Record<string, unknown>).message) }}</p>
              <a v-if="evidenceDocumentation(source)" :href="evidenceDocumentation(source)!.url" target="_blank" rel="noopener noreferrer">{{ evidenceDocumentation(source)!.label }} ↗</a>
            </template>
          </li>
        </ul>
      </section>

      <section v-if="dayItemSources.length" class="dev-section" aria-labelledby="item-source-title">
        <h3 id="item-source-title">条目数据依据</h3>
        <ul class="source-list">
          <li v-for="entry in dayItemSources" :key="`${entry.day}:${entry.name}`">
            <strong>{{ entry.day }} · {{ entry.name }}</strong>
            <p v-for="(ref, refIndex) in entry.refs" :key="refIndex">
              → {{ (() => { const r = resolveRef(ref); return r ? `${text(r.source) || '来源'} · ${evidenceLabel(r)}` : '来源待核实' })() }}
            </p>
          </li>
        </ul>
      </section>
    </aside>
  </div>
</template>

<style scoped>
.dev-backdrop { position: fixed; inset: 0; background: #263f3808; z-index: 50; display: flex; justify-content: flex-end; }
.dev-drawer { width: min(460px, 94vw); height: 100%; overflow-y: auto; background: var(--surface); border-left: 1px solid var(--line); box-shadow: -12px 0 40px #263f3814; padding: 22px 24px 40px; }
.dev-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-bottom: 16px; border-bottom: 1px solid var(--line); }
.dev-header strong { font-size: 17px; font-weight: 500; }
.env-badge { display: inline-flex; align-items: center; gap: 7px; color: var(--green); font-size: 11px; background: #eaf0e5; padding: 4px 10px; border-radius: 20px; margin-left: 8px; }
.env-badge::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: #548976; }
.dev-close { border: none; background: none; font-size: 24px; color: var(--muted); line-height: 1; padding: 4px 8px; }
.dev-section { margin-top: 24px; }
.dev-section h3 { font-size: 13px; font-weight: 500; color: #43604b; margin: 0 0 10px; letter-spacing: .02em; }
.dev-row { font-size: 12px; color: var(--muted); margin: 3px 0; overflow-wrap: anywhere; line-height: 1.7; }
.dev-row code { background: #eef2e9; border-radius: 6px; padding: 1px 6px; font-size: 11px; color: #2f5a44; }
.dev-row.error { color: #a34c2a; }
.dev-empty, .dev-note { font-size: 12px; color: var(--muted); }
.source-list { list-style: none; margin: 8px 0 0; padding: 0; font-size: 12px; color: var(--muted); }
.source-list li { border-top: 1px dashed #e2e7dc; padding: 10px 0; }
.source-list strong { color: var(--ink); font-weight: 500; }
.source-list p { margin: 3px 0; overflow-wrap: anywhere; }
.source-list a { color: var(--green); }
</style>
