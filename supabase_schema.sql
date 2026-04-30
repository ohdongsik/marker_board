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

drop policy if exists "Deny browser marker board state access" on public.marker_board_states;

create policy "Deny browser marker board state access"
on public.marker_board_states
for all
to anon, authenticated
using (false)
with check (false);

insert into public.marker_board_states (id, payload)
values ('default', '{}'::jsonb)
on conflict (id) do nothing;

create table if not exists public.marker_board_workspaces (
  id text primary key,
  sidebar_title text not null default '웹보드',
  current_board_id text null,
  nav_collapsed boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.marker_boards (
  id text primary key,
  workspace_id text not null references public.marker_board_workspaces(id) on delete cascade,
  sort_order integer not null default 0,
  name text not null,
  image_src text not null default '',
  image_name text not null default '',
  image_width integer not null default 0,
  image_height integer not null default 0,
  selected_marker_id text null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.marker_board_markers (
  id text primary key,
  board_id text not null references public.marker_boards(id) on delete cascade,
  sort_order integer not null default 0,
  number integer not null,
  x double precision not null,
  y double precision not null,
  title text not null default '',
  body text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists marker_boards_workspace_sort_idx
on public.marker_boards (workspace_id, sort_order, created_at);

create index if not exists marker_board_markers_board_sort_idx
on public.marker_board_markers (board_id, sort_order, number, created_at);

drop trigger if exists marker_board_workspaces_set_updated_at on public.marker_board_workspaces;
drop trigger if exists marker_boards_set_updated_at on public.marker_boards;
drop trigger if exists marker_board_markers_set_updated_at on public.marker_board_markers;

create trigger marker_board_workspaces_set_updated_at
before update on public.marker_board_workspaces
for each row
execute function public.set_updated_at();

create trigger marker_boards_set_updated_at
before update on public.marker_boards
for each row
execute function public.set_updated_at();

create trigger marker_board_markers_set_updated_at
before update on public.marker_board_markers
for each row
execute function public.set_updated_at();

alter table public.marker_board_workspaces enable row level security;
alter table public.marker_boards enable row level security;
alter table public.marker_board_markers enable row level security;

drop policy if exists "Deny browser marker board workspace access" on public.marker_board_workspaces;
drop policy if exists "Deny browser marker board access" on public.marker_boards;
drop policy if exists "Deny browser marker access" on public.marker_board_markers;

create policy "Deny browser marker board workspace access"
on public.marker_board_workspaces
for all
to anon, authenticated
using (false)
with check (false);

create policy "Deny browser marker board access"
on public.marker_boards
for all
to anon, authenticated
using (false)
with check (false);

create policy "Deny browser marker access"
on public.marker_board_markers
for all
to anon, authenticated
using (false)
with check (false);

create or replace function public.get_marker_board_state(workspace_id_input text default 'default')
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
  select
    jsonb_build_object(
      'boards',
      coalesce(
        (
          select jsonb_agg(board_payload order by sort_order, created_at)
          from (
            select
              b.sort_order,
              b.created_at,
              jsonb_build_object(
                'id', b.id,
                'name', b.name,
                'imageSrc', b.image_src,
                'imageName', b.image_name,
                'imageWidth', b.image_width,
                'imageHeight', b.image_height,
                'selectedId', b.selected_marker_id,
                'createdAt', b.created_at,
                'updatedAt', b.updated_at,
                'markers',
                coalesce(
                  (
                    select jsonb_agg(marker_payload order by sort_order, number, created_at)
                    from (
                      select
                        m.sort_order,
                        m.number,
                        m.created_at,
                        jsonb_build_object(
                          'id', m.id,
                          'number', m.number,
                          'x', m.x,
                          'y', m.y,
                          'title', m.title,
                          'body', m.body,
                          'createdAt', m.created_at,
                          'updatedAt', m.updated_at
                        ) as marker_payload
                      from public.marker_board_markers m
                      where m.board_id = b.id
                    ) marker_rows
                  ),
                  '[]'::jsonb
                )
              ) as board_payload
            from public.marker_boards b
            where b.workspace_id = w.id
          ) board_rows
        ),
        '[]'::jsonb
      ),
      'currentBoardId', w.current_board_id,
      'navCollapsed', w.nav_collapsed,
      'sidebarTitle', w.sidebar_title
    )
  from public.marker_board_workspaces w
  where w.id = workspace_id_input;
$$;

create or replace function public.save_marker_board_state(
  workspace_id_input text default 'default',
  state_input jsonb default '{}'::jsonb
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  board_record record;
  marker_record record;
  v_board_id text;
  v_marker_id text;
begin
  if state_input is null then
    state_input := '{}'::jsonb;
  end if;

  if jsonb_typeof(coalesce(state_input->'boards', '[]'::jsonb)) <> 'array' then
    raise exception 'state_input.boards must be an array';
  end if;

  insert into public.marker_board_workspaces (
    id,
    sidebar_title,
    current_board_id,
    nav_collapsed
  )
  values (
    workspace_id_input,
    coalesce(nullif(state_input->>'sidebarTitle', ''), '웹보드'),
    nullif(state_input->>'currentBoardId', ''),
    coalesce((state_input->>'navCollapsed')::boolean, false)
  )
  on conflict (id) do update
  set
    sidebar_title = excluded.sidebar_title,
    current_board_id = excluded.current_board_id,
    nav_collapsed = excluded.nav_collapsed,
    updated_at = now();

  for board_record in
    select
      value as board_json,
      ordinality::integer - 1 as sort_order
    from jsonb_array_elements(coalesce(state_input->'boards', '[]'::jsonb)) with ordinality
  loop
    v_board_id := coalesce(board_record.board_json->>'id', '');
    if v_board_id = '' then
      continue;
    end if;

    insert into public.marker_boards (
      id,
      workspace_id,
      sort_order,
      name,
      image_src,
      image_name,
      image_width,
      image_height,
      selected_marker_id,
      created_at,
      updated_at
    )
    values (
      v_board_id,
      workspace_id_input,
      board_record.sort_order,
      coalesce(nullif(board_record.board_json->>'name', ''), '새 웹보드'),
      coalesce(board_record.board_json->>'imageSrc', ''),
      coalesce(board_record.board_json->>'imageName', ''),
      coalesce((board_record.board_json->>'imageWidth')::integer, 0),
      coalesce((board_record.board_json->>'imageHeight')::integer, 0),
      nullif(board_record.board_json->>'selectedId', ''),
      coalesce((board_record.board_json->>'createdAt')::timestamptz, now()),
      coalesce((board_record.board_json->>'updatedAt')::timestamptz, now())
    )
    on conflict (id) do update
    set
      workspace_id = excluded.workspace_id,
      sort_order = excluded.sort_order,
      name = excluded.name,
      image_src = excluded.image_src,
      image_name = excluded.image_name,
      image_width = excluded.image_width,
      image_height = excluded.image_height,
      selected_marker_id = excluded.selected_marker_id,
      updated_at = excluded.updated_at;

    delete from public.marker_board_markers
    where board_id = v_board_id
      and id not in (
        select value->>'id'
        from jsonb_array_elements(coalesce(board_record.board_json->'markers', '[]'::jsonb)) as value
        where coalesce(value->>'id', '') <> ''
      );

    for marker_record in
      select
        value as marker_json,
        ordinality::integer - 1 as sort_order
      from jsonb_array_elements(coalesce(board_record.board_json->'markers', '[]'::jsonb)) with ordinality
    loop
      v_marker_id := coalesce(marker_record.marker_json->>'id', '');
      if v_marker_id = '' then
        continue;
      end if;

      insert into public.marker_board_markers (
        id,
        board_id,
        sort_order,
        number,
        x,
        y,
        title,
        body,
        created_at,
        updated_at
      )
      values (
        v_marker_id,
        v_board_id,
        marker_record.sort_order,
        coalesce((marker_record.marker_json->>'number')::integer, marker_record.sort_order + 1),
        coalesce((marker_record.marker_json->>'x')::double precision, 0),
        coalesce((marker_record.marker_json->>'y')::double precision, 0),
        coalesce(marker_record.marker_json->>'title', ''),
        coalesce(marker_record.marker_json->>'body', ''),
        coalesce((marker_record.marker_json->>'createdAt')::timestamptz, now()),
        coalesce((marker_record.marker_json->>'updatedAt')::timestamptz, now())
      )
      on conflict (id) do update
      set
        board_id = excluded.board_id,
        sort_order = excluded.sort_order,
        number = excluded.number,
        x = excluded.x,
        y = excluded.y,
        title = excluded.title,
        body = excluded.body,
        updated_at = excluded.updated_at;
    end loop;
  end loop;

  delete from public.marker_boards
  where workspace_id = workspace_id_input
    and id not in (
      select value->>'id'
      from jsonb_array_elements(coalesce(state_input->'boards', '[]'::jsonb)) as value
      where coalesce(value->>'id', '') <> ''
    );

  update public.marker_board_workspaces w
  set current_board_id = case
    when w.current_board_id is not null
      and exists (
        select 1
        from public.marker_boards b
        where b.workspace_id = w.id and b.id = w.current_board_id
      )
    then w.current_board_id
    else (
      select b.id
      from public.marker_boards b
      where b.workspace_id = w.id
      order by b.sort_order, b.created_at
      limit 1
    )
  end
  where w.id = workspace_id_input;

  return public.get_marker_board_state(workspace_id_input);
end;
$$;

insert into public.marker_board_workspaces (id)
values ('default')
on conflict (id) do nothing;

select public.save_marker_board_state(id, payload)
from public.marker_board_states
where jsonb_typeof(payload->'boards') = 'array';
