-- OPTIONAL. The runner card shows the official gun time (finish_time) by default.
-- Run this once in the Supabase SQL editor if you would rather show chip (net) time;
-- pace then follows the same time. Placings stay as the organiser ranked them (gun time).
-- After running it, rebuild the site:  cd web && node scripts/publish-event.mjs
-- Undo: swap the two replace() pairs below and run it again.
do $mig$
declare
  d text;
  n text;
begin
  select pg_get_functiondef('public.find_runner(text,text,date)'::regprocedure) into d;
  n := replace(d, $a$to_char(v_runner.finish_time, 'FMHH24:MI:SS')$a$,
                  $a$to_char(coalesce(v_runner.chip_time, v_runner.finish_time), 'FMHH24:MI:SS')$a$);
  n := replace(n, $a$public.runner_pace(v_runner.finish_time,$a$,
                  $a$public.runner_pace(coalesce(v_runner.chip_time, v_runner.finish_time),$a$);
  if n = d then
    raise exception 'find_runner did not look as expected (already changed?); nothing done';
  end if;
  execute n;
end
$mig$;
