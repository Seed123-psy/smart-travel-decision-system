<script setup lang="ts">
import { computed } from 'vue'
import type { AgentName, AgentStatus, PlanningTask } from '../types/planning'

const props = defineProps<{ task?: PlanningTask | null; compact?: boolean }>()
const roles: { name: AgentName; label: string; description: string }[] = [
  { name: 'attractions', label: '景点 Agent', description: '寻找有依据的候选景点' },
  { name: 'hotel', label: '住宿 Agent', description: '结合人数与住宿需求筛选' },
  { name: 'weather', label: '天气 Agent', description: '核实预报范围与天气风险' },
  { name: 'opening', label: '营业状态 Agent', description: '核实候选景点营业信息' },
  { name: 'planner', label: 'Planner', description: '汇总真实查询结果，编排行程' },
]
const statusLabels: Record<AgentStatus, string> = {
  queued: '等待中', running: '执行中', succeeded: '已完成', degraded: '部分信息缺失', failed: '失败', skipped: '无需执行',
}
const agents = computed(() => roles.map(role => {
  const runs = props.task?.agents.filter(agent => agent.agent_name === role.name) || []
  return { ...role, run: [...runs].sort((a, b) => b.attempt - a.attempt)[0] }
}))
const duration = (milliseconds: number) => milliseconds < 1_000 ? `${Math.round(milliseconds)} 毫秒` : `${(milliseconds / 1_000).toFixed(1)} 秒`
</script>

<template>
  <section class="agent-section" :class="{ 'agent-compact': compact }" aria-labelledby="agents-heading">
    <div class="section-topline"><span class="eyebrow">协作过程</span><span class="quiet-label">{{ task ? '真实执行记录' : '尚未启动' }}</span></div>
    <h2 id="agents-heading">每个决定，都有分工</h2>
    <p class="section-description">{{ task ? '记录本次任务的状态、耗时与查询摘要。' : '确认需求后，在这里查看每个 Agent 的实际进展。' }}</p>
    <ol class="agent-list">
      <li v-for="(agent, index) in agents" :key="agent.name" :class="{ 'agent-running': agent.run?.status === 'running' }">
        <span class="agent-number" aria-hidden="true">{{ String(index + 1).padStart(2, '0') }}</span>
        <div>
          <h3>{{ agent.label }}</h3>
          <p>{{ agent.run?.summary.message || agent.description }}</p>
          <p v-if="agent.run?.duration_ms != null" class="run-detail">耗时 {{ duration(agent.run.duration_ms) }}<template v-if="agent.run.attempt > 1"> · 第 {{ agent.run.attempt }} 次尝试</template></p>
          <p v-if="agent.run?.summary.candidate_count != null" class="run-detail">候选 {{ agent.run.summary.candidate_count }} 项</p>
          <p v-if="agent.run?.summary.tools?.length" class="run-detail">查询工具：{{ agent.run.summary.tools.join('、') }}</p>
          <p v-if="agent.run?.evidence_refs.length" class="run-detail">依据 {{ agent.run.evidence_refs.length }} 条</p>
          <p v-if="agent.run?.error_code" class="run-detail">{{ agent.run.error_code }}</p>
        </div>
        <span class="pending-label" :class="agent.run ? `status-${agent.run.status}` : ''">{{ agent.run ? statusLabels[agent.run.status] : '尚未运行' }}</span>
      </li>
    </ol>
    <p class="agent-footnote">路线由确定性服务校验，费用尚未精算；执行完成不代表营业和交通条件均已确认。</p>
  </section>
</template>

<style scoped>
.agent-list .run-detail { margin-top: 5px; font-size: 12px; overflow-wrap: anywhere; }
.agent-running .agent-number { background: #dcebdc; border-color: #729580; color: var(--green); }
.status-running { background: #e6f0e4; border-color: #8ea48b; color: var(--green); }
.status-succeeded { background: #eff4ea; color: #385e3e; }
.status-degraded, .status-failed { background: #faf2e5; border-color: #dfc9a6; color: #87622c; }
.agent-compact { padding: 8px 0 0; }
.agent-compact .agent-list { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 12px; margin: 18px 0 14px; }
.agent-compact .agent-list li { display: flex; flex-direction: column; align-items: flex-start; gap: 10px; padding: 16px; margin: 0; border: 1px solid #dce5d5; border-radius: 12px; background: #f8faf3; }
.agent-compact .agent-list li > div { min-width: 0; width: 100%; }
.agent-compact .agent-list li.agent-running { border-color: #88a980; background: #f0f6e9; }
.agent-compact .pending-label { margin: auto 0 0; }
.agent-compact .agent-list p { overflow-wrap: anywhere; }
@media (max-width: 1100px) { .agent-compact .agent-list { grid-template-columns: repeat(3, minmax(0, 1fr)); } }
@media (max-width: 820px) { .agent-compact .agent-list { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 540px) { .agent-compact .agent-list { grid-template-columns: minmax(0, 1fr); } }
</style>
