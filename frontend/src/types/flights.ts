export type FlightMode = 'live' | 'demo'
export type FlightSource = 'amadeus' | 'demo'

export interface FlightSearchQuery {
  origin: string
  destination: string
  depart_date: string
  return_date: string | null
  adults?: number
}

export interface FlightPrice {
  amount: number
  currency: 'CNY'
}
export interface FlightEndpoint {
  iata: string
  time: string
}
export interface FlightOffer {
  airline: string
  flight_number: string
  depart: FlightEndpoint
  arrive: FlightEndpoint
  duration_minutes: number
  stops: number
  price: FlightPrice
}

export interface FlightSearchResult {
  mode: FlightMode
  source: FlightSource
  origin: string
  destination: string
  depart_date: string
  return_date: string | null
  adults: number
  currency: 'CNY'
  fetched_at: string | null
  expires_at: string | null
  status: string
  summary: string
  limitations: string[]
  outbound: FlightOffer[]
  inbound: FlightOffer[]
}

/** Major cities with mainland IATA codes the demo and live provider understand. */
export const iataCities: { label: string; code: string }[] = [
  { label: '上海', code: 'PVG' }, { label: '北京', code: 'PEK' }, { label: '广州', code: 'CAN' },
  { label: '深圳', code: 'SZX' }, { label: '杭州', code: 'HGH' }, { label: '成都', code: 'TFU' },
  { label: '重庆', code: 'CKG' }, { label: '西安', code: 'XIY' }, { label: '武汉', code: 'WUH' },
  { label: '南京', code: 'NKG' }, { label: '三亚', code: 'SYX' }, { label: '厦门', code: 'XMN' },
  { label: '青岛', code: 'TAO' }, { label: '昆明', code: 'KMG' }, { label: '大连', code: 'DLC' },
  { label: '天津', code: 'TSN' }, { label: '长沙', code: 'CSX' }, { label: '海口', code: 'HAK' },
  { label: '郑州', code: 'CGO' }, { label: '哈尔滨', code: 'HRB' }, { label: '贵阳', code: 'KWE' },
  { label: '桂林', code: 'KWL' }, { label: '丽江', code: 'LJG' }, { label: '沈阳', code: 'SHE' },
  { label: '济南', code: 'TNA' }, { label: '合肥', code: 'HFE' }, { label: '福州', code: 'FOC' },
  { label: '南昌', code: 'KHN' },
]
export function iataToLabel(code: string): string {
  const hit = iataCities.find(item => item.code === code.toUpperCase())
  return hit ? hit.label : code.toUpperCase()
}
