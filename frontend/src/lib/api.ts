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
  const response = await fetch(`/api${path}`, {...options, headers:securedHeaders(options?.headers)});
  if(!response.ok) throw new Error(await response.text());
  return response.json();
};

export const eyeApi = async <T>(path:string, options?:RequestInit):Promise<T> => {
  const response = await fetch(`/api/eye${path}`, {...options, headers:securedHeaders(options?.headers)});
  if(response.status===401){localStorage.removeItem('eye-supremo.session');localStorage.removeItem('eye-supremo.user');window.dispatchEvent(new Event('eye-auth-expired'))}
  if(!response.ok) throw new Error(await response.text());
  return response.json();
};

export const saveAuth=(payload:any)=>{localStorage.setItem('eye-supremo.session',payload.session);localStorage.setItem('eye-supremo.user',JSON.stringify(payload.user))};
export const clearAuth=()=>{localStorage.removeItem('eye-supremo.session');localStorage.removeItem('eye-supremo.user')};
export const euro = (value:number|null|undefined) => new Intl.NumberFormat('it-IT',{style:'currency',currency:'EUR'}).format(value || 0);
export const shortDate = (value:string) => new Intl.DateTimeFormat('it-IT').format(new Date(value));
