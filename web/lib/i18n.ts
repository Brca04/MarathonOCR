/**
 * Every string the interface can show, in both languages. Croatian is the
 * default — this is a Zagreb race — and English is what the switch in the
 * header flips to. Anything with a number in it is a function so the caller
 * passes the value rather than the string being glued together at the call
 * site, which is what makes Croatian plurals possible at all.
 */

export type Lang = 'hr' | 'en';

export const LANGS: Lang[] = ['hr', 'en'];

/** Croatian has three number forms: 1 (also 21, 31…), 2–4, and 5+. */
function hrPlural(n: number, [one, few, many]: [string, string, string]): string {
  const mod10 = Math.abs(n) % 10;
  const mod100 = Math.abs(n) % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

export const LOCALE: Record<Lang, string> = { hr: 'hr-HR', en: 'en-GB' };

/** Locale-aware number: 6.214 / 42,195 in Croatian, 6,214 / 42.195 in English. */
export function num(lang: Lang, value: number, digits = 0): string {
  return value.toLocaleString(LOCALE[lang], {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/**
 * Course points and race names arrive from the data (Postgres or the demo
 * event) already written in Croatian, so they are mapped rather than looked up.
 * Anything unrecognised — a point some photographer typed — passes through.
 */
const DATA_EN: Record<string, string> = {
  Polovica: 'Half',
  Cilj: 'Finish',
  Maraton: 'Marathon',
  Polumaraton: 'Half marathon',
  'Utrka 10 km': '10K run',
};

export function dataTerm(lang: Lang, value: string | null | undefined): string {
  if (!value) return '';
  return lang === 'hr' ? value : (DATA_EN[value] ?? value);
}

export type Strings = {
  lang: Lang;
  navHome: string;
  navOfficial: string;
  heroAlt: string;
  statFinishers: (year: number) => string;
  statFirstEdition: string;
  statKm: string;
  statRecord: string;
  footerRights: string;
  footerPrivacy: string;
  footerPhotographers: string;
  footerContact: string;
  langLabel: string;
  searchEyebrow: string;
  searchTitle: string;
  searchSub: string;
  bibLabel: string;
  consentPrefix: string;
  consentLinkText: string;
  consentSuffix: string;
  searchSubmit: string;
  searchBusy: string;
  credits: string;
  raceMarathon: string;
  raceHalf: string;
  race10k: string;
  errNoBib: string;
  errOffline: string;
  errUnknownBib: (bib: string) => string;
  errNoEvent: string;
  errGeneric: string;
  toastZip: string;
  toastUnlockedAll: string;
  toastPurchased: string;
  toastOriginal: (dims: string) => string;
  toastPreview: string;
  finishTime: string;
  pace: string;
  place: string;
  /** ["11 fotografija", "s 7 točaka na stazi"] — the second half is set muted. */
  /** "Pronađeno je 11 vaših fotografija" — the gallery's only heading. */
  photosFound: (n: number) => string;
  backToSearch: string;
  backToTop: string;
  downloadAll: string;
  unlockAll: (price: number) => string;
  noPhotos: (bib: string) => string;
  openPhoto: (point: string, clock: string) => string;
  viewer: string;
  close: string;
  prevPhoto: string;
  nextPhoto: string;
  photoBy: string;
  unknown: string;
  readAs: (read: string) => string;
  downloadOriginal: string;
  downloadPreview: string;
  buyOriginal: (price: number) => string;
  redirectLink: string;
  metaTitle: string;
  metaDescription: string;
  /** Track marks under the runner hero, start → finish. */
  trackMarks: (raceCode: string) => string[];
};

const hr: Strings = {
  lang: 'hr',
  navHome: 'Zagrebački maraton, početna',
  navOfficial: 'Službene fotografije',
  heroAlt: 'Trkači na stazi Zagrebačkog maratona',
  statFinishers: (year) => `Završilo ${year}.`,
  statFirstEdition: 'Prvo izdanje',
  statKm: 'Kilometara',
  statRecord: 'Rekord staze',
  footerRights: '© 2026. Zagrebački maraton · Službena fotografija utrke',
  footerPrivacy: 'Privatnost',
  footerPhotographers: 'Fotografi',
  footerContact: 'Kontakt',
  langLabel: 'Jezik',
  searchEyebrow: 'Pretraga fotografija',
  searchTitle: 'Unesite svoj startni broj',
  searchSub: 'Broj koji ste nosili na utrci.',
  bibLabel: 'Startni broj',
  consentPrefix: 'Slažem se s ',
  consentLinkText: 'pravilima privatnosti',
  consentSuffix: '.',
  searchSubmit: 'Pronađi moje fotografije',
  searchBusy: 'Tražim…',
  credits: 'Omogućili SklopIT i FramePaceMedia',
  raceMarathon: 'Maraton · 42,195 km',
  raceHalf: 'Polumaraton · 21,1 km',
  race10k: 'Utrka · 10 km',
  errNoBib: 'Unesite broj koji ste nosili na utrci.',
  errOffline: 'Rezultati trenutačno nisu dostupni. Pokušajte ponovno za koji trenutak.',
  errUnknownBib: (bib) => `Nema trkača sa startnim brojem ${bib} u ovom izdanju.`,
  errNoEvent: 'Fotografije za ovu utrku još nisu objavljene.',
  errGeneric: 'Nešto je pošlo po zlu. Pokušajte ponovno.',
  toastZip: 'Preuzimanje fotografija je počelo…',
  toastUnlockedAll: 'Sve fotografije otključane',
  toastPurchased: 'Kupljeno — original otključan',
  toastOriginal: (dims) => `Preuzimam original (${dims})…`,
  toastPreview: 'Preuzimam pregled s vodenim žigom…',
  finishTime: 'Ciljno vrijeme',
  pace: 'Tempo',
  place: 'Plasman',
  photosFound: (n) => {
    // The verb agrees with the number, the way it does when spoken.
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return `Pronađena je ${n} vaša fotografija`;
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14))
      return `Pronađene su ${n} vaše fotografije`;
    return `Pronađeno je ${n} vaših fotografija`;
  },
  backToSearch: 'Početna',
  backToTop: 'Na vrh',
  downloadAll: 'Preuzmi sve',
  unlockAll: (price) => `Otključaj sve · ${price} €`,
  noPhotos: (bib) =>
    `Zasad nema fotografija označenih startnim brojem ${bib}. Fotografije se dodaju kako ih fotografi učitavaju i kako se brojevi očitavaju — provjerite ponovno kasnije tijekom dana.`,
  openPhoto: (point, clock) => `Otvori fotografiju ${point} ${clock}`,
  viewer: 'Pregled fotografija',
  close: 'Zatvori',
  prevPhoto: 'Prethodna fotografija',
  nextPhoto: 'Sljedeća fotografija',
  photoBy: 'Foto:',
  unknown: 'Nepoznato',
  readAs: (read) => `očitano kao ${read}`,
  downloadOriginal: 'Preuzmi',
  downloadPreview: 'Preuzmi pregled',
  buyOriginal: (price) => `Kupi original · ${price} €`,
  redirectLink: 'Nastavi na pretragu fotografija',
  metaTitle: '34. Zagrebački maraton · Službene fotografije',
  metaDescription:
    'Pronađite svoje fotografije s utrke prema startnom broju. Službena fotografija 34. Zagrebačkog maratona.',
  trackMarks: (raceCode) =>
    raceCode === 'marathon'
      ? ['Start', '10K', 'Polovica', '30K', 'Cilj']
      : raceCode === 'half'
        ? ['Start', '5K', '10K', '15K', 'Cilj']
        : ['Start', '2,5K', '5K', '7,5K', 'Cilj'],
};

const en: Strings = {
  lang: 'en',
  navHome: 'Zagreb Marathon, home',
  navOfficial: 'Official photo',
  heroAlt: 'Runners on the Zagreb marathon course',
  statFinishers: (year) => `Finishers ${year}`,
  statFirstEdition: 'First edition',
  statKm: 'Kilometres',
  statRecord: 'Course record',
  footerRights: '© 2026 Zagrebački maraton · Official race photography',
  footerPrivacy: 'Privacy',
  footerPhotographers: 'Photographers',
  footerContact: 'Contact',
  langLabel: 'Language',
  searchEyebrow: 'Photo search',
  searchTitle: 'Enter your bib number',
  searchSub: 'The number printed on your race bib.',
  bibLabel: 'Bib number',
  consentPrefix: 'I agree to the ',
  consentLinkText: 'Privacy Policy',
  consentSuffix: '.',
  searchSubmit: 'Find my photos',
  searchBusy: 'Searching…',
  credits: 'Made by SklopIT and FramePaceMedia',
  raceMarathon: 'Marathon · 42.195 km',
  raceHalf: 'Half marathon · 21.1 km',
  race10k: 'Run · 10 km',
  errNoBib: 'Enter the number printed on your bib.',
  errOffline: 'Could not reach the results service. Try again in a moment.',
  errUnknownBib: (bib) => `No runner with bib ${bib} in this edition.`,
  errNoEvent: 'Photos for this event are not published yet.',
  errGeneric: 'Something went wrong. Try again.',
  toastZip: 'Downloading your photos…',
  toastUnlockedAll: 'All photos unlocked',
  toastPurchased: 'Purchased — original unlocked',
  toastOriginal: (dims) => `Downloading original (${dims})…`,
  toastPreview: 'Downloading watermarked preview…',
  finishTime: 'Finish time',
  pace: 'Pace',
  place: 'Place',
  photosFound: (n) => `Found ${n} photo${n === 1 ? '' : 's'} of you`,
  backToSearch: 'Home',
  backToTop: 'Back to top',
  downloadAll: 'Download all originals',
  unlockAll: (price) => `Unlock all · €${price}`,
  noPhotos: (bib) =>
    `No photos are tagged with bib ${bib} yet. Photos are added as the photographers upload and the numbers are read — check back later in the day.`,
  openPhoto: (point, clock) => `Open photo ${point} ${clock}`,
  viewer: 'Photo viewer',
  close: 'Close',
  prevPhoto: 'Previous photo',
  nextPhoto: 'Next photo',
  photoBy: 'Photo by',
  unknown: 'Unknown',
  readAs: (read) => `read as ${read}`,
  downloadOriginal: 'Download original',
  downloadPreview: 'Download preview',
  buyOriginal: (price) => `Buy original · €${price}`,
  redirectLink: 'Continue to the photo search',
  metaTitle: '34th Zagreb Marathon · Official photo',
  metaDescription:
    'Find your race photos by bib number. Official photography of the 34th Zagreb Marathon.',
  trackMarks: (raceCode) =>
    raceCode === 'marathon'
      ? ['Start', '10K', 'Half', '30K', 'Finish 42.195']
      : raceCode === 'half'
        ? ['Start', '5K', '10K', '15K', 'Finish 21.1']
        : ['Start', '2.5K', '5K', '7.5K', 'Finish 10'],
};

export const STRINGS: Record<Lang, Strings> = { hr, en };
