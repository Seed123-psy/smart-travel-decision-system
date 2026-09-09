/** Public documentation links are distinct from authenticated provider endpoints. */
const amapSources: Record<string, { label: string; url: string }> = {
  '/v3/place/text': {
    label: '高德地点检索说明',
    url: 'https://lbs.amap.com/api/webservice/guide/api/search',
  },
  '/v3/place/detail': {
    label: '高德地点详情说明',
    url: 'https://lbs.amap.com/api/webservice/guide/api/search',
  },
  '/v3/weather/weatherInfo': {
    label: '高德天气数据说明',
    url: 'https://lbs.amap.com/api/webservice/guide/api/weatherinfo',
  },
  '/v3/direction/walking': {
    label: '高德步行路线说明',
    url: 'https://lbs.amap.com/api/webservice/guide/api/direction',
  },
}

export function evidenceDocumentation(source: Record<string, unknown>) {
  if (source.source !== 'amap' || typeof source.source_url !== 'string') return null
  try {
    const endpoint = new URL(source.source_url)
    if (endpoint.origin !== 'https://restapi.amap.com' || endpoint.username || endpoint.password) return null
    // Never reuse endpoint parameters: older records may contain credential-bearing URLs.
    return amapSources[endpoint.pathname] || null
  } catch { return null }
}
