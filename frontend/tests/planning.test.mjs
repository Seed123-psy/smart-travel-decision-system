import assert from 'node:assert/strict'
import { afterEach, test } from 'node:test'
import { createPlan, getHistory, getTask, getTrip } from '../.test-build/api/planning.js'
import { monitorTask } from '../.test-build/api/taskMonitor.js'

// Synthetic contract fixtures, reference date 2030-10-01; these never prove live provider accuracy.
const originalFetch = globalThis.fetch
afterEach(() => { globalThis.fetch = originalFetch })
const request = {
  origin: '上海', destination: '杭州', start_date: '2030-10-01', end_date: '2030-10-01',
  travelers: 2, rooms: 0, budget_total: '2000.01', currency: 'CNY', budget_scope: 'destination_only',
  defaults_confirmed: true, pace: '均衡', styles: [], hotel_preference: '不限',
  daily_window: { start: '09:00', end: '18:00' },
}
const taskId = 'f7806f91-5b42-4f96-84ab-5ced95cb4e80'
const tripId = '7a229fd6-a4f0-422b-a2bc-900d9306f183'
const task = (status = 'queued') => ({
  task_id: taskId, trip_id: tripId, status, stage: 'collecting', created_at: '2030-10-01T00:00:00Z',
  finished_at: ['ready', 'degraded', 'failed'].includes(status) ? '2030-10-01T00:00:10Z' : null,
  error_code: status === 'failed' ? 'PROVIDER_TIMEOUT' : null, message: null, result_url: null,
  agents: [{ agent_name: 'attractions', status: 'running', attempt: 1, started_at: '2030-10-01T00:00:01Z',
    finished_at: null, duration_ms: null, summary: { tools: ['search_poi'], candidate_count: 1 }, evidence_refs: ['e1'], error_code: null }],
})
const trip = () => ({
  trip_id: tripId, request, version: 1, created_at: '2030-10-01T00:00:00Z', latest_task: { task_id: taskId, status: 'degraded' },
  plan: { schema_version: 1, title: '合成测试行程', summary: '只验证契约',
    days: [{ date: '2030-10-01', items: [{ id: 'item-1', poi_id: 'synthetic-poi', name: '测试候选', location: null,
      address: null, start_time: '09:00', end_time: '10:00', reason: '合成样例', opening_status: 'unknown', evidence_refs: ['e1'] }],
    segments: [], weather: null, warnings: ['天气未验证'] }], hotel: null,
    evidence: [{ id: 'e1', source: 'synthetic fixture', status: 'unknown', fetched_at: '2030-10-01T00:00:00Z' }] },
  validation: { status: 'degraded', warnings: ['营业未知'] },
  budget: { budget_total: '2000.01', currency: 'CNY', budget_scope: 'destination_only', pricing_status: 'not_calculated',
    known_total: null, estimated_total: null, unknown_items: ['门票'], warnings: [] },
})
const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })

test('planning POST preserves canonical group budget and requires a real 202 task receipt', async () => {
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/trips/plan')
    assert.equal(options.method, 'POST')
    assert.equal(options.cache, 'no-store')
    assert.deepEqual(JSON.parse(options.body), request)
    return json({ task_id: taskId, trip_id: tripId, status: 'queued' }, 202)
  }
  assert.equal((await createPlan(request)).task_id, taskId)
  globalThis.fetch = async () => json({ task_id: taskId, trip_id: tripId, status: 'queued' })
  await assert.rejects(createPlan(request), { code: 'INVALID_RESPONSE' })
})

test('busy and provider configuration errors retain safe error metadata', async () => {
  for (const [status, code] of [[409, 'TASK_BUSY'], [503, 'PROVIDER_NOT_CONFIGURED']]) {
    globalThis.fetch = async () => json({ code, message: '暂时无法规划', request_id: 'trace-1', details: 'invalid' }, status)
    await assert.rejects(createPlan(request), error => error.code === code && error.requestId === 'trace-1' && error.details.length === 0)
  }
})

test('malformed agent states, duplicate attempts and another task cannot overwrite a current task', async () => {
  const valid = task()
  const malformed = [
    { ...valid, task_id: 'another-task' },
    { ...valid, agents: [{ ...valid.agents[0], status: 'imaginary' }] },
    { ...valid, agents: [valid.agents[0], valid.agents[0]] },
    { ...valid, agents: [{ ...valid.agents[0], summary: { tools: 'wrong' } }] },
    { ...valid, result_url: 'https://external.invalid/trip' },
  ]
  for (const value of malformed) {
    globalThis.fetch = async () => json(value)
    await assert.rejects(getTask(taskId), { code: 'INVALID_RESPONSE' })
  }
})

test('a persisted degraded itinerary preserves null prices, null addresses and unknown evidence', async () => {
  globalThis.fetch = async () => json(trip())
  const result = await getTrip(tripId)
  assert.equal(result.plan.days[0].items[0].address, null)
  assert.equal(result.budget.known_total, null)
  assert.equal(result.plan.days[0].items[0].opening_status, 'unknown')
})

test('incomplete plans and inconsistent segment references are rejected before rendering', async () => {
  const malformed = [
    { ...trip(), budget: null },
    { ...trip(), budget: { ...trip().budget, known_total: '0.00' } },
    { ...trip(), plan: { ...trip().plan, days: [{ ...trip().plan.days[0], items: [{ ...trip().plan.days[0].items[0], start_time: '99:99' }] }] } },
    { ...trip(), plan: { ...trip().plan, days: [{ ...trip().plan.days[0], segments: [{ from_item_id: 'missing', to_item_id: 'item-1', mode: 'walking', distance_meters: null, duration_seconds: null, status: 'unknown', message: '' }] }] } },
  ]
  for (const value of malformed) {
    globalThis.fetch = async () => json(value)
    await assert.rejects(getTrip(tripId), { code: 'INVALID_RESPONSE' })
  }
})

test('history reads are paginated and reject malformed money instead of displaying a false amount', async () => {
  globalThis.fetch = async url => {
    assert.equal(url, '/api/trips?limit=20&offset=20')
    return json({ items: [], offset: 20, limit: 20, has_more: false })
  }
  assert.deepEqual((await getHistory({ offset: 20 })).items, [])
  globalThis.fetch = async () => json({ items: [{ trip_id: tripId, destination: '杭州', start_date: '2030-10-01', end_date: '2030-10-01', travelers: 2, budget_total: 'unknown', version: 1, status: 'degraded', created_at: '' }], offset: 0, limit: 20, has_more: false })
  await assert.rejects(getHistory(), { code: 'INVALID_RESPONSE' })
})

test('polling follows backend state in order and stops at a terminal task', async () => {
  let calls = 0
  globalThis.fetch = async () => json(task(['queued', 'running', 'degraded'][calls++]))
  const observed = []
  const completed = await monitorTask(taskId, value => observed.push(value.status), { signal: new AbortController().signal, intervalMs: 1 })
  assert.equal(completed.status, 'degraded')
  assert.deepEqual(observed, ['queued', 'running', 'degraded'])
  await new Promise(resolve => setTimeout(resolve, 5))
  assert.equal(calls, 3)
})

test('leaving the page cancels scheduled polling without another network request', async () => {
  let calls = 0
  const controller = new AbortController()
  globalThis.fetch = async () => { calls += 1; return json(task()) }
  await assert.rejects(monitorTask(taskId, () => controller.abort(), { signal: controller.signal, intervalMs: 1 }), { code: 'REQUEST_CANCELLED' })
  await new Promise(resolve => setTimeout(resolve, 5))
  assert.equal(calls, 1)
})

test('connection failure stops polling for explicit recovery and never creates another task', async () => {
  const methods = []
  globalThis.fetch = async (_url, options) => { methods.push(options.method); throw new TypeError('offline') }
  await assert.rejects(monitorTask(taskId, () => assert.fail('must not emit a fabricated state'), { signal: new AbortController().signal, intervalMs: 1 }), { code: 'NETWORK_ERROR' })
  assert.deepEqual(methods, ['GET'])
})
