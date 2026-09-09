import type { TravelRequest } from './travel.js'

export type TaskStatus = 'queued' | 'running' | 'ready' | 'degraded' | 'failed'
export type TaskStage = 'validating' | 'collecting' | 'planning' | 'checking' | 'persisting'
export type AgentName = 'attractions' | 'hotel' | 'weather' | 'opening' | 'planner'
export type AgentStatus = 'queued' | 'running' | 'succeeded' | 'degraded' | 'failed' | 'skipped'
export type EvidenceRef = string | Record<string, unknown>

export interface AgentRun {
  agent_name: AgentName
  status: AgentStatus
  attempt: number
  started_at: string | null
  finished_at: string | null
  duration_ms: number | null
  summary: { message?: string; tools?: string[]; candidate_count?: number; usage?: Record<string, unknown> }
  evidence_refs: EvidenceRef[]
  error_code: string | null
}

export interface PlanningTask {
  task_id: string
  trip_id: string
  status: TaskStatus
  stage: TaskStage
  created_at: string
  finished_at: string | null
  error_code: string | null
  message: string | null
  agents: AgentRun[]
  result_url: string | null
}

export interface PlanItem {
  id: string
  poi_id: string
  name: string
  location: string | null
  address: string | null
  start_time: string
  end_time: string
  reason: string
  opening_status: 'unknown' | 'verified'
  evidence_refs: EvidenceRef[]
}
export interface RouteSegment {
  from_item_id: string
  to_item_id: string
  mode: 'walking'
  distance_meters: number | null
  duration_seconds: number | null
  status: 'verified' | 'unknown' | 'conflict'
  message: string
}
export interface PlanDay {
  date: string
  items: PlanItem[]
  segments: RouteSegment[]
  weather: Record<string, unknown> | null
  warnings: string[]
}
export interface Plan {
  schema_version: 1
  title: string
  summary: string
  days: PlanDay[]
  hotel: null | { poi_id: string; name: string; address: string | null; location: string | null; price: null; rooms: number; nights: number }
  evidence: Record<string, unknown>[]
}
export interface Budget {
  budget_total: string
  currency: 'CNY'
  budget_scope: 'destination_only'
  pricing_status: 'not_calculated'
  known_total: null
  estimated_total: null
  unknown_items: string[]
  warnings: string[]
}
export interface TripDetail {
  trip_id: string
  request: TravelRequest
  version: number | null
  plan: Plan | null
  validation: { status: string; warnings: string[] } | null
  budget: Budget | null
  latest_task: { task_id: string; status: TaskStatus } | null
  created_at: string
}
export interface TripHistoryItem {
  trip_id: string
  destination: string
  start_date: string
  end_date: string
  travelers: number
  budget_total: string
  version: number | null
  status: TaskStatus
  created_at: string
}
export interface TripHistory {
  items: TripHistoryItem[]
  limit: number
  offset: number
  has_more: boolean
}
export interface PlanAccepted {
  task_id: string
  trip_id: string
  status: 'queued'
}
