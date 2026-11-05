-- Sabi identity layer: compliance-grade provenance and consent
-- Additive only. Nothing existing is dropped or renamed, so the running API keeps working.
begin;

-- 1. Name provenance + canonical phone on the learner row
alter table public.sabi_students
  add column if not exists name_source        text,
  add column if not exists name_status        text,
  add column if not exists name_attempts      int  not null default 0,
  add column if not exists name_verified_at   timestamptz,
  add column if not exists name_verified_by   text,
  add column if not exists phone_e164         text,
  add column if not exists identity_version   int  not null default 2,
  add column if not exists merged_into        uuid references public.sabi_students(id);

alter table public.sabi_students drop constraint if exists sabi_students_name_status_chk;
alter table public.sabi_students add constraint sabi_students_name_status_chk
  check (name_status is null or name_status in
    ('unknown','unverified_utterance','rejected_artifact','confirmed_repeat','confirmed_caregiver','redacted'));

-- 2. Append-only identity audit trail (who changed what, from which call)
create table if not exists public.sabi_identity_events (
  id          uuid primary key default gen_random_uuid(),
  student_id  uuid references public.sabi_students(id) on delete cascade,
  event_type  text not null,
  field       text,
  old_value   text,
  new_value   text,
  source      text,
  confidence  numeric(4,3),
  actor       text,
  call_sid    text,
  session_id  uuid,
  created_at  timestamptz not null default now()
);
create index if not exists sabi_identity_events_student_idx on public.sabi_identity_events(student_id, created_at desc);

create or replace function public.sabi_identity_events_immutable()
returns trigger language plpgsql as $$
begin
  raise exception 'sabi_identity_events is append-only';
end $$;

drop trigger if exists sabi_identity_events_no_update on public.sabi_identity_events;
create trigger sabi_identity_events_no_update
  before update or delete on public.sabi_identity_events
  for each row execute function public.sabi_identity_events_immutable();

-- 3. Consent as first-class records, not a JSON blob
create table if not exists public.sabi_consent_records (
  id              uuid primary key default gen_random_uuid(),
  student_id      uuid references public.sabi_students(id) on delete cascade,
  consent_type    text not null,
  status          text not null,
  method          text,
  language        text,
  collector       text,
  collector_role  text,
  evidence_path   text,
  evidence_sha256 text,
  granted_at      timestamptz,
  withdrawn_at    timestamptz,
  created_at      timestamptz not null default now()
);
alter table public.sabi_consent_records drop constraint if exists sabi_consent_type_chk;
alter table public.sabi_consent_records add constraint sabi_consent_type_chk
  check (consent_type in ('caregiver_consent','child_assent','audio_recording','training_use'));
alter table public.sabi_consent_records drop constraint if exists sabi_consent_status_chk;
alter table public.sabi_consent_records add constraint sabi_consent_status_chk
  check (status in ('granted','refused','withdrawn','pending'));
create index if not exists sabi_consent_records_student_idx on public.sabi_consent_records(student_id, consent_type);

-- 4. Canonical learner view: one row per resolvable child, PII kept separate
create or replace view public.sabi_learner_canonical as
select
  s.id                        as student_id,
  s.learner_key,
  coalesce(s.phone_e164, s.phone_number_normalized, s.phone_number) as phone_e164,
  s.phone_household_key,
  case when s.name_status in ('confirmed_repeat','confirmed_caregiver') then s.name end as verified_name,
  s.name_status,
  s.name_source,
  s.current_level,
  s.tarl_level,
  s.total_sessions,
  s.total_correct,
  s.total_wrong,
  (select count(*) from public.sabi_consent_records c
     where c.student_id = s.id and c.status = 'granted') as consents_granted,
  (select bool_and(c.status = 'granted') from public.sabi_consent_records c
     where c.student_id = s.id
       and c.consent_type in ('caregiver_consent','child_assent')) as pilot_ready,
  s.created_at,
  s.updated_at
from public.sabi_students s
where s.merged_into is null;

-- 5. Backfill provenance for what already exists (no key churn, no name edits)
update public.sabi_students s
set phone_e164 = coalesce(s.phone_e164, s.phone_number_normalized, s.phone_number),
    name_status = case
      when s.name is null or btrim(s.name) = '' then 'unknown'
      when lower(btrim(s.name)) in ('a speech','what the','uhhh','already','and how','qu significa','ja mann','ja mann','what the heck','alem sasi','alem saci','my name','hello','sabi') then 'rejected_artifact'
      else 'unverified_utterance' end,
    name_source = coalesce(s.name_source, case when s.browser_id is not null then 'web_form' else 'phone_stt' end)
where s.name_source is null or s.phone_e164 is null;

commit;

-- 6. Import consent already recorded in consent_state JSON as real records (idempotent)
insert into public.sabi_consent_records (student_id, consent_type, status, method, created_at)
select s.id, t.ctype,
  case
    when t.ctype = 'caregiver_consent' and s.consent_state->>'caregiver_consent_recorded' = 'true' then 'granted'
    when t.ctype = 'child_assent'      and s.consent_state->>'child_assent_recorded'      = 'true' then 'granted'
    when t.ctype = 'training_use'      and s.consent_state->>'training_audio_consent_recorded' = 'true' then 'granted'
    else 'pending'
  end,
  'imported_from_consent_state', now()
from public.sabi_students s
cross join (values ('caregiver_consent'), ('child_assent'), ('audio_recording'), ('training_use')) as t(ctype)
where not exists (
  select 1 from public.sabi_consent_records c
  where c.student_id = s.id and c.consent_type = t.ctype
);
