import { describe, expect, it, vi } from 'vitest'
import { createApiClient, type JarvisSession } from './api'

const session: JarvisSession = {
  owner_id: 'owner-1',
  identity_id: 'identity-1',
  device_id: 'device-1',
  csrf_token: 'csrf-1',
}

describe('JARVIS API adapter', () => {
  it('uses the local /v1 boundary and never puts credentials in browser requests', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }))
    const api = createApiClient(fetcher)

    await api.get('/experience/state')

    expect(fetcher).toHaveBeenCalledWith('/v1/experience/state', expect.objectContaining({
      credentials: 'same-origin',
    }))
    const request = fetcher.mock.calls[0]?.[1] as RequestInit
    expect(JSON.stringify(request)).not.toContain('Authorization')
  })

  it('adds the session CSRF header only to authenticated mutations', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response('{}', { status: 200 }))
    const api = createApiClient(fetcher)
    api.setSession(session)

    await api.post('/messages', { text: 'hello' })

    const request = fetcher.mock.calls[0]?.[1] as RequestInit
    expect(new Headers(request.headers).get('X-JARVIS-CSRF')).toBe('csrf-1')
    expect(new Headers(request.headers).get('Content-Type')).toBe('application/json')
    expect(request.body).toBe(JSON.stringify({ text: 'hello' }))
  })

  it('returns bounded server error details without leaking raw response bodies', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({ error: 'owner_denied' }), { status: 403 }))
    const api = createApiClient(fetcher)

    await expect(api.get('/memory')).rejects.toMatchObject({ status: 403, code: 'owner_denied' })
  })
})
