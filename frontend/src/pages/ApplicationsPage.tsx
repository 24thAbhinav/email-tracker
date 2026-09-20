import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import StatusBadge from '../components/StatusBadge'
import { getApplications, type ApplicationFilters } from '../services/api'
import type { Application, ApplicationStatus } from '../types'
import { formatDateTime } from '../utils/format'

const FILTERS: { label: string; value: ApplicationStatus | 'ALL' }[] = [
  { label: 'All', value: 'ALL' },
  { label: 'Applied', value: 'APPLIED' },
  { label: 'Under Review', value: 'UNDER_REVIEW' },
  { label: 'OA', value: 'OA' },
  { label: 'Interview', value: 'INTERVIEW' },
  { label: 'Offer', value: 'OFFER' },
  { label: 'Rejected', value: 'REJECTED' },
]

const PAGE_SIZE = 200

export default function ApplicationsPage() {
  const [applications, setApplications] = useState<Application[]>([])
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<ApplicationStatus | 'ALL'>('ALL')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    const filters: ApplicationFilters = { limit: PAGE_SIZE }
    if (search.trim()) filters.search = search.trim()
    if (filter !== 'ALL') filters.status = filter

    setLoading(true)
    setError(null)
    const timer = window.setTimeout(() => {
      getApplications(filters)
        .then((data) => {
          if (!active) return
          setApplications(data.items)
          setTotal(data.total)
        })
        .catch(() => {
          if (active) setError('Could not load applications. Is the backend running?')
        })
        .finally(() => {
          if (active) setLoading(false)
        })
    }, 250)

    return () => {
      active = false
      window.clearTimeout(timer)
    }
  }, [search, filter])

  const stats = useMemo(() => {
    const interviews = applications.filter(
      (application) =>
        application.status === 'INTERVIEW' ||
        application.status === 'INTERVIEW_PASSED' ||
        application.status === 'INTERVIEW_REJECTED',
    ).length
    const offers = applications.filter(
      (application) => application.status === 'OFFER',
    ).length
    return { total, interviews, offers }
  }, [applications, total])

  return (
    <div className="page">
      <header className="page-header">
        <h1>Job Application Tracker</h1>
      </header>

      <section className="stats">
        <div className="stat-card">
          <span className="stat-value">{stats.total}</span>
          <span className="stat-label">Total Applications</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{stats.interviews}</span>
          <span className="stat-label">Interviews</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{stats.offers}</span>
          <span className="stat-label">Offers</span>
        </div>
      </section>

      <section className="panel">
        <div className="toolbar">
          <input
            className="search"
            placeholder="Search applications..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <div className="filters">
            {FILTERS.map((option) => (
              <button
                key={option.value}
                className={filter === option.value ? 'filter active' : 'filter'}
                onClick={() => setFilter(option.value)}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        {loading && <p className="state">Loading applications...</p>}
        {error && <p className="state error">{error}</p>}

        {!loading && !error && applications.length === 0 && (
          <p className="state">No applications found.</p>
        )}

        {!loading && !error && applications.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Company</th>
                <th>Role</th>
                <th>Status</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {applications.map((application) => (
                <tr key={application.id}>
                  <td>
                    <Link to={`/applications/${application.id}`}>
                      {application.company}
                    </Link>
                  </td>
                  <td>{application.role}</td>
                  <td>
                    <StatusBadge status={application.status} />
                  </td>
                  <td className="muted">{formatDateTime(application.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
