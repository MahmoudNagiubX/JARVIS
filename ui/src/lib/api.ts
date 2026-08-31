export interface JarvisSession {
  owner_id: string
  identity_id: string
  device_id: string
  csrf_token: string
  expires_at?: string
}

export interface ApiErrorShape {
  error?: string
  detail?: string
}

export class JarvisApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string) {
    super(code)
    this.name = 'JarvisApiError'
    this.status = status
    this.code = code
  }
}

type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>

export interface ApiClient {
  readonly session: JarvisSession | null
  setSession(session: JarvisSession | null): void
  get<T>(path: string, init?: RequestInit): Promise<T>
  post<T>(path: string, body?: unknown, init?: RequestInit): Promise<T>
  patch<T>(path: string, body?: unknown, init?: RequestInit): Promise<T>
  delete<T>(path: string, body?: unknown, init?: RequestInit): Promise<T>
}

function localPath(path: string): string {
  const normalized = path.startsWith('/') ? path : `/${path}`
  return normalized.startsWith('/v1/') ? normalized : `/v1${normalized}`
}

function methodIsMutation(method: string): boolean {
  return !['GET', 'HEAD', 'OPTIONS'].includes(method.toUpperCase())
}

async function readError(response: Response): Promise<string> {
  try {
    const payload = await response.json() as ApiErrorShape
    return String(payload.error || payload.detail || `request_failed_${response.status}`).slice(0, 240)
  } catch {
    return `request_failed_${response.status}`
  }
}

export function createApiClient(fetcher: Fetcher = globalThis.fetch.bind(globalThis)): ApiClient {
  let currentSession: JarvisSession | null = null

  async function request<T>(path: string, init: RequestInit & { body?: unknown } = {}): Promise<T> {
    const method = (init.method || 'GET').toUpperCase()
    const headers = new Headers(init.headers)
    let body: unknown = init.body
    if (body !== undefined && body !== null && typeof body !== 'string' && !(body instanceof FormData) && !(body instanceof Blob)) {
      headers.set('Content-Type', 'application/json')
      body = JSON.stringify(body)
    }
    if (methodIsMutation(method) && currentSession?.csrf_token) {
      headers.set('X-JARVIS-CSRF', currentSession.csrf_token)
    }

    const { body: _ignoredBody, ...rest } = init
    const response = await fetcher(localPath(path), {
      ...rest,
      method,
      body: body as BodyInit | null | undefined,
      headers,
      credentials: 'same-origin',
    })
    if (!response.ok) throw new JarvisApiError(response.status, await readError(response))
    if (response.status === 204) return {} as T
    return await response.json() as T
  }

  const get = <T,>(path: string, init?: RequestInit) => request<T>(path, { ...init, method: 'GET' })
  const post = <T,>(path: string, body?: unknown, init?: RequestInit) => request<T>(path, { ...init, method: 'POST', body } as RequestInit & { body?: unknown })
  const patch = <T,>(path: string, body?: unknown, init?: RequestInit) => request<T>(path, { ...init, method: 'PATCH', body } as RequestInit & { body?: unknown })
  const del = <T,>(path: string, body?: unknown, init?: RequestInit) => request<T>(path, { ...init, method: 'DELETE', body } as RequestInit & { body?: unknown })

  return {
    get, post, patch, delete: del,
    get session() { return currentSession },
    setSession(session) { currentSession = session },
  }
}

export function ownerScoped(path: string, ownerId: string, suffix = ''): string {
  const separator = path.includes('?') ? '&' : '?'
  return `${path}${separator}owner_id=${encodeURIComponent(ownerId)}${suffix}`
}
