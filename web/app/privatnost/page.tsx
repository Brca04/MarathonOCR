'use client';

import InfoPage from '@/components/InfoPage';
import { useApp } from '@/components/AppContext';
import { CONTACT_EMAIL } from '@/lib/config';
import { EVENT } from '@/lib/event';

/**
 * Privacy notice. A DRAFT that describes what the site actually does today;
 * the controller, retention period and legal review are still to be filled in
 * (see legal/PRIVACY_POLICY.md for the full template).
 */
export default function PrivacyPage() {
  const { lang } = useApp();
  const mail = <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>;

  if (lang === 'en') {
    return (
      <InfoPage kicker="Privacy" title="Privacy policy">
        <p data-info-draft="">Draft. This notice describes how the site works today and will be completed and reviewed before public launch.</p>

        <h2>Who we are</h2>
        <p>
          This site publishes the official photographs of {EVENT.nameEn || EVENT.name}. It is run by
          [controller name and address] together with Sklop and FramePaceMedia. Contact: {mail}.
        </p>

        <h2>What data we use</h2>
        <ul>
          <li>Results from the official timing provider: name, bib number, category, club, time and placing.</li>
          <li>Photographs taken at the race, which may show you.</li>
          <li>The bib numbers found in each photo, which link a photo to a runner.</li>
        </ul>

        <h2>How photos are matched</h2>
        <p>
          Bib numbers are read from the photos by computer vision and checked by a person against the start list.
          We do not use facial recognition and create no biometric data.
        </p>

        <h2>Searching</h2>
        <p>
          You search with your bib number only. To stop automated collection of the photos, the site uses
          Cloudflare Turnstile, limits the number of searches per IP address and sets a short-lived session cookie
          (30 minutes) that is needed for searching. Your language choice is kept in your browser. We use no
          analytics or advertising cookies.
        </p>

        <h2>Who processes the data</h2>
        <ul>
          <li>Cloudflare: website hosting, photo storage and protection against abuse.</li>
          <li>Supabase: database, hosted in the EU (Ireland).</li>
        </ul>

        <h2>How long we keep it</h2>
        <p>Photos and results are kept for [period] after the race and then deleted.</p>

        <h2>Your rights</h2>
        <p>
          You can ask for access to, correction or deletion of your data, or object to its use. To have a photo
          removed, write to {mail} with your bib number and the photo you mean. You can also complain to the
          Croatian data protection authority (AZOP, <a href="https://azop.hr">azop.hr</a>).
        </p>
      </InfoPage>
    );
  }

  return (
    <InfoPage kicker="Privatnost" title="Pravila privatnosti">
      <p data-info-draft="">Nacrt. Ova pravila opisuju kako stranica radi danas i bit će dovršena i pravno provjerena prije javnog pokretanja.</p>

      <h2>Tko smo</h2>
      <p>
        Ova stranica objavljuje službene fotografije utrke {EVENT.name}. Vodi je [naziv i adresa voditelja obrade]
        u suradnji s tvrtkama Sklop i FramePaceMedia. Kontakt: {mail}.
      </p>

      <h2>Koje podatke koristimo</h2>
      <ul>
        <li>Rezultate službenog mjeritelja vremena: ime, startni broj, kategoriju, klub, vrijeme i plasman.</li>
        <li>Fotografije snimljene na utrci, na kojima se možete nalaziti.</li>
        <li>Startne brojeve pronađene na fotografijama, koji povezuju fotografiju s trkačem.</li>
      </ul>

      <h2>Kako povezujemo fotografije</h2>
      <p>
        Startne brojeve na fotografijama čita računalni vid, a čovjek ih provjerava prema startnoj listi. Ne koristimo
        prepoznavanje lica i ne stvaramo biometrijske podatke.
      </p>

      <h2>Pretraga</h2>
      <p>
        Pretražuje se samo startnim brojem. Kako bismo spriječili automatsko preuzimanje fotografija, stranica koristi
        Cloudflare Turnstile, ograničava broj pretraga po IP adresi i postavlja kratkotrajni kolačić sesije (30 minuta)
        koji je nužan za pretragu. Odabrani jezik pamti se u vašem pregledniku. Ne koristimo kolačiće za analitiku ni
        oglašavanje.
      </p>

      <h2>Tko obrađuje podatke</h2>
      <ul>
        <li>Cloudflare: smještaj stranice, pohrana fotografija i zaštita od zlouporabe.</li>
        <li>Supabase: baza podataka, smještena u EU (Irska).</li>
      </ul>

      <h2>Koliko dugo čuvamo podatke</h2>
      <p>Fotografije i rezultati čuvaju se [razdoblje] nakon utrke, a zatim se brišu.</p>

      <h2>Vaša prava</h2>
      <p>
        Možete zatražiti pristup svojim podacima, njihov ispravak ili brisanje, ili prigovoriti njihovoj uporabi. Za
        uklanjanje fotografije pišite na {mail} i navedite svoj startni broj i o kojoj je fotografiji riječ. Pritužbu
        možete podnijeti i Agenciji za zaštitu osobnih podataka (AZOP, <a href="https://azop.hr">azop.hr</a>).
      </p>
    </InfoPage>
  );
}
