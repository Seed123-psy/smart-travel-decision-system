<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ApiError } from '../api/client'
import { searchFlights } from '../api/flights'
import { iataCities, iataToLabel, type FlightOffer, type FlightSearchQuery, type FlightSearchResult } from '../types/flights'
import { todayShanghai } from '../utils/tripRules'

const today = todayShanghai()
const roundTrip = ref(true)
const form = reactive({ origin: 'PVG', destination: 'HGH', departDate: '', returnDate: '', adults: 1 })
const loading = ref(false)
const error = ref<ApiError | null>(null)
const result = ref<FlightSearchResult | null>(null)
const controllerRef = ref<AbortController | null>(null)

watch(() => form.departDate, date => {
  if (form.returnDate && date && form.returnDate < date) form.returnDate = date
})

const canSearch = computed(() => form.origin.trim().length === 3 && form.destination.trim().length === 3
  && form.origin.trim().toUpperCase() !== form.destination.trim().toUpperCase()
  && !!form.departDate && form.departDate >= today
  && (!roundTrip.value || (!!form.returnDate && form.returnDate >= form.departDate)))

async function run() {
  if (!canSearch.value || loading.value) return
  controllerRef.value?.abort()
  const controller = new AbortController()
  controllerRef.value = controller
  loading.value = true
  error.value = null
  result.value = null
  const query: FlightSearchQuery = {
    origin: form.origin.trim().toUpperCase(), destination: form.destination.trim().toUpperCase(),
    depart_date: form.departDate, return_date: roundTrip.value ? form.returnDate : null, adults: form.adults,
  }
  try {
    result.value = await searchFlights(query, { signal: controller.signal })
  } catch (caught) {
    if (caught instanceof ApiError && caught.code === 'REQUEST_CANCELLED') return
    error.value = caught instanceof ApiError ? caught : new ApiError({ code: 'UNEXPECTED_ERROR', message: '航班查询失败，请重试。' })
  } finally {
    if (!controller.signal.aborted) loading.value = false
  }
}
function swap() {
  const from = form.origin
  form.origin = form.destination
  form.destination = from
}
function reset() { result.value = null; error.value = null }

const displayName = (code: string) => iataToLabel(code)
const legTime = (offer: FlightOffer) => `${offer.depart.time} ${offer.depart.iata} → ${offer.arrive.time} ${offer.arrive.iata}`
const mins = (offer: FlightOffer) => {
  const h = Math.floor(offer.duration_minutes / 60); const m = offer.duration_minutes % 60
  return h ? `${h}小时${m ? ` ${m}分` : ''}` : `${m}分`
}
const fare = (offer: FlightOffer) => `¥${Math.round(offer.price.amount).toLocaleString('zh-CN')}`
</script>

<template>
  <main id="main-content" class="flights-page">
    <section class="flights-hero">
      <div class="flights-copy">
        <span class="eyebrow">行前参考</span>
        <h1>往返航班，先看个大概</h1>
        <p>查询往返航班的价格与时刻，为出发做预算参考。机票费用单独计列，<b>不占用目的地的游玩预算</b>。</p>
      </div>

      <div class="search-card">
        <div class="trip-toggle" role="group" aria-label="行程类型">
          <button type="button" :class="{ active: !roundTrip }" @click="roundTrip = false">单程</button>
          <button type="button" :class="{ active: roundTrip }" @click="roundTrip = true">往返</button>
        </div>
        <form class="search-form" @submit.prevent="run">
          <div class="city-pair">
            <label class="field-label" for="fl-origin">出发
              <select id="fl-origin" v-model="form.origin">
                <option v-for="city in iataCities" :key="city.code" :value="city.code">{{ city.label }} {{ city.code }}</option>
              </select>
            </label>
            <button type="button" class="swap-btn" aria-label="交换出发与到达" @click="swap">⇄</button>
            <label class="field-label" for="fl-dest">到达
              <select id="fl-dest" v-model="form.destination">
                <option v-for="city in iataCities" :key="city.code" :value="city.code">{{ city.label }} {{ city.code }}</option>
              </select>
            </label>
          </div>
          <div class="date-pair">
            <label class="field-label" for="fl-depart">去程
              <input id="fl-depart" v-model="form.departDate" type="date" :min="today" required />
            </label>
            <label v-if="roundTrip" class="field-label" for="fl-return">返程
              <input id="fl-return" v-model="form.returnDate" type="date" :min="form.departDate || today" required />
            </label>
            <label class="field-label" for="fl-adults">人数
              <select id="fl-adults" v-model.number="form.adults">
                <option v-for="n in 9" :key="n" :value="n">{{ n }} 人</option>
              </select>
            </label>
          </div>
          <button class="primary-button search-cta" type="submit" :disabled="!canSearch || loading">
            <span>{{ loading ? '正在查询…' : '查询航班' }}</span><span aria-hidden="true">→</span>
          </button>
        </form>
      </div>
    </section>

    <section v-if="error" class="flights-note error" role="alert">
      <strong>{{ error.message }}</strong>
    </section>

    <section v-if="result" class="result-zone" aria-live="polite">
      <div class="result-head">
        <div>
          <span class="eyebrow">{{ displayName(result.origin) }} → {{ displayName(result.destination) }}</span>
          <h2>{{ result.depart_date }}<template v-if="result.return_date"> — {{ result.return_date }}</template> · {{ result.adults }} 人</h2>
        </div>
        <span v-if="result.mode === 'demo'" class="mode-badge demo">演示数据</span>
        <span v-else class="mode-badge">实时报价</span>
      </div>
      <p v-if="result.mode === 'demo'" class="demo-note">{{ result.summary }}</p>
      <p v-else class="demo-note">{{ result.summary }}</p>

      <h3 class="leg-heading">去程</h3>
      <ul class="offer-list">
        <li v-for="(offer, index) in result.outbound" :key="'out' + index">
          <div class="offer-route"><span class="airline">{{ offer.airline }}</span><span class="flight-no">{{ offer.flight_number }}</span><span class="times">{{ legTime(offer) }}</span></div>
          <div class="offer-meta"><span>{{ mins(offer) }}</span><span v-if="offer.stops === 0">直飞</span><span v-else>经停 {{ offer.stops }} 次</span></div>
          <div class="offer-price">{{ fare(offer) }}</div>
        </li>
      </ul>

      <template v-if="result.return_date && result.inbound?.length">
        <h3 class="leg-heading">返程</h3>
        <ul class="offer-list">
          <li v-for="(offer, index) in result.inbound" :key="'in' + index">
            <div class="offer-route"><span class="airline">{{ offer.airline }}</span><span class="flight-no">{{ offer.flight_number }}</span><span class="times">{{ legTime(offer) }}</span></div>
            <div class="offer-meta"><span>{{ mins(offer) }}</span><span v-if="offer.stops === 0">直飞</span><span v-else>经停 {{ offer.stops }} 次</span></div>
            <div class="offer-price">{{ fare(offer) }}</div>
          </li>
        </ul>
      </template>

      <p class="scope-note">查询结果仅作行前参考，<b>不构成预订或出票</b>；票价实时变化，请以航司/票务平台为准。此金额不并入目的地游玩预算。</p>
      <button type="button" class="reset-link" @click="reset">← 重新查询</button>
    </section>
  </main>
</template>

<style scoped>
.flights-page { max-width: 960px; margin: 0 auto; padding: 34px 24px 80px; }
.flights-hero { margin-bottom: 26px; }
.flights-copy h1 { font-size: 28px; font-weight: 500; margin: 8px 0 8px; }
.flights-copy p { color: var(--muted); font-size: 14px; margin: 0 0 22px; }
.flights-copy b { font-weight: 500; color: #4f6044; }
.search-card { background: var(--surface); border: 1px solid #e2e7dc; border-radius: 20px; padding: 22px 24px; box-shadow: 0 8px 32px #273f3005; }
.trip-toggle { display: inline-flex; border: 1px solid #d8e1d3; border-radius: 30px; overflow: hidden; margin-bottom: 16px; }
.trip-toggle button { border: none; background: var(--surface); padding: 8px 20px; font-size: 13px; color: var(--muted); }
.trip-toggle button.active { background: var(--green); color: #fff; }
.search-form { display: flex; flex-direction: column; gap: 14px; }
.city-pair { display: grid; grid-template-columns: 1fr auto 1fr; gap: 12px; align-items: end; }
.date-pair { display: grid; grid-template-columns: 1fr 1fr auto; gap: 12px; align-items: end; }
.field-label { display: block; font-size: 12px; color: var(--muted); }
.field-label select, .field-label input { display: block; width: 100%; height: 48px; margin-top: 6px; border: 1px solid #d5dfd1; border-radius: 12px; padding: 0 14px; font-size: 16px; background: var(--surface); color: var(--ink); }
.swap-btn { height: 44px; width: 40px; border: 1px solid #d5dfd1; border-radius: 12px; background: var(--surface); color: var(--green); font-size: 17px; }
.search-cta { width: auto; margin-top: 4px; align-self: flex-end; min-height: 48px; padding: 11px 26px; }
.flights-note { padding: 20px 24px; border-radius: 14px; font-size: 14px; }
.flights-note.error { background: #fff3e9; border: 1px solid #ecd2b8; color: #8f4426; }
.result-zone { margin-top: 26px; }
.result-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.result-head h2 { font-size: 22px; font-weight: 500; margin: 6px 0 0; }
.mode-badge { font-size: 12px; padding: 4px 12px; border-radius: 20px; }
.mode-badge.demo { background: #faf0de; color: #8a6a2f; border: 1px solid #e5d3ad; }
.mode-badge:not(.demo) { background: #e5efe1; color: #38603c; border: 1px solid #cbdcc4; }
.demo-note { color: var(--muted); font-size: 13px; margin: 8px 0 0; }
.leg-heading { font-size: 15px; font-weight: 500; color: #43574a; margin: 22px 0 8px; }
.offer-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.offer-list li { display: flex; align-items: center; gap: 16px; background: var(--surface); border: 1px solid var(--line); border-radius: 14px; padding: 14px 18px; }
.offer-route { flex: 1; min-width: 0; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.airline { font-size: 14px; color: var(--ink); }
.flight-no { font-size: 12px; color: var(--muted); }
.times { font-size: 15px; font-variant-numeric: tabular-nums; color: var(--green); }
.offer-meta { font-size: 12px; color: var(--muted); display: flex; gap: 10px; }
.offer-price { font-size: 20px; font-variant-numeric: tabular-nums; color: #a34c2a; font-weight: 500; white-space: nowrap; }
.scope-note { font-size: 12px; color: var(--muted); margin: 18px 0 8px; line-height: 1.8; }
.reset-link { background: none; border: none; color: var(--green); font-size: 13px; }
@media (max-width: 640px) { .date-pair { grid-template-columns: 1fr 1fr; } .city-pair { grid-template-columns: 1fr auto 1fr; } }
</style>
