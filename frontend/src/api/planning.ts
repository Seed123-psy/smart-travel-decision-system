import { ApiError, isTravelRequest } from './client.js'
import type { TravelRequest } from '../types/travel.js'
import type { AgentRun, Budget, Plan, PlanAccepted, PlanningTask, TaskStatus, TripDetail, TripHistory } from '../types/planning.js'

const record = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)
const string = (value: unknown): value is string => typeof value === 'string'
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(string)
const nullableString = (value: unknown) => value === null || string(value)
const integer = (value: unknown): value is number => typeof value === 'number' && Number.isInteger(value) && value >= 0
const nullableNumber = (value: unknown) => value === null || (typeof value === 'number' && Number.isFinite(value) && value >= 0)
const id = (value: unknown): value is string => string(value) && /^[a-zA-Z0-9_-]{1,128}$/.test(value)
const date = (value: unknown) => string(value) && /^\d{4}-\d{2}-\d{2}$/.test(value)
const time = (value: unknown) => string(value) && /^(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$/.test(value)
const money = (value: unknown) => string(value) && /^\d{1,8}(?:\.\d{1,2})?$/.test(value) && Number(value) > 0
const version = (value: unknown) => value === null || (integer(value) && value > 0)
const refs = (value: unknown) => Array.isArray(value) && value.every(item => string(item) || record(item))
// Optional photo/rating/cost fields from Amap. Missing or null is fine (old trips); the rest must stay within a safe shape.
const photoOk = (value: unknown) => value === undefined || value === null || (string(value) && /^https:\/\/\S+$/i.test(value))
const ratingOk = (value: unknown) => value === undefined || value === null || (typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 5)
const costOk = (value: unknown) => value === undefined || value === null || (typeof value === 'number' && Number.isFinite(value) && value >= 0)
const location = (value: unknown) => value === null || (string(value) && /^-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?$/.test(value))
const statuses = new Set(['queued', 'running', 'ready', 'degraded', 'failed'])
const taskStatus = (value: unknown): value is TaskStatus => string(value) && statuses.has(value)
const agentNames = new Set(['attractions', 'hotel', 'weather', 'opening', 'planner'])

export const isTerminalTask = (status: TaskStatus) => status === 'ready' || status === 'degraded' || status === 'failed'

function isAgent(value: unknown): value is AgentRun {
  if (!record(value) || !string(value.agent_name) || !agentNames.has(value.agent_name)
    || !string(value.status) || !['queued', 'running', 'succeeded', 'degraded', 'failed', 'skipped'].includes(value.status)
    || !integer(value.attempt) || value.attempt < 1 || !nullableString(value.started_at)
    || !nullableString(value.finished_at) || !nullableNumber(value.duration_ms)
    || !record(value.summary) || !refs(value.evidence_refs) || !nullableString(value.error_code)) return false
  const summary = value.summary
  return (summary.message === undefined || string(summary.message))
    && (summary.tools === undefined || strings(summary.tools))
    && (summary.candidate_count === undefined || integer(summary.candidate_count))
    && (summary.usage === undefined || record(summary.usage))
}

function isTask(value: unknown): value is PlanningTask {
  if (!record(value) || !id(value.task_id) || !id(value.trip_id) || !taskStatus(value.status)
    || !string(value.stage) || !['validating', 'collecting', 'planning', 'checking', 'persisting'].includes(value.stage)
    || !string(value.created_at) || !nullableString(value.finished_at) || !nullableString(value.error_code)
    || !nullableString(value.message) || !Array.isArray(value.agents) || !value.agents.every(isAgent)
    || !(value.result_url === null || value.result_url === `/api/trips/${value.trip_id}`)) return false
  const keys = value.agents.map(agent => `${agent.agent_name}:${agent.attempt}`)
  return new Set(keys).size === keys.length
}

function isPlan(value: unknown): value is Plan {
  if (!record(value) || value.schema_version !== 1 || !string(value.title) || !string(value.summary)
    || !Array.isArray(value.days) || value.days.length < 1 || value.days.length > 7
    || !Array.isArray(value.evidence) || !value.evidence.every(record)) return false
  const daysValid = value.days.every(day => {
    if (!record(day) || !date(day.date) || !Array.isArray(day.items) || !Array.isArray(day.segments)
      || !(day.weather === null || record(day.weather)) || !strings(day.warnings)) return false
    const itemsValid = day.items.every(item => record(item) && id(item.id) && string(item.poi_id)
      && string(item.name) && location(item.location) && nullableString(item.address)
      && time(item.start_time) && time(item.end_time) && string(item.reason)
      && ['unknown', 'verified'].includes(String(item.opening_status)) && refs(item.evidence_refs)
      && photoOk(item.photo) && ratingOk(item.rating) && costOk(item.cost))
    if (!itemsValid) return false
    const itemIds = new Set(day.items.map(item => item.id))
    return itemIds.size === day.items.length && day.segments.every(segment => record(segment)
      && string(segment.from_item_id) && itemIds.has(segment.from_item_id)
      && string(segment.to_item_id) && itemIds.has(segment.to_item_id) && segment.mode === 'walking'
      && nullableNumber(segment.distance_meters) && nullableNumber(segment.duration_seconds)
      && ['verified', 'unknown', 'conflict'].includes(String(segment.status)) && string(segment.message))
  })
  const hotel = value.hotel
  return daysValid && new Set(value.days.map(day => day.date)).size === value.days.length
    && (hotel === null || (record(hotel) && string(hotel.poi_id) && string(hotel.name)
      && nullableString(hotel.address) && location(hotel.location) && hotel.price === null
      && integer(hotel.rooms) && integer(hotel.nights)
      && photoOk(hotel.photo) && ratingOk(hotel.rating) && costOk(hotel.cost)))
}

function isBudget(value: unknown): value is Budget {
  return record(value) && money(value.budget_total) && value.currency === 'CNY'
    && value.budget_scope === 'destination_only' && value.pricing_status === 'not_calculated'
    && value.known_total === null && value.estimated_total === null
    && strings(value.unknown_items) && strings(value.warnings)
}

function isTrip(value: unknown): value is TripDetail {
  if (!record(value) || !id(value.trip_id) || !isTravelRequest(value.request) || !version(value.version)
    || !(value.plan === null || isPlan(value.plan)) || !(value.budget === null || isBudget(value.budget))
    || !(value.validation === null || (record(value.validation) && string(value.validation.status) && strings(value.validation.warnings)))
    || !(value.latest_task === null || (record(value.latest_task) && id(value.latest_task.task_id) && taskStatus(value.latest_task.status)))
    || !string(value.created_at)) return false
  // A saved result must include its budget and warnings before the UI can present it.
  return value.plan === null || (value.version !== null && value.budget !== null && value.validation !== null)
}

function isHistory(value: unknown): value is TripHistory {
  return record(value) && Array.isArray(value.items) && integer(value.limit) && value.limit > 0
    && integer(value.offset) && typeof value.has_more === 'boolean'
    && value.items.every(item => record(item) && id(item.trip_id) && string(item.destination)
      && date(item.start_date) && date(item.end_date) && integer(item.travelers) && item.travelers >= 1 && item.travelers <= 10
      && money(item.budget_total) && version(item.version) && taskStatus(item.status) && string(item.created_at))
}

interface RequestOptions { baseUrl?: string; signal?: AbortSignal }

async function requestJson<T>(path: string, guard: (value: unknown) => value is T,
  options: RequestOptions & { body?: TravelRequest; expectedStatus?: number } = {}): Promise<T> {
  const controller = new AbortController()
  let timedOut = false
  const abort = () => controller.abort()
  if (options.signal?.aborted) abort()
  options.signal?.addEventListener('abort', abort, { once: true })
  const timeout = setTimeout(() => { timedOut = true; controller.abort() }, 10_000)
  try {
    const response = await fetch(`${(options.baseUrl || '/api').replace(/\/$/, '')}${path}`, {
      method: options.body ? 'POST' : 'GET',
      headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
      body: options.body ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
      cache: 'no-store',
    })
    const body: unknown = await response.json().catch(() => null)
    if (controller.signal.aborted) throw new Error('Request aborted')
    if (!response.ok) {
      throw new ApiError(record(body) && string(body.code) && string(body.message)
        ? { code: body.code, message: body.message, request_id: string(body.request_id) ? body.request_id : undefined }
        : { code: 'SERVICE_UNAVAILABLE', message: '本地服务暂不可用，请稍后重试。' })
    }
    if ((options.expectedStatus !== undefined && response.status !== options.expectedStatus) || !guard(body)) {
      throw new ApiError({ code: 'INVALID_RESPONSE', message: '服务返回的结果不完整，请重新读取任务或行程。' })
    }
    return body
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError({
      code: options.signal?.aborted ? 'REQUEST_CANCELLED' : timedOut ? 'REQUEST_TIMEOUT' : 'NETWORK_ERROR',
      message: options.signal?.aborted ? '已停止读取。' : timedOut
        ? '读取服务超时。任务可能仍在执行，请恢复连接后查看。'
        : '无法连接本地服务，请确认服务启动后恢复连接。',
    })
  } finally {
    clearTimeout(timeout)
    options.signal?.removeEventListener('abort', abort)
  }
}

export function createPlan(request: TravelRequest, options: RequestOptions = {}) {
  return requestJson('/trips/plan', (value): value is PlanAccepted => record(value)
    && id(value.task_id) && id(value.trip_id) && value.status === 'queued', { ...options, body: request, expectedStatus: 202 })
}
export function getTask(taskId: string, options: RequestOptions = {}) {
  return requestJson(`/tasks/${encodeURIComponent(taskId)}`, (value): value is PlanningTask => isTask(value) && value.task_id === taskId, options)
}
export function getTrip(tripId: string, options: RequestOptions = {}) {
  return requestJson(`/trips/${encodeURIComponent(tripId)}`, (value): value is TripDetail => isTrip(value) && value.trip_id === tripId, options)
}
export function getHistory(options: RequestOptions & { offset?: number } = {}) {
  return requestJson(`/trips?limit=20&offset=${options.offset || 0}`, isHistory, options)
}

export async function deleteTrip(tripId: string, options: RequestOptions = {}): Promise<void> {
  const controller = new AbortController()
  let timedOut = false
  const abort = () => controller.abort()
  if (options.signal?.aborted) abort()
  options.signal?.addEventListener('abort', abort, { once: true })
  const timeout = setTimeout(() => { timedOut = true; controller.abort() }, 10_000)
  try {
    const response = await fetch(
      `${(options.baseUrl || '/api').replace(/\/$/, '')}/trips/${encodeURIComponent(tripId)}`,
      { method: 'DELETE', signal: controller.signal, cache: 'no-store' },
    )
    if (controller.signal.aborted) throw new Error('Request aborted')
    if (response.status === 204) return
    const body: unknown = await response.json().catch(() => null)
    throw new ApiError(record(body) && string(body.code) && string(body.message)
      ? { code: body.code, message: body.message, request_id: string(body.request_id) ? body.request_id : undefined }
      : { code: 'SERVICE_UNAVAILABLE', message: '本地服务暂不可用，请稍后重试。' })
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError({
      code: options.signal?.aborted ? 'REQUEST_CANCELLED' : timedOut ? 'REQUEST_TIMEOUT' : 'NETWORK_ERROR',
      message: options.signal?.aborted ? '已停止操作。' : timedOut ? '删除请求超时，请稍后重试。'
        : '无法连接本地服务，请确认服务启动后重试。',
    })
  } finally {
    clearTimeout(timeout)
    options.signal?.removeEventListener('abort', abort)
  }
}
