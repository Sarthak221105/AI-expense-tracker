import { useState, useEffect } from 'react';
import { LayoutDashboard, Upload, List, RefreshCw, Zap, ChevronRight } from 'lucide-react';
import { api } from './api.js';
import { USER_KEY, MONTHS } from './utils.js';
import DashboardPage     from './pages/DashboardPage.jsx';
import UploadPage        from './pages/UploadPage.jsx';
import TransactionsPage  from './pages/TransactionsPage.jsx';
import SubscriptionsPage from './pages/SubscriptionsPage.jsx';

const NAV = [
  { id: 'dashboard',     label: 'Dashboard',     icon: LayoutDashboard },
  { id: 'upload',        label: 'Upload',         icon: Upload },
  { id: 'transactions',  label: 'Transactions',   icon: List },
  { id: 'subscriptions', label: 'Subscriptions',  icon: RefreshCw },
];

function Logo() {
  return (
    <div style={{ padding: '.5rem .5rem 1.75rem', display: 'flex', alignItems: 'center', gap: '.65rem' }}>
      <div style={{
        width: 32, height: 32, borderRadius: 8,
        background: 'linear-gradient(135deg, #c0522a, #e8754a)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0,
      }}>
        <Zap size={16} color="#fff" fill="#fff" />
      </div>
      <div>
        <div style={{
          fontFamily: "'Playfair Display', Georgia, serif",
          fontWeight: 800, fontSize: '1rem',
          letterSpacing: '-.01em', lineHeight: 1.1,
          color: '#f5f0e8',
        }}>Finance</div>
        <div style={{
          fontWeight: 700, fontSize: '.6rem',
          color: '#c0522a', letterSpacing: '.12em',
          textTransform: 'uppercase',
        }}>AUTOPILOT</div>
      </div>
    </div>
  );
}

export default function App() {
  const [page,    setPage]    = useState('dashboard');
  const [userId,  setUserId]  = useState(null);
  const [months,  setMonths]  = useState([]);
  const [selMonth, setSelMonth] = useState(null);

  // Init user
  useEffect(() => {
    const stored = localStorage.getItem(USER_KEY);
    if (stored) { setUserId(stored); return; }
    api.createUser().then(u => {
      localStorage.setItem(USER_KEY, u.user_id);
      setUserId(u.user_id);
    });
  }, []);

  // Load available months whenever userId changes or we navigate to dashboard
  useEffect(() => {
    if (!userId) return;
    api.getMonths(userId).then(d => {
      const ms = d.months || [];
      setMonths(ms);
      if (ms.length > 0 && !selMonth) setSelMonth(ms[0]);
    }).catch(() => {});
  }, [userId, page]);

  const handleUploadSuccess = (m) => {
    setPage('dashboard');
    setSelMonth(m);
  };

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      {/* Sidebar */}
      <nav className="sidebar">
        <Logo />
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '.2rem' }}>
          {NAV.map(n => (
            <button key={n.id} className={`sidebar-item ${page === n.id ? 'active' : ''}`} onClick={() => setPage(n.id)}>
              <n.icon size={17} />
              {n.label}
              {page === n.id && <ChevronRight size={13} style={{ marginLeft: 'auto', opacity: .6 }} />}
            </button>
          ))}
        </div>

        {/* Month picker (in sidebar) */}
        {months.length > 0 && (
          <div style={{ marginTop: 'auto', paddingTop: '1rem', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
            <p style={{ fontSize: '.65rem', fontWeight: 700, letterSpacing: '.1em', textTransform: 'uppercase', color: 'rgba(245,240,232,0.35)', marginBottom: '.5rem' }}>Active Month</p>
            <select
              value={selMonth ? `${selMonth.year}-${selMonth.month}` : ''}
              onChange={e => {
                const [y, m] = e.target.value.split('-').map(Number);
                setSelMonth({ year: y, month: m });
              }}
              style={{ fontSize: '.8rem', background: 'rgba(255,255,255,0.07)', border: '1px solid rgba(255,255,255,0.1)', color: '#f5f0e8' }}
            >
              {months.map(m => (
                <option key={`${m.year}-${m.month}`} value={`${m.year}-${m.month}`}
                  style={{ background: '#1c1c1a', color: '#f5f0e8' }}>
                  {MONTHS[m.month - 1]} {m.year}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* User ID display */}
        {userId && (
          <div style={{ marginTop: '.75rem' }}>
            <p style={{ fontSize: '.65rem', color: 'rgba(245,240,232,0.3)', letterSpacing: '.04em' }}>User ID</p>
            <p style={{ fontSize: '.65rem', fontFamily: "'JetBrains Mono', monospace", color: 'rgba(245,240,232,0.25)', marginTop: '.2rem', wordBreak: 'break-all' }}>
              {userId.slice(0, 12)}…
            </p>
          </div>
        )}

      </nav>

      {/* Main content */}
      <main style={{ flex: 1, overflowY: 'auto', maxHeight: '100vh' }}>
        {page === 'dashboard'     && <DashboardPage     userId={userId} selectedMonth={selMonth} onMonthChange={setSelMonth} availableMonths={months} />}
        {page === 'upload'        && <UploadPage        userId={userId} onSuccess={handleUploadSuccess} />}
        {page === 'transactions'  && <TransactionsPage  userId={userId} selectedMonth={selMonth} />}
        {page === 'subscriptions' && <SubscriptionsPage userId={userId} />}
      </main>
    </div>
  );
}
