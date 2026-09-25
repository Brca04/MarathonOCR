'use client';

import InfoPage from '@/components/InfoPage';
import { useApp } from '@/components/AppContext';
import { CONTACT_EMAIL, ORGANIZER_URL } from '@/lib/config';
import { EVENT } from '@/lib/event';

/** Who to write to about photos, removals, results and the service itself. */
export default function ContactPage() {
  const { lang } = useApp();
  const mail = <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>;
  const organizer = ORGANIZER_URL ? <a href={ORGANIZER_URL}>{ORGANIZER_URL.replace(/^https?:\/\//, '').replace(/\/$/, '')}</a> : null;

  if (lang === 'en') {
    return (
      <InfoPage kicker="Contact" title="Contact">
        <h2>Photos and removal requests</h2>
        <p>
          Missing a photo, found someone else's, or want a photo of you removed? Write to {mail} with your bib number
          and the photo you mean. Removal requests are handled promptly.
        </p>

        <h2>Results and the race</h2>
        <p>
          Times and placings come from the official timing provider. For questions about results or the race itself,
          contact the organiser of {EVENT.nameEn || EVENT.name}{organizer ? <>: {organizer}</> : '.'}
        </p>

        <h2>The service</h2>
        <p>The photo search is made by Sklop and FramePaceMedia. For cooperation or technical questions: {mail}.</p>
      </InfoPage>
    );
  }

  return (
    <InfoPage kicker="Kontakt" title="Kontakt">
      <h2>Fotografije i uklanjanje fotografija</h2>
      <p>
        Nedostaje vam fotografija, pronašli ste tuđu ili želite ukloniti svoju? Pišite na {mail} i navedite svoj startni
        broj i o kojoj je fotografiji riječ. Zahtjeve za uklanjanje rješavamo brzo.
      </p>

      <h2>Rezultati i utrka</h2>
      <p>
        Vremena i plasmani dolaze od službenog mjeritelja vremena. Za pitanja o rezultatima ili samoj utrci obratite se
        organizatoru utrke {EVENT.name}{organizer ? <>: {organizer}</> : '.'}
      </p>

      <h2>O usluzi</h2>
      <p>Pretragu fotografija izradili su Sklop i FramePaceMedia. Za suradnju ili tehnička pitanja: {mail}.</p>
    </InfoPage>
  );
}
