import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Award,
  Briefcase,
  CalendarClock,
  Inbox,
  RotateCcw,
  Search,
  TriangleAlert,
  X,
} from 'lucide-react'
import StatusBadge, { STATUS_LABELS } from '../components/StatusBadge'
import {
  getApplications,
  getApplicationStats,
  setApplicationClosed,
  updateApplication,
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

function TableSkeleton() {
  return (
    <table className="table" aria-hidden>
      <thead>
        <tr>
          <th>Company</th>
          <th>Role</th>
          <th>Status</th>
          <th>Updated</th>
        </tr>
      </thead>
      <tbody>
        {Array.from({ length: 5 }).map((_, index) => (
          <tr key={index}>
            <td>
              <span className="skeleton" style={{ width: '60%' }} />
            </td>
            <td>
              <span className="skeleton" style={{ width: '45%' }} />
            </td>
            <td>
              <span className="skeleton" style={{ width: 110 }} />
            </td>
            <td>
              <span className="skeleton" style={{ width: 90 }} />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export default function ApplicationsPage() {
  const [applications, setApplications] = useState<Application[]>([])
  const [stats, setStats] = useState<ApplicationStats | null>(null)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState<ApplicationStatus | 'ALL'>('ALL')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const [pendingId, setPendingId] = useState<number | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const loadStats = useCallback(async () => {
    try {
      setStats(await getApplicationStats())
    } catch {
      // Counts are non-critical; a failed fetch just leaves the tabs at zero.
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
      filters.include_closed = false
    }

    setLoading(true)
    setError(false)
    const timer = window.setTimeout(() => {
      getApplications(filters)
        .then((data) => {
          if (active) setApplications(data.items)
        })
        .catch(() => {
          if (active) setError(true)
        })
        .finally(() => {
          if (active) setLoading(false)
        })
    }, 250)

    return () => {
      active = false
      window.clearTimeout(timer)
    }
  }, [search, filter, reloadKey])

  const handleStatusChange = async (
    application: Application,
    newStatus: ApplicationStatus,
  ) => {
    if (application.status === newStatus) return
    setPendingId(application.id)
    setActionError(null)
    try {
      const updated = await updateApplication(application.id, { status: newStatus })
      setApplications((prev) => {
        const stillMatches =
          filter === 'ALL' ? !updated.is_closed : updated.status === filter
        return stillMatches
          ? prev.map((item) => (item.id === updated.id ? updated : item))
          : prev.filter((item) => item.id !== updated.id)
      })
      await loadStats()
    } catch {
      setActionError('Could not update status. Please try again.')
    } finally {
      setPendingId(null)
    }
  }

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

  const isFiltered = search.trim().length > 0 || filter !== 'ALL'

  return (
    <div className="page">
      <header className="page-header">
        <p className="page-eyebrow">Overview</p>
        <h1 className="page-title">Applications</h1>
        <p className="page-subtitle">
          Every application your inbox agent has tracked, newest activity first.
        </p>
      </header>

      <section className="stats">
        <div className="stat-card">
          <div>
            <span className="stat-label">Total applications</span>
            <span className="stat-value">{stats?.total ?? '—'}</span>
          </div>
          <span className="stat-icon" aria-hidden>
            <Briefcase size={16} />
          </span>
        </div>
        <div className="stat-card">
          <div>
            <span className="stat-label">Interviews</span>
            <span className="stat-value">{interviews}</span>
          </div>
          <span className="stat-icon" aria-hidden>
            <CalendarClock size={16} />
          </span>
        </div>
        <div className="stat-card">
          <div>
            <span className="stat-label">Offers</span>
            <span className="stat-value">{offers}</span>
          </div>
          <span className="stat-icon" aria-hidden>
            <Award size={16} />
          </span>
        </div>
      </section>

      <section className="panel">
        <div className="toolbar">
          <div className="search-wrap">
            <span className="search-icon" aria-hidden>
              <Search size={15} />
            </span>
            <input
              className="search"
              type="search"
              placeholder="Search company or role"
              aria-label="Search applications"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>
          <div className="filters" role="group" aria-label="Filter by status">
            {FILTERS.map((option) => (
              <button
                key={option.value}
                type="button"
                className={filter === option.value ? 'filter active' : 'filter'}
                aria-pressed={filter === option.value}
                onClick={() => setFilter(option.value)}
              >
                {option.label}
                <span className="filter-count">{countFor(option.value)}</span>
              </button>
            ))}
          </div>
        </div>

        {actionError && (
          <div className="error-callout callout-spaced">
            <span className="error-icon" aria-hidden>
              <TriangleAlert size={16} />
            </span>
            <div className="error-body">
              <span className="error-title">Update failed</span>
              <span className="error-text">{actionError}</span>
            </div>
          </div>
        )}

        {loading && (
          <div className="table-wrap">
            <TableSkeleton />
          </div>
        )}

        {!loading && error && (
          <div className="error-callout">
            <span className="error-icon" aria-hidden>
              <TriangleAlert size={16} />
            </span>
            <div className="error-body">
              <span className="error-title">Couldn't load applications</span>
              <span className="error-text">
                This is usually a network hiccup. Try again in a moment.
              </span>
              <button
                type="button"
                className="btn btn-sm callout-actions"
                onClick={() => setReloadKey((key) => key + 1)}
              >
                Try again
              </button>
            </div>
          </div>
        )}

        {!loading && !error && applications.length === 0 && (
          <div className="empty">
            <span className="empty-icon" aria-hidden>
              <Inbox size={20} />
            </span>
            {isFiltered ? (
              <>
                <span className="empty-title">No matching applications</span>
                <span className="empty-text">
                  Nothing matches this search or filter. Try a different view.
                </span>
                <button
                  type="button"
                  className="btn btn-sm"
                  onClick={() => {
                    setSearch('')
                    setFilter('ALL')
                  }}
                >
                  Clear filters
                </button>
              </>
            ) : (
              <>
                <span className="empty-title">No applications yet</span>
                <span className="empty-text">
                  Connect Gmail and run a sync to start tracking your
                  applications automatically.
                </span>
                <Link className="btn btn-sm" to="/settings">
                  Go to Settings
                </Link>
              </>
            )}
          </div>
        )}

        {!loading && !error && applications.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Company</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Updated</th>
                  <th aria-label="Actions" />
                </tr>
              </thead>
              <tbody>
                {applications.map((application) => (
                  <tr
                    key={application.id}
                    className={application.is_closed ? 'row-closed' : undefined}
                  >
                    <td className="cell-company">
                      <Link to={`/applications/${application.id}`}>
                        {application.company}
                      </Link>
                    </td>
                    <td className="cell-role">{application.role}</td>
                    <td className="cell-status">
                      <div className="status-cell-flex">
                        <StatusBadge
                          status={
                            application.is_closed ? 'CLOSED' : application.status
                          }
                        />
                        {!application.is_closed && (
                          <select
                            className="table-status-select"
                            value={application.status}
                            disabled={pendingId === application.id}
                            onChange={(e) =>
                              handleStatusChange(
                                application,
                                e.target.value as ApplicationStatus,
                              )
                            }
                            aria-label={`Change status for ${application.company}`}
                            title="Change status"
                          >
                            {Object.entries(STATUS_LABELS)
                              .filter(([key]) => key !== 'CLOSED')
                              .map(([key, label]) => (
                                <option key={key} value={key}>
                                  {label}
                                </option>
                              ))}
                          </select>
                        )}
                      </div>
                    </td>
                    <td className="cell-date">
                      {formatDateTime(application.updated_at)}
                    </td>
                    <td className="cell-actions">
                      <button
                        type="button"
                        className="icon-btn"
                        aria-label={
                          application.is_closed
                            ? `Reopen ${application.company} ${application.role}`
                            : `Mark ${application.company} ${application.role} as closed`
                        }
                        title={
                          application.is_closed
                            ? 'Reopen application'
                            : 'Mark as closed'
                        }
                        aria-busy={pendingId === application.id}
                        disabled={pendingId === application.id}
                        onClick={() => toggleClosed(application)}
                      >
                        {pendingId === application.id ? (
                          <span className="spinner sm" />
                        ) : application.is_closed ? (
                          <RotateCcw size={16} aria-hidden />
                        ) : (
                          <X size={16} aria-hidden />
                        )}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
