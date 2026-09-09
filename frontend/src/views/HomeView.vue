<script setup lang="ts">
import { computed } from 'vue'
import { useSharedPlanning } from '../composables/planningContext'
import { isTerminalTask } from '../api/planning'

const planning = useSharedPlanning()
const running = computed(() => !!planning.taskId.value && !!planning.task.value && !isTerminalTask(planning.task.value.status))
const recent = computed(() => planning.history.value.slice(0, 3))
const inspirations = ['杭州', '三亚', '成都', '西安', '厦门', '昆明']
const money = (value: string) => new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(Number(value))
</script>

<template>
  <main id="main-content" class="page-shell home">
    <section class="hero home-hero" aria-labelledby="home-title">
      <div class="hero-copy">
        <span class="eyebrow">把期待写下来，把旅途交给好计划</span>
        <h1 id="home-title">从一次清晰的出发开始，<br />把时间、路线与预算，<span>交给行知。</span></h1>
        <p>用几句对话告诉我们想去哪、和谁、花多少。剩下的——城市怎么逛、天气怎么看、预算怎么花，交给行知一点一点帮你排好。</p>
        <div class="hero-actions">
          <RouterLink class="primary-button hero-cta" to="/plan/chat"><span>开始规划你的旅行</span><span aria-hidden="true">→</span></RouterLink>
          <RouterLink class="secondary-link" to="/flights">先查往返航班</RouterLink>
        </div>
        <p class="hero-hint">不用一次填完，对话会一步步问：目的地 · 日期 · 人数 · 预算 · 节奏</p>
      </div>
      <aside class="inspire-card" aria-labelledby="inspire-title">
        <span class="eyebrow">今天想去哪</span>
        <h2 id="inspire-title">由灵感开始</h2>
        <ul class="inspire-list">
          <li v-for="city in inspirations" :key="city">
            <RouterLink :to="{ name: 'plan-chat', query: { destination: city } }">{{ city }}<span aria-hidden="true">↗</span></RouterLink>
          </li>
        </ul>
      </aside>
    </section>

    <RouterLink v-if="running" class="running-banner" to="/plan">
      <span class="running-dot" aria-hidden="true"></span>
      <span>已有一个行程正在生成，<b>查看进展 ↗</b></span>
    </RouterLink>

    <section class="module-grid" aria-label="行知能做什么">
      <RouterLink class="module-card" to="/plan/chat">
        <span class="module-index" aria-hidden="true">01</span>
        <h2>对话式规划</h2>
        <p>像和旅行顾问聊天一样，说出想去哪、玩几天、多少人。行知把零散的想法整理成清晰的需求，再给出有据可依的排期。</p>
        <span class="module-link">开始对话 <span aria-hidden="true">→</span></span>
      </RouterLink>
      <RouterLink class="module-card" to="/trips">
        <span class="module-index" aria-hidden="true">02</span>
        <h2>图文行程 · 本机保存</h2>
        <p>每天的安排、地点实景、天气与步行衔接都整理成卡片；行程自动保存在本机，随时回看，不丢灵感。</p>
        <span class="module-link">查看我的行程 <span aria-hidden="true">→</span></span>
      </RouterLink>
      <RouterLink class="module-card" to="/flights">
        <span class="module-index" aria-hidden="true">03</span>
        <h2>往返航班参考</h2>
        <p>出发前先看大交通：查询往返航班的价格与时刻，做行前预算参考。机票单独计列，不影响目的地游玩预算。</p>
        <span class="module-link">查询航班 <span aria-hidden="true">→</span></span>
      </RouterLink>
    </section>

    <section class="trust-band" aria-labelledby="trust-title">
      <div class="trust-copy">
        <span class="eyebrow">有依据，才放心</span>
        <h2 id="trust-title">让不确定，也清清楚楚</h2>
        <p>没法确认的价格，不会记成零元；未知的天气或营业时间，会明确提示你先去核实。每一条建议，都保留来源与查询时间，供你对照当下情况判断。</p>
      </div>
      <ul class="trust-points">
        <li><strong>不虚构</strong><span>拿不到的数据会如实告知</span></li>
        <li><strong>可解释</strong><span>每条安排都能说清依据</span></li>
        <li><strong>更从容</strong><span>预算、天气、路线一次理清</span></li>
      </ul>
    </section>

    <section v-if="recent.length" class="recent-section" aria-labelledby="recent-title">
      <div class="section-topline">
        <div><span class="eyebrow">留在本机的旅途</span><h2 id="recent-title">最近行程</h2></div>
        <RouterLink class="secondary-link" to="/trips">全部行程</RouterLink>
      </div>
      <ul class="recent-list">
        <li v-for="entry in recent" :key="entry.trip_id">
          <RouterLink :to="{ name: 'trip-detail', params: { tripId: entry.trip_id } }">
            <span class="recent-name">{{ entry.destination }}<span class="recent-status">{{ entry.status === 'ready' ? '已生成' : entry.status === 'degraded' ? '部分信息待确认' : '规划未完成' }}</span></span>
            <span class="recent-meta">{{ entry.start_date }} — {{ entry.end_date }} · {{ entry.travelers }} 人 · 预算 {{ money(entry.budget_total) }}</span>
          </RouterLink>
        </li>
      </ul>
    </section>
  </main>
</template>

<style scoped>
.home-hero { align-items: flex-start; padding-bottom: 42px; }
.hero-actions { display: flex; align-items: center; gap: 22px; margin-top: 26px; flex-wrap: wrap; }
.primary-button { width: auto; margin-top: 0; min-height: 50px; padding: 12px 22px; }
.hero-cta { max-width: none; display: inline-flex; text-decoration: none; }
.secondary-link { color: var(--green); font-size: 14px; text-decoration: none; border-bottom: 1px solid #c3d2bd; }
.hero-hint { margin: 14px 0 0; font-size: 12px; }
.inspire-card { flex-shrink: 0; width: 250px; background: var(--surface); border: 1px solid #e2e7dc; border-radius: 20px; padding: 26px 26px 18px; box-shadow: 0 8px 32px #273f3005; }
.inspire-card h2 { font-size: 22px; font-weight: 500; margin: 10px 0 16px; }
.inspire-list { list-style: none; margin: 0; padding: 0; }
.inspire-list a { display: flex; justify-content: space-between; align-items: center; text-decoration: none; color: var(--ink); font-size: 15px; padding: 11px 4px; border-bottom: 1px dashed #e2e7dc; }
.inspire-list a:hover { color: var(--green); }
.inspire-list span { color: var(--green); font-size: 14px; }
.running-banner { display: flex; align-items: center; gap: 12px; text-decoration: none; color: var(--green); background: #e9f1e6; border: 1px solid #cfddc8; border-radius: 14px; padding: 15px 20px; margin: 4px 0 26px; font-size: 14px; }
.running-banner b { font-weight: 500; }
.running-dot { width: 8px; height: 8px; border-radius: 50%; background: #4f8a71; animation: pulse-dot 1.4s ease-in-out infinite; }
@keyframes pulse-dot { 0%, 100% { opacity: .35; } 50% { opacity: 1; } }
.module-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 22px; margin: 30px 0 40px; }
.module-card { display: block; text-decoration: none; color: var(--ink); background: var(--surface); border: 1px solid #e2e7dc; border-radius: 20px; padding: 26px 26px 22px; box-shadow: 0 8px 32px #273f3005; }
.module-card:hover { border-color: #a9bfa2; transform: translateY(-2px); }
.module-index { font-size: 12px; color: #7b9a7f; font-variant-numeric: tabular-nums; letter-spacing: .12em; }
.module-card h2 { font-size: 20px; font-weight: 500; margin: 12px 0 10px; }
.module-card p { font-size: 13px; line-height: 1.9; color: var(--muted); margin: 0 0 18px; }
.module-link { font-size: 14px; color: var(--green); font-weight: 500; }
.trust-band { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(0, 1fr); gap: 36px; align-items: center; background: #e9efe2; border: 1px solid #d9e4d1; border-radius: 22px; padding: 34px 38px; margin-bottom: 44px; }
.trust-copy h2 { font-size: 24px; font-weight: 500; margin: 10px 0 12px; }
.trust-copy p { font-size: 14px; line-height: 1.95; color: #4e644c; margin: 0; }
.trust-points { list-style: none; margin: 0; padding: 0; display: grid; gap: 18px; }
.trust-points li { display: flex; flex-direction: column; gap: 3px; padding: 14px 18px; background: #f6f8f0; border-radius: 14px; }
.trust-points strong { font-size: 16px; font-weight: 500; color: #35543f; }
.trust-points span { font-size: 12px; color: var(--muted); }
.recent-section { margin-top: 6px; }
.section-topline { display: flex; align-items: flex-end; justify-content: space-between; gap: 16px; }
.recent-section h2 { margin: 6px 0 0; }
.recent-list { list-style: none; margin: 20px 0 0; padding: 0; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.recent-list a { display: block; text-decoration: none; border: 1px solid var(--line); border-radius: 14px; padding: 18px 20px; background: var(--surface); color: var(--ink); }
.recent-list a:hover { border-color: #95ae8f; background: #f4f7ef; }
.recent-name { display: flex; justify-content: space-between; align-items: center; gap: 8px; font-size: 16px; }
.recent-status { font-size: 12px; color: #6e7c62; }
.recent-meta { display: block; margin-top: 8px; color: var(--muted); font-size: 12px; }
@media (max-width: 1050px) { .trust-band { grid-template-columns: minmax(0, 1fr); gap: 22px; padding: 28px 26px; } }
@media (max-width: 900px) { .module-grid, .recent-list { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 820px) { .inspire-card { display: none; } .hero { align-items: flex-start; } }
@media (max-width: 540px) { .trust-points { grid-template-columns: minmax(0, 1fr); } .recent-list { grid-template-columns: minmax(0, 1fr); } }
</style>
