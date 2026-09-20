// Shared TypeScript types for job applications (mirrors the FastAPI schemas)

export type ApplicationStatus =
  | 'APPLIED'
  | 'UNDER_REVIEW'
  | 'OA'
  | 'INTERVIEW'
  | 'INTERVIEW_PASSED'
  | 'INTERVIEW_REJECTED'
  | 'OFFER'
  | 'REJECTED'
  | 'WITHDRAWN'
  | 'CLOSED'

export interface Application {
  id: number
  company: string
  role: string
  status: ApplicationStatus
  applied_at: string | null
  updated_at: string
  source_email_id: string
  sender_email: string | null
  notes?: string | null
  action_url?: string | null
  event_date?: string | null
  is_closed: boolean
  closed_at: string | null
}

export interface ApplicationEvent {
  id: number
  application_id: number
  status: ApplicationStatus
  note: string | null
  action_url?: string | null
  event_date?: string | null
  created_at: string
}

export interface ApplicationListResponse {
  items: Application[]
  total: number
  limit: number
  offset: number
}

export interface ApplicationStats {
  total: number // excludes closed
  closed: number
  by_status: Record<string, number>
}
