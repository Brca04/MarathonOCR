'use client';

import InfoPage from '@/components/InfoPage';
import { useApp } from '@/components/AppContext';
import { CONTACT_EMAIL, ORGANIZER_URL } from '@/lib/config';

/** Who to write to about photos, removals, results and the service itself. */
export default function ContactPage() {
  const { lang } = useApp();
  const mail = <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>;
  const organizer = ORGANIZER_URL ? <a href={ORGANIZER_URL}>{ORGANIZER_URL.replace(/^https?:\/\//, '').replace(/\/$/, '')}</a> : null;

  if (lang === 'en') {
    return (
      <InfoPage title="Contact">
        <h2>Photos and removal requests</h2>
        <p>
          Missing a photo, found someone else's, or want a photo of you removed? Write to {mail} with your bib number
          and the photo you mean.
        </p>

        <h2>Results and the race</h2>
        <p>
          Times and placings come from the official timing provider. For questions about results or the race itself,
          contact the race organiser{organizer ? <>: {organizer}</> : '.'}
        </p>

        <h2>The service</h2>
        <p>The photo search is made by Sklop. For cooperation or technical questions: {mail}.</p>
      </InfoPage>
    );
  }

  return (
    <InfoPage title="Kontakt">
      <h2>Fotografije i uklanjanje fotografija</h2>
      <p>
        Nedostaje vam fotografija, pronašli ste tuđu ili želite ukloniti svoju? Pišite na {mail} i navedite svoj startni
        broj i o kojoj je fotografiji riječ.
      </p>

      <h2>Rezultati i utrka</h2>
      <p>
        Vremena i plasmani dolaze od službenog mjeritelja vremena. Za pitanja o rezultatima ili samoj utrci obratite se
        organizatoru utrke{organizer ? <>: {organizer}</> : '.'}
      </p>

      <h2>O usluzi</h2>
      <p>Pretragu fotografija izradio je Sklop. Za suradnju ili tehnička pitanja: {mail}.</p>
    </InfoPage>
  );
}
