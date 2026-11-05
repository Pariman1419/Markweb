import React, { useEffect, useState, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  apiFetch,
  type ActivityData,
  type AdminUser,
  type AuditEvent,
  type User,
} from '../api';

function formatDateInput(d: Date): string {
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

export const Admin: React.FC = () => {
  const navigate = useNavigate();
  const [me, setMe] = useState<User | null>(null);

  // Users state
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loadingUsers, setLoadingUsers] = useState<boolean>(true);
  const [unlockingId, setUnlockingId] = useState<number | null>(null);

  // Overview state
  const today = new Date();
  const fourteenDaysAgo = new Date(today.getTime() - 13 * 24 * 60 * 60 * 1000);
  const [dateFrom, setDateFrom] = useState<string>(formatDateInput(fourteenDaysAgo));
  const [dateTo, setDateTo] = useState<string>(formatDateInput(today));
  const [activity, setActivity] = useState<ActivityData | null>(null);
  const [loadingActivity, setLoadingActivity] = useState<boolean>(true);

  // Events state
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loadingEvents, setLoadingEvents] = useState<boolean>(true);
  const [eventUserFilter, setEventUserFilter] = useState<string>('');
  const [eventActionFilter, setEventActionFilter] = useState<string>('');
  const [eventPage, setEventPage] = useState<number>(1);

  // 1. Check current user & ensure admin
  useEffect(() => {
    apiFetch<User>('/api/auth/me')
      .then((u) => {
        if (u.role !== 'admin') {
          navigate('/', { replace: true });
        } else {
          setMe(u);
        }
      })
      .catch(() => navigate('/login', { replace: true }));
  }, [navigate]);

  // 2. Load users
  const loadUsers = useCallback(() => {
    setLoadingUsers(true);
    apiFetch<AdminUser[]>('/api/admin/users')
      .then(setUsers)
      .catch((err) => console.error('Failed to load admin users:', err))
      .finally(() => setLoadingUsers(false));
  }, []);

  useEffect(() => {
    if (me?.role === 'admin') {
      loadUsers();
    }
  }, [me, loadUsers]);

  // 3. Load activity overview
  const loadActivity = useCallback(() => {
    if (!dateFrom || !dateTo) return;
    setLoadingActivity(true);
    apiFetch<ActivityData>(`/api/admin/activity?from=${dateFrom}&to=${dateTo}`)
      .then(setActivity)
      .catch((err) => console.error('Failed to load activity:', err))
      .finally(() => setLoadingActivity(false));
  }, [dateFrom, dateTo]);

  useEffect(() => {
    if (me?.role === 'admin') {
      loadActivity();
    }
  }, [me, loadActivity]);

  // 4. Load events
  const loadEvents = useCallback(() => {
    setLoadingEvents(true);
    const params = new URLSearchParams();
    if (dateFrom) params.set('from', dateFrom);
    if (dateTo) params.set('to', dateTo);
    if (eventUserFilter) params.set('user_id', eventUserFilter);
    if (eventActionFilter) params.set('action', eventActionFilter);
    params.set('page', String(eventPage));

    apiFetch<AuditEvent[]>(`/api/admin/events?${params.toString()}`)
      .then(setEvents)
      .catch((err) => console.error('Failed to load audit events:', err))
      .finally(() => setLoadingEvents(false));
  }, [dateFrom, dateTo, eventUserFilter, eventActionFilter, eventPage]);

  useEffect(() => {
    if (me?.role === 'admin') {
      loadEvents();
    }
  }, [me, loadEvents]);

  // Unlock user handler
  const handleUnlock = async (userId: number) => {
    try {
      setUnlockingId(userId);
      await apiFetch(`/api/admin/users/${userId}/unlock`, { method: 'POST' });
      loadUsers();
      loadEvents();
    } catch (err: any) {
      alert(`ปลดล็อกไม่สำเร็จ: ${err.message}`);
    } finally {
      setUnlockingId(null);
    }
  };

  const handleLogout = async () => {
    try {
      await apiFetch('/api/auth/logout', { method: 'POST' });
    } finally {
      navigate('/login');
    }
  };

  if (!me) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center text-slate-500 text-sm">
        กำลังโหลดข้อมูล Admin...
      </div>
    );
  }

  // Summary per-user totals from activity.per_user_day
  const userTotalsMap = new Map<number, { display_name: string; reviews: number; approvals: number }>();
  if (activity?.per_user_day) {
    for (const item of activity.per_user_day) {
      const existing = userTotalsMap.get(item.user_id) || {
        display_name: item.display_name,
        reviews: 0,
        approvals: 0,
      };
      existing.reviews += item.reviews;
      existing.approvals += item.approvals;
      userTotalsMap.set(item.user_id, existing);
    }
  }

  return (
    <div className="min-h-screen bg-slate-100 flex flex-col font-sans text-slate-800">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-sm">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-bold text-sm shadow">
              ADM
            </div>
            <div>
              <h1 className="text-base font-bold text-slate-900 leading-tight">Admin Console</h1>
              <span className="text-[11px] text-slate-400">ระบบจัดการผู้ใช้และติดตามกิจกรรมการตรวจสอบ</span>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <Link
              to="/"
              className="text-xs px-3 py-1.5 font-semibold text-slate-600 hover:text-indigo-600 rounded border border-slate-200 hover:border-indigo-300 bg-white transition-colors"
            >
              ← กลับหน้า Dashboard
            </Link>

            <div className="flex items-center gap-3 border-l pl-4 border-slate-200">
              <div className="text-right">
                <div className="text-xs font-bold text-slate-800">{me.display_name || me.username}</div>
                <div className="text-[10px] text-indigo-600 font-semibold uppercase tracking-wider">{me.role}</div>
              </div>
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

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-8">
        {/* Section 1: ผู้ใช้ (Users & Unlock) */}
        <section className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
          <div className="flex justify-between items-center">
            <div>
              <h2 className="text-sm font-bold text-slate-900">ผู้ใช้ (Users)</h2>
              <p className="text-xs text-slate-500">รายชื่อผู้ใช้ทั้งหมด สถานะความพร้อม และการปลดล็อกบัญชี</p>
            </div>
            <button
              onClick={loadUsers}
              className="text-xs px-2.5 py-1 text-slate-600 hover:text-slate-900 border border-slate-200 rounded hover:bg-slate-50"
            >
              รีเฟรช
            </button>
          </div>

          <div className="overflow-x-auto border border-slate-200 rounded-lg">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 uppercase font-semibold">
                <tr>
                  <th className="py-2.5 px-3">ID</th>
                  <th className="py-2.5 px-3">ชื่อผู้ใช้</th>
                  <th className="py-2.5 px-3">ชื่อแสดง</th>
                  <th className="py-2.5 px-3">บทบาท</th>
                  <th className="py-2.5 px-3">สถานะ</th>
                  <th className="py-2.5 px-3">รหัสผิดสะสม</th>
                  <th className="py-2.5 px-3">ล็อกถึง</th>
                  <th className="py-2.5 px-3">เข้าสู่ระบบล่าสุด</th>
                  <th className="py-2.5 px-3 text-right">การดำเนินการ</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {loadingUsers ? (
                  <tr>
                    <td colSpan={9} className="py-6 text-center text-slate-400">
                      กำลังโหลดรายชื่อผู้ใช้...
                    </td>
                  </tr>
                ) : users.length === 0 ? (
                  <tr>
                    <td colSpan={9} className="py-6 text-center text-slate-400">
                      ไม่พบข้อมูลผู้ใช้
                    </td>
                  </tr>
                ) : (
                  users.map((u) => {
                    const isLocked = u.state === 'LOCKED';
                    const stateBadge =
                      u.state === 'OK'
                        ? 'bg-emerald-100 text-emerald-800 border-emerald-200'
                        : isLocked
                        ? 'bg-rose-100 text-rose-800 border-rose-200 animate-pulse'
                        : 'bg-slate-100 text-slate-600 border-slate-200';

                    return (
                      <tr key={u.user_id} className="hover:bg-slate-50/70">
                        <td className="py-2 px-3 font-mono text-slate-400">{u.user_id}</td>
                        <td className="py-2 px-3 font-bold text-slate-800">{u.username}</td>
                        <td className="py-2 px-3 text-slate-700">{u.display_name}</td>
                        <td className="py-2 px-3">
                          <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-100">
                            {u.role}
                          </span>
                        </td>
                        <td className="py-2 px-3">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${stateBadge}`}>
                            {u.state}
                          </span>
                        </td>
                        <td className="py-2 px-3 font-mono">{u.failed_count}</td>
                        <td className="py-2 px-3 text-slate-500 font-mono text-[11px]">
                          {u.locked_until ? new Date(u.locked_until).toLocaleString('th-TH') : '-'}
                        </td>
                        <td className="py-2 px-3 text-slate-500 font-mono text-[11px]">
                          {u.last_login_at ? new Date(u.last_login_at).toLocaleString('th-TH') : '-'}
                        </td>
                        <td className="py-2 px-3 text-right">
                          {isLocked ? (
                            <button
                              disabled={unlockingId === u.user_id}
                              onClick={() => handleUnlock(u.user_id)}
                              className="px-2.5 py-1 text-xs font-semibold bg-rose-600 hover:bg-rose-700 text-white rounded shadow-sm disabled:opacity-50"
                            >
                              {unlockingId === u.user_id ? 'กำลังปลด...' : 'ปลดล็อก (Unlock)'}
                            </button>
                          ) : (
                            <span className="text-slate-300 text-[11px]">ปกติ</span>
                          )}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </section>

        {/* Section 2: ภาพรวม (Overview) */}
        <section className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-6">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
            <div>
              <h2 className="text-sm font-bold text-slate-900">ภาพรวมการทดลอง (Activity Overview)</h2>
              <p className="text-xs text-slate-500">ความคืบหน้าของ run ปัจจุบัน และสถิติการใช้งานรายวัน</p>
            </div>

            {/* Date Range Controls */}
            <div className="flex items-center gap-2">
              <label className="text-xs font-semibold text-slate-600">ช่วงวันที่:</label>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="text-xs bg-slate-50 border border-slate-300 rounded px-2 py-1 text-slate-800"
              />
              <span className="text-slate-400 text-xs">ถึง</span>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="text-xs bg-slate-50 border border-slate-300 rounded px-2 py-1 text-slate-800"
              />
              <button
                onClick={loadActivity}
                className="text-xs px-3 py-1 bg-indigo-600 hover:bg-indigo-700 text-white font-medium rounded shadow-sm"
              >
                ค้นหา
              </button>
            </div>
          </div>

          {/* Progress Cards */}
          {loadingActivity ? (
            <div className="py-6 text-center text-xs text-slate-400">กำลังโหลดข้อมูลภาพรวม...</div>
          ) : activity?.run_progress ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div className="border border-slate-200 rounded-xl p-4 bg-slate-50/50">
                <div className="text-[11px] font-semibold text-slate-500 uppercase">ทั้งหมดใน Run</div>
                <div className="text-2xl font-black text-slate-900 mt-1">{activity.run_progress.total_elrs}</div>
                <div className="text-[10px] text-slate-400 mt-1">Run {activity.run_progress.run_id}</div>
              </div>
              <div className="border border-emerald-200 rounded-xl p-4 bg-emerald-50/40">
                <div className="text-[11px] font-semibold text-emerald-800 uppercase">อนุมัติแล้ว (Approved)</div>
                <div className="text-2xl font-black text-emerald-700 mt-1">{activity.run_progress.approved}</div>
                <div className="text-[10px] text-emerald-600 mt-1">
                  {activity.run_progress.total_elrs > 0
                    ? ((activity.run_progress.approved / activity.run_progress.total_elrs) * 100).toFixed(1)
                    : 0}
                  %
                </div>
              </div>
              <div className="border border-rose-200 rounded-xl p-4 bg-rose-50/40">
                <div className="text-[11px] font-semibold text-rose-800 uppercase">ปฏิเสธ (Rejected)</div>
                <div className="text-2xl font-black text-rose-700 mt-1">{activity.run_progress.rejected}</div>
                <div className="text-[10px] text-rose-600 mt-1">
                  {activity.run_progress.total_elrs > 0
                    ? ((activity.run_progress.rejected / activity.run_progress.total_elrs) * 100).toFixed(1)
                    : 0}
                  %
                </div>
              </div>
              <div className="border border-amber-200 rounded-xl p-4 bg-amber-50/40">
                <div className="text-[11px] font-semibold text-amber-800 uppercase">รอดำเนินการ (Undecided)</div>
                <div className="text-2xl font-black text-amber-700 mt-1">{activity.run_progress.undecided}</div>
                <div className="text-[10px] text-amber-600 mt-1">ยังไม่มีการตัดสินใจ</div>
              </div>
            </div>
          ) : null}

          {/* Activity Breakdown: Reviews/Approvals Per Day & Per User */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 pt-2">
            {/* Per-User Totals Table */}
            <div className="border border-slate-200 rounded-xl p-4 bg-white space-y-3">
              <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                จำนวนการรีวิวและอนุมัติสะสมตามผู้ใช้
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 uppercase font-semibold">
                    <tr>
                      <th className="py-2 px-3">ผู้ใช้</th>
                      <th className="py-2 px-3 text-right">รีวิว (Reviews)</th>
                      <th className="py-2 px-3 text-right">อนุมัติ (Approvals)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {userTotalsMap.size === 0 ? (
                      <tr>
                        <td colSpan={3} className="py-4 text-center text-slate-400">
                          ไม่มีกิจกรรมรีวิวหรืออนุมัติในช่วงเวลานี้
                        </td>
                      </tr>
                    ) : (
                      Array.from(userTotalsMap.entries()).map(([uid, stat]) => (
                        <tr key={uid}>
                          <td className="py-2 px-3 font-semibold text-slate-800">{stat.display_name}</td>
                          <td className="py-2 px-3 text-right font-mono text-indigo-600 font-bold">{stat.reviews}</td>
                          <td className="py-2 px-3 text-right font-mono text-emerald-600 font-bold">
                            {stat.approvals}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Daily Auth Problems Table */}
            <div className="border border-slate-200 rounded-xl p-4 bg-white space-y-3">
              <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
                ปัญหาการเข้าสู่ระบบรายวัน (Auth Issues per Day)
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 uppercase font-semibold">
                    <tr>
                      <th className="py-2 px-3">วันที่</th>
                      <th className="py-2 px-3 text-right">Login สำเร็จ</th>
                      <th className="py-2 px-3 text-right">Login พลาด</th>
                      <th className="py-2 px-3 text-right">ถูกล็อก</th>
                      <th className="py-2 px-3 text-right">Session หมดอายุ</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {!activity?.auth_per_day || activity.auth_per_day.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="py-4 text-center text-slate-400">
                          ไม่มีข้อมูลเหตุการณ์เข้าสู่ระบบในช่วงเวลานี้
                        </td>
                      </tr>
                    ) : (
                      activity.auth_per_day.map((d) => (
                        <tr key={d.day}>
                          <td className="py-2 px-3 font-mono text-slate-700">{d.day}</td>
                          <td className="py-2 px-3 text-right font-mono text-emerald-600">{d.login_ok}</td>
                          <td className="py-2 px-3 text-right font-mono text-rose-600 font-semibold">
                            {d.login_failed}
                          </td>
                          <td className="py-2 px-3 text-right font-mono text-amber-600 font-bold">{d.locked}</td>
                          <td className="py-2 px-3 text-right font-mono text-slate-500">{d.session_expired}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </section>

        {/* Section 3: เหตุการณ์ล่าสุด (Latest Audit Events & Troubleshooting) */}
        <section className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-4">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
            <div>
              <h2 className="text-sm font-bold text-slate-900">เหตุการณ์ล่าสุด (Audit Events)</h2>
              <p className="text-xs text-slate-500">บันทึกเหตุการณ์การตรวจสอบและยืนยันตัวตนสำหรับตรวจเช็กเคส "เข้าไม่ได้"</p>
            </div>

            {/* Filter Controls */}
            <div className="flex items-center gap-2 flex-wrap">
              <select
                value={eventActionFilter}
                onChange={(e) => {
                  setEventActionFilter(e.target.value);
                  setEventPage(1);
                }}
                className="text-xs bg-slate-50 border border-slate-300 rounded px-2 py-1 text-slate-800"
              >
                <option value="">ทุกประเภทเหตุการณ์</option>
                <option value="auth.login_ok">auth.login_ok</option>
                <option value="auth.login_failed">auth.login_failed</option>
                <option value="auth.locked">auth.locked</option>
                <option value="auth.session_expired">auth.session_expired</option>
                <option value="admin.unlock">admin.unlock</option>
                <option value="review.saved">review.saved</option>
                <option value="approval.saved">approval.saved</option>
              </select>

              <select
                value={eventUserFilter}
                onChange={(e) => {
                  setEventUserFilter(e.target.value);
                  setEventPage(1);
                }}
                className="text-xs bg-slate-50 border border-slate-300 rounded px-2 py-1 text-slate-800"
              >
                <option value="">ทุกผู้ใช้</option>
                {users.map((u) => (
                  <option key={u.user_id} value={u.user_id}>
                    {u.display_name} ({u.username})
                  </option>
                ))}
              </select>

              <button
                onClick={loadEvents}
                className="text-xs px-2.5 py-1 text-slate-600 hover:text-slate-900 border border-slate-200 rounded hover:bg-slate-50"
              >
                รีเฟรช
              </button>
            </div>
          </div>

          <div className="overflow-x-auto border border-slate-200 rounded-lg">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 uppercase font-semibold">
                <tr>
                  <th className="py-2.5 px-3">เวลา (UTC+7)</th>
                  <th className="py-2.5 px-3">เหตุการณ์ (Action)</th>
                  <th className="py-2.5 px-3">ผู้ใช้</th>
                  <th className="py-2.5 px-3">IP Address</th>
                  <th className="py-2.5 px-3">Request ID</th>
                  <th className="py-2.5 px-3">รายละเอียด (Detail)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {loadingEvents ? (
                  <tr>
                    <td colSpan={6} className="py-6 text-center text-slate-400">
                      กำลังโหลดรายการเหตุการณ์...
                    </td>
                  </tr>
                ) : events.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-6 text-center text-slate-400">
                      ไม่พบเหตุการณ์ตามเงื่อนไขที่เลือก
                    </td>
                  </tr>
                ) : (
                  events.map((ev, idx) => {
                    const isFailure =
                      ev.action === 'auth.login_failed' || ev.action === 'auth.locked';
                    const actionBadge = isFailure
                      ? 'bg-rose-100 text-rose-800 border-rose-200'
                      : ev.action.startsWith('auth.')
                      ? 'bg-emerald-100 text-emerald-800 border-emerald-200'
                      : 'bg-indigo-100 text-indigo-800 border-indigo-200';

                    return (
                      <tr key={idx} className="hover:bg-slate-50/70">
                        <td className="py-2 px-3 font-mono text-slate-500 text-[11px] whitespace-nowrap">
                          {new Date(ev.created_at).toLocaleString('th-TH')}
                        </td>
                        <td className="py-2 px-3 whitespace-nowrap">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${actionBadge}`}>
                            {ev.action}
                          </span>
                        </td>
                        <td className="py-2 px-3 whitespace-nowrap text-slate-700">
                          {ev.display_name || (ev.user_id ? `User #${ev.user_id}` : '-')}
                        </td>
                        <td className="py-2 px-3 font-mono text-slate-600 text-[11px] whitespace-nowrap">
                          {ev.client_ip || '-'}
                        </td>
                        <td className="py-2 px-3 font-mono text-slate-400 text-[10px] whitespace-nowrap max-w-[120px] truncate" title={ev.request_id || ''}>
                          {ev.request_id || '-'}
                        </td>
                        <td className="py-2 px-3 text-slate-600 font-mono text-[11px]">
                          {ev.detail ? JSON.stringify(ev.detail) : '-'}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="flex justify-between items-center pt-2">
            <span className="text-xs text-slate-500">หน้า {eventPage} (แสดงสูงสุด 50 รายการ/หน้า)</span>
            <div className="flex gap-2">
              <button
                disabled={eventPage <= 1}
                onClick={() => setEventPage((p) => Math.max(1, p - 1))}
                className="text-xs px-3 py-1 border border-slate-200 rounded bg-white hover:bg-slate-50 disabled:opacity-40"
              >
                ก่อนหน้า
              </button>
              <button
                disabled={events.length < 50}
                onClick={() => setEventPage((p) => p + 1)}
                className="text-xs px-3 py-1 border border-slate-200 rounded bg-white hover:bg-slate-50 disabled:opacity-40"
              >
                ถัดไป
              </button>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
};

export default Admin;
