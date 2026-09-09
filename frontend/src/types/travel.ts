export type TravelPace = '紧凑' | '均衡' | '休闲'

export interface TravelRequestInput {
  origin: string
  destination: string
  start_date: string
  end_date: string
  travelers: number
  budget_total: string
  currency: 'CNY'
  budget_scope: 'destination_only'
  defaults_confirmed: true
  pace: TravelPace
  styles: string[]
  hotel_preference: string
  daily_window: { start: string; end: string }
  rooms?: number
}

export interface TravelRequest extends TravelRequestInput {
  rooms: number
}

export interface ValidationResponse {
  valid: true
  request: TravelRequest
  warnings: string[]
}

export interface ApiErrorDetail {
  field: string
  message: string
}

export interface ApiErrorBody {
  code: string
  message: string
  request_id?: string
  details?: ApiErrorDetail[]
}
