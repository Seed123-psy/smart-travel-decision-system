import assert from 'node:assert/strict'
import { test } from 'node:test'
import { evidenceDocumentation } from '../.test-build/api/evidence.js'

test('existing saved API sources resolve to public explanatory pages without authentication', () => {
  for (const path of ['/v3/place/text', '/v3/place/detail', '/v3/weather/weatherInfo', '/v3/direction/walking']) {
    const link = evidenceDocumentation({ source: 'amap', source_url: `https://restapi.amap.com${path}` })
    assert.ok(link.label.includes('说明'))
    assert.equal(new URL(link.url).hostname, 'lbs.amap.com')
    assert.equal(new URL(link.url).search, '')
  }
})

test('query secrets from an old record never reach a browser link', () => {
  const link = evidenceDocumentation({ source: 'amap', source_url: 'https://restapi.amap.com/v3/place/text?key=synthetic-secret#secret' })
  assert.ok(link)
  assert.equal(JSON.stringify(link).includes('secret'), false)
})

test('unknown endpoints and untrusted hosts are not exposed as source links', () => {
  for (const url of ['javascript:alert(1)', 'https://restapi.amap.com.evil.test/v3/place/text',
    'https://user:password@restapi.amap.com/v3/place/text', 'https://restapi.amap.com/unknown', null]) {
    assert.equal(evidenceDocumentation({ source: 'amap', source_url: url }), null)
  }
})
