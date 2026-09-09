// Deterministic trip rules shared by the guided chat and the confirmation card.
// They mirror the backend's field-level validation so the chat can flag issues
// immediately; the canonical result always comes from /requirements/validate.

export const MAX_DAYS = 7
export const MAX_TRAVELERS = 10

export function todayShanghai(): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(new Date())
}

export function tripDays(startDate: string, endDate: string): number | null {
  if (!startDate || !endDate) return null
  const days = Math.round((Date.parse(endDate) - Date.parse(startDate)) / 86_400_000) + 1
  return Number.isFinite(days) ? days : null
}

export function suggestRooms(days: number | null, travelers: number): number {
  return days === null || days === 1 ? 0 : Math.ceil(travelers / 2)
}

/** Cities the chat can suggest. Static list; the planner never spends Amap quota on autocomplete. */
export const majorCities = [
  '北京', '上海', '广州', '深圳', '杭州', '成都', '重庆', '西安', '武汉', '南京',
  '苏州', '天津', '长沙', '郑州', '青岛', '厦门', '大连', '昆明', '三亚', '海口',
  '丽江', '桂林', '贵阳', '南宁', '哈尔滨', '沈阳', '济南', '合肥', '福州', '南昌',
]

/** Mainland-city validation used before sending a request to the backend. */
export function isValidCity(value: string): boolean {
  return value.trim().length >= 2 && value.trim().length <= 80
}
