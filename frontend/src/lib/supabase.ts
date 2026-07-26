import { createClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL ?? "http://localhost:54321";
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "dev-anon-key";

/** Browser Supabase client (anon key; RLS enforces tenant isolation). */
export const supabase = createClient(url, anonKey);
