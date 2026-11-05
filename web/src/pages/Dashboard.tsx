import React, { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  apiFetch,
  type DashboardData,
  type ElrListResponse,
  type Run,
  type User,
} from '../api';
import { StatusCards } from '../components/StatusCards';
import { MonthlyChart } from '../components/MonthlyChart';
import { CauseChart } from '../components/CauseChart';
import { ElrTable } from '../components/ElrTable';

export const Dashboard: React.FC = () => {
  const [user, setUser] = useState<User | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedRun, setSelectedRun] = useState<number | null>(null);

  const [dashboard, setDashboard] = useState<DashboardData | null>(null);

  // Filters
  const [selectedMonth, setSelectedMonth] = useState<string | null>(null);
  const [selectedResult, setSelectedResult] = useState<string | null>(null);
  const [selectedCause, setSelectedCause] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');

  // Table
  const [elrData, setElrData] = useState<ElrListResponse>({ total: 0, page: 1, rows: [] });
  const [loadingTable, setLoadingTable] = useState(false);
  const [page, setPage] = useState(1);

  const navigate = useNavigate();

  // 1. Debounce search 300ms
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchTerm);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  // 2. Fetch User & Runs
  useEffect(() => {
    apiFetch<User>('/api/auth/me')
      .then(setUser)
      .catch(() => navigate('/login'));

    apiFetch<Run[]>('/api/runs')
      .then((data) => {
        setRuns(data);
        if (data.length > 0) {
          // Select newest run by default
          setSelectedRun(data[0].run_id);
        }
      })
      .catch((err) => console.error('Failed to load runs:', err));
  }, [navigate]);

  // 3. Fetch Dashboard data when selectedRun changes
  useEffect(() => {
    if (!selectedRun) return;
    apiFetch<DashboardData>(`/api/dashboard?run=${selectedRun}`)
      .then(setDashboard)
      .catch((err) => console.error('Failed to load dashboard:', err));
  }, [selectedRun]);

  // 4. Fetch ELR Table rows when run, filters, or page changes
  useEffect(() => {
    if (!selectedRun) return;
    setLoadingTable(true);

    const params = new URLSearchParams();
    params.set('run', String(selectedRun));
    params.set('page', String(page));
    if (selectedMonth) params.set('month', selectedMonth);
    if (selectedResult) params.set('result', selectedResult);
    if (selectedCause) params.set('cause', selectedCause);
    if (debouncedSearch) params.set('q', debouncedSearch);

    apiFetch<ElrListResponse>(`/api/elrs?${params.toString()}`)
      .then(setElrData)
      .catch((err) => console.error('Failed to load ELRs:', err))
      .finally(() => setLoadingTable(false));
  }, [selectedRun, page, selectedMonth, selectedResult, selectedCause, debouncedSearch]);

  const handleLogout = async () => {
    try {
      await apiFetch('/api/auth/logout', { method: 'POST' });
    } finally {
      navigate('/login');
    }
  };

  const clearAllFilters = () => {
    setSelectedMonth(null);
    setSelectedResult(null);
    setSelectedCause(null);
    setSearchTerm('');
    setPage(1);
  };

  const hasActiveFilters = Boolean(
    selectedMonth || selectedResult || selectedCause || debouncedSearch
  );

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col text-slate-800">
      {/* Top Navbar */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="font-mono bg-indigo-600 text-white font-black text-sm px-2.5 py-1 rounded-md">
              MARK
            </span>
            <div>
              <h1 className="text-base font-bold leading-tight">Mark Automation Dashboard</h1>
              <span className="text-[11px] text-slate-400">Phase 2 Trial • Jul–Nov 2026 Batch</span>
            </div>
          </div>

          <div className="flex items-center gap-4">
            {/* Run Selector */}
            <div className="flex items-center gap-2">
              <label className="text-xs font-semibold text-slate-500 uppercase">Run:</label>
              <select
                value={selectedRun || ''}
                onChange={(e) => {
                  setSelectedRun(Number(e.target.value));
                  clearAllFilters();
                }}
                className="text-xs font-mono font-bold bg-slate-100 border border-slate-300 rounded px-2.5 py-1 text-slate-800 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                {runs.map((r) => (
                  <option key={r.run_id} value={r.run_id}>
                    Run {r.run_id} ({r.period})
                  </option>
                ))}
              </select>
            </div>

            {/* User Info & Logout */}
            <div className="flex items-center gap-3 border-l pl-4 border-slate-200">
              <div className="text-right">
                <div className="text-xs font-bold text-slate-800">{user?.display_name || user?.username}</div>
                <div className="text-[10px] text-slate-400 uppercase tracking-wider">{user?.role}</div>
              </div>
              {user?.role === 'admin' && (
                <Link
                  to="/admin"
                  className="text-xs px-2.5 py-1 text-indigo-700 hover:text-indigo-900 font-semibold rounded border border-indigo-200 hover:border-indigo-300 bg-indigo-50"
                >
                  Admin
                </Link>
              )}
              <button
                onClick={handleLogout}
                className="text-xs px-2.5 py-1 text-slate-600 hover:text-rose-600 font-medium rounded border border-slate-200 hover:border-rose-200 bg-white"
              >
                Logout
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6 flex-1 w-full">
        {/* Status Cards */}
        {dashboard && (
          <StatusCards
            cards={dashboard.cards}
            selectedResult={selectedResult}
            onSelectResult={(res) => {
              setSelectedResult(res);
              setPage(1);
            }}
          />
        )}

        {/* Charts Row */}
        {dashboard && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <MonthlyChart
              data={dashboard.monthly}
              selectedMonth={selectedMonth}
              onSelectMonth={(m) => {
                setSelectedMonth(m);
                setPage(1);
              }}
            />
            <CauseChart
              errorCauses={dashboard.error_causes}
              holdCauses={dashboard.hold_causes}
              selectedCause={selectedCause}
              onSelectCause={(c) => {
                setSelectedCause(c);
                setPage(1);
              }}
            />
          </div>
        )}

        {/* Filters Bar & Search */}
        <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3 flex-1 min-w-[18rem]">
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search ELR, ABS number, or SLR..."
              className="w-full max-w-md px-3 py-1.5 border border-slate-300 rounded-lg text-xs bg-slate-50 focus:bg-white text-slate-800 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            {hasActiveFilters && (
              <button
                onClick={clearAllFilters}
                className="text-xs text-rose-600 hover:underline font-medium whitespace-nowrap"
              >
                ✕ Clear filters
              </button>
            )}
          </div>

          {/* Active Filter Badges */}
          <div className="flex items-center gap-2 flex-wrap text-xs">
            {selectedResult && (
              <span className="bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-full border border-indigo-200">
                Result: <strong>{selectedResult}</strong>
              </span>
            )}
            {selectedMonth && (
              <span className="bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-full border border-indigo-200">
                Month: <strong>{selectedMonth}</strong>
              </span>
            )}
            {selectedCause && (
              <span className="bg-indigo-50 text-indigo-700 px-2 py-0.5 rounded-full border border-indigo-200">
                Cause: <strong>{selectedCause}</strong>
              </span>
            )}
          </div>
        </div>

        {/* ELR Table */}
        <ElrTable
          rows={elrData.rows}
          total={elrData.total}
          page={page}
          runId={selectedRun || 18}
          onPageChange={setPage}
          loading={loadingTable}
        />
      </main>
    </div>
  );
};
