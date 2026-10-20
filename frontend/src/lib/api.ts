export const currentUser = () => {
  try{return JSON.parse(localStorage.getItem('eye-supremo.user')||'null')}catch{return null}
};
export const currentRole = () => currentUser()?.role_name || 'developer';
export const currentSession = () => localStorage.getItem('eye-supremo.session') || '';

const securedHeaders = (initial?:HeadersInit) => {
  const headers = new Headers(initial || {});
  headers.set('X-Eye-Role', currentRole());
  const session=currentSession();
  if(session)headers.set('X-Eye-Session',session);
  return headers;
};

export const api = async <T>(path:string, options?:RequestInit):Promise<T> => {
  try {
    const sentSession=currentSession();
    const response = await httpDataService.raw('core', path, {...options, headers:securedHeaders(options?.headers)});
    if(options?.signal?.aborted)throw new DOMException('Richiesta annullata','AbortError');
    if(response.status===401&&currentSession()===sentSession){clearAuth();window.dispatchEvent(new Event('eye-auth-expired'))}
    if(!response.ok) {const body=await response.json().catch(()=>null);throw new Error(typeof body?.detail==='string'?body.detail:'Operazione non riuscita')}
    return response.json();
  } catch(error) {
    if(error instanceof TypeError) throw new Error('Backend locale non raggiungibile. Avvia Eye Supremo e riprova.');
    throw error;
  }
};

export const eyeApi = async <T>(path:string, options?:RequestInit):Promise<T> => {
  try {
    const sentSession=currentSession();
    const response = await httpDataService.raw('eye', path, {...options, headers:securedHeaders(options?.headers)});
    if(options?.signal?.aborted)throw new DOMException('Richiesta annullata','AbortError');
    if(response.status===401&&currentSession()===sentSession){localStorage.removeItem('eye-supremo.session');localStorage.removeItem('eye-supremo.user');window.dispatchEvent(new Event('eye-auth-expired'))}
    if(!response.ok) {const body=await response.json().catch(()=>null);throw new Error(typeof body?.detail==='string'?body.detail:'Operazione non riuscita')}
    return response.json();
  } catch(error) {
    if(error instanceof TypeError) throw new Error('Backend locale non raggiungibile. Avvia Eye Supremo e riprova.');
    throw error;
  }
};

export const publicApi = async <T>(path:string, options?:RequestInit):Promise<T> => {
  const response = await httpDataService.raw('eye', `/auth${path}`, options);
  if (!response.ok) throw new Error('Servizio di accesso non disponibile. Riprova.');
  return response.json() as Promise<T>;
};

export const saveAuth=(payload:any)=>{localStorage.setItem('eye-supremo.session',payload.session);localStorage.setItem('eye-supremo.user',JSON.stringify(payload.user))};
export const clearAuth=()=>{localStorage.removeItem('eye-supremo.session');localStorage.removeItem('eye-supremo.user')};
export const euro = (value:number|null|undefined) => new Intl.NumberFormat('it-IT',{style:'currency',currency:'EUR'}).format(value || 0);
export const shortDate = (value:string) => new Intl.DateTimeFormat('it-IT').format(new Date(value));

import { apiUrl, httpDataService } from './dataService';
export { apiUrl, apiPrefix } from './dataService';

