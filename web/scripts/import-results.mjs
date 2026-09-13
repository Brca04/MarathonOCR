#!/usr/bin/env node
/**
 * Import a timing-company results CSV into `runners`.
 *
 *   node scripts/import-results.mjs --csv ../results.csv
 *   node scripts/import-results.mjs --csv results.csv --dry-run
 *   node scripts/import-results.mjs --csv results.csv --date-order mdy
 *   node scripts/import-results.mjs --csv results.csv --map bib=StartNo,dob=Born
 *
 * Column names are matched against a list of aliases (English and Croatian),
 * so most exports import with no flags at all. `--map` overrides one field when
 * the header is something unexpected; `--dry-run` prints the first rows and the
 * column mapping it inferred without writing anything.
 */
import { parse } from 'csv-parse/sync';
import {
  admin,
  args,
  DEFAULT_SLUG,
  die,
  digits,
  ensureEvent,
  log,
  normaliseRow,
  parseDate,
  parseDuration,
  parseInt0,
  pick,
  raceCodeFrom,
  readCsv,
  statusFrom,
  upsertBatched,
} from './lib.mjs';

const FIELDS = {
  bib: ['bib', 'bib_number', 'bibnumber', 'bibno', 'number', 'no', 'startno', 'start_number',
        'startnumber', 'broj', 'startni_broj', 'st_br', 'stbr'],
  dob: ['dob', 'birthdate', 'birth_date', 'dateofbirth', 'date_of_birth', 'born', 'birthday',
        'datum_rodenja', 'datum_rodjenja', 'datumrodjenja', 'rodjen', 'geburtsdatum'],
  birth_year: ['birthyear', 'birth_year', 'yob', 'year_of_birth', 'godina', 'godina_rodenja'],
  full_name: ['name', 'full_name', 'fullname', 'runner', 'athlete', 'imeiprezime', 'ime_i_prezime',
              'participant'],
  first_name: ['firstname', 'first_name', 'given_name', 'ime', 'vorname'],
  last_name: ['lastname', 'last_name', 'surname', 'family_name', 'prezime', 'nachname'],
  gender: ['gender', 'sex', 'spol', 'm_f', 'mf', 'kat_spol'],
  category: ['category', 'cat', 'kategorija', 'agegroup', 'age_group', 'ag', 'class', 'klasa'],
  club: ['club', 'klub', 'team', 'tim', 'ekipa', 'society'],
  nationality: ['nationality', 'nat', 'country', 'nacionalnost', 'drzava', 'ctry', 'noc'],
  race: ['race', 'distance', 'event', 'discipline', 'disciplina', 'trka', 'dionica', 'staza'],
  finish_time: ['finish_time', 'finishtime', 'chip_time', 'chiptime', 'net_time', 'nettime',
                'gun_time', 'guntime', 'official_time', 'time', 'result', 'rezultat', 'vrijeme',
                'ukupno'],
  chip_time: ['chip_time', 'chiptime', 'net_time', 'nettime', 'neto'],
  place_overall: ['place', 'rank', 'position', 'pos', 'overall', 'overall_place', 'mjesto',
                  'plasman', 'ukupno_mjesto'],
  place_gender: ['gender_place', 'place_gender', 'genderrank', 'mjesto_spol'],
  place_category: ['category_place', 'place_category', 'cat_place', 'catplace', 'agrank',
                   'mjesto_kategorija', 'kategorija_mjesto', 'mjesto u kategoriji',
                   'plasman_kategorija'],
  status: ['status', 'finished', 'dnf'],
};

const a = args();
if (!a.csv) {
  die('Pass --csv <path to results csv>. Use --dry-run first to check the mapping.');
}
const slug = a.event || DEFAULT_SLUG;
const dateOrder = a['date-order'] === 'mdy' ? 'mdy' : 'dmy';
const dryRun = Boolean(a['dry-run']);

// --map bib=StartNo,dob=Born
const overrides = {};
if (typeof a.map === 'string') {
  for (const pair of a.map.split(',')) {
    const [k, v] = pair.split('=');
    if (k && v) overrides[k.trim()] = [v.trim()];
  }
}
const aliasesFor = (field) => [...(overrides[field] ?? []), ...(FIELDS[field] ?? [])];

log.step(`Reading ${a.csv}`);
const text = readCsv(a.csv);
const delimiter = (text.split('\n')[0].match(/;/g) || []).length > 1 ? ';' : ',';
const records = parse(text, {
  columns: true,
  skip_empty_lines: true,
  relax_column_count: true,
  bom: true,
  trim: true,
  delimiter,
}).map(normaliseRow);

if (!records.length) die('No data rows found.');
log.info(`${records.length} rows, delimiter "${delimiter}"`);

// Report what mapped, so a wrong guess is visible before anything is written.
log.step('Column mapping');
const headers = Object.keys(records[0]);
for (const field of Object.keys(FIELDS)) {
  const hit = aliasesFor(field).map((x) => x.replace(/[^a-z0-9]/g, '')).find((k) => headers.includes(k));
  log.info(`${field.padEnd(15)} ${hit ? `→ ${hit}` : '— not found'}`);
}

const rows = [];
const problems = [];

for (const [i, row] of records.entries()) {
  const bib = digits(pick(row, aliasesFor('bib')));
  if (!bib) {
    problems.push(`row ${i + 2}: no bib`);
    continue;
  }

  let name = pick(row, aliasesFor('full_name'));
  if (!name) {
    const first = pick(row, aliasesFor('first_name'));
    const last = pick(row, aliasesFor('last_name'));
    name = [first, last].filter(Boolean).join(' ');
  }
  if (!name) {
    problems.push(`row ${i + 2} (bib ${bib}): no name`);
    continue;
  }

  let dob = parseDate(pick(row, aliasesFor('dob')), dateOrder);
  if (!dob) {
    const y = parseInt0(pick(row, aliasesFor('birth_year')));
    // Year-only results cannot power the birthdate gate. Keep the runner, flag it.
    if (y) problems.push(`row ${i + 2} (bib ${bib}): birth year ${y} only, no full date`);
    else problems.push(`row ${i + 2} (bib ${bib}): unparseable birthdate`);
  }

  const raceText = pick(row, aliasesFor('race'));
  const rawStatus = pick(row, aliasesFor('status')) || pick(row, aliasesFor('finish_time'));

  rows.push({
    bib,
    dob,
    full_name: name,
    gender: (pick(row, aliasesFor('gender')).toUpperCase().match(/^[MFWŽ]/) || [''])[0]
      .replace('W', 'F')
      .replace('Ž', 'F') || null,
    category: pick(row, aliasesFor('category')) || null,
    club: pick(row, aliasesFor('club')) || null,
    nationality: pick(row, aliasesFor('nationality')).toUpperCase() || null,
    finish_time: parseDuration(pick(row, aliasesFor('finish_time'))),
    chip_time: parseDuration(pick(row, aliasesFor('chip_time'))),
    place_overall: parseInt0(pick(row, aliasesFor('place_overall'))),
    place_gender: parseInt0(pick(row, aliasesFor('place_gender'))),
    place_category: parseInt0(pick(row, aliasesFor('place_category'))),
    status: statusFrom(rawStatus),
    _race_code: raceCodeFrom(raceText, bib),
  });
}

// Duplicate bibs would silently collapse in the upsert; say so instead.
const seen = new Map();
for (const r of rows) {
  if (seen.has(r.bib)) problems.push(`duplicate bib ${r.bib} — later row wins`);
  seen.set(r.bib, r);
}

log.step('Parsed');
log.info(`${rows.length} runners, ${new Set(rows.map((r) => r._race_code)).size} race(s)`);
log.info(`with a full birthdate: ${rows.filter((r) => r.dob).length}/${rows.length}`);
log.info(`with a finish time:    ${rows.filter((r) => r.finish_time).length}/${rows.length}`);
if (problems.length) {
  log.warn(`${problems.length} issue(s):`);
  problems.slice(0, 15).forEach((p) => log.info(`  ${p}`));
  if (problems.length > 15) log.info(`  … and ${problems.length - 15} more`);
}

console.log('\n  First three rows as they will be stored:');
console.table(
  rows.slice(0, 3).map(({ _race_code, ...r }) => ({ ..._sample(r), race: _race_code })),
);
function _sample(r) {
  return {
    bib: r.bib,
    name: r.full_name,
    dob: r.dob,
    cat: r.category,
    time: r.finish_time,
    place: r.place_overall,
  };
}

if (dryRun) {
  log.step('Dry run — nothing written.');
  process.exit(0);
}

const db = admin();
const { event, races } = await ensureEvent(db, slug);
log.step(`Writing to event ${slug}`);

const payload = rows.map(({ _race_code, ...r }) => ({
  ...r,
  event_id: event.id,
  race_id: races[_race_code]?.id ?? null,
}));

const n = await upsertBatched(db, 'runners', payload, 'event_id,bib');
log.ok(`${n} runners imported`);
log.info('Next: node scripts/import-bibs.mjs --csv "bib_export.csv" --photos <folder>');
