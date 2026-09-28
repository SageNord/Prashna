import { supabase } from './supabase';
const API_URL=(import.meta.env.VITE_API_URL||'http://localhost:8000').replace(/\/$/,'');
export async function api<T=any>(path:string,init:RequestInit={}):Promise<T>{
 const {data}=await supabase?.auth.getSession()??{data:{session:null}};
 const headers=new Headers(init.headers);headers.set('Content-Type','application/json');headers.set('X-User-Timezone',Intl.DateTimeFormat().resolvedOptions().timeZone||'UTC');
 if(data.session?.access_token)headers.set('Authorization',`Bearer ${data.session.access_token}`);
 let response:Response;try{response=await fetch(`${API_URL}${path}`,{...init,headers})}catch{throw Error("Couldn't connect. Please try again.")}
 if(!response.ok){const body=await response.json().catch(()=>({}));throw Error(body.detail||'Something went wrong. Please try again.')}
 return response.json() as Promise<T>;
}
