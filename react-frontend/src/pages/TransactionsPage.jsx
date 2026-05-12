import { useState, useEffect, useCallback } from 'react';
import { Search, Filter, ChevronLeft, ChevronRight, Edit2, Check, X } from 'lucide-react';
import { api } from '../api.js';
import { useToast } from '../useToast.jsx';
import { fmtNum, CAT_COLORS } from '../utils.js';

const CATS = ['All','Food & Dining','Groceries','Transport','Shopping','Entertainment','Health & Fitness',
  'Utilities','Finance & Insurance','Education','Salary','Business Income','ATM Withdrawal',
  'Bank Transfer','EMI & Loans','Subscriptions','Rent','Travel & Holidays','Other'];

function EditCell({ txn, onSave, onCancel }) {
  const [cat, setCat] = useState(txn.category);
  const [mer, setMer] = useState(txn.merchant);
  return (
    <td colSpan={7}>
      <div className="flex items-center gap-3" style={{ padding: '.5rem 0' }}>
        <input value={mer} onChange={e => setMer(e.target.value)} style={{ width: 180 }} placeholder="Merchant" />
        <select value={cat} onChange={e => setCat(e.target.value)} style={{ width: 200 }}>
          {CATS.filter(c => c !== 'All').map(c => <option key={c}>{c}</option>)}
        </select>
        <button className="btn btn-primary" style={{ padding: '.4rem .8rem' }} onClick={() => onSave(txn.id, { category: cat, merchant: mer })}>
          <Check size={14} /> Save
        </button>
        <button className="btn btn-ghost" style={{ padding: '.4rem .8rem' }} onClick={onCancel}>
          <X size={14} />
        </button>
      </div>
    </td>
  );
}

export default function TransactionsPage({ userId, selectedMonth }) {
  const [txns,    setTxns]    = useState([]);
  const [total,   setTotal]   = useState(0);
  const [pages,   setPages]   = useState(1);
  const [page,    setPage]    = useState(1);
  const [loading, setLoading] = useState(false);
  const [search,  setSearch]  = useState('');
  const [catFilter, setCat]   = useState('All');
  const [typeFilter, setType] = useState('all');
  const [editId,  setEditId]  = useState(null);
  const { show, Toast } = useToast();

  const { month, year } = selectedMonth || {};

  const load = useCallback(async () => {
    if (!userId || !month || !year) return;
    setLoading(true);
    try {
      const data = await api.getTransactions(userId, year, month, page);
      setTxns(data.transactions || []);
      setTotal(data.total || 0);
      setPages(data.total_pages || 1);
    } catch { show('Failed to load transactions', 'error'); }
    finally { setLoading(false); }
  }, [userId, month, year, page, catFilter, typeFilter]);


  useEffect(() => { load(); }, [load]);

  const saveEdit = async (id, updates) => {
    try {
      await api.updateTransaction(id, updates);
      setEditId(null);
      show('Transaction updated', 'success');
      load();
    } catch (e) { show(e.message, 'error'); }
  };

  const filtered = txns.filter(t =>
    search === '' ||
    t.description?.toLowerCase().includes(search.toLowerCase()) ||
    t.merchant?.toLowerCase().includes(search.toLowerCase())
  );

  if (!selectedMonth) return <div style={{ padding: '2rem' }}><p className="text-secondary">Select a month to view transactions.</p></div>;

  return (
    <div className="flex-col gap-4" style={{ padding: '1.5rem', maxWidth: 1100, margin: '0 auto' }}>
      <Toast />

      <div className="flex items-center justify-between">
        <h1>Transactions</h1>
        <span className="badge badge-cat">{total} total</span>
      </div>

      {/* Filters */}
      <div className="card" style={{ padding: '1rem' }}>
        <div className="flex items-center gap-3" style={{ flexWrap: 'wrap' }}>
          {/* Search */}
          <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
            <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
            <input style={{ paddingLeft: 32 }} placeholder="Search merchant or description…" value={search} onChange={e => setSearch(e.target.value)} />
          </div>
          {/* Category */}
          <select value={catFilter} onChange={e => { setCat(e.target.value); setPage(1); }} style={{ width: 190 }}>
            {CATS.map(c => <option key={c}>{c}</option>)}
          </select>
          {/* Type */}
          <div className="tabs" style={{ flex: 'none' }}>
            {['all','credit','debit'].map(t => (
              <button key={t} className={`tab-btn ${typeFilter === t ? 'active' : ''}`} onClick={() => { setType(t); setPage(1); }}>
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Table */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {loading ? (
          <div style={{ padding: '3rem', display: 'flex', justifyContent: 'center' }}><div className="spinner" /></div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: '3rem', textAlign: 'center' }}><p className="text-muted">No transactions found.</p></div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Merchant</th>
                  <th>Description</th>
                  <th>Category</th>
                  <th>Type</th>
                  <th style={{ textAlign: 'right' }}>Amount</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(t => (
                  editId === t.id ? (
                    <tr key={t.id} style={{ background: 'rgba(108,99,255,0.05)' }}>
                      <EditCell txn={t} onSave={saveEdit} onCancel={() => setEditId(null)} />
                    </tr>
                  ) : (
                    <tr key={t.id}>
                      <td className="text-sm font-mono text-muted">{t.date || '—'}</td>
                      <td>
                        <div className="flex items-center gap-2">
                          <div className="cat-dot" style={{ background: CAT_COLORS[t.category] || '#6c63ff', flexShrink: 0 }} />
                          <span className="font-bold text-sm">{t.merchant || '—'}</span>
                          {t.is_subscription && <span className="badge badge-sub" style={{ fontSize: '.62rem' }}>Sub</span>}
                          {t.needs_review && <span className="badge badge-review" style={{ fontSize: '.62rem' }}>Review</span>}
                        </div>
                      </td>
                      <td className="text-sm text-muted" style={{ maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {t.description}
                      </td>
                      <td><span className="badge badge-cat text-xs">{t.category}</span></td>
                      <td><span className={`badge ${t.type === 'credit' ? 'badge-credit' : 'badge-debit'}`}>{t.type}</span></td>
                      <td style={{ textAlign: 'right', fontWeight: 700, color: t.type === 'credit' ? 'var(--success)' : 'var(--danger)' }}>
                        {t.type === 'credit' ? '+' : '-'}{fmtNum(t.amount)}
                      </td>
                      <td>
                        <button className="btn btn-ghost" style={{ padding: '.3rem .5rem' }} onClick={() => setEditId(t.id)}>
                          <Edit2 size={13} />
                        </button>
                      </td>
                    </tr>
                  )
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {pages > 1 && (
          <div className="flex items-center justify-between" style={{ padding: '.75rem 1.25rem', borderTop: '1px solid var(--border)' }}>
            <span className="text-sm text-muted">Page {page} of {pages}</span>
            <div className="flex gap-2">
              <button className="btn btn-ghost" style={{ padding: '.4rem .7rem' }} disabled={page === 1} onClick={() => setPage(p => p - 1)}>
                <ChevronLeft size={15} />
              </button>
              <button className="btn btn-ghost" style={{ padding: '.4rem .7rem' }} disabled={page === pages} onClick={() => setPage(p => p + 1)}>
                <ChevronRight size={15} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
