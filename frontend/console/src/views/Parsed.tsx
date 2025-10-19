import React, { useEffect, useState } from 'react'
import { apiGet } from '../api/client'

export function Parsed({ onError }: { onError: (e: string | null) => void }) {
  const [items, setItems] = useState<any[]>([])
  const [next, setNext] = useState<string | null>(null)
  useEffect(() => { load() }, [])
  async function load(cursor?: string) {
    try {
      const r = await apiGet(`/api/v1/parsed/items${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''}`)
      setItems(r.items || [])
      setNext(r.next || null)
      onError(null)
    } catch (e: any) {
      onError(e.message)
    }
  }
  return (
    <div>
      <h2>Parsed</h2>
      <ul>
        {items.map(it => (
          <li key={it.id}>{it.id} — {it.doc_type} — {it.amount || ''}</li>
        ))}
      </ul>
      <button disabled={!next} onClick={() => load(next!)}>Next</button>
    </div>
  )
}

