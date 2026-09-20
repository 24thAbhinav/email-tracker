import type { ApplicationStatus } from '../types'

export const STATUS_LABELS: Record<ApplicationStatus, string> = {
  APPLIED: 'Applied',
  UNDER_REVIEW: 'Under Review',
  OA: 'Online Assessment',
  INTERVIEW: 'Interview',
  INTERVIEW_PASSED: 'Interview Passed',
  INTERVIEW_REJECTED: 'Interview Rejected',
  OFFER: 'Offer',
  REJECTED: 'Rejected',
  WITHDRAWN: 'Withdrawn',
}

export function statusLabel(status: ApplicationStatus): string {
  return STATUS_LABELS[status] ?? status
}

export default function StatusBadge({ status }: { status: ApplicationStatus }) {
  return (
    <span className={`badge badge-${status.toLowerCase()}`}>
      {statusLabel(status)}
    </span>
  )
}
