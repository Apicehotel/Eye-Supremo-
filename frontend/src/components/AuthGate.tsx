import {FormEvent, useEffect, useState} from 'react';
import {LockKeyhole, ShieldCheck} from 'lucide-react';
import {clearAuth, currentSession, eyeApi, publicApi, saveAuth} from '../lib/api';

type LoginUser = {username: string; display_name: string};
type AuthStatus = {configured: boolean; central: boolean};
type IdentityStatus = {offline?: boolean; offline_until?: string | null};
type LoginResponse = IdentityStatus & {session: string; user: {id: number; username: string; display_name: string; role_name: string}};

type PwdCred = {id: string; password?: string};
const credApi = () => (navigator as unknown as {credentials?: {get: (o: object) => Promise<PwdCred | null>; store: (c: unknown) => Promise<unknown>}}).credentials;

async function publicJson<T>(path: string): Promise<T> {
  return publicApi<T>(`/${path}`);
}

export function AuthGate({children}: {children: React.ReactNode}) {
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<AuthStatus>();
  const [users, setUsers] = useState<LoginUser[]>([]);
  const [authenticated, setAuthenticated] = useState(false);
  const [username, setUsername] = useState(() => {try {return localStorage.getItem('eye-supremo.last-username') || '';} catch {return '';}});
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [identity, setIdentity] = useState<IdentityStatus>({});
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let active = true;
    const expired = () => {setAuthenticated(false); setPin('');};
    window.addEventListener('eye-auth-expired', expired);
    async function refresh() {
      setLoading(true);
      setError('');
      try {
        const [nextStatus, options] = await Promise.all([
          publicJson<AuthStatus>('status'), publicJson<LoginUser[]>('login-options'),
        ]);
        if (!active) return;
        setStatus(nextStatus);
        setUsers(options);
        // Anche con identità centrale il profilo locale può essere preselezionato:
        // il campo resta modificabile e il PIN non viene mai memorizzato.
        if (options.length) setUsername(current => current || options[0].username);
        if (!currentSession()) {
          // Chrome: propone le credenziali salvate dal gestore password (senza finestra se ce n'e' una sola).
          try {
            const saved = await credApi()?.get({password: true, mediation: 'optional'});
            if (active && saved?.password) {setUsername(saved.id); setPin(saved.password);}
          } catch { /* gestore password non disponibile */ }
        }
        if (currentSession()) {
          try {
            const me = await eyeApi<IdentityStatus>('/auth/me');
            if (active) {setIdentity(me); setAuthenticated(true);}
          } catch {clearAuth(); if (active) setAuthenticated(false);}
        }
      } catch {
        if (active) setError('Servizio non raggiungibile. Verifica la connessione (o che Eye Supremo sia avviato sul PC) e riprova.');
      } finally {if (active) setLoading(false);}
    }
    void refresh();
    return () => {active = false; window.removeEventListener('eye-auth-expired', expired);};
  }, [retry]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      const endpoint = status?.configured ? 'login' : 'bootstrap';
      const payload = await publicApi<LoginResponse>(`/${endpoint}`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username: username.trim(), pin}),
      });
      const login = payload as LoginResponse;
      saveAuth(login);
      try {
        const Cred = (window as unknown as {PasswordCredential?: new (d: object) => unknown}).PasswordCredential;
        if (Cred) await credApi()?.store(new Cred({id: username.trim(), password: pin, name: login.user.display_name}));
      } catch { /* salvataggio facoltativo */ }
      try {localStorage.setItem('eye-supremo.last-username', username.trim());} catch { /* facoltativo */ }
      setIdentity(login);
      setAuthenticated(true);
      setPin('');
    } catch (err) {setError(err instanceof Error ? err.message : 'Accesso non riuscito');}
    finally {setBusy(false);}
  }

  async function reconnect() {
    try {await eyeApi('/auth/logout', {method: 'POST'});} catch { /* Rimuove comunque la sessione sul PC. */ }
    clearAuth(); setAuthenticated(false); setPin('');
  }

  if (loading) return <div className="auth-screen"><div className="auth-card"><ShieldCheck/><h1>Eye Supremo</h1><p>Verifica accesso…</p></div></div>;
  if (authenticated) return <>
    {identity.offline && <div className="offline-auth-banner" role="status">Accesso offline autorizzato{identity.offline_until ? ` fino al ${new Date(identity.offline_until).toLocaleDateString('it-IT')}` : ''}. <button type="button" onClick={reconnect}>Accedi online</button></div>}
    {children}
  </>;
  return <div className="auth-screen"><form className="auth-card" onSubmit={submit}>
    <LockKeyhole size={38}/><h1>Accedi a Eye Supremo</h1>
    <p>{status?.central ? 'Usa il tuo profilo centrale. Il primo accesso su questo PC richiede Internet.' : 'Seleziona il profilo e inserisci il tuo PIN.'}</p>
    {status?.central ? <label>Nome utente<input id="eye-username" name="username" autoComplete="username" autoCapitalize="none" spellCheck={false} value={username} maxLength={80} list="eye-known-users" onChange={e => setUsername(e.target.value)}/><datalist id="eye-known-users">{users.map(user => <option key={user.username} value={user.username}>{user.display_name}</option>)}</datalist>{users.length > 0 && <span className="login-roles">{users.map(user => <button type="button" key={user.username} className={`secondary-btn${username === user.username ? ' active' : ''}`} onClick={() => setUsername(user.username)}>{user.display_name}</button>)}</span>}</label>
      : <label>Profilo utente<select value={username} onChange={e => setUsername(e.target.value)}>{users.map(user => <option key={user.username} value={user.username}>{user.display_name}</option>)}</select></label>}
    <label>PIN<input id="eye-pin" name="password" autoComplete="current-password" inputMode="numeric" pattern="[0-9]*" minLength={6} maxLength={12} type="password" value={pin} onChange={e => setPin(e.target.value.replace(/\D/g, ''))} placeholder="Il tuo PIN"/></label>
    {error && <div className="error" role="alert">{error}</div>}
    <button className="primary-btn" disabled={!status || !username.trim() || pin.length < 6 || busy}>{busy ? 'Verifica…' : status?.configured ? 'Accedi' : 'Attiva profilo'}</button>
    {!status && <button type="button" className="secondary-btn" onClick={() => setRetry(value => value + 1)}>Riprova</button>}
    <small>{status?.central ? 'Offline puoi accedere solo dopo una verifica online su questo PC, entro il periodo autorizzato.' : 'I dati del profilo restano sul PC.'}</small>
  </form></div>;
}
