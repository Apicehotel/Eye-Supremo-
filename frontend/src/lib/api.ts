const SESSION_KEY = 'randfatture.session';
const USER_KEY = 'randfatture.user';

export type AuthUser = {
  id: number;
  username: string;
  display_name: string;
  role_name: string;
  can_manage_config?: boolean;
  is_uploader?: boolean;
};

export function saveAuth(payload: {session: string; user: AuthUser}) {
  localStorage.setItem(SESSION_KEY, payload.session);
  localStorage.setItem(USER_KEY, JSON.stringify(payload.user));
}

export function clearAuth() {
  localStorage.removeItem(SESSION_KEY);
  localStorage.removeItem(USER_KEY);
}

export function currentSession() {
  return localStorage.getItem(SESSION_KEY);
}

export function currentUser(): AuthUser | null {
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export const api = async <T>(path: string, options?: RequestInit): Promise<T> => {
  const headers = new Headers(options?.headers || {});
  const session = currentSession();
  if (session) headers.set('X-Eye-Session', session);
  const response = await fetch(`/api${path}`, {...options, headers});
  if (response.status === 401) {
    clearAuth();
    window.dispatchEvent(new Event('eye-auth-expired'));
  }
  if (!response.ok) throw new Error(await response.text());
  return response.json();
};

export const euro = (value: number | null | undefined) =>
  new Intl.NumberFormat('it-IT', {style: 'currency', currency: 'EUR'}).format(value || 0);

export const shortDate = (value: string) =>
  new Intl.DateTimeFormat('it-IT').format(new Date(value));
