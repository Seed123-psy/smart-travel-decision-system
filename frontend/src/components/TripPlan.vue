<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { EvidenceRef, RouteSegment, TripDetail } from '../types/planning'
import { evidenceDocumentation } from '../api/evidence'

const props = defineProps<{ trip: TripDetail }>()
const selectedDay = ref(0)
watch(() => props.trip.trip_id, () => { selectedDay.value = 0 })
const day = computed(() => props.trip.plan?.days[selectedDay.value])
const warnings = computed(() => [...new Set([
  ...(props.trip.validation?.warnings || []), ...(props.trip.budget?.warnings || []),
])])
const money = (value: string) => new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(Number(value))
const text = (value: unknown) => typeof value === 'string' || typeof value === 'number' ? String(value) : ''
const evidenceLabels: Record<string, string> = { verified: '已核实', estimated: '估算', stale: '已过期', unknown: '待核实' }
const evidenceLabel = (source: Record<string, unknown>) => {
  const expiry = typeof source.expires_at === 'string' ? Date.parse(source.expires_at) : NaN
  return Number.isFinite(expiry) && expiry <= Date.now() ? '已过期' : evidenceLabels[text(source.status)] || '待核实'
}
const reference = (value: EvidenceRef) => {
  const source = typeof value === 'string' ? props.trip.plan?.evidence.find(entry => entry.id === value) : value
  return source ? `${text(source.source) || '来源记录'} · ${evidenceLabel(source)}` : '来源记录待核实'
}
const fetchedAt = (value: unknown) => {
  if (typeof value !== 'string' || Number.isNaN(Date.parse(value))) return ''
  return new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', dateStyle: 'short', timeStyle: 'short' }).format(new Date(value))
}
const segmentFor = (itemId: string): RouteSegment | undefined => day.value?.segments.find(segment => segment.to_item_id === itemId)
const weatherSummary = computed(() => {
  const weather = day.value?.weather
  if (!weather) return '当前日期暂无可用天气信息，请临近出发再次核实。'
  const dayWeather = text(weather.day_weather)
  const nightWeather = text(weather.night_weather)
  const high = text(weather.day_temperature_celsius ?? weather.day_temp)
  const low = text(weather.night_temperature_celsius ?? weather.night_temp)
  if (dayWeather || nightWeather || high || low) return [
    dayWeather ? `白天${dayWeather}` : '', nightWeather ? `夜间${nightWeather}` : '',
    high ? `日间 ${high}°C` : '', low ? `夜间 ${low}°C` : '',
  ].filter(Boolean).join(' · ')
  const fields = ['summary', 'message', 'dayweather', 'nightweather', 'weather', 'temperature', 'daytemp', 'nighttemp']
  const values = fields.map(key => text(weather[key])).filter(Boolean)
  return values.length ? [...new Set(values)].join(' · ') : '已有天气查询记录，出行条件仍需结合预报有效期核实。'
})
</script>

<template>
  <section v-if="trip.plan" class="trip-plan" aria-labelledby="itinerary-heading">
    <div class="plan-title"><span class="eyebrow">行程建议 · 已保存本机</span><span class="version">版本 {{ trip.version }}</span></div>
    <h2 id="itinerary-heading">{{ trip.plan.title }}</h2>
    <p class="plan-summary">{{ trip.plan.summary }}</p>
    <p class="trip-meta">{{ trip.request.start_date }} — {{ trip.request.end_date }} · {{ trip.request.travelers }} 人 · {{ trip.request.destination }}</p>
    <p class="trip-meta">天气与路线保留生成时的数据；查看历史不会重新查询，请留意来源有效期。</p>
    <div class="budget-summary">
      <div><span>目的地总预算上限</span><strong>{{ money(trip.request.budget_total) }}<small> / 全体出行人</small></strong></div>
      <span class="budget-status">尚未完成费用精算</span>
      <p>人民币（CNY），不含往返城市间大交通。费用未知不能视为免费；当前不保证总费用在预算内。</p>
      <p v-if="trip.budget?.unknown_items.length">待确认：{{ trip.budget.unknown_items.join('、') }}</p>
    </div>
    <nav class="day-tabs" aria-label="选择行程日期">
      <button v-for="(entry, index) in trip.plan.days" :key="entry.date" type="button" :aria-pressed="selectedDay === index" @click="selectedDay = index">
        <span>第 {{ index + 1 }} 天</span><small>{{ entry.date.slice(5) }}</small>
      </button>
    </nav>
    <section v-if="day" class="day-content" :aria-label="day.date + ' 的行程'">
      <div class="weather-note"><strong>天气参考</strong><p>{{ weatherSummary }}</p></div>
      <ul v-if="day.warnings.length" class="warning-list"><li v-for="(warning, index) in day.warnings" :key="index">{{ warning }}</li></ul>
      <ol class="itinerary-list">
        <li v-for="(item, index) in day.items" :key="item.id">
          <div v-if="segmentFor(item.id)" class="route-note">
            <span>步行衔接</span>
            <template v-if="segmentFor(item.id)?.status === 'verified' || segmentFor(item.id)?.status === 'conflict'">
              <span v-if="segmentFor(item.id)?.duration_seconds != null">约 {{ Math.ceil(segmentFor(item.id)!.duration_seconds! / 60) }} 分钟</span>
              <span v-if="segmentFor(item.id)?.distance_meters != null">{{ Math.round(segmentFor(item.id)!.distance_meters!) }} 米</span>
            </template>
            <span v-if="segmentFor(item.id)?.status === 'conflict'">存在衔接冲突</span>
            <span v-else-if="segmentFor(item.id)?.status === 'unknown'">路线尚未核实</span>
            <p v-if="segmentFor(item.id)?.message">{{ segmentFor(item.id)?.message }}</p>
          </div>
          <div class="stop-heading"><span class="stop-number">{{ String(index + 1).padStart(2, '0') }}</span><div><span class="stop-time">{{ item.start_time.slice(0, 5) }} — {{ item.end_time.slice(0, 5) }}</span><h3>{{ item.name }}</h3></div></div>
          <p v-if="item.address" class="stop-address">{{ item.address }}</p>
          <p>{{ item.reason }}</p>
          <span class="opening-status">{{ item.opening_status === 'verified' ? '已有营业依据，出发前请再次确认' : '营业信息待确认' }}</span>
          <details v-if="item.evidence_refs.length" class="item-evidence"><summary>查看数据依据（{{ item.evidence_refs.length }}）</summary><ul><li v-for="(ref, refIndex) in item.evidence_refs" :key="refIndex">{{ reference(ref) }}</li></ul></details>
        </li>
      </ol>
      <p v-if="!day.items.length" class="empty-note">当天尚无可展示的安排，请查看风险说明。</p>
    </section>
    <section class="hotel-note" aria-labelledby="hotel-heading"><h3 id="hotel-heading">住宿参考</h3><template v-if="trip.plan.hotel"><strong>{{ trip.plan.hotel.name }}</strong><p>{{ trip.plan.hotel.address }}</p><p>{{ trip.plan.hotel.rooms }} 间 · {{ trip.plan.hotel.nights }} 晚 · 价格与可订状态待确认</p></template><p v-else>{{ trip.request.rooms === 0 ? '本次无需安排住宿。' : '本次未获得可展示的住宿候选，请自行核实。' }}</p></section>
    <section class="risk-section" aria-labelledby="risk-heading"><h3 id="risk-heading">出发前，请再确认</h3><ul class="warning-list"><li v-for="(warning, index) in warnings" :key="index">{{ warning }}</li><li>行程为建议安排，未知的营业、价格和交通条件仍需确认。</li><li>当前提供文字行程与来源记录；互动地图和 PDF 导出尚未接入。</li></ul></section>
    <details class="source-list">
      <summary>来源记录（{{ trip.plan.evidence.length }}）</summary>
      <p>以下保留生成时的查询记录；说明链接介绍数据来源，出行信息仍请以当天实际情况为准。</p>
      <ul v-if="trip.plan.evidence.length">
        <li v-for="(source, index) in trip.plan.evidence" :key="index">
          <strong>{{ source.source === 'amap' ? '高德地图' : text(source.source) || '来源记录' }}<template v-if="text(source.label)"> · {{ text(source.label) }}</template></strong>
          <span v-if="text(source.status)"> · {{ evidenceLabel(source) }}</span>
          <p v-if="fetchedAt(source.fetched_at)">查询时间：{{ fetchedAt(source.fetched_at) }}（北京时间）</p>
          <p v-if="fetchedAt(source.expires_at)">有效期至：{{ fetchedAt(source.expires_at) }}（北京时间）</p>
          <p v-if="text(source.message)">{{ text(source.message) }}</p>
          <a v-if="evidenceDocumentation(source)" :href="evidenceDocumentation(source)!.url" target="_blank" rel="noopener noreferrer">{{ evidenceDocumentation(source)!.label }} ↗</a>
        </li>
      </ul>
      <p v-else>本次没有可展示的来源记录，请结合风险说明使用建议。</p>
    </details>
  </section>
</template>

<style scoped>
.trip-plan { margin-top: 28px; padding-top: 28px; border-top: 1px solid var(--line); overflow-wrap: anywhere; }
.plan-title { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.version, .trip-meta { font-size: 12px; color: var(--muted); }
.trip-plan h2 { font-size: 26px; line-height: 1.55; font-weight: 500; margin: 14px 0; }
.plan-summary { font-size: 14px; color: var(--muted); margin: 0; }
.budget-summary { display: flex; flex-wrap: wrap; gap: 12px 18px; align-items: center; padding: 20px; background: #f2f3e7; border: 1px solid #e0e3cc; border-radius: 12px; margin: 22px 0; }
.budget-summary > div { flex: 1; min-width: 170px; }
.budget-summary span, .budget-summary p { font-size: 12px; color: #67704f; }
.budget-summary strong { display: block; font-size: 23px; font-weight: 500; color: #435740; }
.budget-summary small { font-size: 12px; font-weight: 400; }
.budget-summary .budget-status { border: 1px solid #d5d8ba; padding: 3px 8px; border-radius: 20px; }
.budget-summary p { width: 100%; margin: 0; }
.day-tabs { display: flex; gap: 8px; overflow-x: auto; padding-bottom: 10px; margin: 24px 0 12px; }
.day-tabs button { flex: 0 0 auto; min-width: 79px; border: 1px solid #d7e0d1; border-radius: 10px; padding: 9px 14px; background: var(--surface); color: var(--muted); font-size: 13px; }
.day-tabs button small { display: block; font-size: 11px; margin-top: 2px; }
.day-tabs button[aria-pressed='true'] { background: var(--green); border-color: var(--green); color: var(--surface); }
.weather-note { border-left: 3px solid #adc6ad; padding-left: 14px; margin: 18px 0; font-size: 13px; color: var(--muted); }
.weather-note strong { color: #466349; font-weight: 500; }
.weather-note p { margin: 3px 0 0; }
.itinerary-list { list-style: none; margin: 24px 0; padding: 0; }
.itinerary-list > li { border-bottom: 1px solid var(--line); padding: 0 0 24px; margin-bottom: 24px; font-size: 14px; }
.stop-heading { display: flex; align-items: center; gap: 14px; }
.stop-number { display: grid; place-items: center; width: 36px; height: 42px; border: 1px solid #d7e1d0; border-radius: 12px 4px; color: #637f5d; background: #f0f4e9; font-size: 12px; }
.stop-time { font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }
.stop-heading h3 { margin: 2px 0 0; font-size: 19px; font-weight: 500; }
.stop-address { color: var(--muted); font-size: 12px; }
.opening-status { display: inline-block; font-size: 12px; color: #876b36; border: 1px solid #e4d7bb; border-radius: 20px; padding: 2px 9px; }
.route-note { display: flex; flex-wrap: wrap; gap: 4px 12px; background: #f5f5ee; padding: 10px 14px; border-radius: 8px; margin-bottom: 18px; color: var(--muted); font-size: 12px; }
.route-note p { width: 100%; margin: 0; }
.item-evidence { font-size: 12px; color: var(--muted); margin-top: 12px; }
.item-evidence ul { padding-left: 18px; }
.hotel-note { background: #eef3e9; padding: 18px 20px; border-radius: 12px; font-size: 13px; color: #5a6e51; }
.hotel-note h3, .risk-section h3 { font-size: 16px; font-weight: 500; margin: 0 0 10px; color: #3f5b43; }
.hotel-note p { margin: 5px 0 0; }
.hotel-note strong { font-weight: 500; }
.risk-section { margin: 24px 0; }
.warning-list { padding-left: 19px; color: #836333; font-size: 13px; }
.warning-list li + li { margin-top: 7px; }
.source-list { border-top: 1px solid var(--line); padding-top: 16px; color: var(--muted); font-size: 12px; }
.source-list > ul { list-style: none; margin: 16px 0 0; padding: 0; }
.source-list li + li { margin-top: 16px; }
.source-list p { margin: 4px 0; }
.source-list strong { font-weight: 500; color: var(--ink); }
.source-list a { color: var(--green); text-underline-offset: 3px; }
.empty-note { font-size: 13px; color: var(--muted); }
@media (max-width: 540px) { .trip-plan h2 { font-size: 23px; } .budget-summary { padding: 17px; } .day-tabs button { min-width: 70px; padding: 8px 11px; } }
</style>
