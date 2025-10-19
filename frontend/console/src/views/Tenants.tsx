import React, { useEffect, useState } from 'react'
import { apiGet } from '../api/client'

export function Tenants({ onError }: { onError: (e: string | null) => void }) {
  const [data, setData] = useState<any>(null)
  useEffect(() => {
    async function load() {
      try {
        const r = await apiGet('/api/v1/ops/tenants')
        setData(r)
        onError(null)
      } catch (e: any) {
        onError(e.message)
      }
    }
    load()
  }, [])

  return (
    <div>
      <h2>Tenants</h2>
      {data ? (
        <div>
          <div>Source: {data.source}</div>
          <div>Version: {data.version}</div>
          <div>Count: {data.count}</div>
          <pre>{JSON.stringify(data.tenants, null, 2)}</pre>
        </div>
      ) : 'loading...'}
    </div>
  )
}

