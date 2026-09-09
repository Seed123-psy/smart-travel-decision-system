<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { PlanItem, RouteSegment, TripDetail } from '../types/planning'

const props = defineProps<{ trip: TripDetail }>()
const selectedDay = ref(0)
const failedImages = ref<Set<string>>(new Set())
watch(() => props.trip.trip_id, () => { selectedDay.value = 0; failedImages.value = new Set() })

const day = computed(() => props.trip.plan?.days[selectedDay.value])
const planWarnings = computed(() => [...new Set([
  ...(props.trip.validation?.warnings || []), ...(props.trip.budget?.warnings || []),
])])
const money = (value: string) => new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY' }).format(Number(value))
const text = (value: unknown) => typeof value === 'string' || typeof value === 'number' ? String(value) : ''
const segmentFor = (itemId: string): RouteSegment | undefined => day.value?.segments.find(segment => segment.to_item_id === itemId)
const imgFailed = (item: PlanItem) => !item.photo || failedImages.value.has(item.id)
const markFailed = (item: PlanItem) => { failedImages.value = new Set(failedImages.value).add(item.id) }

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
const grade = (item: PlanItem) => {
  const parts: string[] = []
  if (item.rating != null) parts.push(`★ ${item.rating.toFixed(1)} 高德评分`)
  if (item.cost != null) parts.push(`人均约 ¥${Math.round(item.cost)}`)
  return parts.join(' · ')
}
</script>

<template>
  <section v-if="trip.plan" class="trip-plan" aria-labelledby="itinerary-heading">
    <div class="plan-head">
      <span class="eyebrow">行程建议</span>
      <h2 id="itinerary-heading">{{ trip.plan.title }}</h2>
      <p class="plan-summary">{{ trip.plan.summary }}</p>
      <p class="trip-meta">{{ trip.request.start_date }} — {{ trip.request.end_date }} · {{ trip.request.travelers }} 人 · {{ trip.request.destination }}</p>
    </div>

    <div class="budget-card">
      <div class="budget-main"><span class="budget-label">目的地游玩预算</span><strong>{{ money(trip.request.budget_total) }}<small> / 全体出行人</small></strong></div>
      <span class="budget-status">尚未精算 · 不含往返大交通</span>
      <ul class="budget-lines">
        <li>人民币（CNY）；未知费用不按 0 元计算，目前不保证总花费在预算内。</li>
        <li v-if="trip.budget?.unknown_items.length">费用待确认：{{ trip.budget.unknown_items.join('、') }}</li>
      </ul>
    </div>

    <nav class="day-tabs" aria-label="选择行程日期">
      <button v-for="(entry, index) in trip.plan.days" :key="entry.date" type="button" :aria-pressed="selectedDay === index" @click="selectedDay = index">
        <span>{{ trip.plan && trip.plan.days.length > 1 ? `第 ${index + 1} 天` : '行程' }}</span><small>{{ entry.date.slice(5) }}</small>
      </button>
    </nav>

    <section v-if="day" class="day-content" :aria-label="day.date + ' 的行程'">
      <div class="weather-strip"><span class="weather-ico" aria-hidden="true">☼</span><div><span class="weather-title">天气参考</span><p>{{ weatherSummary }}</p></div></div>
      <p v-if="day.warnings.length" class="day-warning">{{ day.warnings[0] }}</p>

      <ol class="itinerary-list">
        <li v-for="(item, index) in day.items" :key="item.id" class="stop-card">
          <div v-if="imgFailed(item)" class="stop-media placeholder" aria-hidden="true">{{ item.name.slice(0, 1) }}</div>
          <img v-else class="stop-media" :src="item.photo || ''" :alt="item.name" loading="lazy" referrerpolicy="no-referrer" @error="markFailed(item)" />
          <div class="stop-main">
            <div class="stop-heading">
              <span class="stop-number">{{ String(index + 1).padStart(2, '0') }}</span>
              <div class="stop-id">
                <span class="stop-time">{{ item.start_time.slice(0, 5) }} — {{ item.end_time.slice(0, 5) }}</span>
                <h3>{{ item.name }}</h3>
              </div>
              <span class="opening-chip" :class="{ open: item.opening_status === 'verified' }">{{ item.opening_status === 'verified' ? '有营业依据' : '营业待确认' }}</span>
            </div>
            <p v-if="item.address" class="stop-address">{{ item.address }}</p>
            <p class="stop-reason">{{ item.reason }}</p>
            <p v-if="grade(item)" class="grade" title="高德数据服务展示值，为参考而非当日票价或消费承诺">{{ grade(item) }}</p>
            <div v-if="segmentFor(item.id)" class="route-mini" :class="{ conflict: segmentFor(item.id)!.status === 'conflict' }">
              <span aria-hidden="true">⇄</span>
              <template v-if="segmentFor(item.id)!.status === 'verified' || segmentFor(item.id)!.status === 'conflict'">
                <span>步行衔接约 {{ Math.ceil(segmentFor(item.id)!.duration_seconds! / 60) }} 分钟 · {{ Math.round(segmentFor(item.id)!.distance_meters!) }} 米</span>
              </template>
              <span v-if="segmentFor(item.id)!.status === 'conflict'"> · 到达偏晚，存在衔接冲突</span>
              <span v-else-if="segmentFor(item.id)!.status === 'unknown'"> · 路线尚未核实</span>
              <span v-if="segmentFor(item.id)!.message" class="route-msg">{{ segmentFor(item.id)!.message }}</span>
            </div>
          </div>
        </li>
      </ol>
      <p v-if="!day.items.length" class="empty-note">当天尚无可展示的安排，请查看下方注意事项。</p>
    </section>

    <section v-if="trip.plan.hotel" class="hotel-card">
      <span class="eyebrow">住宿参考</span>
      <template v-if="trip.plan.hotel.photo && !failedImages.has('hotel')">
        <img class="hotel-img" :src="trip.plan.hotel.photo" alt="" loading="lazy" referrerpolicy="no-referrer" @error="failedImages = new Set(failedImages).add('hotel')" />
      </template>
      <div class="hotel-main">
        <h3>{{ trip.plan.hotel.name }}</h3>
        <p v-if="trip.plan.hotel.address">{{ trip.plan.hotel.address }}</p>
        <p>{{ trip.plan.hotel.rooms }} 间 · {{ trip.plan.hotel.nights }} 晚 · 价格与可订状态待确认</p>
        <p v-if="trip.plan.hotel.rating != null || trip.plan.hotel.cost != null" class="grade" title="高德数据服务展示值，为参考而非当日票价或消费承诺">
          <template v-if="trip.plan.hotel.rating != null">★ {{ trip.plan.hotel.rating.toFixed(1) }} 高德评分</template><template v-if="trip.plan.hotel.rating != null && trip.plan.hotel.cost != null"> · </template><template v-if="trip.plan.hotel.cost != null">人均约 ¥{{ Math.round(trip.plan.hotel.cost) }}</template>
        </p>
      </div>
    </section>
    <p v-else class="no-hotel">{{ trip.request.rooms === 0 ? '本次为当天往返，无需安排住宿。' : '本次未取得可展示的住宿候选，请自行核实。' }}</p>

    <section class="risk-section" aria-labelledby="risk-heading">
      <h3 id="risk-heading">出发前，请再确认</h3>
      <ul class="warning-list">
        <li>各景点的游览时长与衔接仅为建议，不构成营业、预约或入场保证。</li>
        <li>尚未精算费用，未知费用不按 0 元计算，现不能保证总花费在预算内。</li>
        <li>天气、路线与营业信息保留生成时点；出发前请以实时信息为准。</li>
        <li v-for="(warning, index) in planWarnings" :key="index">{{ warning }}</li>
      </ul>
    </section>
  </section>
</template>

<style scoped>
.trip-plan { overflow-wrap: anywhere; }
.plan-head { padding: 6px 0 0; }
.plan-head h2 { font-size: 27px; line-height: 1.5; font-weight: 500; margin: 10px 0 8px; }
.plan-summary { font-size: 14px; color: var(--muted); margin: 0; line-height: 1.9; }
.trip-meta { font-size: 13px; color: #7a8b7e; margin: 10px 0 0; font-variant-numeric: tabular-nums; }
.budget-card { margin: 22px 0 8px; padding: 20px 24px; background: #f2f3e7; border: 1px solid #e0e3cc; border-radius: 16px; }
.budget-main { display: flex; flex-wrap: wrap; align-items: baseline; gap: 8px 16px; }
.budget-label { font-size: 13px; color: #67704f; }
.budget-main strong { font-size: 26px; font-weight: 500; color: #435740; font-variant-numeric: tabular-nums; }
.budget-main small { font-size: 12px; font-weight: 400; color: #7a8567; }
.budget-status { display: inline-block; margin: 8px 0 0; font-size: 12px; color: #7a6a3f; background: #efe9d6; border-radius: 20px; padding: 2px 10px; }
.budget-lines { list-style: none; margin: 12px 0 0; padding: 0; font-size: 12px; color: #67704f; line-height: 1.8; }
.day-tabs { display: flex; gap: 8px; overflow-x: auto; padding: 18px 0 6px; margin-bottom: 4px; }
.day-tabs button { flex: 0 0 auto; min-width: 84px; border: 1px solid #d7e0d1; border-radius: 12px; padding: 9px 14px; background: var(--surface); color: var(--muted); font-size: 13px; }
.day-tabs button small { display: block; font-size: 11px; margin-top: 2px; }
.day-tabs button[aria-pressed='true'] { background: var(--green); border-color: var(--green); color: var(--surface); }
.weather-strip { display: flex; gap: 12px; align-items: flex-start; background: #eef4ec; border-radius: 14px; padding: 12px 16px; margin: 12px 0; }
.weather-ico { font-size: 18px; line-height: 1.4; }
.weather-title { font-size: 12px; color: #466349; font-weight: 500; }
.weather-strip p { margin: 2px 0 0; font-size: 13px; color: var(--muted); }
.day-warning { font-size: 13px; color: #9a6a2f; background: #faf2e2; border-radius: 10px; padding: 8px 14px; }
.itinerary-list { list-style: none; margin: 16px 0 6px; padding: 0; display: flex; flex-direction: column; gap: 14px; }
.stop-card { display: flex; gap: 16px; background: var(--surface); border: 1px solid var(--line); border-radius: 16px; padding: 14px; }
.stop-media { flex-shrink: 0; width: 118px; height: 96px; object-fit: cover; border-radius: 12px; background: #eef2e8; }
.stop-media.placeholder { display: grid; place-items: center; font-size: 34px; color: #7b9a7f; border: 1px solid #e2e8dc; }
.stop-main { flex: 1; min-width: 0; }
.stop-heading { display: flex; align-items: flex-start; gap: 12px; }
.stop-number { flex-shrink: 0; display: grid; place-items: center; width: 34px; height: 40px; border: 1px solid #d7e1d0; border-radius: 11px 4px; color: #637f5d; background: #f0f4e9; font-size: 12px; font-variant-numeric: tabular-nums; }
.stop-id { flex: 1; min-width: 0; }
.stop-time { font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }
.stop-id h3 { margin: 2px 0 0; font-size: 19px; font-weight: 500; line-height: 1.4; }
.opening-chip { flex-shrink: 0; font-size: 12px; color: #876b36; border: 1px solid #e4d7bb; border-radius: 20px; padding: 2px 10px; }
.opening-chip.open { color: #3c633f; border-color: #c6d8be; background: #eef4ea; }
.stop-address { color: var(--muted); font-size: 12px; margin: 8px 0 0; }
.stop-reason { font-size: 13px; line-height: 1.8; margin: 7px 0 0; color: #4c6052; }
.grade { margin: 6px 0 0; font-size: 12px; color: #8a6a2f; }
.route-mini { display: flex; flex-wrap: wrap; gap: 4px 8px; align-items: center; margin-top: 8px; background: #f5f6ef; border: 1px solid #e7ead9; border-radius: 10px; padding: 8px 12px; color: var(--muted); font-size: 12px; }
.route-mini.conflict { background: #fbf3e0; border-color: #ecdcb2; }
.route-msg { width: 100%; }
.hotel-card { display: flex; gap: 16px; align-items: stretch; background: #eef3e9; border: 1px solid #dbe6d3; border-radius: 16px; padding: 18px 20px; margin: 18px 0 0; }
.hotel-card > .eyebrow { position: absolute; }
.hotel-card h3 { font-size: 17px; font-weight: 500; margin: 2px 0 6px; color: #3f5b43; }
.hotel-img { flex-shrink: 0; width: 150px; height: 104px; object-fit: cover; border-radius: 12px; }
.hotel-main { flex: 1; min-width: 0; padding-top: 22px; }
.hotel-main p { margin: 4px 0 0; font-size: 12px; color: #5a6e51; }
.no-hotel { color: var(--muted); font-size: 13px; background: #f4f6f0; border-radius: 12px; padding: 14px 18px; margin: 16px 0 0; }
.risk-section { margin: 24px 0 4px; background: #fbf7ec; border: 1px solid #eee2c6; border-radius: 16px; padding: 18px 20px; }
.risk-section h3 { font-size: 16px; font-weight: 500; margin: 0 0 10px; color: #7a6333; }
.warning-list { padding-left: 19px; color: #836333; font-size: 13px; margin: 0; }
.warning-list li + li { margin-top: 6px; }
.empty-note { font-size: 13px; color: var(--muted); }
@media (max-width: 540px) { .stop-card { flex-direction: column; } .stop-media { width: 100%; height: 150px; } .hotel-card { flex-direction: column; } .hotel-img { width: 100%; height: 160px; } .plan-head h2 { font-size: 24px; } }
</style>
