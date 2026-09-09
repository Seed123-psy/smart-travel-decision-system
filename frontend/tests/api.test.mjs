import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'
import { ApiError, validateRequirements } from '../.test-build/api/client.js'

const originalFetch = globalThis.fetch
const request = {
  origin: '上海', destination: '杭州', start_date: '2030-10-01', end_date: '2030-10-03',
  travelers: 3, budget_total: '6000.01', currency: 'CNY', budget_scope: 'destination_only',
  defaults_confirmed: true, pace: '均衡', styles: [], hotel_preference: '不限',
  daily_window: { start: '09:00', end: '18:00' },
}

afterEach(() => { globalThis.fetch = originalFetch })

test('sends group budget as a decimal string and uses server-confirmed room defaults', async () => {
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/requirements/validate')
    assert.equal(options.method, 'POST')
    const input = JSON.parse(options.body)
    assert.equal(input.budget_total, '6000.01')
    assert.equal(input.budget_scope, 'destination_only')
    assert.equal(input.defaults_confirmed, true)
    assert.equal('rooms' in input, false)
    return new Response(JSON.stringify({ valid: true, request: { ...input, rooms: 2 }, warnings: [] }))
  }
  const response = await validateRequirements(request, '/api/')
  assert.equal(response.request.rooms, 2)
  assert.equal(response.request.budget_total, '6000.01')
})

test('keeps validation field errors and request id available to the form', async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({
    code: 'VALIDATION_ERROR', message: '旅行需求不符合要求', request_id: 'request-test',
    details: [{ field: 'end_date', message: '行程最多 7 天' }],
  }), { status: 422 })
  await assert.rejects(validateRequirements(request), (error) => {
    assert.ok(error instanceof ApiError)
    assert.equal(error.code, 'VALIDATION_ERROR')
    assert.equal(error.details[0].field, 'end_date')
    assert.equal(error.requestId, 'request-test')
    return true
  })
})

test('does not treat proxy HTML errors as successful validation', async () => {
  globalThis.fetch = async () => new Response('<html>Proxy unavailable</html>', { status: 502 })
  await assert.rejects(validateRequirements(request), { code: 'SERVICE_UNAVAILABLE' })
})

test('does not show a successful result for a malformed successful response', async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({ message: 'ok' }))
  await assert.rejects(validateRequirements(request), { code: 'INVALID_RESPONSE' })
})

test('rejects incomplete or invalid canonical requests before the confirmation view renders', async () => {
  const canonical = { ...request, rooms: 2 }
  const malformedRequests = [
    {},
    { ...canonical, daily_window: undefined },
    { ...canonical, daily_window: { start: '09:00' } },
    { ...canonical, budget_total: 6000.01 },
    { ...canonical, currency: 'USD' },
    { ...canonical, defaults_confirmed: false },
    { ...canonical, travelers: 1.5 },
  ]
  for (const malformed of malformedRequests) {
    globalThis.fetch = async () => new Response(JSON.stringify({ valid: true, request: malformed, warnings: [] }))
    await assert.rejects(validateRequirements(request), { code: 'INVALID_RESPONSE' })
  }
})

test('connection errors offer a retryable local-service message', async () => {
  globalThis.fetch = async () => { throw new TypeError('fetch failed') }
  await assert.rejects(validateRequirements(request), { code: 'NETWORK_ERROR' })
})
