import React, { useEffect, useState } from 'react'
import { apiGet } from '../api/client'

export function Inbox({ onError }: { onError: (e: string | null) => void }) {
  const [items, setItems] = useState<any[]>([])
  const [next, setNext] = useState<string | null>(null)
  useEffect(() => { load() }, [])
  async function load(cursor?: string) {
    try {
      const r = await apiGet(`/api/v1/inbox/items${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`)
      setItems(r.items || [])
      setNext(r.next || null)
      onError(null)
    } catch (e: any) {
      onError(e.message)
    }
  }
  return (
    <div>
      <h2>Inbox</h2>
      <ul>
        {items.map(it => (
          <li key={it.id}>{it.id} — {it.status} — {it.mime}</li>
        ))}
      </ul>
      <button disabled={!next} onClick={() => load(next!)}>Next</button>
    </div>
  )
}

