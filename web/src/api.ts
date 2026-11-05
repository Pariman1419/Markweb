export interface User {
  user_id: number;
  username: string;
  display_name: string;
  role: string;
}

export interface Run {
  run_id: number;
  period: string;
  created_at: string;
  note: string;
}

export interface StatusCard {
  count: number;
  pct: number;
  top_cause: string;
}

export interface DashboardData {
  cards: {
    TRUE: StatusCard;
    WARNING: StatusCard;
    ERROR: StatusCard;
    HOLD: StatusCard;
  };
  monthly: Array<{
    month: string;
    TRUE: number;
    WARNING: number;
    ERROR: number;
  }>;
  error_causes: Array<{ cause: string; count: number }>;
  hold_causes: Array<{ cause: string; count: number }>;
}

export interface ElrRow {
  elr_no: string;
  month: string;
  abs_file: string;
  result: string;
  true_lines: number;
  total_lines: number;
  cause: string;
}

export interface ElrListResponse {
  total: number;
  page: number;
  rows: ElrRow[];
}

export interface LineDetail {
  line_no: number;
  expected: string;
  oracle: string;
  status: string;
  group: 'TRUE' | 'WARNING' | 'ERROR' | 'NONE';
  warning: string;
  detail: string;
  compare_rules: string;
}

export interface ReviewItem {
  review_id?: number;
  run_id: number;
  elr_no: string;
  line_no: number;
  reason: string;
  note: string;
  corrected_mark: string;
  is_draft: boolean;
  created_at?: string;
}

export interface ElrDetailResponse {
  snapshot: {
    run_id: number;
    elr_no: string;
    top_mark_id: number | null;
    layout_code: string | null;
    line_extra: Record<string, any>;
    mark_remark: string | null;
    mark_require: string | null;
    top_template_remark: string | null;
    oracle_top_raw: string[];
    layout_cells: (string | null)[][] | null;
    abs_file: string | null;
    abs_sha256: string | null;
    image_path: string | null;
    slr_files: string[];
    slr_instructions: Array<{ line: number; value: string; quote: string }>;
  } | null;
  job: {
    processing_status: string;
    hold_reason: string;
    hold_detail?: string;
  };
  lines: LineDetail[];
  reviews: Record<string | number, ReviewItem>;
  approval: {
    approval_id: number;
    decision: 'APPROVED' | 'REJECTED';
    user_id: number;
    created_at: string;
  } | null;
  image_available: boolean;
}

function getCsrfToken(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)(?:mark_csrf|__Secure-mark_csrf)=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

export async function apiFetch<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {});
  headers.set('Accept', 'application/json');

  const method = (options.method || 'GET').toUpperCase();
  if (['POST', 'PUT', 'DELETE', 'PATCH'].includes(method)) {
    const csrf = getCsrfToken();
    if (csrf) {
      headers.set('X-CSRF-Token', csrf);
    }
    if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
      headers.set('Content-Type', 'application/json');
    }
  }

  const res = await fetch(endpoint, {
    ...options,
    headers,
    credentials: 'include',
  });

  if (res.status === 401) {
    if (!window.location.pathname.startsWith('/login')) {
      window.location.href = '/login';
    }
    throw new Error('Unauthorized');
  }

  if (res.status === 423) {
    throw new Error('Account locked. Please try again after 15 minutes.');
  }

  if (!res.ok) {
    let errData: any = null;
    try {
      errData = await res.json();
    } catch {
      // not json
    }
    const err = new Error(errData?.detail || `HTTP ${res.status}`);
    (err as any).data = errData;
    (err as any).status = res.status;
    throw err;
  }

  return res.json() as Promise<T>;
}
