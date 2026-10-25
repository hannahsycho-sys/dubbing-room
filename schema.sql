-- ============================================================
--  Supabase 준비 — 이 파일을 통째로 복사해서
--  Supabase 대시보드 → SQL Editor → 붙여넣기 → Run 하면 끝입니다.
-- ============================================================

-- 1) 녹음이 쌓일 스토리지 버킷 (공개 읽기)
insert into storage.buckets (id, name, public)
values ('takes', 'takes', true)
on conflict (id) do update set public = true;

-- 2) 제출 기록 테이블
create table if not exists public.submissions (
  id          bigserial primary key,
  project     text        not null,
  line_id     int         not null,
  team        text,
  char        text,
  person      text        not null,
  path        text        not null,
  dur         real,
  offset_ms   int         not null default 0,   -- 싱크 미세조정 (음수=당기기, 양수=밀기)
  gain_db     real        not null default 0,   -- 볼륨 보정 (dB, 음수=줄이기 양수=키우기)
  clean       smallint    not null default 0,   -- 음질 보정 (0=끄기 1=약하게 2=보통 3=강하게)
  trim_s      real        not null default 0,   -- 앞에서 잘라낼 길이 (초)
  trim_e      real        not null default 0,   -- 뒤에서 잘라낼 길이 (초)
  created_at  timestamptz not null default now()
);
-- 이미 만들어 둔 표에 칸만 추가할 때
alter table public.submissions add column if not exists offset_ms int not null default 0;
alter table public.submissions add column if not exists gain_db real not null default 0;
alter table public.submissions add column if not exists clean smallint not null default 0;
alter table public.submissions add column if not exists trim_s real not null default 0;
alter table public.submissions add column if not exists trim_e real not null default 0;
create index if not exists submissions_project_idx on public.submissions (project, line_id);

-- 3) 권한
--    수업용이라 링크를 아는 사람은 누구나 읽기/쓰기/지우기가 됩니다.
--    (더빙했다가 지우고 다시 하는 기능 때문에 delete 가 필요합니다)
--    외부에 링크가 새면 곤란하니 수업이 끝나면 4번을 실행해 잠그세요.
alter table public.submissions enable row level security;

drop policy if exists "anyone read"   on public.submissions;
drop policy if exists "anyone insert" on public.submissions;
drop policy if exists "anyone delete" on public.submissions;

create policy "anyone read"   on public.submissions for select using (true);
create policy "anyone insert" on public.submissions for insert with check (true);
create policy "anyone delete" on public.submissions for delete using (true);
drop policy if exists "anyone update" on public.submissions;
create policy "anyone update" on public.submissions for update using (true) with check (true);

drop policy if exists "takes read"   on storage.objects;
drop policy if exists "takes write"  on storage.objects;
drop policy if exists "takes delete" on storage.objects;

create policy "takes read"   on storage.objects for select using (bucket_id = 'takes');
create policy "takes write"  on storage.objects for insert with check (bucket_id = 'takes');
create policy "takes delete" on storage.objects for delete using (bucket_id = 'takes');

-- ============================================================
-- 4) 수업이 끝난 뒤 잠그고 싶을 때만 실행 (쓰기 막고 읽기만 남김)
-- ============================================================
-- drop policy "anyone insert" on public.submissions;
-- drop policy "anyone delete" on public.submissions;
-- drop policy "anyone update" on public.submissions;
-- drop policy "takes write"   on storage.objects;
-- drop policy "takes delete"  on storage.objects;
