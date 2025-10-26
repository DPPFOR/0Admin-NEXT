import React, { useEffect, useState } from 'react'
import { apiGet } from '../api/client'

export function Overview({ onError }: { onError: (e: string | null) => void }) {
  const [health, setHealth] = useState<any>(null)
  const [outbox, setOutbox] = useState<any>(null)
  const [dlqCount, setDlqCount] = useState<number | null>(null)

  useEffect(() => {
    async function load() {
      try {
        const h = await apiGet('/health/ready')
        setHealth(h)
        const o = await apiGet('/api/v1/ops/outbox')
        setOutbox(o.outbox)
        const d = await apiGet('/api/v1/ops/dlq?limit=1')
        setDlqCount((d.items || []).length)
        onError(null)
      } catch (e: any) {
        onError(e.message)
      }
    }
    load()
  }, [])

  return (
    <div>
      <h2>Overview</h2>
      <div>Health: {health ? health.status : 'loading...'}</div>
      <div>Outbox: {outbox ? JSON.stringify(outbox) : 'loading...'}</div>
      <div>DLQ Count: {dlqCount ?? 'loading...'}</div>
      <div>Updated: {new Date().toISOString()}</div>
    </div>
  )
}

