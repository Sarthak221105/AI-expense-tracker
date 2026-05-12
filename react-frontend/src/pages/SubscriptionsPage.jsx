import { useState, useEffect } from 'react';
import { RefreshCw, CalendarClock, TrendingUp } from 'lucide-react';
import { api } from '../api.js';
import { fmtNum } from '../utils.js';

export default function SubscriptionsPage({ userId }) {
  const [data,    setData]    = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!userId) return;
    setLoading(true);
    api.getSubscriptions(userId)
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [userId]);

  if (loading) return (
    <div style={{ padding: '3rem', display: 'flex', justifyContent: 'center' }}>
      <div className="spinner" />
    </div>
  );

  const subs = data?.subscriptions || [];

  return (
    <div className="flex-col gap-6" style={{ padding: '1.5rem', maxWidth: 900, margin: '0 auto' }}>
      <div>
        <h1>Subscriptions</h1>
        <p className="text-secondary mt-1">Recurring charges detected across all uploaded months.</p>
      </div>

      {/* Summary card */}
      {data && (
        <div className="grid-2">
          <div className="stat-card savings">
            <div className="stat-label">Total Monthly</div>
            <div className="stat-value text-accent">{fmtNum(subs.reduce((s,x) => s + x.amount, 0))}</div>
          </div>
          <div className="stat-card expense">
            <div className="stat-label">Estimated Annual</div>
            <div className="stat-value text-danger">{fmtNum(data.total_annual_cost)}</div>
          </div>
        </div>
      )}

      {/* List */}
      {subs.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
          <RefreshCw size={40} color="var(--text-muted)" style={{ margin: '0 auto 1rem' }} />
          <p className="text-secondary">No subscriptions detected yet.<br />Upload at least 2 months of data.</p>
        </div>
      ) : (
        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Merchant</th>
                  <th>Frequency</th>
                  <th>Last Charged</th>
                  <th style={{ textAlign: 'right' }}>Monthly</th>
                  <th style={{ textAlign: 'right' }}>Annual Cost</th>
                </tr>
              </thead>
              <tbody>
                {subs.map((s, i) => (
                  <tr key={i}>
                    <td>
                      <div className="flex items-center gap-3">
                        <div style={{ width: 36, height: 36, borderRadius: 10, background: 'rgba(108,99,255,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '.85rem', fontWeight: 700, color: 'var(--accent)', flexShrink: 0 }}>
                          {s.merchant?.charAt(0)?.toUpperCase() || '?'}
                        </div>
                        <span className="font-bold">{s.merchant}</span>
                      </div>
                    </td>
                    <td>
                      <div className="flex items-center gap-2">
                        <CalendarClock size={14} color="var(--text-muted)" />
                        <span className="text-sm text-secondary" style={{ textTransform: 'capitalize' }}>{s.frequency}</span>
                      </div>
                    </td>
                    <td className="text-sm text-muted font-mono">{s.last_charged || '—'}</td>
                    <td style={{ textAlign: 'right', fontWeight: 700, color: 'var(--accent)' }}>
                      {fmtNum(s.amount)}
                    </td>
                    <td style={{ textAlign: 'right', color: 'var(--danger)', fontWeight: 600 }}>
                      {fmtNum(s.annual_cost)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
