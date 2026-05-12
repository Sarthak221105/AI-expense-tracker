import { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown, Minus, Brain, RefreshCw } from 'lucide-react';
import {
  PieChart, Pie, Cell, Tooltip, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Legend,
} from 'recharts';
import { api } from '../api.js';
import { fmtNum, MONTHS, CAT_COLORS } from '../utils.js';

function HealthRing({ score }) {
  const r = 34, c = 2 * Math.PI * r;
  const filled = (score / 100) * c;
  const color = score >= 70 ? 'var(--success)' : score >= 40 ? 'var(--warning)' : 'var(--danger)';
  return (
    <div className="health-ring">
      <svg width="80" height="80" viewBox="0 0 80 80">
        <circle cx="40" cy="40" r={r} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth="7" />
        <circle cx="40" cy="40" r={r} fill="none" stroke={color} strokeWidth="7"
          strokeDasharray={`${filled} ${c}`} strokeLinecap="round" style={{ transition: 'stroke-dasharray 1s ease' }} />
      </svg>
      <div className="score-text">
        <span style={{ color, fontSize: '1rem', fontWeight: 800 }}>{score}</span>
        <span style={{ fontSize: '.55rem', color: 'var(--text-muted)', letterSpacing: '.04em' }}>/ 100</span>
      </div>
    </div>
  );
}

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: '#fff', border: '1px solid #ddd8ce',
      borderRadius: 8, padding: '.55rem .85rem',
      fontSize: '.8rem', boxShadow: '0 4px 12px rgba(28,24,20,0.1)',
    }}>
      <p style={{ fontWeight: 600, color: '#1a1814' }}>{payload[0].name}</p>
      <p style={{ color: '#c0522a', marginTop: 2, fontWeight: 700 }}>{fmtNum(payload[0].value)}</p>
    </div>
  );
};

export default function DashboardPage({ userId, selectedMonth, onMonthChange, availableMonths }) {
  const [summary,    setSummary]    = useState(null);
  const [comparison, setComparison] = useState(null);
  const [loading,    setLoading]    = useState(false);

  const { month, year } = selectedMonth || {};

  useEffect(() => {
    if (!userId || !month || !year) return;
    setLoading(true);
    Promise.all([
      api.getSummary(userId, year, month),
      api.getComparison(userId).catch(() => null),
    ]).then(([s, c]) => { setSummary(s); setComparison(c); })
      .finally(() => setLoading(false));
  }, [userId, month, year]);

  if (!selectedMonth) return (
    <div style={{ padding: '3rem', textAlign: 'center' }}>
      <Brain size={48} color="var(--text-muted)" style={{ margin: '0 auto 1rem' }} />
      <p className="text-secondary">No data yet. Upload a bank statement to get started.</p>
    </div>
  );

  if (loading) return (
    <div style={{ padding: '3rem', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem' }}>
      <div className="spinner" />
      <p className="text-secondary">Loading dashboard…</p>
    </div>
  );

  if (!summary) return <div style={{ padding: '2rem' }}><p className="text-danger">Could not load summary.</p></div>;

  const catData = Object.entries(JSON.parse(summary.category_breakdown || '{}')).map(([name, value]) => ({ name, value }));
  const trendData = comparison?.summaries?.map(s => ({
    name: `${MONTHS[s.month - 1]} ${s.year}`,
    Income: s.total_income,
    Expenses: s.total_expenses,
    Savings: s.net_savings,
  })) || [];

  return (
    <div className="flex-col gap-6" style={{ padding: '1.5rem', maxWidth: 1100, margin: '0 auto' }}>

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1>Financial Dashboard</h1>
          <p className="text-secondary mt-1">
            {MONTHS[month - 1]} {year}
          </p>
        </div>
        <div style={{ display: 'flex', gap: '.5rem', flexWrap: 'wrap' }}>
          {availableMonths.map(m => (
            <button key={`${m.year}-${m.month}`}
              className={`btn btn-ghost text-xs ${m.month === month && m.year === year ? 'btn-primary' : ''}`}
              onClick={() => onMonthChange(m)}>
              {MONTHS[m.month - 1]} {m.year}
            </button>
          ))}
        </div>
      </div>

      {/* Stat cards */}
      <div className="grid-4">
        <div className="stat-card income">
          <div className="stat-label">Income</div>
          <div className="stat-value text-success">{fmtNum(summary.total_income)}</div>
          <div className="stat-sub">Credits this month</div>
        </div>
        <div className="stat-card expense">
          <div className="stat-label">Expenses</div>
          <div className="stat-value text-danger">{fmtNum(summary.total_expenses)}</div>
          <div className="stat-sub">Debits this month</div>
        </div>
        <div className="stat-card savings">
          <div className="stat-label">Net Savings</div>
          <div className={`stat-value ${summary.net_savings >= 0 ? 'text-success' : 'text-danger'}`}>
            {fmtNum(summary.net_savings)}
          </div>
          <div className="stat-sub">{summary.savings_rate}% savings rate</div>
        </div>
        <div className="stat-card health">
          <div className="stat-label">Health Score</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginTop: '.25rem' }}>
            <HealthRing score={summary.health_score} />
          </div>
        </div>
      </div>

      {/* Charts row */}
      <div className="grid-2">
        {/* Pie chart */}
        <div className="card">
          <h3 style={{ marginBottom: '1rem' }}>Spending by Category</h3>
          {catData.length === 0 ? <p className="text-muted text-sm">No expense data</p> : (
            <ResponsiveContainer width="100%" height={220}>
              <PieChart>
                <Pie data={catData} cx="50%" cy="50%" innerRadius={55} outerRadius={90} paddingAngle={3} dataKey="value">
                  {catData.map((e, i) => <Cell key={i} fill={CAT_COLORS[e.name] || '#6c63ff'} />)}
                </Pie>
                <Tooltip content={<CustomTooltip />} />
              </PieChart>
            </ResponsiveContainer>
          )}
          {/* Legend */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.4rem .75rem', marginTop: '.75rem' }}>
            {catData.slice(0, 8).map((e) => (
              <div key={e.name} className="flex items-center gap-2" style={{ fontSize: '.72rem' }}>
                <div className="cat-dot" style={{ background: CAT_COLORS[e.name] || '#6c63ff' }} />
                <span className="text-secondary">{e.name}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Bar chart / trend */}
        <div className="card">
          <h3 style={{ marginBottom: '1rem' }}>Monthly Trend</h3>
          {trendData.length < 2 ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 220, flexDirection: 'column', gap: '1rem' }}>
              <RefreshCw size={32} color="var(--text-muted)" />
              <p className="text-muted text-sm">Upload more months to see trends</p>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={trendData} barSize={12}>
                <CartesianGrid strokeDasharray="3 3" stroke="#ece7dc" />
                <XAxis dataKey="name" tick={{ fill: '#9e9488', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#9e9488', fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={v => `₹${(v/1000).toFixed(0)}k`} />
                <Tooltip content={<CustomTooltip />} />
                <Bar dataKey="Income"   fill="#3d7a4f" radius={[4,4,0,0]} />
                <Bar dataKey="Expenses" fill="#c0392b" radius={[4,4,0,0]} />
                <Bar dataKey="Savings"  fill="#c0522a" radius={[4,4,0,0]} />
                <Legend wrapperStyle={{ fontSize: '.75rem', color: '#6b6457' }} />
              </BarChart>
            </ResponsiveContainer>

          )}
        </div>
      </div>

      {/* AI Insights */}
      <div className="card">
        <div className="flex items-center gap-2" style={{ marginBottom: '1rem' }}>
          <Brain size={20} color="var(--accent)" />
          <h3>AI Insights</h3>
        </div>
        <div className="insights-box" style={{ whiteSpace: 'pre-wrap' }}>
          {summary.llm_insights || <span className="text-muted">No insights generated yet.</span>}
        </div>
      </div>

      {/* Subscription summary */}
      <div className="card">
        <h3 style={{ marginBottom: '.75rem' }}>Subscriptions</h3>
        {summary.subscription_total > 0 ? (
          <div>
            <p className="text-sm text-secondary">Total this month: <span className="font-bold text-accent">{fmtNum(summary.subscription_total)}</span></p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.5rem', marginTop: '.75rem' }}>
              {Object.entries(JSON.parse(summary.subscription_list || '{}')).map(([m, a]) => (
                <span key={m} className="badge badge-sub">{m} · {fmtNum(a)}</span>
              ))}
            </div>
          </div>
        ) : <p className="text-sm text-muted">No subscriptions detected this month.</p>}
      </div>
    </div>
  );
}
