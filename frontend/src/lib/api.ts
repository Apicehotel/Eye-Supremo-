export const api = async <T>(path:string, options?:RequestInit):Promise<T> => {
  const response = await fetch(`/api${path}`, options);
  if(!response.ok) throw new Error(await response.text());
  return response.json();
};
export const euro = (value:number|null|undefined) => new Intl.NumberFormat('it-IT',{style:'currency',currency:'EUR'}).format(value || 0);
export const shortDate = (value:string) => new Intl.DateTimeFormat('it-IT').format(new Date(value));
