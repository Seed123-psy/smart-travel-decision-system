<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import AgentOverview from '../components/AgentOverview.vue'
import ServiceReadiness from '../components/ServiceReadiness.vue'
import PlanningWorkspace from '../components/PlanningWorkspace.vue'
import { ApiError, validateRequirements } from '../api/client'
import type { TravelPace, ValidationResponse } from '../types/travel'
import type { PlanningTask } from '../types/planning'

const form = reactive({
  origin: '',
  destination: '',
  startDate: '',
  endDate: '',
  travelers: 2,
  budgetTotal: '',
  pace: '均衡' as TravelPace,
  rooms: '',
  confirmed: false,
})
const loading = ref(false)
const error = ref<ApiError | null>(null)
const result = ref<ValidationResponse | null>(null)
const resultElement = ref<HTMLElement | null>(null)
const errorElement = ref<HTMLElement | null>(null)
const planningBusy = ref(false)
const planningTask = ref<PlanningTask | null>(null)
const validationSubmitted = ref(false)
const currentStep = computed(() => planningTask.value && ['ready', 'degraded'].includes(planningTask.value.status) ? 3 : planningBusy.value ? 2 : 1)

// Calendar inputs follow the same timezone as the server, including on other host timezones.
const today = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
}).format(new Date())

const tripDays = computed(() => {
  if (!form.startDate || !form.endDate) return null
  return Math.round((Date.parse(form.endDate) - Date.parse(form.startDate)) / 86_400_000) + 1
})
const suggestedRooms = computed(() => tripDays.value === 1 ? 0 : Math.ceil(Number(form.travelers) / 2))
const confirmedRooms = computed(() => form.rooms === '' ? suggestedRooms.value : Number(form.rooms))
const roomSummary = computed(() => !form.startDate || !form.endDate
  ? '当天往返 0 间；多日按每 2 人 1 间建议'
  : `${confirmedRooms.value} 间${form.rooms === '' ? '（建议值）' : ''}`)
const fieldLabels: Record<string, string> = {
  request: '旅行需求',
  origin: '出发城市', destination: '目的地', start_date: '出发日期', end_date: '结束日期',
  travelers: '出行人数', budget_total: '目的地总预算', rooms: '房间数', daily_window: '每日活动时段',
  defaults_confirmed: '费用范围与默认设置',
}
const money = (value: string) => new Intl.NumberFormat('zh-CN', {
  style: 'currency', currency: 'CNY', minimumFractionDigits: 2,
}).format(Number(value))

watch(form, () => {
  result.value = null
  error.value = null
  validationSubmitted.value = false
})
watch(() => [
  form.origin, form.destination, form.startDate, form.endDate,
  form.travelers, form.budgetTotal, form.rooms, form.pace,
], () => {
  form.confirmed = false
})

async function submit() {
  if (loading.value || planningBusy.value || !form.confirmed) return
  loading.value = true
  error.value = null
  result.value = null
  validationSubmitted.value = false
  try {
    result.value = await validateRequirements({
      origin: form.origin.trim(),
      destination: form.destination.trim(),
      start_date: form.startDate,
      end_date: form.endDate,
      travelers: Number(form.travelers),
      budget_total: form.budgetTotal.trim(),
      currency: 'CNY',
      budget_scope: 'destination_only',
      defaults_confirmed: true,
      pace: form.pace,
      styles: [],
      hotel_preference: '不限',
      daily_window: { start: '09:00', end: '18:00' },
      ...(form.rooms !== '' ? { rooms: Number(form.rooms) } : {}),
    }, import.meta.env.VITE_API_BASE_URL || '/api')
    await nextTick()
    resultElement.value?.focus()
  } catch (caught) {
    error.value = caught instanceof ApiError ? caught : new ApiError({
      code: 'UNEXPECTED_ERROR', message: '需求检查暂时失败，请重试。',
    })
    await nextTick()
    errorElement.value?.focus()
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main id="main-content" class="page-shell">
    <section class="hero" aria-labelledby="page-title">
      <div class="hero-copy">
        <span class="eyebrow">从一次清晰的出发开始</span>
        <h1 id="page-title">把期待写下来，<br />把旅途交给<span>好计划。</span></h1>
        <p>告诉我们去哪、和谁、花多少。让时间、路线与预算，成为旅行的底气。</p>
      </div>
      <div class="hero-note">
        <span class="hero-note-icon" aria-hidden="true">↗</span>
        <span class="eyebrow">当前进展</span>
        <strong>{{ planningBusy ? '好计划，正在路上' : '从需求到行程' }}</strong>
        <p>真实 Agent 协作<br />行程保存在本机</p>
      </div>
    </section>

    <ol class="steps" aria-label="旅行规划步骤">
      <li :class="{ 'step-current': currentStep === 1 }" :aria-current="currentStep === 1 ? 'step' : undefined"><span>01</span>填写与确认</li>
      <li :class="{ 'step-current': currentStep === 2 }" :aria-current="currentStep === 2 ? 'step' : undefined"><span>02</span>协作规划</li>
      <li :class="{ 'step-current': currentStep === 3 }" :aria-current="currentStep === 3 ? 'step' : undefined"><span>03</span>查看行程</li>
    </ol>

    <div class="workspace-grid">
      <section class="form-card" aria-labelledby="requirements-heading">
        <div class="section-topline"><span class="eyebrow">旅行需求</span><span class="quiet-label">带 * 为必填</span></div>
        <h2 id="requirements-heading">这次，想去哪里？</h2>
        <p class="section-description">首版支持中国大陆的单个目的地城市。</p>

        <form @submit.prevent="submit">
          <fieldset :disabled="loading || planningBusy" class="form-fields">
            <legend class="visually-hidden">填写旅行基本信息</legend>
            <div class="field-grid">
              <div class="field">
                <label for="origin">出发城市 <span aria-hidden="true">*</span></label>
                <input id="origin" v-model="form.origin" name="origin" placeholder="例如：上海" required maxlength="80" autocomplete="off" />
              </div>
              <div class="field">
                <label for="destination">目的地城市 <span aria-hidden="true">*</span></label>
                <input id="destination" v-model="form.destination" name="destination" placeholder="例如：杭州" required maxlength="80" autocomplete="off" />
              </div>
              <div class="field">
                <label for="start-date">出发日期 <span aria-hidden="true">*</span></label>
                <input id="start-date" v-model="form.startDate" name="start_date" type="date" :min="today" required />
              </div>
              <div class="field">
                <label for="end-date">结束日期 <span aria-hidden="true">*</span></label>
                <input id="end-date" v-model="form.endDate" name="end_date" type="date" :min="form.startDate || today" required aria-describedby="date-hint" />
                <span id="date-hint" class="field-hint">含出发与结束日，最多 7 天</span>
              </div>
              <div class="field">
                <label for="travelers">出行人数 <span aria-hidden="true">*</span></label>
                <div class="input-with-unit"><input id="travelers" v-model.number="form.travelers" name="travelers" type="number" min="1" max="10" step="1" required /><span>人</span></div>
              </div>
              <div class="field">
                <label for="budget">目的地总预算 <span aria-hidden="true">*</span></label>
                <div class="input-with-unit"><input id="budget" v-model="form.budgetTotal" name="budget_total" inputmode="decimal" pattern="[0-9]+(\.[0-9]{1,2})?" placeholder="例如：6000.00" required aria-describedby="budget-hint" /><span>元</span></div>
                <span id="budget-hint" class="field-hint">全体出行人合计，人民币（CNY）</span>
              </div>
            </div>

            <div class="budget-note"><span aria-hidden="true">¥</span><p><strong>预算算清楚，出行更安心</strong>包括目的地门票、住宿、餐饮、市内交通等费用；<b>不含往返城市间的飞机、火车等大交通。</b></p></div>

            <details class="preferences">
              <summary>旅行偏好与住宿<span>可选设置</span></summary>
              <div class="field-grid preferences-fields">
                <div class="field"><label for="pace">行程节奏</label><select id="pace" v-model="form.pace"><option>均衡</option><option>休闲</option><option>紧凑</option></select></div>
                <div class="field"><label for="rooms">房间数</label><input id="rooms" v-model="form.rooms" type="number" min="0" :max="form.travelers" step="1" :placeholder="String(suggestedRooms)" aria-describedby="rooms-hint" /><span id="rooms-hint" class="field-hint">留空采用建议值；无需住宿填 0</span></div>
              </div>
            </details>

            <div class="defaults-summary">
              <p><strong>本次采用的设置</strong></p>
              <p>活动时段 09:00–18:00（北京时间） · {{ form.pace }}节奏</p>
              <p>住宿 {{ roomSummary }} · 住宿偏好与游玩风格不限</p>
            </div>
            <label class="confirmation" for="confirm-scope">
              <input id="confirm-scope" v-model="form.confirmed" type="checkbox" required />
              <span>我已确认以上设置，以及<b>全体出行人的目的地总预算</b>口径。</span>
            </label>

            <button class="primary-button" type="submit" :disabled="!form.confirmed || loading || planningBusy"><span>{{ loading ? '正在检查需求…' : planningBusy ? '规划任务进行中' : '检查并确认需求' }}</span><span aria-hidden="true">→</span></button>
            <p class="submit-note">先检查输入，再确认联网规划与本地保存。</p>
          </fieldset>
        </form>

        <div v-if="error" ref="errorElement" class="feedback feedback-error" role="alert" tabindex="-1">
          <strong>{{ error.message }}</strong>
          <ul v-if="error.details.length"><li v-for="(detail, index) in error.details" :key="index">{{ fieldLabels[detail.field] || detail.field }}：{{ detail.message }}</li></ul>
          <span v-if="error.requestId" class="field-hint">请求编号：{{ error.requestId }}</span>
        </div>

        <section v-if="result && !validationSubmitted" ref="resultElement" class="feedback feedback-success" tabindex="-1" aria-labelledby="confirmation-heading" aria-live="polite">
          <span class="eyebrow">需求检查通过</span>
          <h3 id="confirmation-heading">{{ result.request.origin }} → {{ result.request.destination }}</h3>
          <dl class="result-grid">
            <div><dt>出行日期</dt><dd>{{ result.request.start_date }} 至 {{ result.request.end_date }}</dd></div>
            <div><dt>人数 / 住宿</dt><dd>{{ result.request.travelers }} 人 · {{ result.request.rooms }} 间房</dd></div>
            <div><dt>目的地总预算</dt><dd>{{ money(result.request.budget_total) }} / 全体出行人</dd></div>
            <div><dt>节奏 / 每日活动</dt><dd>{{ result.request.pace }} · {{ result.request.daily_window.start }}–{{ result.request.daily_window.end }}</dd></div>
          </dl>
          <p>人民币（CNY），不含往返城市间大交通。尚未完成费用精算。</p>
          <ul v-if="result.warnings.length"><li v-for="warning in result.warnings" :key="warning">{{ warning }}</li></ul>
          <p class="result-next">以上为本次校验结果。请在下方确认后开始生成行程。</p>
        </section>
        <p v-if="result && validationSubmitted" class="field-hint">本次需求已提交。请在下方查看任务进展与保存的行程。</p>
      </section>

      <aside class="side-column">
        <ServiceReadiness />
        <AgentOverview v-if="!planningTask && !planningBusy" />
        <section class="principles-card" aria-labelledby="principles-heading"><span class="eyebrow">有依据，才放心</span><h2 id="principles-heading">让不确定，也清清楚楚。</h2><p>无法确认的价格不会记作零元；未知的天气或营业信息会明确标注。旅行建议，将保留来源与时间。</p><span class="principle-line" aria-hidden="true"></span><p class="privacy-note">字段检查只使用本地服务。确认规划后，必要的旅行字段将发送给已配置的模型与数据服务。</p></section>
      </aside>
    </div>
    <PlanningWorkspace :request="result?.request || null" @busy="planningBusy = $event" @task="planningTask = $event" @submitted="validationSubmitted = true" />
  </main>
</template>
