import type { ApiErrorBody, ApiErrorDetail, TravelRequestInput, ValidationResponse } from '../types/travel.js'

export class ApiError extends Error {
  readonly code: string
  readonly details: ApiErrorDetail[]
  readonly requestId?: string

  constructor(body: ApiErrorBody) {
    super(body.message)
    this.name = 'ApiError'
    this.code = body.code
    this.details = body.details ?? []
    this.requestId = body.request_id
  }
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== 'object' || value === null) return false
  const body = value as Record<string, unknown>
  return typeof body.code === 'string' && typeof body.message === 'string'
    && (body.request_id === undefined || typeof body.request_id === 'string')
    && (body.details === undefined || (Array.isArray(body.details)
      && body.details.every(detail => isRecord(detail) && typeof detail.field === 'string' && typeof detail.message === 'string')))
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every(item => typeof item === 'string')
}

export function isTravelRequest(request: unknown): request is ValidationResponse['request'] {
  if (!isRecord(request)) return false
  const datePattern = /^\d{4}-\d{2}-\d{2}$/
  const timePattern = /^(?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d{1,6})?)?$/
  return typeof request.origin === 'string' && request.origin.trim().length > 0
    && typeof request.destination === 'string' && request.destination.trim().length > 0
    && typeof request.start_date === 'string' && datePattern.test(request.start_date)
    && typeof request.end_date === 'string' && datePattern.test(request.end_date)
    && typeof request.budget_total === 'string' && /^\d{1,8}(?:\.\d{1,2})?$/.test(request.budget_total)
    && Number(request.budget_total) > 0
    && request.currency === 'CNY' && request.budget_scope === 'destination_only'
    && typeof request.travelers === 'number' && Number.isInteger(request.travelers)
    && request.travelers >= 1 && request.travelers <= 10
    && typeof request.rooms === 'number' && Number.isInteger(request.rooms)
    && request.rooms >= 0 && request.rooms <= request.travelers
    && isRecord(request.daily_window)
    && typeof request.daily_window.start === 'string' && timePattern.test(request.daily_window.start)
    && typeof request.daily_window.end === 'string' && timePattern.test(request.daily_window.end)
    && (request.pace === '紧凑' || request.pace === '均衡' || request.pace === '休闲')
    && request.defaults_confirmed === true
    && isStringArray(request.styles)
    && typeof request.hotel_preference === 'string'
}

function isValidationResponse(value: unknown): value is ValidationResponse {
  return isRecord(value) && value.valid === true && isTravelRequest(value.request)
    && isStringArray(value.warnings)
}

export async function validateRequirements(
  request: TravelRequestInput,
  baseUrl = '/api',
): Promise<ValidationResponse> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 10_000)

  try {
    const response = await fetch(`${baseUrl.replace(/\/$/, '')}/requirements/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal: controller.signal,
    })
    const body: unknown = await response.json().catch(() => null)

    if (!response.ok) {
      throw new ApiError(isApiErrorBody(body) ? body : {
        code: 'SERVICE_UNAVAILABLE',
        message: '暂时无法检查需求，请确认本地后端服务已启动后重试。',
      })
    }

    if (!isValidationResponse(body)) {
      throw new ApiError({ code: 'INVALID_RESPONSE', message: '需求检查返回了无法识别的结果，请稍后重试。' })
    }

    return body
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError({
      code: controller.signal.aborted ? 'REQUEST_TIMEOUT' : 'NETWORK_ERROR',
      message: controller.signal.aborted
        ? '需求检查超时，请稍后重试。'
        : '无法连接本地服务，请确认后端已启动后重试。',
    })
  } finally {
    clearTimeout(timeout)
  }
}
