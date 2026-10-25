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

// Funzioni RPC di Supabase (schema public): stesse usate dal backend locale, accettano il token di sessione.
async function rpc(name: string, args: object): Promise<Response> {
  try {
    const res = await fetch(`${baseUrl}/rest/v1/rpc/${name}`, {
      method: "POST",
      headers: { "Content-Type": "application/json", apikey: publishableKey },
      body: JSON.stringify({ p_username: storedUser()?.username || "", p_pin: token(), ...args }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) return reply(data);
    const message = String(data?.message || "");
    if (/credenziali/i.test(message)) return reply({ detail: "Sessione scaduta" }, 401);
    return reply({ detail: message || "Operazione non riuscita" }, res.status);
  } catch {
    return reply({ detail: "Servizio non raggiungibile" }, 503);
  }
}
const withEnabled = async (r: Response) => (r.ok ? reply({ enabled: true, ...(await r.json()) }) : r);

const gateway = (body: object) => call("eye-central-gateway", { username: storedUser()?.username || "", pin: token(), ...body });
const failure = (r: { status: number; data: any }) => reply({ detail: r.data?.error || "Operazione non riuscita" }, r.status === 200 ? 500 : r.status);

async function eyeRequest(path: string, options?: RequestInit): Promise<Response> {
  const url = new URL(path, "http://x");
  const route = url.pathname.replace(/\/+$/, "");
  const method = (options?.method || "GET").toUpperCase();

  if (route === "/auth/status") return reply({ configured: true, bootstrap_required: false, central: true });
  if (route === "/auth/login-options") return reply([
    { username: "supremo", display_name: "Supremo", role_name: "supremo" },
    { username: "sviluppatore", display_name: "Sviluppatore", role_name: "developer" },
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

  const detail = (prefix: string) => (route.startsWith(prefix) ? decodeURIComponent(route.slice(prefix.length)) : "");
  const invoiceHash = detail("/central/invoices/") || detail("/invoice-ref/");
  if (invoiceHash) {
    const r = await rpc("eye_central_invoice_detail", { p_source_hash: invoiceHash });
    if (!r.ok) return r;
    const data = await r.json();
    return data?.invoice_number ? reply({ ...data, source: "central" }) : reply({ detail: "Fattura non trovata" }, 404);
  }
  if (route === "/central/suppliers") {
    return withEnabled(await rpc("eye_central_supplier_page", { p_query: url.searchParams.get("q") || "", p_limit: Number(url.searchParams.get("limit")) || 2000 }));
  }
  const supplierId = detail("/central/suppliers/");
  if (supplierId) {
    const r = await rpc("eye_central_supplier_detail", { p_supplier_id: supplierId });
    if (!r.ok) return r;
    const data = await r.json();
    return data?.supplier ? reply(data) : reply({ detail: "Fornitore non trovato" }, 404);
  }
  const productName = detail("/central/products/");
  if (productName) {
    const r = await rpc("eye_central_product_detail", { p_canonical_name: productName });
    if (!r.ok) return r;
    const data = await r.json();
    return data?.product ? reply(data) : reply({ detail: "Prodotto non trovato" }, 404);
  }

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

// Area "core": elenchi che il backend locale arricchisce con regole Python; online arriva il catalogo grezzo.
async function coreRequest(path: string, options?: RequestInit): Promise<Response> {
  const url = new URL(path, "http://x");
  const route = url.pathname.replace(/\/+$/, "");
  if ((options?.method || "GET").toUpperCase() !== "GET") return unavailable();
  if (route === "/products") {
    const r = await rpc("eye_central_product_page", { p_query: url.searchParams.get("q") || "", p_limit: Math.min(Number(url.searchParams.get("limit")) || 200, 500) });
    return r.ok ? reply((await r.json()).items || []) : r;
  }
  if (route === "/product-config" || route === "/product-tracking") return reply({});
  return unavailable();
}

export const supabaseDataService: DataService = {
  async request<T>(area: ApiArea, path: string, options?: RequestInit) {
    const response = await supabaseDataService.raw(area, path, options);
    if (!response.ok) throw response;
    return response.json() as Promise<T>;
  },
  raw: async (area, path, options) => (area === "eye" ? eyeRequest(path, options) : coreRequest(path, options)),
};
