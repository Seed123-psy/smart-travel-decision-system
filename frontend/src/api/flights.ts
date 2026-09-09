import { ApiError } from './client.js'
import type { FlightOffer, FlightPrice, FlightSearchQuery, FlightSearchResult } from '../types/flights.js'

const record = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)
const string = (value: unknown): value is string => typeof value === 'string'
const date = (value: unknown) => string(value) && /^\d{4}-\d{2}-\d{2}$/.test(value)
const time = (value: unknown) => string(value) && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value)
const iata = (value: unknown) => string(value) && /^[A-Z]{3}$/.test(value)
const nullableString = (value: unknown) => value === null || string(value)
const integer = (value: unknown): value is number => typeof value === 'number' && Number.isInteger(value) && value >= 0

function isPrice(value: unknown): value is FlightPrice {
  return record(value) && typeof value.amount === 'number' && Number.isFinite(value.amount) && value.amount > 0
    && value.currency === 'CNY'
}
function isOffer(value: unknown): value is FlightOffer {
  return record(value) && string(value.airline) && string(value.flight_number)
    && record(value.depart) && iata(value.depart.iata) && time(value.depart.time)
    && record(value.arrive) && iata(value.arrive.iata) && time(value.arrive.time)
    && integer(value.duration_minutes) && integer(value.stops) && isPrice(value.price)
}

function isFlightSearchResult(value: unknown): value is FlightSearchResult {
  if (!record(value) || (value.mode !== 'live' && value.mode !== 'demo')
    || (value.source !== 'amadeus' && value.source !== 'demo')
    || !iata(value.origin) || !iata(value.destination) || !date(value.depart_date)
    || !(value.return_date === null || date(value.return_date))
    || !(typeof value.adults === 'number' && Number.isInteger(value.adults) && value.adults >= 1 && value.adults <= 9)
    || value.currency !== 'CNY' || !nullableString(value.fetched_at) || !nullableString(value.expires_at)
    || !string(value.status) || !string(value.summary)
    || !Array.isArray(value.limitations) || !value.limitations.every(string)
    || !Array.isArray(value.outbound) || value.outbound.length < 1 || !value.outbound.every(isOffer)) return false
  return value.inbound === undefined || (Array.isArray(value.inbound) && value.inbound.every(isOffer))
}

export async function searchFlights(query: FlightSearchQuery,
  options: { signal?: AbortSignal; baseUrl?: string } = {}): Promise<FlightSearchResult> {
  const controller = new AbortController()
  let timedOut = false
  const abort = () => controller.abort()
  if (options.signal?.aborted) abort()
  options.signal?.addEventListener('abort', abort, { once: true })
  const timeout = setTimeout(() => { timedOut = true; controller.abort() }, 15_000)
  const params = new URLSearchParams({
    origin: query.origin.toUpperCase(), destination: query.destination.toUpperCase(),
    depart_date: query.depart_date, adults: String(query.adults || 1),
  })
  if (query.return_date) params.set('return_date', query.return_date)

  try {
    const response = await fetch(`${(options.baseUrl || '/api').replace(/\/$/, '')}/flights/search?${params.toString()}`, {
      signal: controller.signal, cache: 'no-store',
    })
    const body: unknown = await response.json().catch(() => null)
    if (controller.signal.aborted) throw new Error('Request aborted')
    if (!response.ok) {
      throw new ApiError(record(body) && string(body.code) && string(body.message)
        ? { code: body.code, message: body.message, request_id: string(body.request_id) ? body.request_id : undefined }
        : { code: 'SERVICE_UNAVAILABLE', message: '航班服务暂不可用，请稍后重试。' })
    }
    if (!isFlightSearchResult(body)) {
      throw new ApiError({ code: 'INVALID_RESPONSE', message: '航班服务返回的结果不完整，请稍后重试。' })
    }
    return body
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError({
      code: options.signal?.aborted ? 'REQUEST_CANCELLED' : timedOut ? 'REQUEST_TIMEOUT' : 'NETWORK_ERROR',
      message: options.signal?.aborted ? '已停止查询。'
        : timedOut ? '航班查询超时，请稍后重试。' : '无法连接本地服务，请确认服务启动后重试。',
    })
  } finally {
    clearTimeout(timeout)
    options.signal?.removeEventListener('abort', abort)
  }
}
