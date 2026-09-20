import { useState } from 'react'
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
  return 'Something went wrong.'
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
      await triggerFullSync()
      setSyncMessage({ type: 'success', text: 'Sync complete.' })
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
        <h1>Settings</h1>
      </header>

      <section className="panel">
        <h2>Gmail Connection</h2>
        <p className="muted">
          You'll be redirected to Google to authorize access to your Gmail inbox.
        </p>
        <button className="btn-primary" onClick={connectGmail} disabled={busy}>
          {loading === 'auth' ? (
            <>
              <span className="spinner" /> Working...
            </>
          ) : (
            'Connect Gmail'
          )}
        </button>
        {gmailError && <p className="notice error">{gmailError}</p>}
      </section>

      <section className="panel">
        <h2>Push Notifications</h2>
        <button className="btn" onClick={registerGmailWatch} disabled={busy}>
          {loading === 'watch' ? (
            <>
              <span className="spinner" /> Working...
            </>
          ) : (
            'Register Gmail Watch'
          )}
        </button>
        {watchMessage && (
          <p className={`notice ${watchMessage.type}`}>{watchMessage.text}</p>
        )}
      </section>

      <section className="panel">
        <h2>Manual Sync</h2>
        <button className="btn" onClick={runFullSync} disabled={busy}>
          {loading === 'sync' ? (
            <>
              <span className="spinner" /> Working...
            </>
          ) : (
            'Run Full Sync'
          )}
        </button>
        {syncMessage && (
          <p className={`notice ${syncMessage.type}`}>{syncMessage.text}</p>
        )}
      </section>
    </div>
  )
}
