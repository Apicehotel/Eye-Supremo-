import {createClient} from "npm:@supabase/supabase-js@2.75.0";
import postgres from "npm:postgres@3.4.7";

const BUCKET = "eye-updates";
const sql = postgres(Deno.env.get("SUPABASE_DB_URL")!, {prepare: false, max: 2, idle_timeout: 20});
const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "apikey, authorization, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status,
  headers: {...cors, "Content-Type": "application/json", "Cache-Control": "no-store"},
});
const tokenHash = async (value: string) => [...new Uint8Array(
  await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)),
)].map((item) => item.toString(16).padStart(2, "0")).join("");

Deno.serve(async (request) => {
  if (request.method === "OPTIONS") return new Response("ok", {headers: cors});
  if (request.method !== "POST") return json({error: "Metodo non consentito"}, 405);

  try {
    const body = await request.json().catch(() => null);
    const username = typeof body?.username === "string" ? body.username.trim().toLowerCase() : "";
    const token = (request.headers.get("authorization") || "").replace(/^Bearer\s+/i, "");
    if (!username || !/^eye1_[a-f0-9]{64}$/.test(token)) return json({error: "Sessione centrale richiesta"}, 401);

    const url = Deno.env.get("SUPABASE_URL")!;
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
    const client = createClient(url, serviceKey, {auth: {persistSession: false, autoRefreshToken: false}});
    const sessions = await sql`
      select s.username from eye_supremo.eye_identity_sessions s
      join eye_supremo.eye_central_users u on u.username=s.username
      where s.token_hash=${await tokenHash(token)} and s.username=${username}
        and s.expires_at>now() and u.active and u.auth_version=s.auth_version
      limit 1`;
    if (!sessions[0]) {
      return json({error: "Sessione centrale non valida"}, 401);
    }

    const {data: manifestBlob, error: manifestError} = await client.storage.from(BUCKET).download("latest.json");
    if (manifestError || !manifestBlob) return json({error: "Nessun aggiornamento pubblicato"}, 404);
    const manifest = JSON.parse(await manifestBlob.text());
    const filename = String(manifest?.filename || "");
    if (!/^EyeSupremo-Setup-\d+\.\d+\.\d+\.exe$/.test(filename)) {
      return json({error: "Manifest aggiornamento non valido"}, 503);
    }
    const {data: signed, error: signedError} = await client.storage.from(BUCKET).createSignedUrl(filename, 600);
    if (signedError || !signed?.signedUrl) return json({error: "Installer non disponibile"}, 503);

    return json({...manifest, download_url: signed.signedUrl});
  } catch (error) {
    console.error("eye-updates failed", error instanceof Error ? error.message : "internal");
    return json({error: "Servizio aggiornamenti non disponibile"}, 503);
  }
});
