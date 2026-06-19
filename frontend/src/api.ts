export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const TOKEN_KEY = "vigil_admin_token";

export const getToken = () => window.sessionStorage.getItem(TOKEN_KEY);
export const saveToken = (token: string) => window.sessionStorage.setItem(TOKEN_KEY, token);
export const clearToken = () => window.sessionStorage.removeItem(TOKEN_KEY);

export function apiFetch(path: string, options: RequestInit = {}) {
  const token = getToken();
  const headers = new Headers(options.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(`${API_URL}${path}`, { ...options, headers });
}
