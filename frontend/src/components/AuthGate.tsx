import {FormEvent,useEffect,useState} from 'react';
import {LockKeyhole,ShieldCheck} from 'lucide-react';
import {clearAuth,currentSession,eyeApi,saveAuth} from '../lib/api';

type LoginUser={username:string;display_name:string;role_name?:string};

function roleLabel(role?: string) {
 if (role === 'developer') return 'Accesso tecnico';
 if (role === 'supremo') return 'Accesso completo';
 if (role?.startsWith('level')) return `Profilo operativo ${role.replace('level','')}`;
 return 'Profilo locale';
}

export function AuthGate({children}:{children:React.ReactNode}){
 const [loading,setLoading]=useState(true),[configured,setConfigured]=useState<boolean|null>(null),[users,setUsers]=useState<LoginUser[]>([]),[authenticated,setAuthenticated]=useState(false),[username,setUsername]=useState(''),[pin,setPin]=useState(''),[error,setError]=useState('');
 async function refresh(){setLoading(true);try{const status:any=await fetch('/api/eye/auth/status').then(r=>r.json());setConfigured(status.configured);const options=await fetch('/api/eye/auth/login-options').then(r=>r.json());setUsers(options);if(options.length&&!options.some((u:LoginUser)=>u.username===username)){const preferred=options.find((u:LoginUser)=>u.role_name!=='developer')||options[0];setUsername(preferred.username)}if(status.configured&&currentSession()){try{await eyeApi('/auth/me');setAuthenticated(true)}catch{clearAuth();setAuthenticated(false)}}else setAuthenticated(false)}finally{setLoading(false)}}
 useEffect(()=>{refresh();const expired=()=>{setAuthenticated(false);setConfigured(true);fetch('/api/eye/auth/login-options').then(r=>r.json()).then(setUsers).catch(()=>{})};window.addEventListener('eye-auth-expired',expired);return()=>window.removeEventListener('eye-auth-expired',expired)},[]);
 async function submit(e:FormEvent){e.preventDefault();setError('');try{const endpoint=configured?'/auth/login':'/auth/bootstrap';const body=configured?{username,pin}:{username,pin};const payload:any=await fetch(`/api/eye${endpoint}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(async r=>{if(!r.ok)throw new Error(await r.text());return r.json()});saveAuth(payload);setAuthenticated(true);setConfigured(true);setPin('')}catch(err:any){setError(err.message)}}
 if(loading)return <div className="auth-screen"><div className="auth-card"><ShieldCheck/><h1>Eye Supremo</h1><p>Avvio sicurezza locale…</p></div></div>;
 if(authenticated)return <>{children}</>;
 return <div className="auth-screen"><form className="auth-card" onSubmit={submit}><LockKeyhole size={38}/><h1>Accedi a Eye Supremo</h1>{configured?<><p>Seleziona il tuo profilo e inserisci il PIN personale.</p><label>Profilo utente<select value={username} onChange={e=>setUsername(e.target.value)}>{users.map(u=><option key={u.username} value={u.username}>{u.display_name} · {roleLabel(u.role_name)}</option>)}</select></label></>:<><p>Configura il primo accesso scegliendo il profilo locale da utilizzare.</p><label>Profilo utente<select value={username} onChange={e=>setUsername(e.target.value)}>{users.map(u=><option key={u.username} value={u.username}>{u.display_name}</option>)}</select></label></>}<label>PIN<input autoFocus inputMode="numeric" pattern="[0-9]*" minLength={6} maxLength={12} type="password" value={pin} onChange={e=>setPin(e.target.value.replace(/\D/g,''))} placeholder="Inserisci il PIN"/></label>{error&&<div className="error">{error}</div>}<button className="primary-btn" disabled={!username||pin.length<6}>{configured?'Accedi':'Attiva profilo'}</button><small>Ogni utente accede con il proprio profilo e le autorizzazioni assegnate. I dati restano nel database locale del PC.</small></form></div>;
}
