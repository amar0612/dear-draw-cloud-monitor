-- Dear Draw Analyzer: allow signed-in app users to read cloud draw records.
-- This is needed for automatic Supabase -> app synchronization.
-- Only Nagaland Dear 1PM and 8PM rows are exposed to authenticated users.
-- API writes continue to use the server-side secret key in GitHub Actions.
-- Non-destructive: this migration does not drop policies, tables, or draw rows.

grant select on table public.draws to authenticated;

create policy "dda_authenticated_nagaland_draws_read_v1"
on public.draws
for select
to authenticated
using (draw_slot in ('1PM', '8PM'));
