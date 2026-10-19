// Eseguire solo contro il database di test locale, mai contro Supabase produzione.
import postgres from "npm:postgres@3.4.7";
import bcrypt from "npm:bcryptjs@2.4.3";

function assert(condition: unknown, message = "Assertion failed"): asserts condition {
  if (!condition) throw new Error(message);
}
const databaseUrl = Deno.env.get("EYE_IDENTITY_TEST_DB");
Deno.test({name: "identity: utenti centrali, sessioni, revoca e permessi SQL", ignore: !databaseUrl, sanitizeOps: false, sanitizeResources: false, fn: async () => {
  const parsed = new URL(databaseUrl!);
  assert(["localhost", "127.0.0.1", "[::1]"].includes(parsed.hostname), "Sono consentiti solo database locali di test");
  assert(parsed.pathname === "/eye_identity_test", "Usare il database eye_identity_test");
  const sql = postgres(databaseUrl!, {prepare: false, max: 1, onnotice: () => {}});
  let server: Deno.ChildProcess | undefined;
  let gateway: Deno.ChildProcess | undefined;
  try {
    await sql.unsafe(`create schema if not exists extensions; create extension if not exists pgcrypto with schema extensions;
      do $$ begin if not exists(select 1 from pg_roles where rolname='anon') then create role anon; end if;
      if not exists(select 1 from pg_roles where rolname='authenticated') then create role authenticated; end if; end $$;
      create schema if not exists eye_supremo;
      create table if not exists eye_supremo.eye_central_users(username text primary key,pin_hash text not null,role text not null,
        active boolean not null default true,created_at timestamptz not null default now());`);
    const migration = await Deno.readTextFile(new URL("../migrations/20261019212228_central_identity_sessions.sql", import.meta.url));
    await sql.unsafe(migration);
    await sql.unsafe(migration); // Migrazione ripetibile anche sullo schema già aggiornato.
    await sql.unsafe("create table if not exists eye_supremo.eye_central_product_catalog(canonical_name text); truncate eye_supremo.eye_central_product_catalog; insert into eye_supremo.eye_central_product_catalog values('Test A'),('Test B');");
    await sql`delete from eye_supremo.eye_identity_sessions`;
    await sql`delete from eye_supremo.eye_identity_limits`;
    await sql`delete from eye_supremo.eye_central_users`;
    await sql`insert into eye_supremo.eye_central_users(username,display_name,pin_hash,role) values('admin','Admin',${await bcrypt.hash('654321',10)},'developer')`;
    server = new Deno.Command(Deno.execPath(), {
      args: ["run", "--node-modules-dir=manual", "--allow-env", "--allow-net", new URL("../functions/eye-identity/index.ts", import.meta.url).pathname],
      env: {SUPABASE_DB_URL: databaseUrl!, PORT: "18871"}, stdout: "null", stderr: "piped",
    }).spawn();
    const request = async (body: Record<string, unknown>, token?: string) => {
      const response = await fetch("http://127.0.0.1:18871", {method:"POST", headers:{"Content-Type":"application/json",...(token?{Authorization:`Bearer ${token}`}:{})}, body:JSON.stringify(body)});
      return {status:response.status, body:await response.json()};
    };
    let ready = false;
    for (let i=0;i<100;i++) {
      try {await request({action:"me"}); ready=true; break;} catch {await new Promise(resolve=>setTimeout(resolve,100));}
    }
    assert(ready,"Il servizio identità non è partito");
    gateway = new Deno.Command(Deno.execPath(), {
      args: ["run", "--node-modules-dir=manual", "--allow-env", "--allow-net", new URL("../functions/eye-central-gateway/index.ts", import.meta.url).pathname],
      env: {SUPABASE_DB_URL: databaseUrl!, PORT: "18872"}, stdout: "null", stderr: "piped",
    }).spawn();
    const gatewayRequest = async (username: string, pin: string) => {
      const response = await fetch("http://127.0.0.1:18872", {method:"POST", headers:{"Content-Type":"application/json"},body:JSON.stringify({action:"unknown",username,pin})});
      await response.arrayBuffer(); return response.status;
    };
    let gatewayReady=false;
    for (let i=0;i<100;i++) {try {await gatewayRequest("invalid", "invalid");gatewayReady=true;break;} catch {await new Promise(resolve=>setTimeout(resolve,100));}}
    assert(gatewayReady,"Il gateway dati non è partito");
    assert((await request({action:"list_users"})).status===401);
    assert((await request({action:"login",username:"admin",pin:"111111"})).status===401);
    const logged = await request({action:"login",username:"admin",pin:"654321"});
    assert(logged.status===200, `Login HTTP ${logged.status}: ${JSON.stringify(logged.body)}`);
    const token = logged.body.token;
    assert(/^eye1_[a-f0-9]{64}$/.test(token));
    assert(!("pin_hash" in logged.body.user));
    assert(await gatewayRequest("admin",token)===403, "Il gateway deve riconoscere il token personale prima di autorizzare l'azione");
    assert(await gatewayRequest("other",token)===401);
    const summary = await sql.begin(async tx => {
      await tx.unsafe("set local role anon");
      return await tx`select public.eye_central_product_summary('admin',${token}) as result`;
    });
    assert(summary[0].result.distinct_products===2, "La RPC dati deve funzionare col token e il ruolo anon");
    assert((await sql`select eye_supremo.eye_credentials_valid('admin',${token}) ok`)[0].ok);
    assert(!(await sql`select eye_supremo.eye_credentials_valid('someone_else',${token}) ok`)[0].ok);
    const created = await request({action:"create_user",username:"bob",display_name:"Bob",pin:"789654",role:"developer"},token);
    assert(created.status===200 && created.body.user.role==="supremo");
    assert((await request({action:"create_user",username:"bob",display_name:"Bob",pin:"789654"},token)).status===409);
    assert((await request({action:"set_active",username:"bob",active:"false"},token)).status===422);
    assert((await request({action:"set_active",username:"admin",active:false},token)).status===403);
    const pc2 = await request({action:"login",username:"bob",pin:"789654"});
    assert(pc2.status===200);
    assert((await request({action:"list_users"},pc2.body.token)).body.users.length===2);
    assert((await request({action:"set_active",username:"bob",active:false},token)).status===200);
    assert((await request({action:"me"},pc2.body.token)).status===401);
    assert(!(await sql`select eye_supremo.eye_credentials_valid('bob',${pc2.body.token}) ok`)[0].ok);
    assert((await request({action:"set_active",username:"bob",active:true},token)).status===200);
    assert((await request({action:"set_pin",username:"bob",pin:"456789"},token)).status===200);
    assert((await request({action:"login",username:"bob",pin:"789654"})).status===401);
    const newBob = await request({action:"login",username:"bob",pin:"456789"});
    assert(newBob.status===200);
    assert((await request({action:"logout"},newBob.body.token)).status===200);
    assert((await request({action:"me"},newBob.body.token)).status===401);
    assert((await request({action:"set_pin",username:"admin",pin:"456789"},token)).status===200);
    assert((await request({action:"me"},token)).status===401);
    assert(await gatewayRequest("admin",token)===401);
    for (let i=0;i<20;i++) assert((await request({action:"login",username:"missing",pin:"111111"})).status===401);
    assert((await request({action:"login",username:"missing",pin:"111111"})).status===429);
    const fresh = await request({action:"login",username:"admin",pin:"456789"});
    await sql`update eye_supremo.eye_identity_sessions set expires_at=now()-interval '1 second' where username='admin'`;
    assert((await request({action:"me"},fresh.body.token)).status===401);
    const privileges = await sql`select has_table_privilege('anon','eye_supremo.eye_identity_sessions','SELECT') as sessions,
      has_table_privilege('authenticated','eye_supremo.eye_central_users','SELECT') as users,
      has_function_privilege('anon','eye_supremo.eye_credentials_valid(text,text)','EXECUTE') as helper`;
    assert(!privileges[0].sessions && !privileges[0].users && !privileges[0].helper);
    const rls = await sql`select count(*)::int n from pg_class c join pg_namespace n on n.oid=c.relnamespace
      where n.nspname='eye_supremo' and c.relname in ('eye_central_users','eye_identity_sessions','eye_identity_limits') and c.relrowsecurity`;
    assert(rls[0].n===3);
  } finally {
    if (gateway) {try {gateway.kill("SIGTERM");} catch {} await gateway.output();}
    if (server) {try {server.kill("SIGTERM");} catch {} const output=await server.output(); if (output.stderr.length) console.error(new TextDecoder().decode(output.stderr));}
    await sql.end();
  }
}});
