-- TrendCast AI — harden function search_path
--
-- Supabase's database linter (0011_function_search_path_mutable) flags both
-- project functions as having a role-mutable search_path. A function without a
-- pinned search_path resolves unqualified names against whatever the CALLER's
-- search_path happens to be, so a caller who can create objects in an earlier
-- schema could shadow a referenced table or operator and have the function run
-- against their object instead.
--
-- Both functions are SECURITY INVOKER, so this is defence in depth rather than
-- a privilege-escalation fix — but it is free, and it silences a standing WARN.
--
-- Safe because both bodies already schema-qualify every table they touch
-- (public.tracked_asins, public.signal_events); only pg_catalog builtins are
-- referenced unqualified, and pg_catalog is always searched implicitly.
--
-- Idempotent: ALTER FUNCTION ... SET is safe to re-run.

alter function public.enforce_asin_cap()    set search_path = '';
alter function public.prune_signal_events() set search_path = '';
