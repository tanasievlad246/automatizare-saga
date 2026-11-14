# A demo setup, a rule test screen, the menu's foot, and login without the browser — design

Date: 2026-11-14. Builds on release 0.3.0.

## Why

Four things were asked for by the owner of the program:

1. **A development setup with made-up data** that works on Windows, macOS and Linux, with no ANAF account, token or OpenRouter key.
2. **A screen for testing the rules**: write a trial invoice, change it, and see how it would be classified by the rules and by Jev, and which rule would be proposed from it.
3. **A button that checks for a newer version**, visible in the page.
4. **A line with the version, the author's name and contact** on every screen.

A fifth came out of a real problem on the Windows PC (the browser never shows the certificate window, and ANAF answers `access_denied`):

5. **Connecting to ANAF without the browser**: the program asks Windows for the certificate itself.

## Who reads the screen

A Romanian accountant who is not at ease with computers. Every text on screen is Romanian, in the formal voice ("dumneavoastră"), with plain words instead of program words. Identifiers, comments, log lines and error messages of the program stay English. The screens below are drawn on the design canvas (https://claude.ai/artifact/VSxb2ocdWVd9UtMUcuWukH, artboards "Testează regulile", "Josul meniului și modul de probă", "Fereastra: Conectare la ANAF cu certificatul"); the texts quoted here are the ones on those artboards and are to be used as written.

## Goals, non-goals, anti-goals

**Goals**
- `uv run efactura demo` is the only command a developer needs to see every screen and every flow working.
- The rule test does exactly what the program does with a real invoice, and saves nothing but the cost of asking Jev.
- The version check and the author line are on every screen, at the foot of the menu.

**Non-goals**
- Docker, or any setup that is not `uv` (and `pnpm` for changing the page).
- Testing several trial invoices at once, saving trial invoices, or importing one from a file.
- Changing how real invoices are classified.

**Anti-goals** (these would make it a failure even if it works)
- Demo mode contacting the real ANAF or the real OpenRouter, or being on in an installed copy.
- A trial invoice appearing among a client's invoices, in SAGA's folder, or in the proposed rules.
- A Jev question asked from the rule test that costs money and is not shown under "Costuri Jev".
- The program reading, storing or logging the token's PIN.

## 1. Demo setup

**What it is.** `uv run efactura demo` builds a folder `demo/` (settings and a database of made-up clients, invoices, accounts and rules) if it is not there, and starts the program on it. `--fresh` builds it again from nothing. `--port N` as for `dev`. With `pnpm` present it runs as `efactura dev` does (the API restarting on change, the page's dev server); without it, it serves the built page and says so.

**How it is switched on, and what keeps it away from real data.** A new section in the settings file, `[demo]` with `enabled = true`, read into `Config.demo: bool` (default false). `config.example.toml` does not mention it. A line in a settings file is not enough by itself: the demo builder also leaves a marker file, `demo-data`, in the data folder it makes, and settings that ask for demo over a data folder without that marker are refused with a settings error. So a real database can never be put in demo mode, and made-up invoices can never be written among real ones. `efactura demo` only ever builds and uses the folder `demo/` inside the project; a `demo/` left by an earlier version (its settings do not say demo) is built again. The demo listens on port 8770, so it does not collide with a real copy on 8765.

**What stands in for the outside world.** When `Config.demo` is true, every `Service` is built with a stand-in HTTP client that answers for `logincert.anaf.ro`, `api.anaf.ro` and `openrouter.ai` and refuses every other host. The real ones are never contacted.

- *ANAF's list and downloads.* Each time the list is asked for a client, the stand-in has one or two new made-up received invoices for that client, dated now, taken in turn from a fixed catalogue of suppliers and lines. So every press of "Descarcă facturile" brings something. What it has handed out is kept in `demo/data/standin.json`, so it survives a restart and the reloads of the dev server.
- *The ANAF login.* "Deschide pagina ANAF" opens the program's own address `/api/demo/anaf-login` (reachable without the key, and only in demo), which sends the browser to `https://localhost/callback?code=demo-<number>`, as ANAF would. Nothing listens there, so the browser shows its error page and the address is pasted back, exactly as in the real flow. The stand-in accepts any code that starts with `demo-`.
- *Jev.* The stand-in answers from a table of words (the one the demo data is built with: "ciment" → 302 at 0.58, "hârtie" → 302 at 0.91, "pungi" → 302 at 0.93, "revizie" → 628 at 0.88), anything else → 628 at 0.95, cost 0.00002 $ a call, and accepts any key. Two more words exist so that every answer can be seen: a line with "nimic" makes Jev decline, and a line with "eroare" makes the call fail.

**What the demo does not cover.** The notice and the window of a program update (they need an installed copy and a newer release; looking for a version still asks the real repository), and connecting with the Windows certificate (section 5), which is not offered in demo.

**Where the stand-ins live.** They exist today in `tests/helpers.py` (`FakeAnaf`, `FakeOpenRouter`, the invoice builders) and `scripts/seed_demo.py` imports them from the tests. They move into the package, `src/efactura/standins.py`, so the program can use them; `tests/helpers.py` re-exports them under the same names, so no test changes. The building of the demo data moves from `scripts/seed_demo.py` into `src/efactura/demo.py`; the script stays as a three-line wrapper.

**On the page.** While demo is on, the top bar shows a label "Date de probă" between the name and the two chips, with the hint "Clienții și facturile sunt inventate. Nimic nu vine de la ANAF și nimic nu se plătește lui Jev." The page learns it from the answer of `GET /settings`, which gains `"demo": true|false`.

## 2. Testing the rules

**Where.** A button "Testează regulile" on "Reguli de clasificare" opens a screen of its own (`#/reguli/test`) with a link back, "‹ Înapoi la reguli". The menu keeps "Reguli de clasificare" marked.

**The trial invoice.** Client (the first choice is "Fără client (doar regulile pentru toți clienții)"; some rules are for one client), supplier name, supplier CUI, and lines: description, quantity, price without VAT. Behind "› Coduri de pe factură (codul furnizorului, cod de bare, cod CPV sau NC)" each line can also carry a seller code, a barcode and commodity codes. It starts from one of: "O factură goală", "O factură salvată…", "Exemplu: materiale", "Exemplu: combustibil". Numbers accept a decimal comma.

"O factură salvată…" opens a window, "Alegeți o factură salvată", listing the chosen client's last 20 received invoices as "furnizor · număr · dată"; pressing one fills the supplier and the lines. Until a client is chosen the button is off, with the hint "Alegeți întâi clientul." What the form does not show (each line's unit and VAT rate, the currency, invoice or credit note) is kept from that invoice and sent along, so that an unchanged trial puts the same question to Jev as the real invoice did; the form says so: "Pornită de la factura FV-1042: unitățile, cota de TVA și moneda rămân ca pe acea factură." Starting again from an empty invoice or an example drops them.

**Two buttons** (the owner's wording of what they must do):
- "Vezi ce cont primește": the real path. The rules first; if one fits, it decides and Jev is not asked. If none fits, the real Jev is asked.
- "Întreabă-l direct pe Jev": skips the rules and asks Jev.

While an answer is awaited the pressed button reads "Se caută contul…" (or "Este întrebat Jev…") and both are off.

Under them: "„Vezi ce cont primește” face ce face programul cu o factură adevărată: întâi regulile dumneavoastră, iar dacă niciuna nu se potrivește, este întrebat Jev. „Întreabă-l direct pe Jev” sare peste reguli." and "Fiecare întrebare pusă lui Jev costă puțin. Costul apare la „Costuri Jev”, ca „probă de reguli”."

**The answer**, one of:
- *A rule decided*: "Contul 6022" with the account's description, the label "Ales de o regulă", "Regula dumneavoastră „combustibil”, pentru rândul „Motorină Euro 5”." and "Jev nu a fost întrebat, deci nu a costat nimic."
- *Jev decided*: "Contul 302" with its description, the label "Ales de Jev", "Nicio regulă nu s-a potrivit, așa că a fost întrebat Jev." (or, for the direct button, "Regulile au fost sărite."), "Cât de sigur este: 93%. Pragul dumneavoastră este 80%, deci o factură adevărată ar fi primit contul fără să vă mai întrebe.", when Jev weighed other accounts "S-a gândit și la: 371 (27%), 628 (9%).", and "A costat 0,00002 $ și a durat 1,4 s." Jev gives no reason in words, so none is shown.
- *Jev was not sure enough*: "De verificat", "Jev propune contul 628", "Jev este sigur doar 61%, sub pragul dumneavoastră de 80%." and "O factură adevărată ar aștepta la „De verificat” până îi alegeți dumneavoastră contul."
- *Jev declined or found no account that fits*: "De verificat" with "Jev nu a ales niciun cont pentru această factură."
- *Nobody could be asked*: "Jev nu a putut fi întrebat." with the reason in words: no lines ("Factura de probă nu are niciun rând."), no key ("Lipsește cheia OpenRouter. O scrieți la „Chei și parole”." and "Regulile se pot încerca și fără cheie: dacă o regulă se potrivește, răspunsul vine de la ea."), no accounts ("Nu există niciun cont din care Jev să aleagă. Le adăugați la „Reguli de clasificare”."), or Jev failed ("Jev nu a răspuns. Încercați din nou puțin mai târziu." with the program's English line under "Detalii tehnice").

**The proposed rule.** When there is an account (Jev's choice, sure or not) and no rule of the rulebook already fits the invoice, the screen shows the same card an invoice's screen shows, with the same texts and the same behaviour: the words of the largest line as chips or the supplier, how such a rule would have done on the last 90 days, and "Creează regula". The only difference: "Nu acum" just hides the card, and nothing is remembered about it. With "Întreabă-l direct pe Jev" on an invoice a rule already fits, no rule is proposed.

**What is and is not saved.** No invoice row, no SAGA file, no proposed rule. Each call to Jev is written to the table of Jev calls with the marker `rule-test` in place of an invoice id and the client's CUI if one was chosen, so its cost is in the totals of "Costuri Jev"; it is not counted as an invoice there and is left out of the average cost per invoice, and the list shows it as "Probă de reguli" instead of a link to an invoice. One line goes to the journal (`rule.tested`), read on the "Jurnal" screen as "A fost încercată o factură de probă: contul 302, ales de Jev." (or "…, ales de o regulă.", or "A fost încercată o factură de probă: nu a primit niciun cont.").

**The program's side.** One route, `POST /rules/test`, and one method on the service. It builds the invoice in memory from the values sent (the parsed-invoice classes are plain frozen dataclasses) and runs the same functions the real path runs: `decide_by_rules`, `jev_request`, `jev.ask` (once, no second attempt), `read_jev_answer`, the confidence level from the settings, `propose`. Limits: at most 50 lines, 500 characters a description; beyond that the request is refused as bad input.

## 3 and 4. The foot of the menu

On every screen, under the last menu entry, in this order:

- "AutoSaga 0.3.0" (the version as today, without the word "Versiunea").
- A button, "Caută o versiune nouă" ("Se caută…" while it looks). It is always there, also on a development copy.
- What the look found, said from the status the page holds now:
  - "Aveți cea mai nouă versiune."
  - when a newer one exists the button gives way to "Există versiunea 0.4.0." and the button "Actualizează programul", which opens the existing update window (the notice on top of the screen stays as it is);
  - on a development copy: "Ultima versiune publicată este 0.3.0. O copie de dezvoltare se actualizează cu git, nu de aici.";
  - in a folder that is not a clone at all: "Această copie nu a fost instalată cu programul de instalare, așa că nu are de unde căuta.";
  - "Nu am putut căuta. Verificați conexiunea la internet."
- A thin line, then "© 2026 Tanasie Vlad-Cristian" and under it the address tanasievladcristian@gmail.com as a `mailto:` link. Small grey text.

For the development copy to have something to say, `GET /update?check=true` asks the remote for the newest release whenever the folder is a git clone, updatable or not. `can_update` and `update_available` keep their meaning.

## 5. Connecting to ANAF without the browser (Windows)

**Gate.** The helper script is written first and put in the repository, with the two lines needed to run it by hand. The owner runs that very script on the Windows PC, with the token in. Only if it prints an address containing `code=` is the rest built (the window, the route, the program starting the script itself). So the test proves the thing that ships. None of it can be tried on the development machine: it needs Windows and the token. In demo mode this way of connecting is not offered.

**What happens.** In the "Conectare la ANAF" window, on Windows, the first thing offered is:

- "Aveți nevoie de tokenul USB și de PIN-ul lui. Se face cam o dată pe an."
- "1. Introduceți tokenul USB în calculator. 2. Apăsați butonul de mai jos. Windows vă arată certificatele: alegeți-l pe al dumneavoastră. 3. Scrieți PIN-ul în fereastra tokenului."
- The button "Conectează-mă cu certificatul", and the link "Nu merge așa? Conectare prin browser", which shows the three steps there are today.

While Windows asks: "Se așteaptă certificatul…", "Alegeți certificatul în fereastra Windows, apoi scrieți PIN-ul.", "Fereastra poate fi în spatele browserului. Dacă nu o vedeți, uitați-vă în bara de jos a ecranului.", and "Renunță". If ANAF refuses: "ANAF nu a acceptat certificatul.", "Verificați că este certificatul cu care intrați în SPV și că nu a expirat.", the technical line, and the buttons "Încearcă din nou" and "Conectare prin browser". If no certificate was chosen: "Nu a fost ales niciun certificat."

**How.** The program starts Windows' own PowerShell with a short script: it lists the certificates of the signed-in user that have a private key and have not expired, shows Windows' standard "choose a certificate" window, and asks ANAF's login address with the chosen one, without following the redirect. The token's own software asks for the PIN. The script prints where ANAF sent it; the program takes the code from that address and finishes the login as it does for a pasted address. The key never leaves the token and the PIN is never seen by the program.

**Also, and not behind the gate.** An address or an answer carrying `error=access_denied` gets an error code of its own (`login_refused`) and a Romanian sentence that says what to check, instead of today's "ANAF a răspuns cu o eroare. Încercați din nou puțin mai târziu.", which sends the person to wait when waiting does not help. `README-ANAF.md` gains an entry for it under "Dacă ceva nu merge". This serves the browser way as much as the new one, and can be built and tested now. The program's error codes are what a Power Automate flow reads; this turns one case of `anaf_error` into `login_refused`.

## Decisions taken on the owner's behalf (say if any should change)

- Demo mode needs both the line in the settings and the builder's marker in the data folder; without the marker the program refuses to start rather than guess.
- The demo does not stand in for program updates.
- A trial started from a saved invoice carries that invoice's units, VAT rates and currency without showing them.
- The proposed rule on the test screen is the card an invoice's screen has, not a new one.
- `access_denied` gets its own error code, `login_refused`, and that part is built without waiting for the gate.
- A Jev question from the rule test is recorded with its cost and shown under "Costuri Jev", but kept out of the average cost per invoice.
- The rule test asks Jev once; the real path's second attempt after a passing failure is left out, so a failure is seen at once.
- In demo mode every download brings one or two new invoices, instead of a fixed set per day.
- The author line is written in the page's code, not read from the settings.
- "Renunță" while Windows asks for the certificate only stops the page waiting; if the certificate is chosen afterwards, the login is still saved.

## Left to the builder

File and function names inside the new modules beyond the ones the plan fixes; the catalogue of made-up suppliers and lines for the demo; the look of the "Date de probă" label within the colours the page already has.
