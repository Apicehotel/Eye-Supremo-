import {FormEvent, useEffect, useState} from 'react';
import {LockKeyhole, ShieldCheck} from 'lucide-react';
import {clearAuth, currentSession, eyeApi, saveAuth} from '../lib/api';

type LoginUser = {username: string; display_name: string};
type AuthStatus = {configured: boolean; central: boolean};
type IdentityStatus = {offline?: boolean; offline_until?: string | null};
type LoginResponse = IdentityStatus & {session: string; user: {id: number; username: string; display_name: string; role_name: string}};

async function publicJson<T>(path: string): Promise<T> {
  const response = await fetch(`/api/eye/auth/${path}`);
  if (!response.ok) throw new Error('Servizio di accesso non disponibile. Riprova.');
  return response.json();
}

export function AuthGate({children}: {children: React.ReactNode}) {
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState<AuthStatus>();
  const [users, setUsers] = useState<LoginUser[]>([]);
  const [authenticated, setAuthenticated] = useState(false);
  const [username, setUsername] = useState('');
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
        if (!nextStatus.central && options.length) setUsername(current => current || options[0].username);
        if (currentSession()) {
          try {
            const me = await eyeApi<IdentityStatus>('/auth/me');
            if (active) {setIdentity(me); setAuthenticated(true);}
          } catch {clearAuth(); if (active) setAuthenticated(false);}
        }
      } catch {
        if (active) setError('Backend locale non raggiungibile. Verifica che Eye Supremo sia avviato e riprova.');
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
      const response = await fetch(`/api/eye/auth/${endpoint}`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({username: username.trim(), pin}),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(typeof payload.detail === 'string' ? payload.detail : 'Accesso non riuscito');
      const login = payload as LoginResponse;
      saveAuth(login);
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
    {status?.central ? <label>Nome utente<input autoComplete="username" value={username} maxLength={80} list="eye-known-users" onChange={e => setUsername(e.target.value)}/><datalist id="eye-known-users">{users.map(user => <option key={user.username} value={user.username}>{user.display_name}</option>)}</datalist></label>
      : <label>Profilo utente<select value={username} onChange={e => setUsername(e.target.value)}>{users.map(user => <option key={user.username} value={user.username}>{user.display_name}</option>)}</select></label>}
    <label>PIN<input autoComplete="current-password" inputMode="numeric" pattern="[0-9]*" minLength={6} maxLength={12} type="password" value={pin} onChange={e => setPin(e.target.value.replace(/\D/g, ''))} placeholder="Il tuo PIN"/></label>
    {error && <div className="error" role="alert">{error}</div>}
    <button className="primary-btn" disabled={!status || !username.trim() || pin.length < 6 || busy}>{busy ? 'Verifica…' : status?.configured ? 'Accedi' : 'Attiva profilo'}</button>
    {!status && <button type="button" className="secondary-btn" onClick={() => setRetry(value => value + 1)}>Riprova</button>}
    <small>{status?.central ? 'Offline puoi accedere solo dopo una verifica online su questo PC, entro il periodo autorizzato.' : 'I dati del profilo restano sul PC.'}</small>
  </form></div>;
}
