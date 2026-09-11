import {useEffect,useState} from 'react';
import {KeyRound,Users} from 'lucide-react';
import {eyeApi} from '../lib/api';
import {Status} from './UI';

type User={id:number;username:string;display_name:string;role_name:string;pin_configured:boolean;active:boolean};

export function UserAdmin(){
 const [users,setUsers]=useState<User[]>([]),[pins,setPins]=useState<Record<number,string>>({}),[message,setMessage]=useState('');
 const load=()=>eyeApi<User[]>('/auth/users').then(setUsers);
 useEffect(()=>{load().catch(()=>{})},[]);
 async function save(user:User){const pin=pins[user.id]||'';if(pin.length<6){setMessage('Il PIN deve avere almeno 6 cifre.');return}try{await eyeApi(`/auth/users/${user.id}/pin`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin})});setPins({...pins,[user.id]:''});setMessage(`PIN aggiornato per ${user.display_name}`);await load()}catch(e:any){setMessage(e.message)}}
 return <section className="panel"><div className="panel-title"><h2><Users size={18}/> Utenti locali e PIN</h2></div><p>Lo Sviluppatore configura i profili. I PIN sono salvati come hash PBKDF2, mai in chiaro.</p>{message&&<p>{message}</p>}<div className="table-wrap"><table><thead><tr><th>Utente</th><th>Ruolo</th><th>PIN</th><th>Nuovo PIN</th><th></th></tr></thead><tbody>{users.map(u=><tr key={u.id}><td><b>{u.display_name}</b><small style={{display:'block'}}>{u.username}</small></td><td>{u.role_name}</td><td><Status tone={u.pin_configured?'ok':'warn'}>{u.pin_configured?'Configurato':'Da configurare'}</Status></td><td><input inputMode="numeric" type="password" maxLength={12} value={pins[u.id]||''} onChange={e=>setPins({...pins,[u.id]:e.target.value.replace(/\D/g,'')})} placeholder="6–12 cifre"/></td><td><button className="secondary-btn" onClick={()=>save(u)}><KeyRound size={15}/>Salva PIN</button></td></tr>)}</tbody></table></div></section>;
}
