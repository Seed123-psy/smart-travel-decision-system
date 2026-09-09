<script setup lang="ts">
import { computed, reactive, ref, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError, validateRequirements } from '../api/client'
import { isTerminalTask } from '../api/planning'
import { useSharedPlanning } from '../composables/planningContext'
import { majorCities, tripDays, suggestRooms, todayShanghai, isValidCity } from '../utils/tripRules'
import type { TravelPace } from '../types/travel'

type StepId = 'origin' | 'destination' | 'dates' | 'travelers' | 'budget' | 'pace' | 'preferences' | 'confirm'
const stepOrder: StepId[] = ['origin', 'destination', 'dates', 'travelers', 'budget', 'pace', 'preferences', 'confirm']
const stepLabels: Record<StepId, string> = {
  origin: '从哪里出发', destination: '想去哪里', dates: '玩几天', travelers: '几个人去',
  budget: '预算多少', pace: '节奏怎么定', preferences: '还想补充吗', confirm: '确认需求',
}

const planning = useSharedPlanning()
const { task, busy, submissionError } = planning
const route = useRoute()
const router = useRouter()

const draft = reactive({
  origin: '', destination: '', startDate: '', endDate: '', travelers: 2, budgetTotal: '',
  pace: '均衡' as TravelPace, rooms: '', hotelPreference: '不限', styles: [] as string[],
})
const draftKey = 'xingzhi:wizard-draft'
const today = todayShanghai()
const stepIndex = ref(stepOrder.indexOf('origin'))
const validation = ref<Awaited<ReturnType<typeof validateRequirements>> | null>(null)
const validationError = ref<ApiError | null>(null)
const submitting = ref(false)
const submitted = ref(false)
const consent = ref(false)

const answered = computed(() => {
  const days = tripDays(draft.startDate, draft.endDate)
  return {
    origin: isValidCity(draft.origin),
    destination: isValidCity(draft.destination),
    dates: draft.startDate >= today && draft.endDate >= draft.startDate && days !== null && days >= 1 && days <= 7,
    travelers: Number.isInteger(draft.travelers) && draft.travelers >= 1 && draft.travelers <= 10,
    budget: /^\d{1,8}(\.\d{1,2})?$/.test(draft.budgetTotal) && Number(draft.budgetTotal) > 0,
    pace: true,
  }
})
const requiredDone = computed(() => answered.value.origin && answered.value.destination && answered.value.dates
  && answered.value.travelers && answered.value.budget)
const currentStep = computed(() => stepOrder[stepIndex.value])
const dayCount = computed(() => tripDays(draft.startDate, draft.endDate))
const suggestedRooms = computed(() => suggestRooms(dayCount.value, draft.travelers))
const roomText = computed(() => draft.rooms === '' ? `${suggestedRooms.value} 间（按建议）` : `${draft.rooms} 间`)
const money = (value: string) => new Intl.NumberFormat('zh-CN', { style: 'currency', currency: 'CNY', minimumFractionDigits: 2 }).format(Number(value))
const fieldLabels: Record<string, string> = {
  request: '旅行需求', origin: '出发城市', destination: '目的地', start_date: '出发日期',
  end_date: '结束日期', travelers: '出行人数', budget_total: '目的地总预算', rooms: '房间数',
  daily_window: '每日活动时段', defaults_confirmed: '费用范围与默认设置',
}

const stylesOptions = ['风景', '人文', '美食', '亲子', '摄影', '休闲', '购物', '建筑']

function loadDraft() {
  try {
    const raw = localStorage.getItem(draftKey)
    if (!raw) return
    const saved = JSON.parse(raw) as Partial<typeof draft>
    if (typeof saved.origin === 'string') draft.origin = saved.origin
    if (typeof saved.destination === 'string') draft.destination = saved.destination
    if (typeof saved.startDate === 'string') draft.startDate = saved.startDate
    if (typeof saved.endDate === 'string') draft.endDate = saved.endDate
    if (typeof saved.travelers === 'number' && saved.travelers >= 1 && saved.travelers <= 10) draft.travelers = saved.travelers
    if (typeof saved.budgetTotal === 'string') draft.budgetTotal = saved.budgetTotal
    if (saved.pace === '休闲' || saved.pace === '均衡' || saved.pace === '紧凑') draft.pace = saved.pace
    if (typeof saved.rooms === 'string') draft.rooms = saved.rooms
    if (typeof saved.hotelPreference === 'string') draft.hotelPreference = saved.hotelPreference
    if (Array.isArray(saved.styles)) draft.styles = saved.styles.filter((item): item is string => typeof item === 'string')
    // Resume at the first unanswered required step.
    const firstMissing = stepOrder.findIndex(id => {
      if (id === 'origin') return !answered.value.origin
      if (id === 'destination') return !answered.value.destination
      if (id === 'dates') return !answered.value.dates
      if (id === 'travelers') return !answered.value.travelers
      if (id === 'budget') return !answered.value.budget
      return false
    })
    stepIndex.value = firstMissing === -1 ? stepOrder.indexOf('confirm') : firstMissing
  } catch { /* ignore malformed drafts */ }
}
function persistDraft() {
  try { localStorage.setItem(draftKey, JSON.stringify(draft)) } catch { /* storage unavailable */ }
}
watch(draft, persistDraft, { deep: true })

function goto(id: StepId) {
  stepIndex.value = stepOrder.indexOf(id)
  if (validation.value) { validation.value = null; validationError.value = null }
}
function goBack() { if (stepIndex.value > 0) stepIndex.value -= 1 }
function next() { if (stepIndex.value < stepOrder.length - 1) stepIndex.value += 1 }
function askPreferences() { stepIndex.value = stepOrder.indexOf('preferences') }
function toConfirm() { stepIndex.value = stepOrder.indexOf('confirm') }
function enterAdvance() {
  const ok = currentStep.value === 'origin' ? answered.value.origin
    : currentStep.value === 'destination' ? answered.value.destination
      : currentStep.value === 'budget' ? answered.value.budget
        : currentStep.value === 'dates' ? answered.value.dates
          : currentStep.value === 'travelers' ? answered.value.travelers : false
  if (ok) next()
}
function setRooms(delta: number) {
  const base = draft.rooms === '' ? suggestedRooms.value : Number(draft.rooms)
  const next = Number.isNaN(base) ? (delta > 0 ? 1 : 0) : base + delta
  const clamped = Math.min(Math.max(next, 0), draft.travelers)
  draft.rooms = String(clamped)
}
function toggleStyle(option: string) {
  if (draft.styles.includes(option)) draft.styles = draft.styles.filter(item => item !== option)
  else if (draft.styles.length < 10) draft.styles = [...draft.styles, option]
}

async function checkAndSubmit() {
  if (!requiredDone.value || validation.value || submitting.value) return
  submitting.value = true
  validationError.value = null
  try {
    validation.value = await validateRequirements({
      origin: draft.origin.trim(), destination: draft.destination.trim(),
      start_date: draft.startDate, end_date: draft.endDate, travelers: draft.travelers,
      budget_total: draft.budgetTotal.trim(), currency: 'CNY', budget_scope: 'destination_only',
      defaults_confirmed: true, pace: draft.pace, styles: draft.styles,
      hotel_preference: draft.hotelPreference || '不限',
      daily_window: { start: '09:00', end: '18:00' },
      ...(draft.rooms !== '' ? { rooms: Number(draft.rooms) } : {}),
    }, import.meta.env.VITE_API_BASE_URL || '/api')
  } catch (caught) {
    validationError.value = caught instanceof ApiError ? caught : new ApiError({
      code: 'UNEXPECTED_ERROR', message: '需求检查暂时失败，请重试。',
    })
  } finally { submitting.value = false }
}

async function submitPlan() {
  if (!consent.value || !validation.value || submitting.value) return
  submitting.value = true
  try {
    await planning.generate(validation.value.request)
    if (planning.taskId.value && !planning.submissionError.value) {
      try { localStorage.removeItem(draftKey) } catch { /* noop */ }
      submitted.value = true
      await router.push('/plan')
      return
    }
  } finally { submitting.value = false }
}

const serverErrorDetail = computed(() => {
  if (!validationError.value) return []
  const errors = new Map<string, string>()
  for (const detail of validationError.value.details) {
    if (!errors.has(detail.field)) errors.set(detail.field, detail.message)
  }
  return [...errors.entries()].map(([field, message]) => ({ field, label: fieldLabels[field] || field, message }))
})

function restart() {
  try { localStorage.removeItem(draftKey) } catch { /* noop */ }
  Object.assign(draft, { origin: '', destination: '', startDate: '', endDate: '', travelers: 2, budgetTotal: '', pace: '均衡', rooms: '', hotelPreference: '不限', styles: [] })
  validation.value = null; validationError.value = null; consent.value = false; submitted.value = false
  stepIndex.value = stepOrder.indexOf('origin')
}

onMounted(() => {
  if (typeof route.query.destination === 'string' && route.query.destination.trim() && !draft.destination) {
    draft.destination = String(route.query.destination).slice(0, 80)
  }
  loadDraft()
})
</script>

<template>
  <main id="main-content" class="chat-shell">
    <div class="chat-header">
      <div class="chat-avatar" aria-hidden="true">行</div>
      <div>
        <h1>和行知聊聊这趟旅行</h1>
        <p>下面每步都只问一件事，回答完即可继续；随时可回上一步修改。</p>
      </div>
      <button type="button" class="restart-link" :disabled="submitting" @click="restart">重新开始</button>
    </div>

    <ol class="chat-progress" aria-label="问答进度">
      <li v-for="(id, index) in stepOrder" :key="id" :class="{ active: index === stepIndex, done: index < stepIndex }">
        <button type="button" :aria-current="index === stepIndex ? 'step' : undefined" :disabled="index > stepIndex" @click="goto(id)">{{ index + 1 }}</button>
        <span>{{ stepLabels[id] }}</span>
      </li>
    </ol>

    <div v-if="task && !isTerminalTask(task.status) && !submitted" class="busy-note" role="status">
      已有一个行程正在生成（{{ task.status === 'running' ? '进行中' : '排队中' }}）。
      <RouterLink to="/plan">去查看进展 ↗</RouterLink>
    </div>

    <div v-if="submitted" class="chat-done" role="status">
      <strong>已提交，正在为你规划行程…</strong>
      <p>正在前往进展页，真实的服务调用会逐步展示在这里。</p>
    </div>

    <template v-else>
      <section class="conversation" aria-live="polite">
        <div class="bubble-row bot">
          <div class="bubble bot"><span class="eyebrow">行知</span>
            <template v-if="stepIndex === stepOrder.indexOf('origin')">你好，我是行知。想从哪个城市出发？<br /><small>例如：上海。首版支持中国大陆城市。</small></template>
            <template v-else-if="stepIndex === stepOrder.indexOf('destination')">好，从<b>{{ draft.origin }}</b>出发。那这次想去哪里？<br /><small>首版支持中国大陆的单个目的地城市。</small></template>
            <template v-else-if="stepIndex === stepOrder.indexOf('dates')">从 {{ draft.origin }} 到 {{ draft.destination }}，打算玩几天？<br /><small>含出发与返程日，最多 7 天。</small></template>
            <template v-else-if="stepIndex === stepOrder.indexOf('travelers')">一共几个人出行？<br /><small>包括你，最多 10 人。</small></template>
            <template v-else-if="stepIndex === stepOrder.indexOf('budget')">这趟<b>目的地游玩</b>的总预算大约是多少？<br /><small>全体出行人合计（人民币）；不含往返大交通。</small></template>
            <template v-else-if="stepIndex === stepOrder.indexOf('pace')">{{
              draft.budgetTotal ? `按 ${money(draft.budgetTotal)} 的预算` : '这趟' }}你偏好什么样的节奏？</template>
            <template v-else-if="stepIndex === stepOrder.indexOf('preferences')">还有想补充的偏好吗？都可以跳过，默认安排也很稳妥。</template>
            <template v-else>都记好了。下面是这次行程的<b>需求摘要</b>，确认后开始为你生成排期。</template>
          </div>
        </div>

        <div v-if="currentStep === 'origin' || (answered.origin && stepIndex > stepOrder.indexOf('origin'))" class="bubble-row user">
          <div class="bubble user"><button type="button" class="editable-answer" @click="goto('origin')">{{ draft.origin || '（未填）' }} <span aria-hidden="true">✎</span></button></div>
        </div>
        <div v-if="currentStep === 'destination' || (answered.destination && stepIndex > stepOrder.indexOf('destination'))" class="bubble-row user">
          <div class="bubble user"><button type="button" class="editable-answer" @click="goto('destination')">{{ draft.destination || '（未填）' }} <span aria-hidden="true">✎</span></button></div>
        </div>
        <div v-if="currentStep === 'dates' || (answered.dates && stepIndex > stepOrder.indexOf('dates'))" class="bubble-row user">
          <div class="bubble user"><button type="button" class="editable-answer" @click="goto('dates')">{{ draft.startDate }} 至 {{ draft.endDate }} · 共 {{ dayCount }} 天 <span aria-hidden="true">✎</span></button></div>
        </div>
        <div v-if="currentStep === 'travelers' || (answered.travelers && stepIndex > stepOrder.indexOf('travelers'))" class="bubble-row user">
          <div class="bubble user"><button type="button" class="editable-answer" @click="goto('travelers')">{{ draft.travelers }} 人 <span aria-hidden="true">✎</span></button></div>
        </div>
        <div v-if="currentStep === 'budget' || (answered.budget && stepIndex > stepOrder.indexOf('budget'))" class="bubble-row user">
          <div class="bubble user"><button type="button" class="editable-answer" @click="goto('budget')">{{ money(draft.budgetTotal) }} <span aria-hidden="true">✎</span></button></div>
        </div>
        <div v-if="currentStep === 'pace' || stepIndex > stepOrder.indexOf('pace')" class="bubble-row user">
          <div class="bubble user">{{ draft.pace }}节奏</div>
        </div>
        <div v-if="stepIndex > stepOrder.indexOf('preferences')" class="bubble-row user">
          <div class="bubble user">{{ roomText }}<template v-if="draft.hotelPreference && draft.hotelPreference !== '不限'"> · {{ draft.hotelPreference }}</template><template v-if="draft.styles.length"> · {{ draft.styles.join('、') }}</template><template v-if="(!draft.hotelPreference || draft.hotelPreference === '不限') && !draft.styles.length"> · 无额外偏好</template></div>
        </div>

        <div v-if="currentStep === 'preferences'" class="bubble-row user">
          <div class="bubble user options-bubble">
            <fieldset class="pref-field">
              <legend>房间数（多日默认每 2 人 1 间）</legend>
              <div class="pref-row">
                <label><input type="radio" v-model="draft.rooms" value="" /><span>按建议（{{ suggestedRooms }} 间）</span></label>
                <button v-if="dayCount && dayCount > 1" type="button" class="chip" :class="{ selected: draft.rooms === '0' }" @click="draft.rooms = '0'">当日往返 / 无需住宿</button>
              </div>
              <div v-if="dayCount && dayCount > 1" class="stepper">
                <span>指定间数</span>
                <button type="button" aria-label="减少房间" @click="setRooms(-1)">−</button>
                <input type="text" inputmode="numeric" readonly :value="draft.rooms === '' ? String(suggestedRooms) : draft.rooms" aria-label="房间数" />
                <button type="button" aria-label="增加房间" @click="setRooms(1)">＋</button>
              </div>
            </fieldset>
            <fieldset class="pref-field">
              <legend>住宿偏好</legend>
              <div class="chips">
                <button v-for="option in ['不限', '舒适型', '经济型', '特色民宿']" :key="option" type="button" class="chip" :class="{ selected: draft.hotelPreference === option }" @click="draft.hotelPreference = option">{{ option }}</button>
              </div>
            </fieldset>
            <fieldset class="pref-field">
              <legend>游玩风格（可多选）</legend>
              <div class="chips">
                <button v-for="option in stylesOptions" :key="option" type="button" class="chip" :class="{ selected: draft.styles.includes(option) }" @click="toggleStyle(option)">{{ option }}</button>
              </div>
            </fieldset>
            <div class="pref-actions">
              <button type="button" class="text-button" @click="toConfirm">不额外指定，直接下一步 →</button>
            </div>
          </div>
        </div>
      </section>

      <section class="answer-tray" aria-label="当前问题">
        <template v-if="currentStep === 'origin'">
          <label class="visually-hidden" for="w-origin">出发城市</label>
          <input id="w-origin" v-model="draft.origin" list="city-list" class="text-answer" placeholder="例如：上海" maxlength="80" @keydown.enter="enterAdvance()" />
        </template>
        <template v-else-if="currentStep === 'destination'">
          <label class="visually-hidden" for="w-destination">目的地城市</label>
          <input id="w-destination" v-model="draft.destination" list="city-list" class="text-answer" placeholder="例如：杭州" maxlength="80" @keydown.enter="enterAdvance()" />
        </template>
        <template v-else-if="currentStep === 'dates'">
          <div class="date-answer">
            <div><label for="w-start">出发日</label><input id="w-start" v-model="draft.startDate" type="date" :min="today" /></div>
            <span aria-hidden="true">—</span>
            <div><label for="w-end">返程日</label><input id="w-end" v-model="draft.endDate" type="date" :min="draft.startDate || today" /></div>
          </div>
        </template>
        <template v-else-if="currentStep === 'travelers'">
          <div class="stepper large">
            <button type="button" aria-label="减少人数" @click="draft.travelers = Math.max(1, draft.travelers - 1)">−</button>
            <span class="stepper-value">{{ draft.travelers }}<small> 人</small></span>
            <button type="button" aria-label="增加人数" @click="draft.travelers = Math.min(10, draft.travelers + 1)">＋</button>
          </div>
        </template>
        <template v-else-if="currentStep === 'budget'">
          <div class="money-answer">
            <span class="unit">¥</span><input id="w-budget" v-model="draft.budgetTotal" class="text-answer" inputmode="decimal" placeholder="例如 6000" @keydown.enter="enterAdvance()" />
          </div>
        </template>
        <template v-else-if="currentStep === 'pace'">
          <div class="chips big">
            <button v-for="option in (['休闲', '均衡', '紧凑'] as const)" :key="option" type="button" class="chip" :class="{ selected: draft.pace === option }" @click="draft.pace = option; next()">
              {{ option }}<small>{{ option === '休闲' ? '轻松慢游' : option === '均衡' ? '劳逸结合' : '高效打卡' }}</small>
            </button>
          </div>
        </template>

        <div class="tray-error" v-if="currentStep === 'dates' && draft.startDate && !answered.dates" role="alert">出发与返程需在 1–7 天之间，且不早于今天。</div>
        <div class="tray-error" v-else-if="currentStep === 'budget' && draft.budgetTotal && !answered.budget" role="alert">请输入一个正的金额，最多两位小数。</div>
      </section>

      <nav class="chat-nav" aria-label="问答操作">
        <button type="button" class="secondary-link-button" :disabled="stepIndex === 0" @click="goBack">上一步</button>
        <button v-if="currentStep !== 'preferences'" type="button" class="primary-button next-button" :disabled="currentStep === 'confirm' || (currentStep === 'origin' && !answered.origin) || (currentStep === 'destination' && !answered.destination) || (currentStep === 'dates' && !answered.dates) || (currentStep === 'travelers' && !answered.travelers) || (currentStep === 'budget' && !answered.budget)" @click="currentStep === 'pace' ? askPreferences() : next()">
          <span>{{ currentStep === 'pace' ? '选择偏好' : '下一步' }}</span><span aria-hidden="true">→</span>
        </button>
        <button v-else type="button" class="primary-button next-button" @click="toConfirm"><span>查看需求摘要</span><span aria-hidden="true">→</span></button>
      </nav>

      <section v-if="requiredDone && currentStep === 'confirm'" class="confirm-card" aria-labelledby="confirm-title">
        <div class="section-topline"><span class="eyebrow">需求摘要</span><button type="button" class="text-button" @click="goto('origin')">修改</button></div>
        <h2 id="confirm-title">{{ draft.origin }} → {{ draft.destination }}</h2>
        <dl class="confirm-grid">
          <div><dt>出行日期</dt><dd>{{ draft.startDate }} 至 {{ draft.endDate }} · 共 {{ dayCount }} 天</dd></div>
          <div><dt>人数 / 住宿</dt><dd>{{ draft.travelers }} 人 · {{ roomText }}</dd></div>
          <div><dt>目的地总预算</dt><dd>{{ money(draft.budgetTotal) }}<small> / 全体出行人</small></dd></div>
          <div><dt>节奏 / 偏好</dt><dd>{{ draft.pace }}节奏<template v-if="draft.styles.length"> · {{ draft.styles.join('、') }}</template><template v-if="draft.hotelPreference && draft.hotelPreference !== '不限'"> · {{ draft.hotelPreference }}</template></dd></div>
        </dl>
        <p class="scope-note">预算为全体同行人的<b>目的地游玩总支出</b>（人民币），不含往返城市间的大交通费用。</p>

        <div v-if="serverErrorDetail.length" class="feedback feedback-error" role="alert">
          <strong>有些信息需要调整：</strong>
          <ul><li v-for="item in serverErrorDetail" :key="item.field">{{ item.label }}：{{ item.message }}</li></ul>
        </div>

        <div v-if="validationError && !serverErrorDetail.length" class="feedback feedback-error" role="alert"><strong>{{ validationError.message }}</strong></div>

        <template v-if="!validation">
          <label class="consent-row" for="confirm-summary">
            <input id="confirm-summary" v-model="consent" type="checkbox" />
            <span>我确认以上需求与预算口径无误。</span>
          </label>
          <button class="primary-button" :disabled="submitting || busy" @click="checkAndSubmit">
            <span>{{ submitting ? '正在检查…' : '检查并确认需求' }}</span><span aria-hidden="true">→</span>
          </button>
        </template>

        <template v-else>
          <div class="feedback feedback-success" aria-live="polite">
            <span class="eyebrow">检查通过</span>
            <p>出行日期 · {{ validation.request.rooms }} 间房 · {{ money(validation.request.budget_total) }}。人民币（CNY），不含往返大交通；费用精算将在后续提供。</p>
            <ul v-if="validation.warnings.length"><li v-for="warning in validation.warnings" :key="warning">{{ warning }}</li></ul>
          </div>
          <p v-if="submissionError && submissionError.code === 'TASK_BUSY'" class="busy-note" role="alert">当前已有一个行程正在生成。<RouterLink to="/plan">查看进展 ↗</RouterLink></p>
          <p v-if="submissionError && submissionError.code !== 'TASK_BUSY'" class="feedback feedback-error" role="alert"><strong>{{ submissionError.message }}</strong></p>
          <label class="consent-row" for="confirm-generate">
            <input id="confirm-generate" v-model="consent" type="checkbox" />
            <span>我确认生成行程：规划时会访问在线旅行与天气数据服务；我的行程将保存在本机。</span>
          </label>
          <button class="primary-button" :disabled="!consent || submitting || busy" @click="submitPlan">
            <span>{{ submitting ? '正在提交…' : '确认并生成行程' }}</span><span aria-hidden="true">→</span>
          </button>
        </template>
        <p v-if="validation" class="hint-line">提交后进入进展页，真实的服务调用会逐步展示。</p>
      </section>

      <section v-else-if="requiredDone" class="to-confirm-row">
        <button type="button" class="primary-button" @click="toConfirm"><span>查看需求摘要</span><span aria-hidden="true">→</span></button>
      </section>
    </template>
  </main>
  <datalist id="city-list">
    <option v-for="city in majorCities" :key="city" :value="city"></option>
  </datalist>
</template>

<style scoped>
.chat-shell { max-width: 900px; margin: 0 auto; padding: 34px 24px 72px; }
.chat-header { display: flex; align-items: center; gap: 16px; padding-bottom: 20px; border-bottom: 1px solid var(--line); }
.chat-avatar { flex-shrink: 0; width: 46px; height: 50px; border: 1px solid #7da091; border-radius: 15px 6px; color: var(--green); display: grid; place-items: center; font-size: 25px; background: #edf2e8; }
.chat-header h1 { font-size: 23px; font-weight: 500; margin: 0; line-height: 1.45; }
.chat-header p { font-size: 13px; color: var(--muted); margin: 3px 0 0; }
.restart-link { margin-left: auto; background: none; border: none; color: var(--muted); font-size: 12px; text-decoration: underline; text-underline-offset: 3px; }
.chat-progress { display: flex; gap: 6px; list-style: none; margin: 18px 0 6px; padding: 0; overflow-x: auto; }
.chat-progress li { display: flex; align-items: center; gap: 7px; font-size: 12px; color: #97a49a; white-space: nowrap; }
.chat-progress li + li::before { content: '·'; margin: 0 2px; color: #cfd8cd; }
.chat-progress button { width: 22px; height: 22px; border-radius: 50%; border: 1px solid #d7dfd2; background: var(--surface); color: var(--muted); font-size: 11px; }
.chat-progress li.active button { background: var(--green); border-color: var(--green); color: #fff; }
.chat-progress li.active { color: var(--green); font-weight: 500; }
.chat-progress li.done button { color: var(--green); border-color: #b6cbb2; }
.chat-progress button:disabled { cursor: default; }
.chat-progress span { display: none; }
.chat-progress li.active span { display: inline; }
.busy-note { margin: 18px 0 0; padding: 14px 18px; border: 1px solid #e2d3ad; background: #faf4e4; color: #78643b; border-radius: 12px; font-size: 13px; }
.busy-note a { color: var(--green); margin-left: 6px; }
.chat-done { margin: 34px 0; padding: 28px; border-radius: 16px; background: #eef5e9; border: 1px solid #cddfc3; text-align: center; }
.chat-done strong { font-size: 18px; color: #3b5b3d; font-weight: 500; }
.chat-done p { color: var(--muted); font-size: 13px; margin: 8px 0 0; }
.conversation { display: flex; flex-direction: column; gap: 12px; margin: 22px 0 18px; }
.bubble-row { display: flex; }
.bubble-row.user { justify-content: flex-end; }
.bubble { max-width: 78%; padding: 13px 17px; border-radius: 16px; font-size: 14px; line-height: 1.85; }
.bubble .eyebrow { display: block; margin-bottom: 6px; }
.bubble.bot { background: var(--surface); border: 1px solid #e2e7dc; border-top-left-radius: 5px; color: var(--ink); }
.bubble.bot small { color: var(--muted); }
.bubble.bot b { font-weight: 500; color: var(--green); }
.bubble.user { background: #e7efe3; border: 1px solid #cfddd0; border-top-right-radius: 5px; color: #33503f; }
.editable-answer { background: none; border: none; color: inherit; font-size: 14px; text-decoration: underline dotted; text-underline-offset: 4px; }
.editable-answer span { color: var(--green); }
.options-bubble { width: 92%; max-width: 92%; }
.pref-field { border: none; padding: 0; margin: 0 0 14px; }
.pref-field legend { font-size: 13px; font-weight: 500; color: #3f5b43; margin-bottom: 8px; }
.pref-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.pref-row label { display: flex; align-items: center; gap: 7px; font-size: 13px; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; }
.chips.big button small { display: block; color: inherit; opacity: .75; font-weight: 400; }
.chip { border-radius: 30px; padding: 7px 15px; font-size: 13px; background: var(--surface); border: 1px solid #d6e0d1; color: #44604f; line-height: 1.4; }
.chip.selected { background: var(--green); border-color: var(--green); color: #fff; }
.chip small { display: block; }
.stepper { display: inline-flex; align-items: center; gap: 8px; margin-top: 8px; }
.stepper.large { gap: 14px; margin-top: 0; }
.stepper button { width: 38px; height: 38px; border-radius: 10px; border: 1px solid #cfddd0; background: var(--surface); color: var(--green); font-size: 20px; }
.stepper input { width: 60px; height: 38px; text-align: center; border: 1px solid #d5dfd1; border-radius: 10px; color: var(--ink); background: var(--surface); }
.stepper-value { font-size: 26px; font-variant-numeric: tabular-nums; color: var(--green); }
.stepper-value small { font-size: 14px; color: var(--muted); }
.pref-actions { text-align: right; }
.text-button { background: none; border: none; color: var(--green); font-size: 13px; text-underline-offset: 3px; }
.answer-tray { padding: 20px 22px; background: var(--surface); border: 1px solid #e2e7dc; border-radius: 16px; }
.text-answer { width: 100%; height: 50px; border: 1px solid #d5dfd1; border-radius: 12px; padding: 0 16px; font-size: 16px; background: var(--surface); color: var(--ink); }
.text-answer:focus { outline: none; border-color: #568572; box-shadow: 0 0 0 3px #17584e0c; }
.date-answer { display: flex; gap: 14px; align-items: flex-end; flex-wrap: wrap; }
.date-answer label { display: block; font-size: 12px; color: var(--muted); margin-bottom: 6px; }
.date-answer input { width: 160px; height: 50px; border: 1px solid #d5dfd1; border-radius: 12px; padding: 0 12px; font-size: 15px; }
.money-answer { position: relative; max-width: 340px; }
.money-answer .unit { position: absolute; left: 16px; top: 50%; transform: translateY(-50%); color: var(--green); font-weight: 500; }
.money-answer .text-answer { padding-left: 40px; }
.tray-error { margin-top: 10px; color: #a34c2a; font-size: 12px; }
.chat-nav { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin: 16px 0 4px; }
.secondary-link-button { background: none; border: none; color: var(--green); font-size: 13px; }
.secondary-link-button:disabled { color: #b6c1b4; cursor: default; }
.next-button { width: auto; min-height: 46px; margin-top: 0; padding: 10px 20px; }
.confirm-card { margin-top: 18px; padding: 28px; background: var(--surface); border: 1px solid #e2e7dc; border-radius: 20px; }
.confirm-card h2 { font-size: 24px; font-weight: 500; margin: 12px 0 20px; }
.confirm-grid { display: grid; grid-template-columns: minmax(0, 1fr); gap: 14px; margin: 0 0 16px; }
.confirm-grid dt { font-size: 12px; color: #617356; }
.confirm-grid dd { margin: 3px 0 0; font-size: 15px; font-variant-numeric: tabular-nums; }
.confirm-grid small { font-size: 12px; color: var(--muted); }
.scope-note { font-size: 13px; color: #5c7052; background: #f3f4e9; border-radius: 10px; padding: 13px 16px; line-height: 1.8; margin: 4px 0 6px; }
.consent-row { display: flex; gap: 10px; align-items: flex-start; font-size: 13px; color: var(--muted); margin: 16px 0 0; line-height: 1.8; }
.consent-row input { width: 17px; height: 17px; margin-top: 3px; accent-color: var(--green); }
.hint-line { font-size: 12px; color: var(--muted); text-align: center; }
.to-confirm-row { display: flex; justify-content: flex-end; }
.to-confirm-row .primary-button { width: auto; margin-top: 12px; }
.feedback { margin-top: 0; }
@media (max-width: 820px) { .chat-header p { display: none; } }
@media (max-width: 540px) { .chat-shell { padding: 22px 14px 52px; } .bubble { max-width: 92%; } }
</style>
