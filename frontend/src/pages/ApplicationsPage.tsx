import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import StatusBadge from '../components/StatusBadge'
import {
  getApplications,
  getApplicationStats,
  setApplicationClosed,
  type ApplicationFilters,
} from '../services/api'
import type { Application, ApplicationStats, ApplicationStatus } from '../types'
import { formatDateTime } from '../utils/format'

const FILTERS: { label: string; value: ApplicationStatus | 'ALL' }[] = [
  { label: 'All', value: 'ALL' },
  { label: 'Applied', value: 'APPLIED' },
  { label: 'Under Review', value: 'UNDER_REVIEW' },
  { label: 'OA', value: 'OA' },
  { label: 'Interview', value: 'INTERVIEW' },
  { label: 'Offer', value: 'OFFER' },
  { label: 'Rejected', value: 'REJECTED' },
  { label: 'Closed', value: 'CLOSED' },
]

const PAGE_SIZE = 200

export default function ApplicationsPage() {
  const [applications, setApplications] = useState<Application[]>([])
  const [stats, setStats] = useState<ApplicationStats | null>(null)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<ApplicationStatus | 'ALL'>('ALL')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pendingId, setPendingId] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const loadStats = useCallback(async () => {
    try {
      setStats(await getApplicationStats())
    } catch {
      // Counts are non-critical; ignore failures.
    }
  }, [])

  useEffect(() => {
    loadStats()
  }, [loadStats])

  useEffect(() => {
    let active = true
    const filters: ApplicationFilters = { limit: PAGE_SIZE }
    if (search.trim()) filters.search = search.trim()
    if (filter !== 'ALL') {
      filters.status = filter
    } else {
      filters.include_closed = false // hide closed from the All tab
    }

    setLoading(true)
    setError(null)
    const timer = window.setTimeout(() => {
      getApplications(filters)
        .then((data) => {
          if (active) setApplications(data.items)
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

  const toggleClosed = async (application: Application) => {
    setPendingId(application.id)
    setActionError(null)
    try {
      const updated = await setApplicationClosed(
        application.id,
        !application.is_closed,
      )
      setApplications((prev) => {
        const stillMatches =
          filter === 'ALL' ? !updated.is_closed : updated.status === filter
        return stillMatches
          ? prev.map((item) => (item.id === updated.id ? updated : item))
          : prev.filter((item) => item.id !== updated.id)
      })
      await loadStats()
    } catch {
      setActionError('Could not update that application. Please try again.')
    } finally {
      setPendingId(null)
    }
  }

  const countFor = (value: ApplicationStatus | 'ALL'): number => {
    if (!stats) return 0
    if (value === 'ALL') return stats.total
    return stats.by_status[value] ?? 0
  }

  const interviews = stats
    ? (stats.by_status['INTERVIEW'] ?? 0) +
      (stats.by_status['INTERVIEW_PASSED'] ?? 0) +
      (stats.by_status['INTERVIEW_REJECTED'] ?? 0)
    : 0
  const offers = stats?.by_status['OFFER'] ?? 0

  return (
    <div className="page">
      <header className="page-header">
        <h1>Job Application Tracker</h1>
      </header>

      <section className="stats">
        <div className="stat-card">
          <span className="stat-value">{stats?.total ?? '—'}</span>
          <span className="stat-label">Total Applications</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{interviews}</span>
          <span className="stat-label">Interviews</span>
        </div>
        <div className="stat-card">
          <span className="stat-value">{offers}</span>
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
                <span className="filter-count">{countFor(option.value)}</span>
              </button>
            ))}
          </div>
        </div>

        {loading && <p className="state">Loading applications...</p>}
        {error && <p className="state error">{error}</p>}
        {actionError && <p className="state error">{actionError}</p>}

        {!loading && !error && applications.length === 0 && (
          <p className="state">No applications found.</p>
        )}

        {!loading && !error && applications.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th className="actions-cell" />
                <th>Company</th>
                <th>Role</th>
                <th>Status</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {applications.map((application) => (
                <tr
                  key={application.id}
                  className={application.is_closed ? 'row-closed' : undefined}
                >
                  <td className="actions-cell">
                    <button
                      className={
                        application.is_closed ? 'icon-btn reopen' : 'icon-btn close'
                      }
                      title={
                        application.is_closed
                          ? 'Reopen application'
                          : 'Mark as closed'
                      }
                      aria-label={
                        application.is_closed
                          ? 'Reopen application'
                          : 'Mark as closed'
                      }
                      onClick={() => toggleClosed(application)}
                      disabled={pendingId === application.id}
                    >
                      {pendingId === application.id ? (
                        <span className="spinner small" />
                      ) : application.is_closed ? (
                        '↺'
                      ) : (
                        '×'
                      )}
                    </button>
                  </td>
                  <td>
                    <Link to={`/applications/${application.id}`}>
                      {application.company}
                    </Link>
                  </td>
                  <td>{application.role}</td>
                  <td>
                    <StatusBadge
                      status={application.is_closed ? 'CLOSED' : application.status}
                    />
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
