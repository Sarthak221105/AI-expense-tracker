import { useState, useRef } from 'react';
import { Upload, FileText, Lock, Calendar, ChevronDown, Loader, CheckCircle, AlertCircle } from 'lucide-react';
import { api } from '../api.js';
import { useToast } from '../useToast.jsx';
import { MONTH_NAMES } from '../utils.js';

const YEARS  = [2024, 2025, 2026];

export default function UploadPage({ userId, onSuccess }) {
  const [file,     setFile]     = useState(null);
  const [month,    setMonth]    = useState(new Date().getMonth() + 1);
  const [year,     setYear]     = useState(new Date().getFullYear());
  const [password, setPassword] = useState('');
  const [drag,     setDrag]     = useState(false);
  const [job,      setJob]      = useState(null); // { id, status, progress, error }
  const fileRef = useRef();
  const pollRef = useRef();
  const { show, Toast } = useToast();

  const pickFile = (f) => {
    if (!f) return;
    const ext = f.name.split('.').pop().toLowerCase();
    if (!['pdf', 'csv', 'xlsx', 'xls'].includes(ext)) { show('Unsupported file type', 'error'); return; }
    setFile(f);
  };

  const onDrop = (e) => { e.preventDefault(); setDrag(false); pickFile(e.dataTransfer.files[0]); };

  const pollJob = (jobId) => {
    pollRef.current = setInterval(async () => {
      try {
        const s = await api.getJobStatus(jobId);
        setJob(j => ({ ...j, status: s.status, progress: s.progress, error: s.error }));
        if (s.status === 'complete') {
          clearInterval(pollRef.current);
          show('Statement processed successfully!', 'success');
          setTimeout(() => onSuccess({ month, year }), 800);
        } else if (s.status === 'failed') {
          clearInterval(pollRef.current);
          show(`Processing failed: ${s.error}`, 'error');
        }
      } catch { clearInterval(pollRef.current); }
    }, 1200);
  };

  const submit = async () => {
    if (!file) { show('Please select a file', 'error'); return; }
    const fd = new FormData();
    fd.append('file', file);
    fd.append('month', month);
    fd.append('year', year);
    fd.append('user_id', userId);
    fd.append('replace', 'true');
    if (password) fd.append('pdf_password', password);

    setJob({ id: null, status: 'uploading', progress: 5, error: null });
    try {
      const res = await api.uploadStatement(fd);
      setJob({ id: res.job_id, status: 'queued', progress: 10, error: null });
      pollJob(res.job_id);
    } catch (e) {
      setJob(null);
      show(e.message, 'error');
    }
  };

  const statusLabel = {
    uploading: 'Uploading…',
    queued:    'In queue…',
    parsing:   'Parsing PDF with AI…',
    categorising: 'Categorising transactions…',
    detecting_subscriptions: 'Detecting subscriptions…',
    saving:    'Saving to database…',
    calculating: 'Calculating summary…',
    generating_insights: 'Generating AI insights…',
    complete:  'Done!',
    failed:    'Failed',
  };

  return (
    <div className="flex-col gap-6" style={{ maxWidth: 640, margin: '0 auto', padding: '2rem 1rem' }}>
      <Toast />

      {/* Header */}
      <div>
        <h1>Upload Statement</h1>
        <p className="text-secondary mt-2">Upload your bank statement PDF or CSV to analyse your finances.</p>
      </div>

      {/* Supported banks */}
      <div className="card" style={{ padding: '1rem 1.5rem' }}>
        <p className="text-xs text-muted" style={{ marginBottom: '.4rem', fontWeight: 700, letterSpacing: '.08em', textTransform: 'uppercase' }}>Supported Banks</p>
        <p className="text-sm text-secondary">HDFC · SBI · ICICI · Axis · Kotak · Yes Bank · PNB · Bank of Baroda · IndusInd · Federal Bank</p>
      </div>

      {/* Drop Zone */}
      <div
        className={`upload-zone ${drag ? 'dragover' : ''}`}
        onClick={() => !job && fileRef.current.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
      >
        <input ref={fileRef} type="file" accept=".pdf,.csv,.xlsx,.xls" style={{ display: 'none' }} onChange={e => pickFile(e.target.files[0])} />

        {file ? (
          <div className="flex-col items-center gap-3">
            <div style={{ width: 52, height: 52, borderRadius: 14, background: 'rgba(108,99,255,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <FileText size={26} color="var(--accent)" />
            </div>
            <div>
              <p className="font-bold">{file.name}</p>
              <p className="text-sm text-muted">{(file.size / 1024).toFixed(1)} KB</p>
            </div>
            <button className="btn btn-ghost text-xs" onClick={e => { e.stopPropagation(); setFile(null); }}>Change file</button>
          </div>
        ) : (
          <div className="flex-col items-center gap-3">
            <div style={{ width: 56, height: 56, borderRadius: 16, background: 'rgba(108,99,255,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Upload size={26} color="var(--accent)" />
            </div>
            <div>
              <p className="font-bold">Drop your statement here</p>
              <p className="text-sm text-secondary mt-1">or click to browse · PDF, CSV, XLSX · max 10 MB</p>
            </div>
          </div>
        )}
      </div>

      {/* Month / Year */}
      <div className="grid-2">
        <div>
          <label className="text-xs text-muted" style={{ display: 'block', marginBottom: '.4rem', fontWeight: 600, letterSpacing: '.06em', textTransform: 'uppercase' }}>
            <Calendar size={12} style={{ display: 'inline', marginRight: 4 }} /> Month
          </label>
          <select value={month} onChange={e => setMonth(+e.target.value)} disabled={!!job}>
            {MONTH_NAMES.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
          </select>
        </div>
        <div>
          <label className="text-xs text-muted" style={{ display: 'block', marginBottom: '.4rem', fontWeight: 600, letterSpacing: '.06em', textTransform: 'uppercase' }}>Year</label>
          <select value={year} onChange={e => setYear(+e.target.value)} disabled={!!job}>
            {YEARS.map(y => <option key={y}>{y}</option>)}
          </select>
        </div>
      </div>

      {/* Password field for PDF */}
      {file?.name?.endsWith('.pdf') && (
        <div>
          <label className="text-xs text-muted" style={{ display: 'block', marginBottom: '.4rem', fontWeight: 600, letterSpacing: '.06em', textTransform: 'uppercase' }}>
            <Lock size={12} style={{ display: 'inline', marginRight: 4 }} /> PDF Password (if protected)
          </label>
          <input type="password" placeholder="Leave blank if not password-protected" value={password} onChange={e => setPassword(e.target.value)} disabled={!!job} />
        </div>
      )}

      {/* Progress */}
      {job && (
        <div className="card flex-col gap-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              {job.status === 'complete'
                ? <CheckCircle size={20} color="var(--success)" />
                : job.status === 'failed'
                ? <AlertCircle size={20} color="var(--danger)" />
                : <div className="spinner" style={{ width: 20, height: 20, borderWidth: 2 }} />
              }
              <span className="text-sm font-bold">{statusLabel[job.status] || job.status}</span>
            </div>
            <span className="text-sm text-muted font-mono">{job.progress}%</span>
          </div>
          <div className="progress-track">
            <div className="progress-fill" style={{ width: `${job.progress}%` }} />
          </div>
          {job.error && <p className="text-sm text-danger">{job.error}</p>}
        </div>
      )}

      {/* Submit */}
      {!job && (
        <button className="btn btn-primary w-full" style={{ justifyContent: 'center', padding: '.875rem' }} onClick={submit}>
          <Upload size={18} /> Process Statement
        </button>
      )}
    </div>
  );
}
