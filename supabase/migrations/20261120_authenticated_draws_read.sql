-- Dear Draw Analyzer: allow signed-in app users to read cloud draw records.
-- This is needed for automatic Supabase -> app synchronization.
-- Only Nagaland Dear 1PM and 8PM rows are exposed to authenticated users.
-- API writes continue to use the server-side secret key in GitHub Actions.

grant select on table public.draws to authenticated;

drop policy if exists "authenticated_nagaland_draws_read" on public.draws;

create policy "authenticated_nagaland_draws_read"
on public.draws
for select
to authenticated
using (draw_slot in ('1PM', '8PM'));
