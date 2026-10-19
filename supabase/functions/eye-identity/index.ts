import postgres from "npm:postgres@3.4.7";
import bcrypt from "npm:bcryptjs@2.4.3";

const sql = postgres(Deno.env.get("SUPABASE_DB_URL")!, {prepare: false, max: 3, idle_timeout: 20, connect_timeout: 10});
const cors = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "apikey, authorization, content-type", "Access-Control-Allow-Methods": "POST, OPTIONS"};
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), {status, headers: {...cors, "Content-Type": "application/json", "Cache-Control": "no-store"}});
const usernameOf = (v: unknown) => typeof v === "string" ? v.trim().toLowerCase() : "";
const validUsername = (v: string) => /^[a-z0-9_-]{1,80}$/.test(v);
const validPin = (v: unknown): v is string => typeof v === "string" && /^[0-9]{6,12}$/.test(v);
const tokenHash = async (v: string) => [...new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(v)))].map(x => x.toString(16).padStart(2, "0")).join("");
const publicUser = (u: any) => ({username: u.username, display_name: u.display_name || u.username, role: u.role, active: u.active, auth_version: u.auth_version});

async function limited(key: string, max: number) {
  const digest = await tokenHash(key);
  const rows = await sql`
    insert into eye_supremo.eye_identity_limits(key, window_start, attempts) values(${digest}, now(), 1)
    on conflict(key) do update set
      attempts=case when eye_identity_limits.window_start < now()-interval '15 minutes' then 1 else eye_identity_limits.attempts+1 end,
      window_start=case when eye_identity_limits.window_start < now()-interval '15 minutes' then now() else eye_identity_limits.window_start end
    returning attempts`;
  return rows[0].attempts > max;
}

async function actor(token: string) {
  if (!/^eye1_[a-f0-9]{64}$/.test(token)) return null;
  const rows = await sql`
    select u.* from eye_supremo.eye_identity_sessions s
    join eye_supremo.eye_central_users u on u.username=s.username
    where s.token_hash=${await tokenHash(token)} and s.expires_at>now()
      and s.auth_version=u.auth_version and u.active=true and u.role in ('developer','supremo')`;
  return rows[0] || null;
}

Deno.serve({port: Number(Deno.env.get("PORT") || 8000)}, async req => {
  if (req.method === "OPTIONS") return new Response("ok", {headers: cors});
  if (req.method !== "POST") return json({error: "Metodo non consentito"}, 405);
  try {
    const raw = await req.text();
    if (raw.length > 8192) return json({error: "Richiesta troppo grande"}, 413);
    let body: any;
    try { body = JSON.parse(raw); } catch { return json({error: "JSON non valido"}, 422); }
    if (!body || typeof body !== "object" || Array.isArray(body)) return json({error: "Richiesta non valida"}, 422);
    const action = body.action;
    if (action === "availability") return json({available: true});
    if (action === "login") {
      const username = usernameOf(body.username);
      const ip = req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() || "unknown";
      if (await limited(`ip:${ip}`, 100)) return json({error: "Troppi tentativi"}, 429);
      if (!validUsername(username) || !validPin(body.pin)) return json({error: "Credenziali non valide"}, 401);
      if (await limited(`user:${username}`, 20)) return json({error: "Troppi tentativi"}, 429);
      const rows = await sql`select * from eye_supremo.eye_central_users where username=${username}`;
      const user = rows[0];
      const hash = user?.pin_hash || "$2a$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy";
      if (!(await bcrypt.compare(body.pin, hash)) || !user?.active || !["developer", "supremo"].includes(user.role)) return json({error: "Credenziali non valide"}, 401);
      const bytes = crypto.getRandomValues(new Uint8Array(32));
      const token = "eye1_" + [...bytes].map(x => x.toString(16).padStart(2, "0")).join("");
      const expires = new Date(Date.now() + 12*60*60*1000).toISOString();
      await sql.begin(async tx => {
        const fresh = await tx`select auth_version,active from eye_supremo.eye_central_users where username=${username} for update`;
        if (!fresh[0]?.active || fresh[0].auth_version !== user.auth_version) throw new Error("AUTH_CHANGED");
        await tx`delete from eye_supremo.eye_identity_sessions where expires_at<now()`;
        await tx`delete from eye_supremo.eye_identity_limits where window_start<now()-interval '1 day'`;
        await tx`insert into eye_supremo.eye_identity_sessions(token_hash,username,auth_version,expires_at) values(${await tokenHash(token)},${username},${user.auth_version},${expires})`;
      });
      return json({user: publicUser(user), token, expires_at: expires});
    }
    const token = (req.headers.get("authorization") || "").replace(/^Bearer\s+/i, "");
    const user = await actor(token);
    if (!user) return json({error: "Sessione centrale non valida"}, 401);
    if (action === "me") return json({user: publicUser(user)});
    if (action === "logout") {
      await sql`delete from eye_supremo.eye_identity_sessions where token_hash=${await tokenHash(token)}`;
      return json({ok: true});
    }
    if (action === "list_users") {
      const users = await sql`select username,display_name,role,active,auth_version from eye_supremo.eye_central_users order by display_name,username`;
      return json({users: users.map(publicUser)});
    }
    const username = usernameOf(body.username);
    if (!validUsername(username)) return json({error: "Username non valido"}, 422);
    if (!["create_user", "set_pin", "set_active"].includes(action)) return json({error: "Azione non consentita"}, 403);
    if ((action === "create_user" || action === "set_pin") && !validPin(body.pin)) return json({error: "PIN non valido"}, 422);
    const display = typeof body.display_name === "string" ? body.display_name.trim() : "";
    if (action === "create_user" && (!display || display.length > 160)) return json({error: "Nome non valido"}, 422);
    if (action === "set_active" && typeof body.active !== "boolean") return json({error: "Stato non valido"}, 422);
    if (action === "set_active" && username === user.username && !body.active) return json({error: "Non puoi disattivare il tuo profilo"}, 403);
    const hash = validPin(body.pin) ? await bcrypt.hash(body.pin, 12) : null;
    const result = await sql.begin(async tx => {
      await tx`select pg_advisory_xact_lock(hashtext('eye_supremo.identity_admin'))`;
      const fresh = await tx`
        select u.username from eye_supremo.eye_identity_sessions s
        join eye_supremo.eye_central_users u on u.username=s.username
        where s.token_hash=${await tokenHash(token)} and s.expires_at>now()
          and u.active and u.auth_version=s.auth_version and u.role in ('developer','supremo')`;
      if (!fresh[0]) throw new Error("AUTH_CHANGED");
      if (action === "create_user") {
        const users = await tx`insert into eye_supremo.eye_central_users(username,display_name,pin_hash,role,active) values(${username},${display},${hash},'supremo',true) returning *`;
        return users[0];
      }
      if (action === "set_active" && !body.active) {
        const count = await tx`select count(*)::int n from eye_supremo.eye_central_users where active and role in ('developer','supremo') and username<>${username}`;
        if (!count[0].n) throw new Error("LAST_USER");
      }
      const users = action === "set_pin"
        ? await tx`update eye_supremo.eye_central_users set pin_hash=${hash},auth_version=auth_version+1 where username=${username} returning *`
        : await tx`update eye_supremo.eye_central_users set active=${body.active},auth_version=auth_version+1 where username=${username} returning *`;
      if (!users[0]) throw new Error("NOT_FOUND");
      await tx`delete from eye_supremo.eye_identity_sessions where username=${username}`;
      return users[0];
    });
    return json({user: publicUser(result)});
  } catch (e: any) {
    if (e?.code === "23505") return json({error: "Username già esistente"}, 409);
    if (e?.message === "AUTH_CHANGED") return json({error: "Sessione centrale revocata"}, 401);
    if (e?.message === "NOT_FOUND") return json({error: "Utente non trovato"}, 404);
    if (e?.message === "LAST_USER") return json({error: "Deve restare un profilo attivo"}, 409);
    console.error("eye-identity request failed", {code: e?.code || "internal"});
    return json({error: "Servizio utenti non disponibile"}, 503);
  }
});
