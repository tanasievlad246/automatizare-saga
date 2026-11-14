# Cum obțineți Client ID și Client Secret de la ANAF

Programul are nevoie de două chei de la ANAF ca să poată descărca facturile din e-Factura: **Client ID** și **Client Secret**. Ele se obțin o singură dată, de pe site-ul ANAF, și se scriu în program pe pagina „Chei și parole”.

Aceste două chei identifică **programul**, nu firmele. O singură pereche ajunge pentru toți clienții dumneavoastră. Ce firme puteți vedea hotărăște certificatul digital cu care vă conectați apoi la ANAF.

Durează cam zece minute.

## Ce vă trebuie înainte

- **Un certificat digital calificat** (tokenul USB), înregistrat în SPV cu unul dintre drepturile pentru persoane juridice: reprezentant legal, reprezentant desemnat sau împuternicit. Dacă intrați deja în SPV cu tokenul pentru firmele clienților, îl aveți. Înregistrarea în SPV se face la <https://www.anaf.ro/InregPersFizicePublic/#tabs-2>.
- **O adresă de e-mail** la care aveți acces chiar atunci. ANAF trimite pe ea un cod de verificare.

## Pasul 1 — Vă înregistrați pentru API-uri

1. Deschideți <https://www.anaf.ro/InregOauth>.
   Ajungeți în același loc și de pe <https://anaf.ro>: **Servicii Online** → **Înregistrare utilizatori** → **Înregistrare pentru API-uri**.
2. Alegeți situația în care sunteți:
   - **Nu aveți cont pe portalul ANAF, sau aveți un cont cu certificat digital:** mergeți pe „Creare cont nou de utilizator”.
   - **Aveți un cont cu nume de utilizator și parolă:** mergeți pe „Înregistrare cu un cont existent de portal/SPV”.
3. Completați datele cerute în formular și apăsați **Continuă**.
4. Primiți pe e-mail un cod. Scrieți-l la **Cod de verificare** și apăsați din nou **Continuă**.
5. Apare mesajul că înregistrarea a reușit.

## Pasul 2 — Intrați în „Editare profil Oauth”

1. Apăsați **Autentificare utilizator**.
2. Scrieți numele de utilizator și parola și apăsați **Autentificare**.
   Dacă ați uitat parola, folosiți „Recuperare credențiale/parolă”; vi se cer CNP-ul și adresa de e-mail.
3. Din meniu alegeți **Editare profil Oauth**.

## Pasul 3 — Înregistrați programul și generați cheile

În „Editare profil Oauth”, la **Gestionare aplicații**, completați:

| Câmpul | Ce scrieți |
|---|---|
| Denumirea aplicației | Orice nume, de exemplu `e-Factura pentru SAGA` |
| Serviciul | **E-Factura** |
| Callback URL | `https://localhost/callback` |

Apoi apăsați **Generare Client ID**.

Aplicația apare în listă. **Dați clic pe rândul ei**: se afișează Grant Type, Callback URL, Auth URL, **Client ID** și **Client Secret**. Pe ultimele două le copiați în program. Le puteți vedea din nou oricând, tot de aici.

> **Atenție la Callback URL.** Trebuie scris exact așa: `https://localhost/callback`, cu `https` și fără niciun spațiu. Programul trimite la ANAF aceeași adresă, iar dacă cele două diferă chiar și cu o literă, conectarea nu merge.
>
> La această adresă nu există nicio pagină. Este normal: programul are nevoie doar de adresa pe care o afișează browserul după conectare.

## Pasul 4 — Scrieți cheile în program

1. Deschideți programul și mergeți la **Chei și parole**.
2. La **ANAF — Client ID** apăsați **Modifică**, lipiți valoarea și apăsați **Salvează**.
3. Faceți la fel la **ANAF — Client Secret**.

## Pasul 5 — Vă conectați la ANAF

1. Introduceți tokenul USB în calculator.
2. În bara de sus a programului apăsați **Conectați-vă la ANAF**.
3. Apăsați **Conectează-mă cu certificatul**. Windows vă arată certificatele: alegeți-l pe al dumneavoastră, apoi scrieți PIN-ul în fereastra tokenului. Fereastra poate apărea în spatele browserului; dacă nu o vedeți, uitați-vă în bara de jos a ecranului.

Atât: programul primește singur răspunsul de la ANAF.

**Dacă butonul „Conectează-mă cu certificatul” lipsește sau nu merge**, alegeți **Conectare prin browser** și urmați cei trei pași din fereastră: se deschide pagina ANAF, alegeți certificatul și scrieți PIN-ul. Browserul arată apoi o pagină de eroare („nu se poate accesa pagina”). **Este normal.** Copiați toată adresa din bara de adrese și lipiți-o în program, **în cel mult un minut**. Butonul cu certificatul există doar pe Windows.

După aceasta programul rămâne conectat și își reînnoiește singur accesul. Tokenul USB și PIN-ul sunt necesare din nou cam o dată pe an: cheia de acces ține 90 de zile, iar cea de reînnoire 365 de zile.

## Dacă ceva nu merge

- **Ați greșit Callback URL sau serviciul.** Procedura ANAF nu descrie modificarea unei aplicații, doar ștergerea ei. În „Editare profil Oauth” alegeți **Renunțare Oauth**, selectați aplicația și apăsați **Șterge aplicația**. Apoi înregistrați-o din nou la Pasul 3 și scrieți în program cheile noi.
- **ANAF spune că nu aveți drepturi pentru o firmă.** Certificatul cu care v-ați conectat nu are drepturi în SPV pentru acea firmă. Cheile sunt bune; lipsește împuternicirea în SPV.
- **ANAF a refuzat certificatul („access_denied”).** ANAF răspunde așa când nu primește niciun certificat. De obicei browserul nu a arătat fereastra de alegere a certificatului, deci nu a trimis nimic. Ce faceți:
  1. Verificați că tokenul USB este introdus în calculator.
  2. Pe Windows, folosiți **Conectează-mă cu certificatul** din fereastra „Conectare la ANAF”. Programul cere certificatul direct de la Windows, fără browser.
  3. Dacă ANAF refuză și așa, apăsați **Încearcă din nou**. La o probă, a doua încercare a mers fără nicio altă schimbare.
  4. Dacă tot nu merge, intrați în SPV cu același certificat. Dacă nici acolo nu merge, problema este la certificat sau la token, nu la program.
- **ANAF răspunde cu `invalid_client`.** Client ID-ul scris în program nu este cel dat de ANAF. Copiați-l din nou de la ANAF (Pasul 3) și scrieți-l în program (Pasul 4).
- **ANAF răspunde cu `invalid_request` și cu textul „Redirect-URI … does not match”.** Callback URL de la ANAF diferă de adresa pe care o trimite programul, `https://localhost/callback`. Vedeți mai sus „Ați greșit Callback URL sau serviciul”.
- **Ați lipit adresa prea târziu.** Codul din adresă ține cam un minut și merge o singură dată. Apăsați din nou **Conectați-vă la ANAF** și repetați Pasul 5.
- **Aveți nevoie de ajutor de la ANAF.** Folosiți Formularul de contact de pe anaf.ro, categoria „Asistență tehnică servicii informatice”, subcategoria „OAUTH”.

## Păstrați cheile în siguranță

Nu trimiteți nimănui Client Secret și nu îl puneți în e-mailuri sau capturi de ecran. Dacă bănuiți că a ajuns la altcineva, ștergeți aplicația de la ANAF (vezi mai sus) și înregistrați una nouă.

## De unde sunt acești pași

Din procedura ANAF „Înregistrare aplicații profil OAUTH”, citită la 14 noiembrie 2026:
<https://static.anaf.ro/static/10/Anaf/Informatii_R/API/Oauth_procedura_inregistrare_aplicatii_portal_ANAF.pdf>

Numele butoanelor și ale meniurilor sunt cele din acel document. Dacă ANAF își schimbă site-ul, ele pot arăta altfel; documentul de mai sus are și capturi de ecran.

Răspunsurile ANAF de la „Dacă ceva nu merge” sunt cele primite la o probă pe un calculator cu Windows, la 15 noiembrie 2026.
