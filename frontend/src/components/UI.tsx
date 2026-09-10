import {ReactNode} from 'react';
import {Search} from 'lucide-react';
export function PageHeader({title,subtitle,children}:{title:string,subtitle?:string,children?:ReactNode}){return <header className="page-header"><div><h1>{title}</h1>{subtitle&&<p>{subtitle}</p>}</div>{children}</header>}
export function SearchBox({value,onChange,placeholder='Cerca…'}:{value:string,onChange:(v:string)=>void,placeholder?:string}){return <label className="search-box"><Search size={18}/><input value={value} onChange={e=>onChange(e.target.value)} placeholder={placeholder}/></label>}
export function Empty({title='Nessun dato',text='Importa una fattura o aggiungi un elemento per iniziare.'}:{title?:string,text?:string}){return <div className="empty"><strong>{title}</strong><span>{text}</span></div>}
export function Loading(){return <div className="loading">Caricamento…</div>}
export function Status({children,tone='ok'}:{children:ReactNode,tone?:string}){return <span className={`status ${tone}`}>{children}</span>}
