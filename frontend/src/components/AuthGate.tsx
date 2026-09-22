import {FormEvent, useEffect, useState} from 'react';
import {LockKeyhole, ShieldCheck} from 'lucide-react';
import {clearAuth, currentSession, saveAuth} from '../lib/api';

const USERS: [string, string][] = [
  ['sviluppatore', 'Sviluppatore'],
  ['supremo', 'Supremo'],
  ['livello1', 'Utente Livello 1'],
  ['livello2', 'Utente Livello 2'],
  ['livello3', 'Utente Livello 3'],
  ['caricatore', 'Caricatore fatture'],
];

export function AuthGate({children}: {children: React.ReactNode}) {
  const [loading, setLoading] = useState(true);
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [authenticated, setAuthenticated] = useState(false);
  const [username, setUsername] = useState('sviluppatore');
  const [pin, setPin] = useState('');
  const [error, setError] = useState('');

  async function refresh() {
    setLoading(true);
    try {
      const status: any = await fetch('/api/auth/status').then((r) => r.json());
      setConfigured(status.configured);
      if (status.configured && currentSession()) {
        try {
          const headers = {'X-Eye-Session': currentSession() || ''};
          const me = await fetch('/api/auth/me', {headers}).then(async (r) => {
            if (!r.ok) throw new Error('expired');
            return r.json();
          });
          localStorage.setItem('randfatture.user', JSON.stringify(me));
          setAuthenticated(true);
        } catch {
          clearAuth();
          setAuthenticated(false);
        }
      } else {
        setAuthenticated(false);
      }
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
    const expired = () => {
      setAuthenticated(false);
      setConfigured(true);
    };
    window.addEventListener('eye-auth-expired', expired);
    return () => window.removeEventListener('eye-auth-expired', expired);
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError('');
    try {
      const endpoint = configured ? '/auth/login' : '/auth/bootstrap';
      const body = configured ? {username, pin} : {pin};
      const payload: any = await fetch(`/api${endpoint}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      }).then(async (r) => {
        if (!r.ok) throw new Error(await r.text());
        return r.json();
      });
      saveAuth(payload);
      setAuthenticated(true);
      setConfigured(true);
      setPin('');
    } catch (err: any) {
      setError(err.message || 'Accesso non riuscito');
    }
  }

  if (loading) {
    return (
      <div className="auth-screen">
        <div className="auth-card">
          <ShieldCheck />
          <h1>RandFatture</h1>
          <p>Avvio sicurezza locale…</p>
        </div>
      </div>
    );
  }

  if (authenticated) return <>{children}</>;

  return (
    <div className="auth-screen">
      <form className="auth-card" onSubmit={submit}>
        <LockKeyhole size={38} />
        <h1>RandFatture</h1>
        {configured ? (
          <>
            <p>Accedi al profilo locale sul PC.</p>
            <label>
              Utente
              <select value={username} onChange={(e) => setUsername(e.target.value)}>
                {USERS.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </>
        ) : (
          <p>
            Prima configurazione: crea il PIN dello <b>Sviluppatore</b>. Poi potrai impostare i PIN degli altri
            utenti, incluso il <b>Caricatore</b> che vede solo l’upload verso Supabase Storage.
          </p>
        )}
        <label>
          PIN
          <input
            autoFocus
            inputMode="numeric"
            pattern="[0-9]*"
            minLength={6}
            maxLength={12}
            type="password"
            value={pin}
            onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
            placeholder="6–12 cifre"
          />
        </label>
        {error && <div className="error">{error}</div>}
        <button className="primary-btn" disabled={pin.length < 6}>
          {configured ? 'Accedi' : 'Configura'}
        </button>
        <small>Credenziali e archivio restano sul PC. Supabase serve solo per i file.</small>
      </form>
    </div>
  );
}
