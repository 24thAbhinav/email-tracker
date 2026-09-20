import { useState } from 'react'
import {
  BellRing,
  Check,
  Mail,
  RefreshCw,
  TriangleAlert,
} from 'lucide-react'
import { getAuthUrl, registerWatch, triggerFullSync } from '../services/api'

type Action = 'auth' | 'watch' | 'sync'
type Message = { type: 'success' | 'error'; text: string }

function errorMessage(error: unknown): string {
  if (typeof error === 'object' && error !== null) {
    const detail = (error as { response?: { data?: { detail?: unknown } } })
      .response?.data?.detail
    if (typeof detail === 'string') return detail
    const message = (error as { message?: unknown }).message
    if (typeof message === 'string') return message
  }
  return 'Something went wrong. Please try again.'
}

function Notice({ message }: { message: Message }) {
  return (
    <p className={`notice ${message.type}`} role="status">
      <span className="icon" aria-hidden>
        {message.type === 'error' ? (
          <TriangleAlert size={15} />
        ) : (
          <Check size={15} />
        )}
      </span>
      {message.text}
    </p>
  )
}

export default function SettingsPage() {
  const [loading, setLoading] = useState<Action | null>(null)
  const [gmailError, setGmailError] = useState<string | null>(null)
  const [watchMessage, setWatchMessage] = useState<Message | null>(null)
  const [syncMessage, setSyncMessage] = useState<Message | null>(null)

  const connectGmail = async () => {
    setLoading('auth')
    setGmailError(null)
    try {
      const url = await getAuthUrl()
      window.location.href = url
    } catch (error) {
      setGmailError(errorMessage(error))
      setLoading(null)
    }
  }

  const registerGmailWatch = async () => {
    setLoading('watch')
    setWatchMessage(null)
    try {
      await registerWatch()
      setWatchMessage({
        type: 'success',
        text: 'Watch registered. Gmail will push new emails automatically.',
      })
    } catch (error) {
      setWatchMessage({ type: 'error', text: errorMessage(error) })
    } finally {
      setLoading(null)
    }
  }

  const runFullSync = async () => {
    setLoading('sync')
    setSyncMessage(null)
    try {
      const result = await triggerFullSync()
      const fetched = result.fetched
      const added = result.processed.length
      const skipped = Math.max(fetched - added, 0)
      setSyncMessage({
        type: 'success',
        text:
          fetched === 0
            ? 'Sync complete. No emails to fetch.'
            : `Sync complete. Refetched ${fetched} email${
                fetched === 1 ? '' : 's'
              } — ${added} new, ${skipped} already tracked.`,
      })
    } catch (error) {
      setSyncMessage({ type: 'error', text: errorMessage(error) })
    } finally {
      setLoading(null)
    }
  }

  const busy = loading !== null

  return (
    <div className="page">
      <header className="page-header">
        <p className="page-eyebrow">Configuration</p>
        <h1 className="page-title">Settings</h1>
        <p className="page-subtitle">
          Connect your inbox and control how new applications are ingested.
        </p>
      </header>

      <section className="panel">
        <div className="setting">
          <div className="setting-info">
            <span className="setting-title">Gmail connection</span>
            <span className="setting-desc">
              You'll be redirected to Google to authorize read access to your
              inbox. Do this once.
            </span>
          </div>
          <button
            type="button"
            className="btn-primary"
            onClick={connectGmail}
            disabled={busy}
            aria-busy={loading === 'auth'}
          >
            {loading === 'auth' ? (
              <>
                <span className="spinner sm" /> Connecting
              </>
            ) : (
              <>
                <Mail size={15} aria-hidden /> Connect Gmail
              </>
            )}
          </button>
        </div>
        {gmailError && <Notice message={{ type: 'error', text: gmailError }} />}
      </section>

      <section className="panel">
        <div className="setting">
          <div className="setting-info">
            <span className="setting-title">Push notifications</span>
            <span className="setting-desc">
              Subscribe Gmail to your Pub/Sub topic so new mail is processed as
              it arrives. Watches expire roughly weekly — re-run before then.
            </span>
          </div>
          <button
            type="button"
            className="btn"
            onClick={registerGmailWatch}
            disabled={busy}
            aria-busy={loading === 'watch'}
          >
            {loading === 'watch' ? (
              <>
                <span className="spinner sm" /> Working
              </>
            ) : (
              <>
                <BellRing size={15} aria-hidden /> Register watch
              </>
            )}
          </button>
        </div>
        {watchMessage && <Notice message={watchMessage} />}
      </section>

      <section className="panel">
        <div className="setting">
          <div className="setting-info">
            <span className="setting-title">Manual sync</span>
            <span className="setting-desc">
              Pull recent messages now and run them through the classifier. Use
              this to backfill history or test without waiting for a push.
            </span>
          </div>
          <button
            type="button"
            className="btn"
            onClick={runFullSync}
            disabled={busy}
            aria-busy={loading === 'sync'}
          >
            {loading === 'sync' ? (
              <>
                <span className="spinner sm" /> Syncing
              </>
            ) : (
              <>
                <RefreshCw size={15} aria-hidden /> Run full sync
              </>
            )}
          </button>
        </div>
        {syncMessage && <Notice message={syncMessage} />}
      </section>
    </div>
  )
}
