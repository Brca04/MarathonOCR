'use client';

import InfoPage from '@/components/InfoPage';
import { useApp } from '@/components/AppContext';
import { CONTACT_EMAIL } from '@/lib/config';
import { EVENT } from '@/lib/event';

/**
 * Privacy notice (GDPR art. 13): who runs the site, what it processes and
 * why, who processes it for us, how long it is kept, and the visitor's rights,
 * including the complaint to AZOP. Keep the Croatian and English texts in step.
 */
export default function PrivacyPage() {
  const { lang } = useApp();
  const mail = <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>;
  const azop = (
    <a href="https://azop.hr" target="_blank" rel="noopener noreferrer">
      azop.hr
    </a>
  );

  if (lang === 'en') {
    return (
      <InfoPage title="Privacy policy">
        <h2>Who we are</h2>
        <p>
          This photo search for {EVENT.nameEn || EVENT.name} is run by Sklop, which is the controller of your
          personal data on this site. Contact: {mail}.
        </p>

        <h2>What data we use</h2>
        <ul>
          <li>Results from the official timing provider: name, bib number, category, club, nationality, time and placing.</li>
          <li>Photographs taken at the race by the event photographers, which may show you.</li>
          <li>The bib numbers found in each photo, which link a photo to a runner.</li>
          <li>Technical data from your visit: IP address, browser type and the time of the request.</li>
        </ul>

        <h2>Why, and on what basis</h2>
        <p>
          We use this data so that runners can find their own race photos and results by bib number. The legal
          basis is our legitimate interest, and the participants&apos; interest, in making the official race
          photos easy to find (Art. 6(1)(f) GDPR). Technical data is used only to run the site and protect it from
          abuse and automated scraping.
        </p>

        <h2>How photos are matched</h2>
        <p>
          Bib numbers are read from the photos by computer vision and confirmed by a person. Photos where no bib
          was confirmed are not published. We do not use facial recognition and create no biometric data.
        </p>

        <h2>Who processes the data for us</h2>
        <ul>
          <li>
            <strong>Cloudflare</strong>: hosting of the site, photo storage (in the EU), bot protection
            (Turnstile) and cookie-free visitor statistics.
          </li>
          <li>
            <strong>Supabase</strong>: the database of results and bib numbers (in the EU, Ireland).
          </li>
          <li>
            <strong>Anthropic</strong>: an AI model that helped read bib numbers from the photos. Photos were sent
            only for that purpose; under its terms Anthropic does not use them to train its models.
          </li>
        </ul>
        <p>
          Some of these providers are based in the United States. Any transfer outside the EU is covered by the
          European Commission&apos;s standard contractual clauses or the EU-US Data Privacy Framework.
        </p>

        <h2>How long we keep it</h2>
        <ul>
          <li>Photos, bib numbers and results stay online for one month, until 16 November 2026, and are then deleted.</li>
          <li>Request logs with IP addresses are kept for up to 7 days.</li>
          <li>A photo you ask us to remove is taken down as soon as possible, within a few days at most.</li>
        </ul>

        <h2>Searching and cookies</h2>
        <p>
          You search with your bib number only. The site limits the number of searches per IP address and sets a
          short-lived session cookie (30 minutes) that is needed for searching. Your language choice is kept in your
          browser. Visitor statistics are counted without cookies. We use no advertising cookies.
        </p>

        <h2>Your rights</h2>
        <p>
          You can ask for access to your data, its correction or deletion, a restriction of its use, or object to
          its use. To have a photo removed, write to {mail} with your bib number and the photo you mean. If you
          believe we handle your data unlawfully, you can complain to the Croatian data protection authority,
          AZOP ({azop}).
        </p>

        <p style={{ color: 'var(--mute)', fontSize: 13 }}>Last updated: 16 October 2026.</p>
      </InfoPage>
    );
  }

  return (
    <InfoPage title="Pravila privatnosti">
      <h2>Tko smo</h2>
      <p>
        Pretragu fotografija utrke {EVENT.name} vodi Sklop, koji je voditelj obrade vaših osobnih podataka na ovoj
        stranici. Kontakt: {mail}.
      </p>

      <h2>Koje podatke koristimo</h2>
      <ul>
        <li>Rezultate službenog mjeritelja vremena: ime, startni broj, kategoriju, klub, državljanstvo, vrijeme i plasman.</li>
        <li>Fotografije koje su na utrci snimili fotografi utrke, na kojima se možete nalaziti.</li>
        <li>Startne brojeve pronađene na fotografijama, koji povezuju fotografiju s trkačem.</li>
        <li>Tehničke podatke o posjetu: IP adresu, vrstu preglednika i vrijeme zahtjeva.</li>
      </ul>

      <h2>Zašto i na kojoj osnovi</h2>
      <p>
        Podatke koristimo kako bi trkači po startnom broju mogli pronaći svoje fotografije i rezultat s utrke. Pravna
        osnova je naš legitimni interes, kao i interes sudionika, da službene fotografije utrke budu lako dostupne
        (čl. 6. st. 1. t. (f) GDPR-a). Tehničke podatke koristimo samo za rad stranice i zaštitu od zlouporabe i
        automatiziranog preuzimanja.
      </p>

      <h2>Kako povezujemo fotografije</h2>
      <p>
        Startne brojeve na fotografijama čita računalni vid, a potvrđuje ih čovjek. Fotografije na kojima nijedan
        broj nije potvrđen ne objavljujemo. Ne koristimo prepoznavanje lica i ne stvaramo biometrijske podatke.
      </p>

      <h2>Tko obrađuje podatke za nas</h2>
      <ul>
        <li>
          <strong>Cloudflare</strong>: smještaj stranice, pohrana fotografija (u EU), zaštita od botova (Turnstile) i
          statistika posjeta bez kolačića.
        </li>
        <li>
          <strong>Supabase</strong>: baza rezultata i startnih brojeva (u EU, Irska).
        </li>
        <li>
          <strong>Anthropic</strong>: model umjetne inteligencije koji je pomogao očitati startne brojeve s
          fotografija. Fotografije su mu poslane samo u tu svrhu; prema svojim uvjetima Anthropic ih ne koristi za
          treniranje modela.
        </li>
      </ul>
      <p>
        Neki od ovih pružatelja imaju sjedište u Sjedinjenim Američkim Državama. Svaki prijenos izvan EU-a pokriven je
        standardnim ugovornim klauzulama Europske komisije ili Okvirom za privatnost podataka EU-a i SAD-a.
      </p>

      <h2>Koliko dugo čuvamo podatke</h2>
      <ul>
        <li>Fotografije, startni brojevi i rezultati dostupni su mjesec dana, do 16. studenoga 2026., a zatim se brišu.</li>
        <li>Zapisi zahtjeva s IP adresama čuvaju se najviše 7 dana.</li>
        <li>Fotografiju koju zatražite ukloniti uklanjamo što prije, najkasnije u roku od nekoliko dana.</li>
      </ul>

      <h2>Pretraga i kolačići</h2>
      <p>
        Pretražuje se samo startnim brojem. Stranica ograničava broj pretraga po IP adresi i postavlja kratkotrajni
        kolačić sesije (30 minuta) koji je nužan za pretragu. Odabrani jezik pamti se u vašem pregledniku. Statistika
        posjeta broji se bez kolačića. Ne koristimo kolačiće za oglašavanje.
      </p>

      <h2>Vaša prava</h2>
      <p>
        Možete zatražiti pristup svojim podacima, njihov ispravak ili brisanje, ograničenje obrade ili prigovoriti
        njihovoj uporabi. Za uklanjanje fotografije pišite na {mail} i navedite svoj startni broj i o kojoj je
        fotografiji riječ. Ako smatrate da vaše podatke obrađujemo protivno propisima, možete podnijeti prigovor
        Agenciji za zaštitu osobnih podataka, AZOP ({azop}).
      </p>

      <p style={{ color: 'var(--mute)', fontSize: 13 }}>Zadnja izmjena: 16. listopada 2026.</p>
    </InfoPage>
  );
}
