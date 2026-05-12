// Centralised API client — all backend calls go through the Vite dev proxy.
// In production, set VITE_API_URL to your backend base URL.
const BASE = import.meta.env.VITE_API_URL
  ? import.meta.env.VITE_API_URL.replace(/\/$/, '')
  : '';          // Empty string = same origin (proxy handles it in dev)

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export const api = {
  health:           ()             => req('/health'),
  createUser:       ()             => req('/api/users', { method: 'POST' }),
  getMonths:        (uid)          => req(`/api/months/${uid}`),
  getSummary:       (uid, y, m)    => req(`/api/summary/${uid}/${y}/${m}`),
  getTransactions:  (uid, y, m, p) => req(`/api/transactions/${uid}/${y}/${m}?page=${p}&per_page=50`),
  getComparison:    (uid)          => req(`/api/comparison/${uid}`),
  getSubscriptions: (uid)          => req(`/api/subscriptions/${uid}`),
  getJobStatus:     (jobId)        => req(`/api/jobs/${jobId}`),

  updateTransaction: (id, data) => req(`/api/transactions/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }),

  deleteStatement: (uid, y, m) =>
    req(`/api/statements/${uid}/${y}/${m}`, { method: 'DELETE' }),

  uploadStatement: (formData) =>
    fetch(`${BASE}/api/upload`, { method: 'POST', body: formData })
      .then(r =>
        r.ok
          ? r.json()
          : r.json().then(b => Promise.reject(new Error(b.detail || 'Upload failed')))
      ),
};
