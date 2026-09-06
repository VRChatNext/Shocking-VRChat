const BASE = ''

export async function api<T = any>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(BASE + path, options)
  if (!resp.ok) throw new Error(`API ${resp.status}: ${resp.statusText}`)
  return resp.json()
}

export function apiPost<T = any>(path: string, body?: any): Promise<T> {
  return api(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
}

export function apiDelete<T = any>(path: string): Promise<T> {
  return api(path, { method: 'DELETE' })
}

export function apiPut<T = any>(path: string, body?: any): Promise<T> {
  return api(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
}
