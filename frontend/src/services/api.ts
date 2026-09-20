// api.ts - typed API client for the FastAPI backend

import axios from 'axios'
import type {
  Application,
  ApplicationEvent,
  ApplicationListResponse,
  ApplicationStats,
} from '../types'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

export interface ApplicationFilters {
  status?: string
  company?: string
  search?: string
  limit?: number
  offset?: number
  include_closed?: boolean
}

export async function getApplicationStats(): Promise<ApplicationStats> {
  const { data } = await api.get<ApplicationStats>('/applications/stats')
  return data
}

export async function getApplications(
  filters: ApplicationFilters = {},
): Promise<ApplicationListResponse> {
  const { data } = await api.get<ApplicationListResponse>('/applications', {
    params: filters,
  })
  return data
}

export async function getApplication(id: number): Promise<Application> {
  const { data } = await api.get<Application>(`/applications/${id}`)
  return data
}

export async function getApplicationEvents(
  id: number,
): Promise<ApplicationEvent[]> {
  const { data } = await api.get<ApplicationEvent[]>(`/applications/${id}/events`)
  return data
}

export async function setApplicationClosed(
  id: number,
  isClosed: boolean,
): Promise<Application> {
  const { data } = await api.patch<Application>(`/applications/${id}`, {
    is_closed: isClosed,
  })
  return data
}

export default api

// Gmail & auth endpoints
export async function getAuthUrl(): Promise<string> {
  // /api/auth/url does a 307 redirect — return the redirect target URL
  // We open it directly in the browser, so just build the URL
  return `${api.defaults.baseURL}/auth/url`
}

export async function registerWatch(): Promise<{ history_id: string | null; expiration: string | null }> {
  const { data } = await api.post('/gmail/watch')
  return data
}

export interface SyncResult {
  fetched: number
  processed: unknown[]
}

export async function triggerFullSync(): Promise<SyncResult> {
  const { data } = await api.post<SyncResult>('/gmail/sync')
  return data
}
