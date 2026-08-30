export type TaskStatus = 'queued' | 'running' | 'completed' | 'failed'

export interface TravelRequest {
  origin: string
  destination: string
  start_date: string
  end_date: string
  adults: number
  children: number
  budget: number
  currency: string
  interests: string[]
  pace: '轻松' | '适中' | '紧凑'
  accommodation: string
  dietary_restrictions: string
  must_visit: string[]
  additional_requirements: string
}

export interface Evidence {
  id: string
  content: string
  source: string
  destination: string
  topic: string
  updated_at: string
  distance?: number
}

export interface TimeSlot {
  period: '上午' | '下午' | '晚上'
  activity: string
  location: string
  duration: string
  transport: string
  estimated_cost: number
  citations: string[]
}

export interface DayPlan {
  day: number
  date: string
  theme: string
  activities: TimeSlot[]
  meals: string[]
  notes: string[]
}

export interface BudgetItem {
  category: string
  amount: number
  note: string
}

export interface TravelGuide {
  title: string
  overview: string
  planning_rationale: string[]
  days: DayPlan[]
  transportation_advice: string[]
  food_and_stay_advice: string[]
  budget_items: BudgetItem[]
  budget_total: number
  preparation: string[]
  warnings: string[]
  citations: string[]
  insufficient_evidence: boolean
}

export interface ApiErrorDetail {
  code: string
  message: string
  details?: unknown
}

export interface TaskResponse {
  task_id: string
  status: TaskStatus
  created_at: string
  updated_at: string
  guide: TravelGuide | null
  evidence: Evidence[]
  error: ApiErrorDetail | null
}

export interface StatusResponse {
  service: 'ok'
  llm: { configured: boolean; model: string; base_url: string }
  embedding: { configured: boolean; model: string; base_url: string }
  knowledge_base: {
    collection_name: string
    path: string
    chunks: number
    embedding_model: string
    embedding_dimension: number
    compatible: boolean
    compatibility_message: string
  }
  queue: { queued: number; running: number }
}

