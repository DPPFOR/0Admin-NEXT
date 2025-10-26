import { describe, it, expect, beforeEach, vi } from 'vitest'
import { Overview } from '../views/Overview'
import { renderToString } from 'react-dom/server'

describe('Overview', () => {
  beforeEach(() => {
    global.fetch = vi.fn(async (url: any) => {
      const u = String(url)
      if (u.endsWith('/health/ready')) return new Response(JSON.stringify({ status: 'OK' }), { headers: { 'content-type': 'application/json' } })
      if (u.includes('/api/v1/ops/outbox')) return new Response(JSON.stringify({ outbox: { pending: 1, sent: 2 } }), { headers: { 'content-type': 'application/json' } })
      if (u.includes('/api/v1/ops/dlq')) return new Response(JSON.stringify({ items: [] }), { headers: { 'content-type': 'application/json' } })
      return new Response('not found', { status: 404 })
    }) as any
  })

  it('renders health/outbox/dlq', async () => {
    const html = renderToString(<Overview onError={() => {}} />)
    expect(html).toContain('Overview')
  })
})

