export type RaceCode = 'marathon' | 'half' | '10k';

export type EventStats = {
  ok: boolean;
  name: string;
  edition: number | null;
  race_date: string | null;
  city: string | null;
  first_year: number | null;
  finishers: number;
  photos: number;
  tagged_bibs: number;
  distance_km: number | null;
  course_record: string | null;
};

export type Runner = {
  bib: string;
  name: string;
  category: string | null;
  club: string | null;
  nationality: string | null;
  race: string;
  race_code: RaceCode | string;
  distance_km: number;
  status: string;
  /** "3:24:17" */
  time: string | null;
  /** "4:51" per km */
  pace: string | null;
  place_overall: number | null;
  place_category: number | null;
};

export type PhotoMatch = {
  id: string;
  file_name: string;
  preview_path: string | null;
  /** Small grid image; the gallery falls back to the preview. */
  thumb_path?: string | null;
  original_path?: string | null;
  width: number | null;
  height: number | null;
  captured_at: string | null;
  photographer: string | null;
  course_point: string | null;
  course_km: number | null;
  /** 'exact' when a detection read the bib verbatim, 'fuzzy' when one edit away. */
  match_kind: 'exact' | 'fuzzy';
  match_score: number;
  /** What the recognizer actually read — useful when match_kind is 'fuzzy'. */
  read_as: string;
};

export type FindRunnerResult =
  | { ok: true; runner: Runner; photos: PhotoMatch[] }
  | { ok: false; reason: 'missing_input' | 'no_event' | 'no_bib' | 'dob_mismatch' | 'rate_limited' };

/** A photo with a resolved, displayable URL and a clock label. */
export type GalleryPhoto = PhotoMatch & {
  src: string;
  thumb: string;
  clock: string;
  hint: string;
  dims: string;
  ratio: string;
};
