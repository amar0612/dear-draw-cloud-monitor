-- Dear Draw Analyzer: allow authenticated users to append local-history imports.
-- This is intentionally INSERT-only. Existing cloud rows cannot be updated or deleted
-- from the browser. API automation continues to use its server-side secret key.
-- Run once in the Supabase SQL Editor for project sxdrqithncjdrokwpkzm.

grant insert on table public.draws to authenticated;

drop policy if exists "authenticated_local_history_insert" on public.draws;

create policy "authenticated_local_history_insert"
on public.draws
for insert
to authenticated
with check (
  auth.uid() is not null
  and draw_slot in ('1PM', '8PM')
  and source = 'Local device history migration'
  and verification_status = 'LOCAL_IMPORT_UNVERIFIED'
  and jsonb_typeof(prizes) = 'object'
  and jsonb_typeof(prizes -> '1st') = 'array'
  and jsonb_typeof(prizes -> 'Consolation') = 'array'
  and jsonb_typeof(prizes -> '2nd') = 'array'
  and jsonb_typeof(prizes -> '3rd') = 'array'
  and jsonb_typeof(prizes -> '4th') = 'array'
  and jsonb_typeof(prizes -> '5th') = 'array'
  and jsonb_array_length(prizes -> '1st') = 1
  and jsonb_array_length(prizes -> 'Consolation') = 1
  and jsonb_array_length(prizes -> '2nd') = 10
  and jsonb_array_length(prizes -> '3rd') = 10
  and jsonb_array_length(prizes -> '4th') = 10
  and jsonb_array_length(prizes -> '5th') = 100
  and (prizes -> '1st' ->> 0) ~ '^[0-9]{2}[A-Z] [0-9]{5}$'
  and (prizes -> 'Consolation' ->> 0) ~ '^[0-9]{5}$'
  and right(prizes -> '1st' ->> 0, 5) = (prizes -> 'Consolation' ->> 0)
);
