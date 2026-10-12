export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  const response = await fetch('/api' + path, { method, headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined });
  if (!response.ok) {
    let message = `Request failed (${response.status}). Is the backend running?`;
    try { const data = await response.json(); message = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail); } catch { /* use fallback */ }
    throw new Error(message);
  }
  return response.headers.get('content-type')?.includes('json') ? response.json() : response.text() as Promise<T>;
}
export function time(ms: number) { return new Date(ms).toISOString().slice(11, 19); }
export function download(content: string, filename: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
