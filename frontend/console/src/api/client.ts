import { v4 as uuidv4 } from 'uuid'

export type ConsoleConfig = { base?: string; token?: string; tenant?: string }

let cfg: ConsoleConfig = { base: import.meta.env.VITE_API_BASE }

export function setConfig(c: ConsoleConfig) {
  cfg = { ...cfg, ...c }
}

export async function apiGet(path: string): Promise<any> {
  const trace = uuidv4()
  const res = await fetch(`${cfg.base}${path}`, {
    headers: {
      'Authorization': cfg.token ? `Bearer ${cfg.token}` : '',
      'X-Tenant': cfg.tenant || '',
      'X-Trace-ID': trace
    }
  })
  const ct = res.headers.get('content-type') || ''
  const body = ct.includes('application/json') ? await res.json() : await res.text()
  if (!res.ok) {
    throw new Error(typeof body === 'string' ? body : JSON.stringify(body))
  }
  return body
}

