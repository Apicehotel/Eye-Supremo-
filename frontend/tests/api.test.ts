import test from 'node:test';
import assert from 'node:assert/strict';
import {api, eyeApi, currentSession, saveAuth} from '../src/lib/api.ts';

const values=new Map<string,string>();
(globalThis as any).localStorage={getItem:(key:string)=>values.get(key)??null,setItem:(key:string,value:string)=>values.set(key,value),removeItem:(key:string)=>values.delete(key)};
(globalThis as any).window=new EventTarget();
const actualFetch=globalThis.fetch;
function session(token:string){saveAuth({session:token,user:{username:'test',role_name:'supremo'}});}

for(const [label,request] of [['legacy',api],['eye',eyeApi]] as const){
 test(`${label}: un 401 tardivo non cancella il login successivo`,async()=>{
  let finish!:(response:Response)=>void;
  globalThis.fetch=()=>new Promise(resolve=>{finish=resolve});
  try{
   session('old');const work=request('/test');session('new');finish(new Response(JSON.stringify({detail:'scaduto'}),{status:401}));
   await assert.rejects(work);assert.equal(currentSession(),'new');
  }finally{globalThis.fetch=actualFetch;}
 });
 test(`${label}: la cancellazione ignora anche un 401 tardivo`,async()=>{
  let finish!:(response:Response)=>void;
  globalThis.fetch=()=>new Promise(resolve=>{finish=resolve});
  try{
   session('valid');const controller=new AbortController();const work=request('/test',{signal:controller.signal});controller.abort();
   finish(new Response('{}',{status:401}));
   await assert.rejects(work,{name:'AbortError'});assert.equal(currentSession(),'valid');
  }finally{globalThis.fetch=actualFetch;}
 });
 test(`${label}: un 401 della sessione corrente richiede di accedere`,async()=>{
  globalThis.fetch=async()=>new Response(JSON.stringify({detail:'Sessione richiesta'}),{status:401});
  try{session('expired');await assert.rejects(request('/test'));assert.equal(currentSession(),'');}
  finally{globalThis.fetch=actualFetch;}
 });
}
