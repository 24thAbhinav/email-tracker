import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  Calendar,
  Link2,
  RotateCcw,
  TriangleAlert,
  X,
} from 'lucide-react'
import StatusBadge, { statusLabel } from '../components/StatusBadge'
import {
  getApplication,
  getApplicationEvents,
  setApplicationClosed,
} from '../services/api'
import type { Application, ApplicationEvent } from '../types'
import { formatDateTime } from '../utils/format'

export default function ApplicationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [application, setApplication] = useState<Application | null>(null)
  const [events, setEvents] = useState<ApplicationEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  const [pending, setPending] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    const applicationId = Number(id)
    let active = true

    setLoading(true)
    setError(false)
    Promise.all([
      getApplication(applicationId),
      getApplicationEvents(applicationId),
    ])
      .then(([loadedApplication, loadedEvents]) => {
        if (!active) return
        setApplication(loadedApplication)
        setEvents(loadedEvents)
      })
      .catch(() => {
        if (active) setError(true)
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [id, reloadKey])

  const toggleClosed = async () => {
    if (!application) return
    setPending(true)
    setActionError(null)
    try {
      const updated = await setApplicationClosed(
        application.id,
        !application.is_closed,
      )
      setApplication(updated)
    } catch {
      setActionError('Could not update this application. Please try again.')
    } finally {
      setPending(false)
    }
  }

  const displayStatus = application
    ? application.is_closed
      ? 'CLOSED'
      : application.status
    : 'APPLIED'

  return (
    <div className="page">
      <Link className="back" to="/">
        <ArrowLeft size={15} aria-hidden />
        Back to applications
      </Link>

      {loading && (
        <div className="panel">
          <span className="skeleton" style={{ width: '40%', height: 22 }} />
          <div className="skeleton-stack">
            <span className="skeleton" style={{ width: '25%' }} />
            <span className="skeleton" style={{ width: '30%' }} />
          </div>
        </div>
      )}

      {!loading && error && (
        <div className="error-callout">
          <span className="error-icon" aria-hidden>
            <TriangleAlert size={16} />
          </span>
          <div className="error-body">
            <span className="error-title">Couldn't load this application</span>
            <span className="error-text">
              It may have been removed, or the backend is unreachable.
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

      {!loading && !error && application && (
        <>
          <header className="detail-header">
            <div>
              <h1 className="detail-company">{application.company}</h1>
              <p className="detail-role">{application.role}</p>
            </div>
            <div className="detail-actions">
              <StatusBadge status={displayStatus} />
              {application.action_url && (
                <a
                  className="btn btn-sm"
                  href={application.action_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <Link2 size={15} aria-hidden />
                  Open link
                </a>
              )}
              <button
                type="button"
                className="btn btn-sm"
                onClick={toggleClosed}
                disabled={pending}
                aria-busy={pending}
              >
                {pending ? (
                  <>
                    <span className="spinner sm" /> Working
                  </>
                ) : application.is_closed ? (
                  <>
                    <RotateCcw size={15} aria-hidden /> Reopen
                  </>
                ) : (
                  <>
                    <X size={15} aria-hidden /> Mark as closed
                  </>
                )}
              </button>
            </div>
          </header>

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

          <section className="panel detail-grid">
            <div className="field">
              <span className="field-label">Company</span>
              <span className="field-value">{application.company}</span>
            </div>
            <div className="field">
              <span className="field-label">Role</span>
              <span className="field-value">{application.role}</span>
            </div>
            <div className="field">
              <span className="field-label">Status</span>
              <span className="field-value">{statusLabel(displayStatus)}</span>
            </div>
            <div className="field">
              <span className="field-label">Applied</span>
              <span className="field-value mono">
                {formatDateTime(application.applied_at)}
              </span>
            </div>
            <div className="field">
              <span className="field-label">Last updated</span>
              <span className="field-value mono">
                {formatDateTime(application.updated_at)}
              </span>
            </div>
            {application.event_date && (
              <div className="field">
                <span className="field-label">Scheduled / deadline</span>
                <span className="field-value mono">{application.event_date}</span>
              </div>
            )}
            {application.notes && (
              <div className="field field-span">
                <span className="field-label">Latest summary</span>
                <p className="note-block">{application.notes}</p>
              </div>
            )}
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2 className="panel-title">Timeline</h2>
              <span className="panel-meta">
                {events.length} {events.length === 1 ? 'event' : 'events'}
              </span>
            </div>
            {events.length === 0 ? (
              <div className="empty">
                <span className="empty-icon" aria-hidden>
                  <Calendar size={20} />
                </span>
                <span className="empty-title">No events yet</span>
                <span className="empty-text">
                  Status changes from future emails will appear here.
                </span>
              </div>
            ) : (
              <ol className="timeline">
                {events.map((event) => (
                  <li key={event.id} className="timeline-item">
                    <span className="timeline-marker" aria-hidden />
                    <div className="timeline-body">
                      <div className="timeline-head">
                        <span className="timeline-status">
                          {statusLabel(event.status)}
                        </span>
                        <span className="timeline-date">
                          {formatDateTime(event.created_at)}
                        </span>
                      </div>
                      {event.note && (
                        <p className="timeline-note">{event.note}</p>
                      )}
                      {(event.event_date || event.action_url) && (
                        <div className="timeline-meta">
                          {event.event_date && (
                            <span className="meta-chip">
                              <Calendar size={13} aria-hidden />
                              {event.event_date}
                            </span>
                          )}
                          {event.action_url && (
                            <a
                              className="meta-chip link"
                              href={event.action_url}
                              target="_blank"
                              rel="noopener noreferrer"
                            >
                              <Link2 size={13} aria-hidden />
                              Open link
                            </a>
                          )}
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </>
      )}
    </div>
  )
}
