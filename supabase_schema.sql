create table if not exists public.marker_board_states (
  id text primary key,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create or replace function public.set_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists marker_board_states_set_updated_at on public.marker_board_states;

create trigger marker_board_states_set_updated_at
before update on public.marker_board_states
for each row
execute function public.set_updated_at();

alter table public.marker_board_states enable row level security;

drop policy if exists "Allow marker board state reads" on public.marker_board_states;
drop policy if exists "Allow marker board state inserts" on public.marker_board_states;
drop policy if exists "Allow marker board state updates" on public.marker_board_states;
drop policy if exists "Deny browser marker board state access" on public.marker_board_states;

-- The deployed app reads and writes through Vercel Functions with the
-- Supabase service-role key. No browser-facing RLS policy is needed.
create policy "Deny browser marker board state access"
on public.marker_board_states
for all
to anon, authenticated
using (false)
with check (false);

insert into public.marker_board_states (id, payload)
values ('default', '{}'::jsonb)
on conflict (id) do nothing;
