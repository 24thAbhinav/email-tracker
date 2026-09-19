// Shared TypeScript types for job applications

export type ApplicationStatus =
  | 'applied'
  | 'screening'
  | 'interview'
  | 'offer'
  | 'rejected'
  | 'withdrawn'
  | 'unknown'

export interface JobApplication {
  id: string
  company: string
  role: string
  status: ApplicationStatus
  appliedAt: string          // ISO date string
  updatedAt: string
  sourceEmailId?: string     // Gmail message ID
  notes?: string
  jobUrl?: string
  salary?: string
  location?: string
}

export interface ApiResponse<T> {
  data: T
  message?: string
}
