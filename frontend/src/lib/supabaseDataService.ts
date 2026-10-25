// Versione online (sola lettura): il frontend parla direttamente con le Edge Functions
// Supabase `eye-identity` e `eye-central-gateway`, senza backend FastAPI.
// Implementa la stessa interfaccia `DataService` e restituisce oggetti Response, cosi'
// le pagine esistenti non cambiano. Endpoint non coperti rispondono 404 "non disponibile online".
import type { ApiArea, DataService } from "./dataService.ts";

const env = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env || {};
const baseUrl = String(env.VITE_SUPABASE_URL || "").replace(/\/+$/, "");
const publishableKey = String(env.VITE_SUPABASE_PUBLISHABLE_KEY || "");

export const supabaseOnline = env.VITE_EYE_BACKEND === "supabase" && Boolean(baseUrl && publishableKey);

const reply = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const unavailable = () => reply({ detail: "Funzione non disponibile nella versione online" }, 404);

const storedUser = (): { username?: string } | null => {
  try { return JSON.parse(localStorage.getItem("eye-supremo.user") || "null"); } catch { return null; }
};
const token = () => localStorage.getItem("eye-supremo.session") || "";

async function call(fn: "eye-identity" | "eye-central-gateway", body: object, bearer?: string) {
  const headers: Record<string, string> = { "Content-Type": "application/json", apikey: publishableKey };
  if (bearer) headers.Authorization = `Bearer ${bearer}`;
  try {
    const res = await fetch(`${baseUrl}/functions/v1/${fn}`, { method: "POST", headers, body: JSON.stringify(body) });
    const data = await res.json().catch(() => ({}));
    return { status: res.status, data: data as any };
  } catch {
    return { status: 503, data: { error: "Servizio non raggiungibile" } };
  }
}

const gateway = (body: object) => call("eye-central-gateway", { username: storedUser()?.username || "", pin: token(), ...body });
const failure = (r: { status: number; data: any }) => reply({ detail: r.data?.error || "Operazione non riuscita" }, r.status === 200 ? 500 : r.status);

async function eyeRequest(path: string, options?: RequestInit): Promise<Response> {
  const url = new URL(path, "http://x");
  const route = url.pathname.replace(/\/+$/, "");
  const method = (options?.method || "GET").toUpperCase();

  if (route === "/auth/status") return reply({ configured: true, bootstrap_required: false, central: true });
  if (route === "/auth/login-options") return reply([
    { username: "supremo", display_name: "Supremo (supremo)", role_name: "supremo" },
    { username: "sviluppatore", display_name: "Sviluppatore (developer)", role_name: "developer" },
  ]);
  if (route === "/auth/login" && method === "POST") {
    const body = JSON.parse(String(options?.body || "{}"));
    const r = await call("eye-identity", { action: "login", username: body.username, pin: body.pin });
    if (r.status !== 200) return reply({ detail: r.data?.error || "Accesso non riuscito" }, r.status);
    const u = r.data.user;
    return reply({ session: r.data.token, user: { id: 0, username: u.username, display_name: u.display_name, role_name: u.role } });
  }
  if (route === "/auth/me") {
    const r = await call("eye-identity", { action: "me" }, token());
    return r.status === 200 ? reply({ offline: false }) : reply({ detail: "Sessione non valida" }, 401);
  }
  if (route === "/auth/logout" && method === "POST") {
    await call("eye-identity", { action: "logout" }, token());
    return reply({ ok: true });
  }

  if (method !== "GET") return unavailable();

  if (route === "/central/invoices") {
    const q = (url.searchParams.get("q") || "").trim();
    const limit = Number(url.searchParams.get("limit")) || 50;
    const offset = Number(url.searchParams.get("offset")) || 0;
    if (q) {
      const r = await gateway({ action: "search_invoices", query: q, limit });
      if (r.status !== 200) return failure(r);
      const items = r.data.items || [];
      return reply({ enabled: true, items, count: items.length, total: items.length, offset: 0, limit, source: "supabase" });
    }
    const r = await gateway({ action: "invoice_page", limit, offset });
    if (r.status !== 200) return failure(r);
    return reply({ enabled: true, items: r.data.items || [], count: (r.data.items || []).length, total: r.data.total, offset, limit, source: "supabase" });
  }
  return unavailable();
}

export const supabaseDataService: DataService = {
  async request<T>(area: ApiArea, path: string, options?: RequestInit) {
    const response = await supabaseDataService.raw(area, path, options);
    if (!response.ok) throw response;
    return response.json() as Promise<T>;
  },
  raw: async (area, path, options) => (area === "eye" ? eyeRequest(path, options) : unavailable()),
};
