import type { Dialect, QueryResponse, SchemaInput, SessionDetail, SessionSummary } from './types'

const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')
const CLIENT_ID_KEY = 'sqlbuddy.clientId'
let transientClientId: string | undefined

function clientId(): string {
  if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    return 'local'
  }
  try {
    const saved = window.localStorage.getItem(CLIENT_ID_KEY)
    if (saved) return saved
    const created = crypto.randomUUID()
    window.localStorage.setItem(CLIENT_ID_KEY, created)
    return created
  } catch {
    // If browser storage is unavailable, keep this page's history scope stable.
    transientClientId ??= crypto.randomUUID()
    return transientClientId
  }
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}/api/v1${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        'X-SQLBuddy-Client-ID': clientId(),
        ...init?.headers,
      },
    })
  } catch {
    throw new ApiError('Could not reach SQLBuddy. Check that the backend is running.', 0)
  }
  if (!response.ok) {
    const result = await response.json().catch(() => null) as { error?: { message?: string } } | null
    throw new ApiError(result?.error?.message ?? 'Something went wrong. Please try again.', response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export const api = {
  createQuery: (question: string, dialect: Dialect, schema: SchemaInput | null, sessionId?: string) =>
    request<QueryResponse>('/queries', {
      method: 'POST',
      body: JSON.stringify({ question, dialect, schema, session_id: sessionId ?? null }),
    }),
  listSessions: () => request<SessionSummary[]>('/sessions'),
  getSession: (id: string) => request<SessionDetail>(`/sessions/${id}`),
  renameSession: (id: string, title: string) =>
    request<SessionSummary>(`/sessions/${id}`, { method: 'PATCH', body: JSON.stringify({ title }) }),
  deleteSession: (id: string) => request<void>(`/sessions/${id}`, { method: 'DELETE' }),
}
