import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
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
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

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
      setActionError('Could not update this application.')
    } finally {
      setPending(false)
    }
  }

  useEffect(() => {
    if (!id) return
    const applicationId = Number(id)
    let active = true

    setLoading(true)
    setError(null)
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
        if (active) setError('Could not load this application.')
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [id])

  return (
    <div className="page">
      <Link className="back" to="/">
        ← Back to applications
      </Link>

      {loading && <p className="state">Loading application...</p>}
      {error && <p className="state error">{error}</p>}

      {!loading && !error && application && (
        <>
          <header className="page-header detail-header">
            <div>
              <h1>{application.company}</h1>
              <p className="muted">{application.role}</p>
            </div>
            <div className="detail-actions">
              {application.action_url && (
                <a
                  href={application.action_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="action-btn"
                >
                  Open Link ↗
                </a>
              )}
              <StatusBadge
                status={application.is_closed ? 'CLOSED' : application.status}
              />
              <button
                className="btn small"
                onClick={toggleClosed}
                disabled={pending}
                title={
                  application.is_closed
                    ? 'Reopen application'
                    : 'Mark as closed'
                }
              >
                {pending ? (
                  <>
                    <span className="spinner small" /> Working...
                  </>
                ) : application.is_closed ? (
                  'Reopen'
                ) : (
                  'Mark as closed'
                )}
              </button>
            </div>
          </header>

          {actionError && <p className="state error">{actionError}</p>}

          <section className="panel detail-grid">
            <div>
              <span className="field-label">Company</span>
              <span>{application.company}</span>
            </div>
            <div>
              <span className="field-label">Role</span>
              <span>{application.role}</span>
            </div>
            <div>
              <span className="field-label">Status</span>
              <span>
                {statusLabel(application.is_closed ? 'CLOSED' : application.status)}
              </span>
            </div>
            <div>
              <span className="field-label">Applied</span>
              <span>{formatDateTime(application.applied_at)}</span>
            </div>
            <div>
              <span className="field-label">Last updated</span>
              <span>{formatDateTime(application.updated_at)}</span>
            </div>
            {application.event_date && (
              <div>
                <span className="field-label">Scheduled / Deadline</span>
                <span className="highlight-date">🗓 {application.event_date}</span>
              </div>
            )}
            {application.notes && (
              <div className="notes-span">
                <span className="field-label">Latest Summary</span>
                <p className="note-text">{application.notes}</p>
              </div>
            )}
          </section>

          <section className="panel">
            <h2>Timeline</h2>
            {events.length === 0 ? (
              <p className="state">No events recorded yet.</p>
            ) : (
              <ol className="timeline">
                {events.map((event) => (
                  <li key={event.id} className="timeline-item">
                    <span className="timeline-dot" />
                    <div className="timeline-body">
                      <div className="timeline-header">
                        <span className="timeline-status">
                          {statusLabel(event.status)}
                        </span>
                        <span className="timeline-date muted">
                          {formatDateTime(event.created_at)}
                        </span>
                      </div>
                      {event.note && (
                        <p className="timeline-note">{event.note}</p>
                      )}
                      {(event.event_date || event.action_url) && (
                        <div className="timeline-meta">
                          {event.event_date && (
                            <span className="meta-chip date-chip">
                              🗓 {event.event_date}
                            </span>
                          )}
                          {event.action_url && (
                            <a
                              href={event.action_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="meta-chip link-chip"
                            >
                              🔗 Link ↗
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
