export const currentRole = () => localStorage.getItem('eye-supremo.role') || 'developer';

export const api = async <T>(path:string, options?:RequestInit):Promise<T> => {
  const headers = new Headers(options?.headers || {});
  headers.set('X-Eye-Role', currentRole());
  const response = await fetch(`/api${path}`, {...options, headers});
  if(!response.ok) throw new Error(await response.text());
  return response.json();
};

export const eyeApi = async <T>(path:string, options?:RequestInit):Promise<T> => {
  const headers = new Headers(options?.headers || {});
  headers.set('X-Eye-Role', currentRole());
  const response = await fetch(`/api/eye${path}`, {...options, headers});
  if(!response.ok) throw new Error(await response.text());
  return response.json();
};

export const euro = (value:number|null|undefined) => new Intl.NumberFormat('it-IT',{style:'currency',currency:'EUR'}).format(value || 0);
export const shortDate = (value:string) => new Intl.DateTimeFormat('it-IT').format(new Date(value));
