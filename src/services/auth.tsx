import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { Session, User } from '@supabase/supabase-js';
import { supabase, supabaseConfigured } from './supabase';

type AuthValue = { session: Session | null; user: User | null; loading: boolean; configured: boolean; recovery: boolean; signIn:(email:string,password:string)=>Promise<void>; signUp:(email:string,password:string,name:string)=>Promise<void>; signOut:()=>Promise<void>; resetPassword:(email:string)=>Promise<void>; updatePassword:(password:string)=>Promise<void> };
const AuthContext=createContext<AuthValue|null>(null);
export function AuthProvider({children}:{children:ReactNode}){
 const [session,setSession]=useState<Session|null>(null),[loading,setLoading]=useState(true),[recovery,setRecovery]=useState(new URLSearchParams(location.search).get('auth')==='reset');
 useEffect(()=>{if(!supabase){setLoading(false);return}let active=true;supabase.auth.getSession().then(({data})=>{if(active){setSession(data.session);setLoading(false)}});const{data:{subscription}}=supabase.auth.onAuthStateChange((event,next)=>{setSession(next);if(event==='PASSWORD_RECOVERY')setRecovery(true);if(event==='SIGNED_OUT')setRecovery(false);setLoading(false)});return()=>{active=false;subscription.unsubscribe()}},[]);
 const value=useMemo<AuthValue>(()=>({session,user:session?.user??null,loading,configured:supabaseConfigured,recovery,
  signIn:async(email,password)=>{if(!supabase)throw Error('Authentication is not configured yet.');const{error}=await supabase.auth.signInWithPassword({email,password});if(error)throw friendly(error.message)},
  signUp:async(email,password,name)=>{if(!supabase)throw Error('Authentication is not configured yet.');const{error}=await supabase.auth.signUp({email,password,options:{data:{display_name:name.trim()}}});if(error)throw friendly(error.message)},
  signOut:async()=>{if(!supabase)return;const{error}=await supabase.auth.signOut();if(error)throw friendly(error.message)},
  resetPassword:async(email)=>{if(!supabase)throw Error('Authentication is not configured yet.');const{error}=await supabase.auth.resetPasswordForEmail(email,{redirectTo:`${location.origin}/?auth=reset`});if(error)throw friendly(error.message)},
  updatePassword:async(password)=>{if(!supabase)throw Error('Authentication is not configured yet.');const{error}=await supabase.auth.updateUser({password});if(error)throw friendly(error.message);setRecovery(false);history.replaceState({},'',location.pathname)}
 }),[session,loading,recovery]);
 return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
export function useAuth(){const value=useContext(AuthContext);if(!value)throw Error('AuthProvider is missing');return value}
function friendly(message:string){const m=message.toLowerCase();if(m.includes('invalid login')||m.includes('invalid credentials'))return Error('Email or password is incorrect.');if(m.includes('already registered')||m.includes('already been registered'))return Error('An account with this email already exists.');if(m.includes('network')||m.includes('fetch'))return Error("Couldn't connect. Please try again.");if(m.includes('expired'))return Error('Your session expired. Please sign in again.');return Error(message)}
