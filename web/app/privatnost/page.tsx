'use client';

import InfoPage from '@/components/InfoPage';
import { useApp } from '@/components/AppContext';
import { CONTACT_EMAIL } from '@/lib/config';
import { EVENT } from '@/lib/event';

/** Privacy notice: what the site does with runners' data. */
export default function PrivacyPage() {
  const { lang } = useApp();
  const mail = <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>;

  if (lang === 'en') {
    return (
      <InfoPage title="Privacy policy">
        <h2>Who we are</h2>
        <p>
          This site publishes the official photographs of {EVENT.nameEn || EVENT.name}. Contact: {mail}.
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
          You search with your bib number only. The site limits the number of searches per IP address and sets a
          short-lived session cookie
          (30 minutes) that is needed for searching. Your language choice is kept in your browser. We use no
          analytics or advertising cookies.
        </p>

        <h2>Your rights</h2>
        <p>
          You can ask for access to, correction or deletion of your data, or object to its use. To have a photo
          removed, write to {mail} with your bib number and the photo you mean.
        </p>
      </InfoPage>
    );
  }

  return (
    <InfoPage title="Pravila privatnosti">
      <h2>Tko smo</h2>
      <p>
        Ova stranica objavljuje službene fotografije utrke {EVENT.name}. Kontakt: {mail}.
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
        Pretražuje se samo startnim brojem. Stranica ograničava broj pretraga po IP adresi i postavlja kratkotrajni
        kolačić sesije (30 minuta)
        koji je nužan za pretragu. Odabrani jezik pamti se u vašem pregledniku. Ne koristimo kolačiće za analitiku ni
        oglašavanje.
      </p>

      <h2>Vaša prava</h2>
      <p>
        Možete zatražiti pristup svojim podacima, njihov ispravak ili brisanje, ili prigovoriti njihovoj uporabi. Za
        uklanjanje fotografije pišite na {mail} i navedite svoj startni broj i o kojoj je fotografiji riječ.
      </p>
    </InfoPage>
  );
}
