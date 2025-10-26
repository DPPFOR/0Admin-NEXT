import React, { useEffect, useState } from 'react'
import { Overview } from './views/Overview'
import { Tenants } from './views/Tenants'
import { Inbox } from './views/Inbox'
import { Parsed } from './views/Parsed'
import { apiGet, setConfig, ConsoleConfig } from './api/client'

type View = 'overview' | 'tenants' | 'inbox' | 'parsed'

export function App() {
  const [view, setView] = useState<View>('overview')
  const [tenant, setTenant] = useState('')
  const [token, setToken] = useState('')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const cfg = (window as any).__CONSOLE_CONFIG__ as ConsoleConfig | undefined
    if (cfg) {
      setConfig(cfg)
      setTenant(cfg.tenant || '')
      setToken(cfg.token || '')
    }
  }, [])

  function updateConfig() {
    setConfig({ token, tenant, base: import.meta.env.VITE_API_BASE })
  }

  return (
    <div style={{ fontFamily: 'sans-serif', padding: 16 }}>
      <h1>0Admin Mini-Console</h1>
      <div style={{ marginBottom: 8 }}>
        <label>Tenant:&nbsp;<input value={tenant} onChange={e => setTenant(e.target.value)} /></label>
        &nbsp;&nbsp;
        <label>Token:&nbsp;<input value={token} onChange={e => setToken(e.target.value)} type="password" /></label>
        &nbsp;&nbsp;
        <button onClick={updateConfig}>Apply</button>
      </div>
      {error && <div style={{ color: 'red' }}>{error}</div>}
      <nav style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
        <button onClick={() => setView('overview')}>Overview</button>
        <button onClick={() => setView('tenants')}>Tenants</button>
        <button onClick={() => setView('inbox')}>Inbox</button>
        <button onClick={() => setView('parsed')}>Parsed</button>
      </nav>
      {view === 'overview' && <Overview onError={setError} />}
      {view === 'tenants' && <Tenants onError={setError} />}
      {view === 'inbox' && <Inbox onError={setError} />}
      {view === 'parsed' && <Parsed onError={setError} />}
    </div>
  )
}

