# AutoSaga (efactura)

On screen, in the shortcuts and in its messages the program is called **AutoSaga**. The command, the Python package and the files keep the name `efactura`.

Fetches ANAF e-Factura messages for a company CUI and keeps them locally:

- a SQLite database (`data/efactura.db`) with one row per message and an "uploaded to accounting" flag
- the XML files in a folder named after the day they were fetched (`data/invoices/11-11-2026/`)

Only messages not saved before are downloaded. It never uploads or changes anything at ANAF.

Each newly received invoice is then given an account (`cont`) and written, together with the client's other invoices that wait for import, into a file the SAGA C accounting program can import (`data/SAGA Import/<client's name> - <CUI>/`). See [Classification and SAGA](#classification-and-saga).

There are three ways to use it, all on the same data:

- **The screen** (in Romanian), for the accountant: clients, invoices, accounts, rules, costs, backups, the journal. See [The screen](#the-screen).
- **Terminal commands**, each printing one JSON document.
- **A local REST API** with the same steps, so a Power Automate Desktop flow can call them and read the result.

## How the login works

The key on the USB signature token cannot be read or copied, so this tool never touches it. The token is used once, by Windows or in the browser (two ways, below), exactly like logging in to SPV. ANAF then issues a login that this tool saves and renews by itself:

| | Lasts | Needs the USB token |
|---|---|---|
| Access token | 90 days | no |
| Refresh token (renews the access token) | 365 days | no |
| A new login | — | yes: certificate + PIN, in Windows' own windows or in the browser |

So the token and PIN are needed about once a year. The PIN is typed into Windows' own prompt; this tool never sees it.

There are two ways to log in. On Windows the page offers **Conectează-mă cu certificatul** first: the program starts a PowerShell helper (`src/efactura/certificate_login.ps1`, no browser) that shows Windows' own certificate window, makes the token ask for its PIN in the token's own prompt, and then follows ANAF's login to the address it ends on. The key never leaves the token and the program never sees the PIN. The address holds a one-time code; the program exchanges it at once and neither the address nor the code is shown, logged or written to the journal (the journal keeps only that Windows was asked, how long it took, how many tries ANAF needed and whether the token was opened first). The other way, on any system, is the browser: ANAF's own page, then the address copied back (see below). Only one helper runs at a time: a second request that arrives while Windows is being asked (the person pressed the button again, perhaps with the window hidden behind the browser) waits for the first and gets the same answer or the same error. A download in progress refuses the try at the start with `busy`, before Windows is asked, and not after the PIN. ANAF's answers `invalid_client` and `invalid_request` ("Redirect-URI ... does not match") come out as `config_error`, with ANAF's own words. A helper that prints nothing readable is reported with its exit code and the first line it wrote on standard error. `POST /auth/login/certificate` and the page's button are offered only where `certificate_login` in the login status is true: on Windows, with Windows PowerShell found, and not in the demo.

## Installing on the accountant's PC

`install.ps1` does it in one go. Open an ordinary PowerShell window, signed in to Windows as the person who will work with the program (not "Run as administrator"). Download the script:

```powershell
irm https://raw.githubusercontent.com/tanasievlad246/automatizare-saga/main/install.ps1 -OutFile install.ps1
```

Then run it:

```powershell
powershell -ExecutionPolicy Bypass -File install.ps1
```

What it does:

1. **Git and uv.** Installs them if they are missing. Windows asks an administrator to approve only when Git has to be installed; uv is installed for the user alone.
2. **The latest release** of [tanasievlad246/automatizare-saga](https://github.com/tanasievlad246/automatizare-saga) is cloned into `%LOCALAPPDATA%\AutoSaga` (`-InstallDir` chooses another folder). `-Repo owner/name` installs from another repository; a private one works too, as Git asks the PC to sign in to GitHub once. Without any release, the main branch is installed and the script says so.
3. **The dependencies** go into that folder (`.venv`). uv downloads Python as well if the PC has none.
4. **`config.toml`** is written with a random key for the local API. The port is 8765, or the next free port after it when that one is taken. Port 80 is never used: other programs expect to find it free.
5. **Two shortcuts**, both named "AutoSaga". One in the Windows Startup folder starts the program, without a window, each time that user signs in. One on the Desktop opens the page and starts the program first if it is not running. Shortcuts left by an earlier install under the old name, "e-Factura pentru SAGA", are removed.
6. The program is started and the page opens at **`http://autosaga.localhost:8765`** (with the port from step 4).

Then, on the page: fill in the ANAF client ID and secret and the OpenRouter key under "Chei și parole", and connect to ANAF. Getting the client ID and secret from ANAF is done by hand, once: [README-ANAF.md](README-ANAF.md) explains it in Romanian, and the "Chei și parole" screen links to it.

- **Updating:** on the page, press "Actualizează programul" when it says a new version exists; see [Updating](#updating). Running the script again does the same.
- **Removing:** `install.ps1 -Uninstall` stops the program and removes the two shortcuts. The folder, with the settings and every saved invoice, stays until it is deleted by hand.
- **Other programs** (a Power Automate flow) reach the local API at `http://127.0.0.1:8765` (the port in `config.toml`), with the key from the same file.
- **Why the address needs no hosts-file entry.** Chrome, Edge and Firefox open any name ending in `.localhost` on the computer itself, and treat it as they treat `localhost`. A made-up name such as `local.autosaga` would need the hosts file, would be marked "Not secure", and the page could no longer prove itself to the program.
- **Why it starts at sign-in, not at boot.** The saved ANAF login belongs to one Windows user, and the folder dialog and "Deschide folderul" need that user's desktop.
- **The built page must be in the repository** (`src/efactura/ui/`), so the accountant's PC needs no Node. Run `pnpm --dir frontend build` before tagging a release.

`install.ps1` was written on a Mac without PowerShell and has had one run on Windows so far, which got as far as starting the program. See [Not yet confirmed](#not-yet-confirmed-against-the-real-services).

## Updating

An installed copy updates itself to the newest release, from the page or from the terminal:

- **On the page:** when a newer release exists, a notice appears on top of every screen with the button "Actualizează programul". The foot of the menu shows the installed version and "Caută o versiune nouă", which looks at once. Otherwise the program looks at most every twelve hours.
- **In the terminal, on Windows:** `update.bat` in the program's folder (a double click works too), or `.venv\Scripts\python.exe -m efactura update`. Not `uv run efactura update`: that starts the program through `efactura.exe`, the update has to replace that very file, and Windows does not replace a program that is running. Started that way the update is refused at once, before anything is stopped, and says which command to use.
- **In the terminal, on macOS and Linux:** `uv run efactura update`.
- `efactura update --check` only says whether a newer release exists, however it is started.

What an update does: while invoices are being downloaded it is refused at once, before anything is stopped, since stopping the program does not stop a download under way. Otherwise it keeps any download from starting until it is done, stops the program, copies the database, moves the folder to the newest release tag, installs that release's dependencies and starts the program again. If any step fails, the folder goes back to the release it had and the program is started again on that one.

**The database and the settings are not replaced:**

- `config.toml` and `data\` are not part of any release, so changing release does not touch them.
- Git would silently overwrite such a file if a release ever came to contain one. Before anything is stopped, the update checks the new release for files at those two places and refuses it if there are any.
- A copy of the database is written to `data\backups\` before each update, named after the release being left and the time. The last three are kept. These are apart from the [backups](#backups) in the folder chosen on screen.
- A newer release may add columns to the database when it first opens it; nothing is removed.

Only a copy made by `install.ps1` can be updated this way: a folder standing on a release tag. A development checkout on a branch is refused, and the page shows no update button there; it looks for the newest release only when "Caută o versiune nouă" is pressed, never by itself, so opening its page (or the demo's) does not wait on the remote. Every tag counts as a release, and the highest version is the newest.

How the last update ended is kept in `data\last-update.json`, and what it printed in `data\update.log`.

## Automatic download

The program can download invoices by itself, for every client that is switched on, on the days and at the times the accountant chooses (up to four times a day). It is a schedule, kept in the database (the setting `auto_sync`), and it is off until it is switched on.

- **The program has to be running.** The running program looks at the schedule half a minute after it starts and then every half minute. A PC that is off, or a program that is stopped, downloads nothing; the moments it missed are not lost, see the next point.
- **A missed moment is made up once.** When the program finds that a moment has passed without a download, it runs one download for the latest such moment, however many were missed. A moment that was already past when the schedule was saved is never made up.
- **What a run does:** the same as a download by hand for each client that is on, one after another, then the invoices just saved are given an account and their SAGA files are written. A client that fails does not stop the others. A failure that would be the same for all of them (the login is needed, ANAF's limit is reached, the settings are wrong, ANAF cannot be reached) stops the run, and it is recorded how it ended: `ok`, `partial`, `failed` or `unreachable`.
- **Which invoices a run asks for.** The schedule holds a period, chosen on the same screen: the last 3, 5, 7 or 10 days, or a first and a last day. A number of days is a minimum: after a pause the run reaches back to the last complete run, as a download by hand does. Two chosen days stay the same at every run; each run asks for those of them that have come (the last day may still be ahead when it is saved) and that ANAF still keeps. Once the last day has passed, the runs bring nothing newer, and the screen and the menu say so. Once it is more than 60 days back, the run ends as `failed` with `invalid_input` before anyone is contacted. A schedule that is on cannot be saved with a period that has not begun or that ended more than 60 days ago. A schedule saved before the period existed asks for the last 7 days; `default_days` in `config.toml` no longer decides the automatic download.
- **Three more attempts.** A run that could not reach ANAF, or that the program did not live to finish, is tried again a quarter of an hour later, up to four attempts in all. The next moment of the schedule starts over. A run that failed for another reason (no login, for instance) is not repeated until the next moment.
- **A run in which no client succeeded is a failed run.** It is recorded as `failed` with the first client's error (ANAF's, for instance), shown as failed on the page, and not tried again before the next moment. One client failing among others leaves the run `partial`.
- **A download made by hand** at the same time is waited for, one client at a time, for about a minute per client; after that the client counts as failed. The two never write together.
- **It spends what a download by hand spends:** the calls to ANAF and, for invoices no rule decides, the calls to Jev, which are counted on the costs screen like any other.
- **Where it shows:** the last run (its moment, attempt, how it ended and the counts), the run in progress and the next moment come from `GET /sync/schedule`. The journal holds `sync.auto_started` and `sync.auto_finished` and, under the same trace number, every line of the run itself. If the run ended but its record could not be saved, the journal says so with `sync.record_unsaved` (an error); the run's outcome is kept in memory, shown as it ended and saved at the next look, and if the program is stopped before that, the run shows as interrupted.
- **Where it runs:** under `serve`, `start`, and `demo` serving the built page. When `efactura demo` starts the page's dev server (`pnpm` found), the background threads are not started, so a schedule saved there never runs.

## Backups

The database holds everything: clients, invoices, accounts, rules, settings, and the keys typed on screen. The screen "Copii de siguranță" keeps copies of it in a folder the accountant chooses. The files of the confirmed imports in SAGA (`data/saga-archive`) are not in these copies; the database's record of them is.

- **The folder** is typed, or picked with "Alege folderul", and is made if it does not exist. It has to be a whole path (`E:\Copii AutoSaga`). Until one is chosen, no copy is made, and the screen says so. A stick, another disk or a folder that syncs to the internet is the point: a copy on the program's own disk does not survive that disk.
- **A copy on a click:** "Fă o copie acum", or `efactura backup`.
- **A copy every 24 hours,** counted from the newest good copy in the folder, whoever made it. The running program looks a minute after it starts and then every quarter of an hour, so a PC that was off overnight gets its copy soon after it is switched on. If the folder is missing (stick unplugged), the failure is shown on the screen and written in the journal, and the next look tries again.
- **At most 25 copies.** When a new one arrives the oldest are removed. The limit counts every copy in the folder, however it was made. Only files with the program's own names are ever deleted; anything else in the folder is left alone. The copy just made is never the one removed, nor the copy made before the latest wipe (`…-before-wipe`), which after 25 daily copies would be the only one left holding what was deleted; the oldest of the others goes in its place. Copies named later than today (made while the PC's clock was ahead) count as the oldest, and do not hold up the daily copy.
- **What a copy is:** one zip, `autosaga-20261114-161217-manual.zip` (the PC's date and time, then `auto`, `manual`, `before-restore` or `before-wipe`), holding `efactura.db`. It is made with SQLite's own copy, so it is complete while the program works; it is checked (`PRAGMA quick_check`, then the zip is read back) and written under a `.partial` name first, so a half-written file is never taken for a copy. A `.partial` left by a PC switched off mid-copy is removed at the next copy, once it is an hour old.
- **A copy is not encrypted** and holds the keys from "Chei și parole". The folder is as private as `config.toml`.

**Restoring.** "Restaurează" next to a copy, after a ticked confirmation, or `efactura restore <file name>`:

1. The chosen zip is opened, checked and made ready next to the database. A file that is not a usable database is refused here, before anything is touched. So is a restore while invoices are being downloaded or classified, while an update runs, or while the data is being wiped.
   - **A copy made by an older version** is brought up to date here (the same `_migrate` the program runs on starting, keyed on SQLite's `user_version`), so one that cannot be is refused while the database in use is still untouched.
   - **A copy made by a newer version** (its `user_version` is above this program's `SCHEMA_VERSION`) is refused with `snapshot_too_new`, at once on the page ("Copia a fost făcută de o versiune mai nouă a programului…"): this version would not know what the newer one changed. Update the program, then restore it. The page reads the number from the start of the file inside the zip, without unpacking it.
2. The program is stopped.
3. The database as it is now is kept. Normally as one more copy in the folder (`…-before-restore.zip`), so the restore can be undone by restoring that one. If no sound copy can be made, because the folder has gone or the database is damaged, the old file itself is kept in `data\` as `efactura.db.replaced-<date>-<time>`, and the journal says so.
4. The chosen copy replaces the database. The backup folder setting is carried over, so copies go on to the same folder. A file that Windows says is still in use is tried again for a few seconds.
5. The program is started again, whatever happened at steps 3 and 4.

Everything saved after the chosen copy is gone from the program: downloaded invoices, chosen accounts, the "imported in SAGA" ticks, rules, clients, settings and keys changed since, and the journal's lines since then. The files for SAGA are written again from the copy as the program starts; a file written after the copy was made is no longer known to the program and stays in its client's folder, so look through the SAGA folder after a restore and delete what should not be imported again. A client renamed after the copy was made has its earlier name again, and its files are written in the folder of that name; the folder under the later name stays as it is, with what is in it. If the copy cannot be put in place, the database that was there is kept and the screen says the restore failed. How the last restore ended is kept in `data\last-restore.json`, and what it printed in `data\restore.log`.

**Deleting everything, to start from zero.** "Șterge toate datele…" at the bottom of the same screen, after typing `STERG` in the window that opens (small or capital letters, with Ș or without; the button stays grey until then). It needs the backup folder: without it, or with the folder away, the button cannot be pressed and the screen says why. There is no terminal command for it.

1. Refused with `busy` while invoices are being downloaded or classified, while an update or a restore runs, or while the files for SAGA are being written. Nothing is copied or deleted then. A download over every client that was waiting for the lock checks again, once it has it, that its client is still in the list, so it cannot bring a deleted client's invoices back.
2. A copy is made in the backup folder (`…-before-wipe.zip`), as every copy is (SQLite's own copy, `PRAGMA quick_check`, the zip read back).
3. That copy is then read back from the folder and checked whole: unpacked, `PRAGMA integrity_check`, every table the program has, and the rows of each table that is about to be emptied counted. If any of steps 2 and 3 fails, nothing is deleted and the screen says so.
4. In one transaction, holding the database's write lock, each table is fingerprinted again (its rows and a SHA-256 of what they hold, leaving out the invoice and Jev request texts, which never change once written) and must match the copy. So a rule edited or an invoice ticked on another tab while the copy was being made is never lost: the wipe is refused with `busy` and can simply be tried again. Then the tables are emptied with `secure_delete` on, so the deleted rows are overwritten, and the example accounts and rules are put back, as on the first day. Still holding the locks, the file is compacted (`VACUUM`, then the `-wal` folded in), so it is small again and the deleted invoices do not linger in it or in the copies made from it later.

What goes: `clients`, `messages` (the invoices, with their accounts, the "imported in SAGA" ticks and the proposed-rule state), `decisions` (each account's history), `sync_runs` (the downloads), `jev_calls` (the calls to Jev and their costs), `accounts`, `issued_accounts`, `rules`, `saga_files`, `saga_problems`, `saga_imports` and `saga_import_invoices` (what the program knew of the files for SAGA and the confirmed imports). What stays: the whole `settings` table (the SAGA folder, the backup folder, the keys from "Chei și parole", the automatic download and its last run, Jev's questions, the confidence level), the journal (`events`), the login to ANAF (`tokens.json`), `config.toml`, every copy in the backup folder, and every file on disk: `data/invoices`, `data/saga-archive`, and the files for SAGA in the SAGA folder, which the program no longer knows of, so look through that folder afterwards and delete what should not be imported. `store.WIPED` and `store.KEPT_BY_WIPE` list the tables; a test fails when a new table is in neither.

It runs inside the program, which keeps running: the database file stays where it is, so there is nothing for Windows to refuse, and the next request already reads the emptied database. The journal holds `wipe.finished` (with the copy's name and how many rows each table lost) or `wipe.failed`. To undo it, restore the `…-before-wipe` copy.

**When the database itself is damaged.** This is what the copies are for, and it is done from the terminal, because a program that cannot read its database does not start:

```powershell
uv run efactura restore "E:\Copii AutoSaga\autosaga-20261114-090000-auto.zip"
```

The whole path is needed there: where the backup folder is was written in the database that cannot be read. A database that still opens but has a damaged part can be restored from the page as usual. In both cases the damaged file is kept beside the new one (step 3).

**By hand,** if that does not work either: stop the program (`efactura stop`), unzip the copy, and put its `efactura.db` in `data\` in place of the old one, deleting `efactura.db-wal` and `efactura.db-shm` if they are there.

## The journal

The screen "Jurnal" shows what the program did, line by line. It is for the moment something does not work and someone has to find out why.

- **What is written:** the program starting and stopping; every download (its start, each call to ANAF with how long it took and how it ended, each message that could not be saved, the end); every account decision (by a rule, by Jev with its confidence, by a person, or left to check); every call to Jev (duration, cost, failure); rules, accounts and clients added, changed or removed; settings changed; connecting to ANAF and the login being renewed; invoices marked as imported; backups, restores and updates; and every error, with its technical detail. The program's ordinary log lines land there too.
- **What is never written:** keys, passwords, the ANAF login tokens, the pasted login address. A changed key is recorded as "this key was changed" and nothing more. On top of that, any detail whose name contains `key`, `secret`, `token`, `password`, `pin` or `authorization` is stored as `[hidden]`, and so is anything shaped like a secret (`Bearer …`, a JWT, an OpenRouter key, `token=…`) or equal to a key or token the program holds, wherever it stands in a line (`src/efactura/redact.py`).
- **One operation, one trace.** Every line written during one request from the page, one terminal command or one round of the background job carries the same trace number. "Arată tot ce s-a întâmplat în această operațiune" on a line shows the whole story in order, details included. Each answer of the local API names its trace in the `X-Trace-Id` header.
- **Four levels:** `info`, `warning`, `error` and `detail`. Details are the page's own requests and each call to ANAF; the screen hides them until "Arată și detaliile" is ticked.
- **On screen in Romanian, underneath in English.** Each kind of event has a code (`sync.finished`, `account.by_jev`, `backup.made`). The page turns the codes it knows into a Romanian sentence and shows the program's English line under "Detalii tehnice". The sentences name what the line knows: the dates a download asks for, how long it took and how many of ANAF's messages were saved already; the page of the list or the message each call to ANAF was for, and the code ANAF answered with when it was not 200; the invoice (and line) Jev answered about, and why OpenRouter gave nothing usable (key, credit, too many requests, its own trouble, unreachable); why a download or a message failed, by its error code; until when the login is valid. A program log line carries the logger and the place in the code (`where`) that wrote it.
- **"Descarcă jurnalul"** saves every line that matches the filters on screen as a text file to send to whoever helps. With the technical view on, the file also holds one line per request and program record of those operations, without the bodies.
- **30 days are kept, and at most 50,000 lines.** The running program removes the rest once a quarter of an hour.
- **Writing the journal never breaks the work.** A line that cannot be written (the database is busy) is dropped, and the download or the click carries on.

The journal is a table in the database (`events`), so restoring a backup also brings back the journal as it was then. `data\efactura.log` is still written as before (information and up) and is not replaced by a restore.

### The technical view

For whoever looks into how the program works. The switch **"Vizualizare tehnică"** on the "Jurnal" screen is off whenever the page opens; on, it stays on from the list to an operation and back (it is `tehnic=1` in the page's address). The ordinary view does not change.

- **In the list,** each line also shows its code and its operation, and opened, its details as the JSON the program wrote, its level, area, duration and time to the millisecond, and the way to its operation with how many requests and program records it holds.
- **In one operation,** each request and program record stands among the steps, in the order things happened, with a strip on top: how many requests went to ANAF and to Jev, how many went wrong, how many program records, from when to when. A request shows its method, its code (or "fără răspuns"), its duration and its address; opened, it shows what was sent and what came back: the headers, and the body laid out to be read (JSON, XML, a form), with "Copiază conținutul". A program record shows its level, its file and line, its message, and opened, its function, logger and exception.
- **What is kept, the table `technical`:** every exchange of the program's HTTP client (`technical.watch`, set on every `Service`) with ANAF's login service, ANAF's API and OpenRouter, answered or not; and every debug record of the program's own loggers (`efactura.*`), with the file, line and function. Debug records go nowhere else; records from information up stay journal lines. Calls the program does not make through that client are not there: the certificate login (made by PowerShell; its journal line says how it went) and the check for updates on GitHub.
- **What is never kept:** the values of the `Authorization`, `Cookie`, `Set-Cookie` and `X-API-Key` headers and of any header, address parameter, form field or JSON key whose name holds a secret word (`key`, `token`, `secret`, `password`, `pin`, `cookie`, `session`…), and the login `code` in a form or an address; anything shaped like a secret; and every key and token the program holds (the ANAF Client ID and Client Secret, the access and refresh tokens it reads or receives, the login code it exchanges, the OpenRouter key, this program's own key). They become `[hidden]` before anything is written. Binary bodies (the ZIP of each download) are never kept: only their type and size.
- **How much:** each body, program record and exception up to 32 kB (a longer body says it was cut, and how long it was; one over 1 MB is not read at all); the whole at most about 10 MB and 20,000 records, the oldest going first; nothing older than 7 days. The limits are applied at the first record each process writes (so short terminal commands do not pile up), then every 200 records or 500 kB, and at each quarter-hour housekeeping of the running program. A record that cannot be written within half a second (another program is writing to the database) is dropped, so the work never waits long. The journal itself keeps 30. It never leaves this computer.
- **For other programs:** `GET /events/technical?trace=…` and `GET /events/technical/{id}`; `GET /events?technical=true` adds `technical`, the counts of each operation on the page.

## One-time setup

These are the steps by hand, for a PC set up without `install.ps1`.


1. **Windows PC:** the token's driver is installed and logging in to SPV works in Edge or Chrome.
2. **Register an application with ANAF** to get the client ID and client secret. [README-ANAF.md](README-ANAF.md) has the steps in Romanian, for the accountant. In short: <https://www.anaf.ro/InregOauth> (anaf.ro → Servicii Online → Înregistrare utilizatori → "Înregistrare pentru API-uri"), sign in, then "Editare profil Oauth" → "Gestionare aplicații" → "Generare Client ID".
   - Service: E-Factura.
   - Callback URL: `https://localhost/callback` (must be `https://`; ANAF's procedure describes deleting an application, not editing one, so type it carefully).
   - Click the application's row to see the **client ID** and **client secret**.
3. **Install uv** (it installs Python and the dependencies by itself): see <https://docs.astral.sh/uv/getting-started/installation/>, or `winget install --id=astral-sh.uv -e`.
4. **Copy this folder** to a local disk on the PC (not a network share: the database must be local).
5. **Create the settings file:** copy `config.example.toml` to `config.toml` and fill in `client_id`, `client_secret` and, for the local API, `[api] key` (any long random text).
6. **Log in once:** `uv run efactura login`

The first `uv run` downloads the dependencies and needs internet access.

## The screen

Double-click `start.bat`, or run

```bash
uv run efactura serve --open
```

The page opens at `http://autosaga.localhost:8765/ui/`. `http://127.0.0.1:8765/ui/` is the same page. It only works on this computer.

| Screen | What it is for |
|---|---|
| **Clienți** | Import clients from Excel or CSV, add one by hand, download invoices for one client or all (the last 1 to 30 days, or two dates). Shows how many invoices are new and how many wait for an account. A search field narrows the list by name or CUI as it is typed (no matter the case, the diacritics, or whether the CUI is written with `RO`); the download for all clients still covers every client that is on. The list shows 20 clients a page, by name, with a bar under it to the other pages. Once a client has new issued invoices, the new ones are counted by kind ("3 primite noi", "2 emise noi"); "de verificat" counts both kinds, and "Vezi facturile de verificat" opens the list they are in. Beside it, "Clasifică din nou, la toți clienții" sends every client's invoices to check back through the rules and Jev, see [Classifying again](#classifying-again) |
| **A client's invoices** | Four tabs, "Facturi primite", "Facturi emise", "Fișiere pentru SAGA" and "Arhivă", each with how many there are ("Fișiere pentru SAGA" is described under [the files waiting for SAGA, on screen](#the-files-waiting-for-saga-on-screen), the archive under [confirming an import in SAGA](#confirming-an-import-in-saga)); on the first two under each, the same four lists: new, to check, not yet in SAGA, all. Above the list: a search by the supplier's name (on issued invoices, the buyer's), its CUI or the invoice's number; the invoice's days, from and to; the account (an invoice whose lines are on several accounts is found under each, "Fără cont încă" finds those still missing one); and the order: newest first (the start), oldest first, supplier A to Z, total largest or smallest first. While something narrows the list, the counts beside new, to check, not yet in SAGA and all are of the invoices found, and "Arată toate facturile" clears the search, the days and the account. The list shows 25 invoices a page. What is chosen is kept in the address, so the link back from an invoice returns to the same page of the same list. Totals in different currencies are compared as written. Under the list, on both tabs and under "Fișiere pentru SAGA", the client's file for SAGA: its path, when it was written, how many of its invoices are received and how many issued (SAGA puts the first in "Intrări", the others in "Ieșiri"), a link to the "Fișiere pentru SAGA" tab ("Vezi ce este în fișier"), and one button that names how many invoices it marks as imported; it also moves the file to the archive, and refuses, marking nothing, when the file has changed since the page was opened. While the folder is not up to date, a notice says so and offers "Încearcă din nou", and the marking button is off. Above the tabs, while the client has invoices to check or waiting for Jev, "Clasifică din nou facturile de verificat" sends them back through the rules and Jev, see [Classifying again](#classifying-again). See [issued invoices](#issued-invoices) |
| **One invoice** | The invoice as a person reads it (each line's description under its name; an earlier balance, what was already paid or a rounding shown apart from what the invoice is worth), ANAF's XML, its own part of the SAGA XML, and "Cum s-a ales contul", the [history of its account](#the-history-of-an-invoices-account); its account and who chose it; accept Jev's proposal or pick another; "Hotărăște din nou…" and, for an invoice with one account and several lines, "Împarte pe linii" (see [changing an account, splitting, deciding again](#changing-an-account-splitting-an-invoice-into-lines-deciding-again)); for an imported invoice, the steps to change its account all the same; a rule proposed from it when no rule decided it; the file for SAGA it is in, or why it is in none; a warning, and no ticking as imported, while the client's folder is not up to date. An invoice the client issued is shown the same way, marked "Emisă", with its income accounts to choose from |
| **Reguli de clasificare** | Two tabs, "Pentru facturile primite" and "Pentru facturile emise", each with its rules, the accounts Jev chooses from and the two questions Jev is asked; rules proposed from recent decisions are on the first. How sure Jev must be is one setting for both. The button "Testează regulile" opens the rule test, see [Testing the rules](#testing-the-rules) |
| **Costuri Jev** | Cost between two dates, by day, week, month or year, and every invoice Jev classified |
| **Descărcare automată** | Switch the automatic download on or off, the days and times (up to four a day, chosen as 00 to 23 hours whatever the PC's regional settings), the period of the invoices (the last 3, 5, 7 or 10 days, or two dates), when the next one is, and how the last one went. See [Automatic download](#automatic-download) |
| **Copii de siguranță** | The folder for the copies of the database, when the last one was made and when the next is due, "Fă o copie acum", and the copies kept, each with "Restaurează". See [Backups](#backups) |
| **Jurnal** | What the program did, line by line: everything or only the problems, by area, period or a word; one line opens to its technical details and to the whole operation it belongs to. See [The journal](#the-journal) |
| **Chei și parole** | The OpenRouter key and ANAF client details (hidden until asked for, changeable), and when the ANAF login expires |

On every screen, a notice appears on top when a newer release of the program exists; see [Updating](#updating). The foot of the menu, under the last entry, holds two things: the installed version ("AutoSaga 0.4.0") and the button "Caută o versiune nouă" (always there, also on a development copy; it says what it found, and when a newer release exists it offers "Actualizează programul"). The author line, "© 2026 Tanasie Vlad-Cristian" with a `mailto:` link to the address and a `tel:` link to the phone number, is in the footer of every screen, across the whole page. It is written in the page's code, not read from the settings.

On every screen, the top bar holds the name, the **folder for SAGA** and the **ANAF connection**:

- "Folder SAGA" shows the end of the path; "Schimbă" opens a small window, "Fișierele pentru SAGA". There the folder is typed, or "Alege folderul" opens Windows' own folder dialog, and one of two ways is chosen: one file per client ("Un singur fișier pentru fiecare client") or one file per invoice ("Câte un fișier pentru fiecare factură"). See [the SAGA files](#classification-and-saga).
- The ANAF chip says one of: connected, with the days left; expiring, from 30 days before the end; not connected. Clicking it opens the login steps. While the program does not answer it says that instead, and does not ask for a login.

The menu on the left has a fixed width and the screen's content takes the rest. In a window narrower than about 1020 px the menu moves above the content.

### Issued invoices

ANAF lists the invoices a client issued (`FACTURA TRIMISA`) next to the ones it received, and the program saves both. Since 0.11.0 an issued invoice is classified like a received one and goes into the client's file for SAGA beside them; SAGA files it under "Ieșiri" because its supplier is the client itself.

- **Their own accounts, rules and questions.** Issued invoices are booked on income accounts (701, 704, 707 to begin with, changed on the rules screen's tab "Pentru facturile emise"). A rule is for one kind: a rule for received invoices never decides an issued one, and the other way round. A rule for issued invoices looks at the words, the article code and the CPV or NC codes of a line, never at a supplier or a buyer. Jev is asked its own two questions about them (about one line, and about a whole invoice for a client with one account per invoice), with the income accounts to choose from. How sure Jev must be is one setting for both kinds.
- **Jev is told neither party.** For an issued invoice only its kind, currency and lines are sent: not the buyer, who may be a person, and not the client.
- **An invoice whose parties do not fit its kind waits for a person.** An issued invoice whose supplier is not the client, an invoice the client issued to itself, and a received invoice whose supplier is the client would be filed on the wrong side in SAGA; they are "de verificat", with why.
- **The file for SAGA leaves out the buyer's phone and e-mail** on an issued invoice.
- **The ones saved before.** At the first start of 0.11.0, every issued invoice already saved that can be read and is not marked as imported starts waiting, once; each client's next download decides them. A client whose sales SAGA already has (issued from SAGA itself) can tick them as imported, or let SAGA's "Nr.+data" skip what it has.
- **Counted apart.** The client list says "3 primite noi" and "2 emise noi"; the download window "3 facturi primite noi, 2 emise noi, 2 de verificat"; a client's screen has a tab for each kind. "Reguli propuse" and "Testează regulile" are still about received invoices only; the test decides line by line like the program.
- **For other programs:** issued invoices are in `GET /invoices` with `type=trimisa`, carry the same classification fields, and can be classified and given an account like received ones. `show_issued` is still accepted by `/settings` and changes nothing on screen any more.

### An invoice's value and what is left to pay

Most invoices ask for what they are worth. Some do not: a supplier adds an earlier unpaid balance to the amount due (utilities do this, writing it as a negative paid amount, BT-113 `PrepaidAmount`), or takes off what was already paid, or rounds the amount due (BT-114).

- **"Total" is the invoice's own value, VAT included**, on every list and in the title of an invoice's screen. It is the value the file for SAGA adds up to (with a minus there for a credit note). It is worked out as the total without VAT plus the VAT, which the e-Factura rules make equal to the invoice's total with VAT; an invoice on which either cannot be read shows the amount left to pay, as before.
- **The invoice itself shows the rest** when there is any: "Total factură", then "Datorie restantă (sold anterior)" for a negative paid amount or "Deja plătit" for a positive one, then "Rotunjire", then "De plată", with a line saying which sum goes to SAGA. On a credit note, or an invoice whose own total is negative, a paid amount may be money given back, so it is shown as written under "Sumă plătită" and without that line. An invoice with none of these shows the three rows it always did.
- **The file for SAGA never held the amount due**, only the lines and their VAT, so an earlier balance is not booked a second time.
- For other programs: every invoice returned carries `total_with_vat` beside `total_payable`, which still is the amount left to pay. `document` in `GET /invoices/{id}/view` also carries `total_prepaid` and `total_rounding`, as written in the invoice, or `null`.

A client can be switched off. A client that is off keeps its invoices and is left out of every download until it is switched on again; asking to download it answers `client_off`. A CUI that is not in the client list is not affected and is downloaded as before.

**"New"** means: an invoice brought in by that client's latest download that brought any of its kind (received, or issued by the client), and not yet marked as imported in SAGA. Asked for alone (`new=true`, `--new`), "new" still gives the received invoices only, as it always did; with `type=trimisa` (`--type trimisa`) it gives the new issued ones. Every invoice returned says `is_new` for its own kind.

**Downloading from the screen never leaves a gap.** "Ultimele 5 zile" means at least five days: if the last complete download for that client was longer ago, the program reaches back to it (up to ANAF's 60 days) and says so. Two dates are taken exactly as chosen. If some invoices could not be downloaded, the window says how many.

**What is changed on screen is stored in the database** and wins over `config.toml`: the SAGA folder, the OpenRouter key, the ANAF client ID and secret. Clearing a key on screen goes back to the value in `config.toml`.

**The client file** needs two columns, name and CUI, in any order; other columns, such as a row number, are ignored. A header row is recognised in the first five rows (`CUI`, `C.U.I.`, `CIF`, `Cod fiscal`; `Nume`, `Denumire`, `Client`, `Firma`, `Societate`). Without one, the cell that passes the CUI check is the CUI. Rows that cannot be used are listed with the reason.

**Building the page.** The page's source is in `frontend/` (React, shadcn/ui). The built page lives in `src/efactura/ui/` and is what `serve` shows, so the accountant's PC needs only `uv`. After changing the source:

```bash
pnpm --dir frontend build
```

**Trying it without ANAF.** One command builds a made-up copy in `demo/` the first time and starts everything on it:

```bash
uv run efactura demo
```

Then open the address it prints. A top-bar label, "Date de probă", says the data is made up. Add `--fresh` to throw away what was done in it and build it again (stop a demo that is running first: on Windows its folder cannot be deleted while it is in use, and `--fresh` then says so), or `--port N` to use another port.

What works: each download brings one or two made-up invoices; the ANAF login is finished by pasting the address the browser ends on; Jev answers from a table of words, and a line with "nimic" or "eroare" in it makes him decline or fail, so both can be seen. What is not covered: program updates and the Windows certificate login.

It cannot touch real data: it uses only its own `demo/` folder, which the program starts on only because of a marker file made in it, its settings say it is a demo, and it listens on port 8770, not the usual one. On settings that say demo, every part of the program talks to the stand-ins for ANAF and Jev, never to the real ones. It needs `uv`; `pnpm` is needed only to change the page (without it, the built page is served).

## Commands

Run them from this folder. Use `--config PATH` before the command if `config.toml` is elsewhere.

| Command | What it does |
|---|---|
| `uv run efactura demo [--fresh] [--port N]` | Builds the made-up demo in `demo/` if needed, then starts the program on it. See "Trying it without ANAF". |
| `uv run efactura auth-status` | Reports `valid`, `needs_refresh` or `needs_login`, with expiry dates. Contacts nothing. |
| `uv run efactura login` | For a person: opens ANAF's login in the browser, then waits for the pasted address. |
| `uv run efactura login-start [--open]` | Returns the ANAF login address (for a flow that drives the browser). |
| `uv run efactura login-finish "<address>"` | Takes the address the browser ended on and saves the login. |
| `uv run efactura list <CUI> [--days N]` | What ANAF has, each marked new or already saved. Saves nothing. |
| `uv run efactura sync <CUI> [--days N] [--from DATE --to DATE] [--no-classify]` | Fetches and saves everything not saved yet, then classifies the invoices it saved, received and issued. The period is the last `N` days, or the days from `--from` to `--to` (`--to` defaults to today). |
| `uv run efactura sync-all` | Does `sync` for every client that is switched on, one after another, with the default period. It does once, now, what the schedule does, and leaves no record of an automatic run. |
| `uv run efactura invoices [--cui CUI] [--pending] [--new] [--type T] [--since YYYY-MM-DD] [--classification S]` | Reads the database. `--pending` = not yet uploaded. `--new` = from the latest download and not yet uploaded: received invoices, unless `--type` names another kind. `T` is `primita`, `trimisa`, `erori` or `mesaj`. `S` is `pending`, `classified` or `review`. |
| `uv run efactura invoice <id> [--xml]` | One message; `--xml` adds the XML text. |
| `uv run efactura mark-uploaded <id>... [--undo]` | Sets (or clears) the uploaded flag. |
| `uv run efactura saga-files [CUI]` | What waits for SAGA: each client's `folder`, its files, their invoices and their `version`. |
| `uv run efactura saga-imported CUI [--version V]` | SAGA imported the client's files: marks their invoices as imported and moves the files to the archive. |
| `uv run efactura saga-archive CUI` or `saga-archive --id N` | A client's confirmed imports, or one with its invoices. |
| `uv run efactura classify <id> [--force] [--jev-only] [--line N]` | Classifies one saved invoice, from the start; `--jev-only` skips the rules; `--line N` decides that line alone, on an invoice decided line by line. |
| `uv run efactura split <id>` | Turns an invoice with one account into one decided line by line, every line starting with that account. |
| `uv run efactura classify-again CUI [--no-jev]` or `classify-again --all [--no-jev]` | Sends a client's invoices to check, or waiting for Jev, back through the rules and Jev; `--all` for every client that has any; `--no-jev` for the rules alone. See [Classifying again](#classifying-again). |
| `uv run efactura review [--cui CUI]` | Invoices a person must decide, with Jev's suggestion. |
| `uv run efactura set-cont <id> --accept` | Accepts Jev's suggestion. |
| `uv run efactura set-cont <id> --cont 628` | Sets the account a person chose. On an invoice decided line by line, `--line N` sets it for that line only; without it, every line. |
| `uv run efactura confidence [VALUE]` | Shows, or sets, the confidence level (0 to 1). |
| `uv run efactura costs [--since DATE] [--until DATE] [--group day\|week\|month\|year] [--cui CUI]` | What the Jev calls have cost, in total and per period. |
| `uv run efactura serve [--port N] [--open]` | Starts the screen and the local API; `--open` also opens the browser. |
| `uv run efactura dev [--port N]` | For development: the API and the page's dev server together, both reloading on change. |
| `uv run efactura setup [--port N]` | Writes the first `config.toml` from `config.example.toml`, with a random API key and port 8765, or the next free port after it. Leaves an existing `config.toml` alone. |
| `uv run efactura start` | Runs the program in the background, without a window, unless it already runs. What it prints goes to `data/server.log`. |
| `uv run efactura open` | `start`, then opens the page in the browser. This is what the Desktop shortcut runs. |
| `uv run efactura stop` | Stops the program running in the background. |
| `uv run efactura update [--check]` | Moves an installed copy to the newest release, keeping `config.toml` and the data; `--check` only reports. On Windows, update with `update.bat` instead. See [Updating](#updating). |
| `uv run efactura backup` | Makes a copy of the database now, in the folder chosen on screen. See [Backups](#backups). |
| `uv run efactura restore <file name or whole path>` | Replaces the database with that copy: stops the program, keeps the database as it is, puts the chosen one in place, starts the program again. A file name is looked for in the backup folder; a whole path works even when the database cannot be read. |

Notes:

- One CUI per call, with or without `RO`. A mistyped CUI is rejected by its check digit before ANAF is contacted.
- The window is 7 days by default. If the last fully successful run for that CUI was longer ago, the window widens to cover the gap, up to ANAF's limit of 60 days. For a first run that should reach back further, use `--days 60`.
- `list` and `sync` renew the saved login by themselves when it has expired.
- Only one `sync` runs at a time; a second one gets `busy`.
- A date range that stops before today does not count as "caught up", so the next default run still reaches back over the days after it.

### The login address

After the certificate and PIN step, ANAF sends the browser to `https://localhost/callback?code=...`. Nothing listens there, so the browser shows "can't reach this page". That is expected: the address bar now holds the one-time code. Copy the whole address and hand it back (paste it into `login`, or pass it to `login-finish`). The code is reported to last about a minute and works once; if it is too late you get `login_code_expired` and repeat the login.

### Trying the certificate login by hand

When a login with the certificate does not work, this is the helper the program itself starts, run by hand. It presents a certificate to ANAF without a browser, follows ANAF's hops on its own host (`/anaf-oauth2/v1/authorize`, then `/my.policy`, `/my.policy_nonce`, with the cookies kept and the certificate offered at each) and prints the address ANAF ends on. Run these three lines in Windows PowerShell, with the token in:

```powershell
cd $env:LOCALAPPDATA\AutoSaga
$env:AUTOSAGA_AUTHORIZE_URL = (uv run efactura login-start | Out-String | ConvertFrom-Json).authorize_url
powershell -NoProfile -ExecutionPolicy Bypass -File src\efactura\certificate_login.ps1
```

A window lists the certificates; pick the one used for SPV. The token then asks for its PIN. The script prints one line of JSON:

- `{"location": "...code=...", "tries": 1, "opened": true}`: it works. The address holds a one-time code: use it within a minute and send it to nobody. It can be pasted into the program's window.
- `{"location": "...error=access_denied...", "tries": 2, "opened": ...}`: ANAF refuses, even after the second try.
- `{"cancelled": true}`: the window was closed without a choice.
- `{"error": "...", "tries": ..., "opened": ...}`: the script could not finish; the text is what Windows or ANAF said (for a wrong Client ID, ANAF's own `Invalid client_id ...`).

`tries` is how many times ANAF was asked and `opened` says whether using the key first (which makes the token ask for its PIN before ANAF is contacted) worked. If ANAF still refuses after that, the helper asks once more by itself.

Windows PowerShell 5.1 writes each `&` inside the address as the six characters backslash, `u`, `0026`. The program reads that as an ampersand; when pasting the address by hand, replace each of those with `&` first.

The script is run from the program's own folder, so no installation step is needed.

## Output

Success (from `sync`):

```json
{
  "ok": true,
  "cui": "12345674",
  "window_days": 7,
  "listed": 12,
  "new_count": 1,
  "received_count": 1,
  "issued_count": 0,
  "failed_count": 0,
  "folder": "C:\\efactura\\data\\invoices\\11-11-2026",
  "new": [
    {
      "id": "3001234567",
      "cui": "12345674",
      "message_type": "FACTURA PRIMITA",
      "anaf_created_at": "2026-11-10T14:15",
      "invoice_number": "FV-1042",
      "invoice_issue_date": "2026-11-09",
      "supplier_cui": "87654321",
      "supplier_name": "Furnizor SRL",
      "total_payable": "1190.00",
      "currency": "RON",
      "xml_path": "C:\\efactura\\data\\invoices\\11-11-2026\\12345674_primita_3001234567.xml",
      "possible_duplicate_of": null,
      "uploaded_to_accounting": false
    }
  ],
  "failed": []
}
```

(Entries carry a few more fields: due date, type code, customer, totals, `first_seen_at`, `uploaded_at`, and the classification fields described [below](#classification-and-saga). The reply also has a `classification` summary and `saga_folder`.)

`total_payable` is what is left to pay. `total_with_vat`, on every entry, is what the invoice itself is worth; the two differ when the supplier added an earlier balance or took off an advance, see [an invoice's value and what is left to pay](#an-invoices-value-and-what-is-left-to-pay).

`new_count` is every message saved. Of those, `received_count` are received invoices and `issued_count` are invoices the client issued; error messages and other messages from ANAF are in neither. `sync-all` answers the same three in total as `new`, `received` and `issued`, and for each client under the names above. The record of an automatic download (`last_run` in `GET /sync/schedule`) carries `new`, `received` and `issued` too; `received` and `issued` are `null` for a run that failed before counting, and missing from a record written by an earlier version.

Failure (from any command):

```json
{ "ok": false, "error": { "code": "login_needed", "message": "..." } }
```

| Exit code | Meaning |
|---|---|
| 0 | `ok` is true |
| 3 | `login_needed`: someone must plug in the token and log in |
| 1 | any other failure |

| Error code | Meaning |
|---|---|
| `login_needed` | No saved login, or ANAF no longer accepts it. |
| `login_code_expired` | The pasted address was too old or already used. Repeat the login. |
| `login_cancelled` | No certificate was chosen in Windows' window, or the time (five minutes) ran out. Try again. |
| `login_refused` | ANAF did not accept the certificate (`error=access_denied`). Waiting does not help: check the certificate and the token, then log in again. |
| `invalid_cui` | Not a CUI, or the check digit does not match. |
| `invalid_input` | A wrong or missing argument. |
| `no_spv_rights` | The certificate holder has no SPV rights for that company. |
| `anaf_limit_reached` | ANAF's daily call limit (e.g. 10 downloads a day per message): only that message fails. When ANAF limits every call (HTTP 429), the client's download stops there and what was saved stays. |
| `anaf_error` | ANAF refused or answered something unexpected; the message carries ANAF's text. |
| `network_error` | ANAF could not be reached. |
| `not_found` | No saved message with that id, or no client with that CUI in the list. |
| `client_off` | The client is switched off in the client list. Switch it on to download its invoices. |
| `busy` | Another sync or login renewal is running. For a restore or a wipe: a download, a classification, an update, a restore or a wipe is running. |
| `backup_error` | A copy could not be made, checked or put back; for a wipe, nothing was deleted. |
| `snapshot_too_new` | The copy was made by a newer version of the program than this one; update, then restore it. From the page and from `efactura restore`. |
| `config_error` | `config.toml` is missing or incomplete, or ANAF rejected the client ID/secret. In the certificate login: ANAF answered `invalid_client` (wrong Client ID) or `invalid_request` with "Redirect-URI ... does not match" (wrong Callback URL); the message keeps ANAF's words. |
| `not_classifiable` | The message is not an invoice (received or issued), cannot be read as one, is marked as uploaded, was saved outside classification, or is already classified. `force` lifts the last two. |
| `jev_error` | OpenRouter refused or could not be reached; the message says why (key, credit, rate limit). |
| `internal_error` | A bug. The details are in `data/efactura.log`. |

A `sync` in which some messages failed still has `"ok": true`; the failures are listed in `failed` and are retried on the next run. `possible_duplicate_of` is set when the same supplier and invoice number were already saved under another message id (ANAF treats a re-submitted invoice as a new message).

Letters outside ASCII are written as `\u....` escapes, so Romanian names are not damaged by the Windows console's code page. Nothing but the JSON is written to standard output; activity is logged to `data/efactura.log`.

## Local API

Start it with `uv run efactura serve` (or double-click `start.bat`). It listens on `http://127.0.0.1:8765` only, so other computers cannot reach it. Every route except `/health` needs the header `X-API-Key: <the key from config.toml>`.

The screen uses the same routes under `/api/...` and needs no key. That is safe because the program only accepts a keyless request when the browser itself marks it as coming from the program's own page (`Sec-Fetch-Site: same-origin`, which a page cannot fake) and it is addressed to `autosaga.localhost`, `127.0.0.1` or `localhost` on the program's port. A page from any other site, and any other program, still needs the key.

`http://127.0.0.1:8765/openapi.json` describes every route; any API tool can load it. FastAPI's interactive pages (`/docs`, `/redoc`) are switched off: they load their scripts from the internet, and on this address a page is trusted without a key.

| Route | Same as |
|---|---|
| `GET /health` | (no key needed) is the API running? |
| `GET /auth/status` | `auth-status`; also carries `certificate_login`, true where the certificate way is offered |
| `POST /auth/login/start` | `login-start` |
| `POST /auth/login/finish` with `{"address": "..."}` | `login-finish` |
| `POST /auth/login/certificate` | (the page's button) asks Windows for the certificate and saves the login; can last minutes, answers like `login-finish`; `invalid_input` where `certificate_login` is false |
| `GET /anaf/messages?cui=...&days=...` | `list` |
| `POST /sync` with `{"cui": "...", "days": 7, "classify": true}` (`days`, `classify` optional; or `"start"` and `"end"` dates; `"cover_gap": true` makes `days` a minimum) | `sync` |
| `GET /invoices?cui=...&pending=true&type=...&since=...&classification=...` | `invoices` |
| `GET /invoices/{id}?xml=true` | `invoice` |
| `POST /invoices/{id}/uploaded` | `mark-uploaded` |
| `DELETE /invoices/{id}/uploaded` | `mark-uploaded --undo` |
| `POST /invoices/{id}/classify` with optional `{"force": true, "ask": "jev_only", "line": 2, "per_line": true}` | `classify`. `ask` is `rules_then_jev` (the default) or `jev_only`; `per_line` `true` or `false` sets the invoice's shape; left out, an invoice on lines stays on lines and one with one account follows the client's switch |
| `POST /invoices/{id}/split` | `split` |
| `GET /invoices/{id}/decisions` | The history of the invoice's account, the newest change first: `at`, `source` (`download`, `again`, `redecide`, `person` or `split`), `line` (`null` for the whole invoice), `cont`, `method`, `reason`, and `said`: `rule`, `match`, what Jev said (`suggested_cont`, `confidence`, `confidence_threshold`, `probabilities`), `jev_only`, and `before` (`cont`, `method`, `rule` it had, or `null`) |
| `GET /review?cui=...` | `review` |
| `POST /invoices/{id}/cont` with `{"accept": true}` or `{"cont": "628"}` (optional `"force": true`, and `"line": 2` for one line of an invoice decided line by line) | `set-cont` |
| `GET /classification/settings` | `confidence` |
| `PUT /classification/settings` with `{"min_confidence": 0.8}` | `confidence 0.8` |
| `GET /classification/costs?since=...&until=...&group=...&cui=...` | `costs` |

Routes that exist for the screen and have no command:

| Route | What it does |
|---|---|
| `GET /clients`, `POST /clients` with `{"cui", "name"}`, `DELETE /clients/{cui}` | The client list. Each client has `invoices` and `new_count` (received), `issued_count` and `issued_new_count`, `review_count` and `ready_count` (both kinds), and `issued_review_count` |
| `PUT /clients/{cui}/enabled` with `{"enabled": true}` or `false` | Switch a client on or off |
| `GET /sync/schedule` | When the program downloads by itself: `enabled`, `days` (0 is Monday), `times`, `period` (`{"days": 7}`, or `{"start", "end"}`), `next_at`, the run in progress (`running`), the last run with its `retry_at`, and how many clients are on and off. Not written in the journal |
| `PUT /sync/schedule` with `{"enabled", "days": [0, 1], "times": ["08:00"], "period": {"days": 7}}` | Save the schedule (at most four times, `HH:MM`) and answer the same as `GET`. `period` is `{"days": 1 to 60}` or `{"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}`; left out, the stored period stays. Answers 400 for a schedule that makes no sense |
| `POST /clients/import?filename=clienti.xlsx` (the file as the body) | Add clients from Excel or CSV |
| `POST /invoices/uploaded` with `{"ids": [...], "uploaded": true}` | Mark several invoices as uploaded, or not |
| `GET /invoices/{id}/view` | One invoice: the row, the parsed invoice (each line with `description`, its name, and `details`, its description when it says more), both XML texts, Jev's answer, and `rule_suggestion` (the rule proposed from it, with the line's `details`, or `null`) |
| `GET /rules`, `POST /rules`, `PUT /rules/{id}`, `DELETE /rules/{id}`, `POST /rules/{id}/move` | The classification rules. A rule has `direction`, `received` or `issued`; left out, a new rule is for received invoices and a replaced one keeps its own. A rule for issued invoices cannot name a supplier. A rule moves only among the rules of its kind. `GET /rules` also has `issued_accounts`, `jev_issued_instructions` and `jev_issued_line_instructions`, and `jev_configured`, whether an OpenRouter key is set |
| `GET /rules/suggestions` | Rules proposed from the decisions of the last 90 days that no rule made: for each, the account, the `keywords` or `supplier_cuis` to look for, the invoices behind it, and how it would have done (`matches`, `by_cont`) |
| `POST /rules/preview` with `{"keywords": [...], "supplier_cuis": [...], "client_cui": ...}` (all optional, as are `item_codes` and `commodity_prefixes`) | How a rule with these conditions would have done on the invoices given an account in the last 90 days. Saves nothing |
| `POST /rules/test` with `{"lines": [{"description", "quantity", "unit_price", ...}], "supplier_name", "supplier_cui", "client_cui", "currency", "credit_note", "ask": "rules_then_jev" or "jev_only"}` (only `lines` is required, and in a line only `description`, what is written on it; a line may also carry `details`, its description, `seller_code`, `barcode`, `commodity_codes`, `unit`, `vat_percent` and `value`, its value without VAT, which is quantity × price when missing) | Put a made-up invoice through the same path as a received one: line by line (`per_line: true`) when no client is given or the client has an account per line, otherwise one account by the largest line. `lines` holds each line (for one account per invoice, the line that decides): `line`, `description`, `details`, `value`, who decided (`rule`, `jev`, `follows` for a discount that takes the largest line's account, or `nobody`), `cont`, `account_description`, `rule` (its `name`, the `condition` the line meets: `keyword`, `supplier_cui`, `seller_code`, `barcode` or `commodity_code`, what was `found`, the `prefix` of a classification code, for a keyword the words `matched` and whether they are `in_details`, `client_only`, and `also`, the rules further down that match too), `jev` (its choice, confidence, the level, `refused`, `probabilities` for every account offered and `altul` for none of them, cost, duration, error, `http_status`, OpenRouter's answer, `null` when it was not reached, and `sent`, the question and what it was asked about), `why_not`, `follows` and `same_as` (an earlier line that says the same; Jev was asked once). Beside them: `accounts` (what Jev chose from), `jev_calls`, `cost_usd`, `waiting` (lines without an account), and the rule worth creating, with `from_line`. `decided_by`, `cont`, `rule`, `jev` and `why_not` at the top are the largest line's; line by line, `cont` is there only once every line has an account, and `why_not` is `lines_left` when another line waits. Saves nothing but the cost of asking Jev, which counts in the costs but not as an invoice |
| `POST /rules/suggestions/dismiss` with `{"invoice_ids": [...]}` | "Nu acum": stop proposing a rule for these invoices |
| `PUT /accounts/{cont}` with `{"description"}` (and `"kind": "issued"` for issued invoices), `DELETE /accounts/{cont}` (with `?kind=issued`) | The accounts Jev chooses from, for each kind of invoice |
| `PUT /classification/settings` with `{"min_confidence", "jev_instructions", "jev_line_instructions", "jev_issued_instructions", "jev_issued_line_instructions"}` | The confidence level, the question for Jev about a whole invoice and the one about a line, and the same two for issued invoices |
| `PUT /clients/{cui}/per-line` with `{"enabled": true}` or `false` | An account for each line of this client's invoices, or one for the whole invoice |
| `POST /clients/{cui}/classify-again` with optional `{"jev": false}` | `classify-again`, for one client. Answers `{"cui", "client", "total", "classified", "review", "waiting", "skipped", "jev_asked", "jev_stopped", "jev_calls", "jev_cost_usd"}` |
| `GET /classification/calls?since=...&until=...&cui=...&limit=...` | What Jev was asked, newest first |
| `GET /settings`, `PUT /settings` with `{"saga_folder", "saga_file_per", "show_issued"}` | The folder for SAGA, whether it gets one file per `"client"` or one per `"invoice"`, and `show_issued` (`true` or `false`), which an earlier version used to show [issued invoices](#issued-invoices) and which now changes nothing. Any field may be left out and then stays as it is; nothing is saved unless all of it is valid. When a setting for SAGA is given, what waits for SAGA is written again. The reply to `PUT` adds `problems`: the clients whose files could not be, an empty list when nothing was written |
| `POST /saga-files/write` with `{"cui"}` or `{}` | Bring the files for SAGA up to date, for one client or for all. Answers `{"clients", "problems": [{"cui", "message", "at"}]}` |
| `GET /saga-files`, `GET /saga-files/{cui}` | What waits for SAGA: every client with a file, or one client. Each has `cui`, `client`, `file_per`, `folder` (the client's folder, `<SAGA folder>\<name> - <CUI>`), `files` (`name`, `path`, `invoices`, `ids`, `written_at`, and `present`: still in the folder), `invoices`, `up_to_date` and `version`, a fingerprint of the files on disk |
| `GET /saga-files/{cui}/files/{name}` | One of the client's waiting files, as it is in its folder now (XML). Only the files the program wrote for that client are served; 404 for any other name, and for a file gone from the folder |
| `POST /saga-files/{cui}/imported` with `{"version"}` or `{}` | SAGA imported the client's files: mark every invoice in them as imported and move the files to the archive. Answers `archive` (`id`, `cui`, `imported_at`, `source`, `invoices`, `ids`, `folder`, `files`), `null` when nothing was waiting. 409 `saga_files_changed` when the files changed since `version`, 409 `saga_files_stale` when they are not up to date; then nothing is marked or moved |
| `GET /saga-archive?cui=`, `GET /saga-archive/{id}` | A client's confirmed imports, the newest first, each with `invoices`, `received`, `issued`, `unmarked` and `files` (`name`, `path`, `present`); one import with its `invoices` as the lists give them |
| `GET /saga-archive/{id}/files/{name}`, `POST /saga-archive/{id}/open` | A file of a confirmed import as SAGA got it; show the import's folder |
| `POST /settings/choose-folder?purpose=saga` (or `backups`), `POST /folders/open` with `{"invoice_id"}` or `{"cui"}` | Open the computer's folder dialog, titled for the SAGA folder or the backup folder and starting there; show in Explorer the folder an invoice's SAGA file is in, or a client's folder |
| `GET /secrets`, `PUT /secrets/{key}` with `{"value"}` | The keys, in full |
| `POST /shutdown` | Stops the program (what `efactura stop` calls). With the key only; the page cannot reach it |
| `GET /update?check=true` | The installed release, the newest one, whether an update exists and how the last update ended. `check` asks the remote now |
| `POST /update` | Starts the update as a process of its own and answers at once; the program stops and comes back on the new release |
| `GET /backups` | The backup folder and whether it is there, the copies kept (newest first), the limit, when the last was made and the next is due, the last failure, and how the last restore ended |
| `PUT /backups/folder` with `{"folder"}` | Choose the backup folder (a whole path; made if missing) |
| `POST /backups` | Make a copy now (`backup`) |
| `POST /backups/restore` with `{"name"}` | Starts the restore of that copy as a process of its own and answers at once; the program stops and comes back with the restored database. `name` is a file in the backup folder, never a path. Answers `busy` while invoices are being downloaded or classified, an update runs or the data is being wiped, and `snapshot_too_new` for a copy made by a newer version |
| `POST /backups/wipe` | Makes a copy, checks it, then deletes every client, invoice, account and rule; answers `{"ok", "kept_as", "kept_at", "deleted"}` with the copy's name and time and how many rows each table lost. `busy` (something was running, or changed while the copy was made: try again) or `backup_error` (the copy could not be made or checked) when nothing was deleted (see [Backups](#backups)) |
| `POST /backups/open-folder` | Show the backup folder in Explorer |
| `GET /events?details=true&problems=true&area=...&q=...&since=...&trace=...&before=...&limit=...` | The journal, newest line first, 200 at a time (`before` is the `id` of the last line read; `has_more` says whether older ones exist). `problems` keeps warnings and errors; `trace` gives one whole operation |
| `GET /events/export` with the same filters | Every line that matches, as a text file. `details` is true here unless `details=false` is sent; `technical=true` adds one line per technical record of those operations |
| `GET /events/technical?trace=...&before=...&limit=...` | The [technical side](#the-technical-view) of the journal: requests to ANAF and Jev and the program's debug records, newest first, 500 at a time (at most 2,000), without their bodies. `GET /events?technical=true` adds `technical`: for each operation on the page, `{"http", "problems", "log"}` |
| `GET /events/technical/{id}` | One technical record whole: `body.request` and `body.response` (`headers` as pairs, `body` as kept), or `body.exception` |

The body is the same JSON the command prints. Every answer carries an `X-Trace-Id` header: the number under which the journal holds what that request did. HTTP status: 200 success; 400 bad input; 401 missing or wrong key; 404 unknown id or route; 409 `login_needed`, `login_code_expired`, `login_refused`, `login_cancelled`, `busy`, `not_classifiable`, `update_error`, `backup_error` or `snapshot_too_new`; 502 ANAF or OpenRouter refused or was unreachable; 500 a bug or a settings problem.

## Testing the rules

The button "Testează regulile" on "Reguli de clasificare" opens a screen of its own (`#/reguli/test`), with a link back to the rules. On it a person writes a trial invoice (an optional client, the supplier's name and CUI, and lines with what is written on them, quantity and price without VAT; under "Mai multe de pe factură" each line can also carry its description and codes) or starts from an empty one, a saved invoice of the chosen client, or one of two examples.

A blank quantity counts as 1 and a blank price as 0, so a line with a description alone is enough to try a rule on a word. Numbers are read as they are written in Romanian: spaces between the digits are dropped ("12 000"), and when there is a comma it is the decimal point and the dots group thousands ("1.234,50" is 1234.50); without a comma a dot is the decimal point ("28.50"). The program reads them the same way when another program calls the route. A number that still cannot be read is refused, and the screen says how numbers are written.

A trial started from a saved invoice is that invoice: each line's description and codes (supplier's code, barcode, CPV or NC codes) are filled in and shown, and "Mai multe de pe factură" opens by itself; each line's unit code, VAT rate and value, and the invoice's currency and kind (invoice or credit note), are kept without being shown. The value is kept because it is not always quantity × price (a line discount, a price per several units), and the line with the largest value is the one the rules read. Changing a line's quantity or price drops its kept value. So an unchanged trial puts the same questions to the rules and to Jev as the real invoice did.

**Line by line, as the program decides.** With no client chosen, or a client whose invoices get an account per line (the default), each line of a trial with more than one line is decided on its own, as a real invoice is: the rules first; a discount or a line worth nothing takes the account of the largest line; Jev for the rest, one question per distinct line. For a client switched to one account per invoice, the trial is decided by its largest line, and Jev is asked about the whole invoice. The note under the client says which.

Two buttons answer:

- **"Vezi ce cont primește"** does what the program does with a real invoice: the rules first, and Jev is asked only if no rule fits.
- **"Întreabă-l direct pe Jev"** skips the rules and asks Jev.

The answer says first whether a real invoice would get its accounts by itself, which lines would wait, and what asking Jev cost. Then each line: its account and why. For a rule, which of its conditions the line meets ("pe linie scrie „motorina”", "în descrierea liniei scrie „tonercartus”, iar regula caută cuvinte care conțin „cartus”", the supplier's CUI, the article code or barcode, the start of a classification code), whether it is for one client only, and which rules further down would have matched too. For a discount, that it takes the largest line's account. For Jev, how sure it is against the confidence level, and, folded under "Ce a spus Jev", how likely it found each account (with what the account is for, "Niciunul din listă" included), what the question cost, and, folded once more, exactly what it was sent: the question, the supplier, the invoice and the line, and the accounts. Jev writes no reasons; those figures are what it says. The three ways Jev leaves a line without an account are told apart: none of the accounts fits, Jev refused (a refusal carries nothing else), or Jev named an account without saying how sure it is. Last comes the rule worth creating, from the largest line Jev named an account for, shown as the card an invoice's screen shows; the card goes once its rule is made, by either of its buttons. With the second button on an invoice that a rule already fits, no rule is proposed. When OpenRouter refuses the question (HTTP 401, 402 or 403), the screen says to check the OpenRouter key and the credit, not to try again later.

**What is saved.** No invoice, no SAGA file, no proposed rule. Only each call to Jev is written, in the table of Jev calls, with the marker `rule-test` in place of an invoice id (and the client's CUI if one was chosen). So its cost is in the total of "Costuri Jev", where the list shows it as "Probă de reguli"; it is not counted as an invoice and is left out of the average cost per invoice. One line, `rule.tested`, goes to the journal. Jev is asked once per question, with no second attempt, so a failure is seen at once; each question is its own row in "Costuri Jev".

**Limits.** At most 50 lines, 500 characters in a line's text or description, and numbers of at most 15 digits before the decimal point and 20 after it; more is refused as bad input.

**Route.** `POST /rules/test`, see [Local API](#local-api).

## Classification and SAGA

SAGA C does not read ANAF's XML. Its import ("Import date din fișiere XML") reads SAGA's own layout, which has an account (`<Cont>`) on every line. So each invoice, received or issued by the client, is given an account and rewritten in that layout. Issued invoices have accounts, rules and questions of their own: see [issued invoices](#issued-invoices).

**An account for each line, or one for the whole invoice.** Each client in the list has the switch "Clasificare pe fiecare linie", on to begin with (also for the clients of an earlier version). With it on, every line of an invoice gets its own account; an invoice of a single line is decided whole, as before, since one line is one account. With it off, the line with the largest value decides one account for the whole invoice, as before. A company that is not in the client list is decided the old way. The switch holds for invoices decided from then on; an invoice that already has its account keeps it until it is classified again (`POST /invoices/{id}/classify` with `force`).

**How the account of a line is decided** (switch on)

1. **Rules.** Each line is checked against the rules written on the "Reguli de clasificare" screen, on its own: its name and its description (see below). A rule belongs to every client unless it names one; a client's own rules are checked first. A rule on a supplier gives every line of that supplier its account.
2. **The largest line.** A discount (a line whose value has the other sign than the largest line's) and a line worth nothing take the account of the invoice's largest line, unless a rule matches them. Jev cannot judge "Discount" on its own. A line of the other sign that is not a discount ("Storno avans", an advance invoiced earlier) is treated the same way and goes to SAGA on the largest line's account: write a rule on its words ("avans", "storno") if such lines belong on another account.
3. **Jev.** Each line left is sent to the Jev decision model on OpenRouter, on its own, with the question about one line set on the rules screen. Lines with the same words, codes and unit are one question. Jev is sent the supplier and that line, never the other lines or the buyer.
4. **Review.** A line waits for a person when Jev's confidence is below the confidence level (0.80 until you change it), when Jev finds that no account fits or gives no usable answer, or when no OpenRouter key is set. Only that line waits; the others keep their accounts. The invoice is "de verificat" until every line has an account, and only then goes into the file for SAGA. When the same invoice (supplier, number and date) is already saved under another ANAF id, every line waits.
5. **When OpenRouter fails as a whole** (no connection, key refused, no credit, too many requests), the invoice waits for the next download, with the lines decided so far. The next download asks Jev only about the lines it has not answered, so a long invoice is not paid for again from the start; the invoices after it are not sent to Jev in that run. Classifying an invoice again on purpose asks about every line afresh.

**One account for the whole invoice** (switch off): the rules read the largest line; if none matches, the invoice is sent to Jev with the question about a whole invoice; it waits for a person on the same grounds as above.

**Cost.** With the switch on, Jev is asked once per distinct line no rule decides, where before it was asked once per invoice. Rules are what keeps that down; "Costuri Jev" shows each call.

**What other programs see.** Every invoice returned carries `line_accounts`: `null` for an invoice on one account, otherwise one entry per line with `line` (its number on the invoice), `cont` (or `null` while it waits), `method` (`rules`, `jev`, `jev_accepted`, `human`, or `follows` for a line that takes the largest line's account), `rule`, `reason`, what Jev said (`suggested_cont`, `confidence`, `confidence_threshold`, and `probabilities`, how likely it found each account) and `asked` (whether Jev was asked about the line), and `match` (which condition of the rule the line meets: `condition`, `found`, `prefix`, `matched`, the words it found, and `in_details`, found in the description; `null` otherwise, and missing on lines decided before 0.14.0). `method` is also `invoice` for a line that kept the whole invoice's account when a person split it into lines. While an invoice waits after OpenRouter failed, `line_accounts` holds the lines decided so far. `cont` and `classification_method` of the invoice are those of its largest line, and `cont` is set only once every line has an account. `POST /invoices/{id}/cont` and `set-cont` take `line`; without it every line gets the account, or, with `accept`, every line left gets Jev's proposal for it. On an invoice with one account, `line` is refused: split it into lines first (`split`).

**A new database starts with examples.** Three example accounts and two example rules are put in once, so there is something to look at. Replace them on the "Reguli de clasificare" screen with the accountant's real ones; deleted examples do not come back. The accounts must exist in the company's chart of accounts in SAGA.

A rule matches a line when any of its conditions holds: a keyword in the line's name or its description (case and diacritics ignored, whole words; a `*` stands for any letters where it is: `transport*` starts with, `*cartus` ends with, `*cartus*` contains; a `*` in the middle is a plain character, and a keyword of stars alone is dropped), the supplier's CUI (with or without `RO`), the supplier's article code, or the start of a CPV/NC code.

**A line's name and its description.** An e-Factura line has a name (`cbc:Name`) and may have a description (`cbc:Description`). The rules look for their words in both, each a text of its own, so a phrase never runs from the name into the description. Jev is sent the description beside the name (`detalii` beside `descriere`), only when the line has one, so a line without one is sent as before; two lines with the same name and different descriptions are two questions. A description that says what the name says, case and diacritics aside, is left out. The screen shows it under the name. The file for SAGA keeps the name alone in `<Descriere>`, as before (the description when there is no name). Proposed rules take their words from the name, then from the description. Invoices decided before 0.14.0 kept no description for proposed rules; they take part with it once decided again.

**Proposed rules.** When no rule decided an invoice (Jev chose the account, a person accepted Jev's proposal, or a person chose it), the program proposes the rule that would have decided it. The proposal is on the invoice's screen and under "Reguli propuse" on the rules screen; the menu shows how many there are.

- **What it looks for.** A word from the invoice's largest line, its name first, then its description: the first one that tells what was bought. Numbers, units of measure, link words, month names and words about the document ("nr", "conform", "contract") are never offered, nor is a word joined to digits ("Office365"), because a keyword has to stand as a word of its own; general words such as "servicii" or "abonament" are offered but not ticked. When the line says nothing telling ("Servicii conform contract"), the proposal is for the supplier instead. On the invoice's screen the person can tick other words (the rule then matches any of them) or choose the supplier. The two word lists are in `src/efactura/suggestions.py`; they are a judgement, to adjust once real invoices show what they miss.
- **How it would have done.** Each proposal says how many of the invoices given an account in the last 90 days it matches, and on which accounts those are. All on the proposed account is shown in green; anything else in orange, to check before creating it.
- **Creating it** adds an ordinary rule for every client, at the end of the list. "Schimb-o întâi" opens it in the rule window first, for instance to limit it to one client. No saved invoice changes: the rule applies from the next download.
- **When it goes away.** As soon as any rule in force for that client matches the invoice, however that rule was made. "Nu acum" hides the proposal for those invoices until their account changes (choosing the same account again keeps it hidden); a later invoice of the same kind brings it back.
- **Limits.** The rules screen lists proposals from decisions made in the last 90 days, the ones with most invoices first, 20 at most. An invoice that got its account before this feature existed takes part only after its account is chosen again.

**Only new invoices are classified.** An invoice enters classification at the moment `sync` saves it. Invoices already in the database, and those saved with `--no-classify`, are never classified automatically; `classify <id> --force` does one on request. Use `sync <CUI> --days 60 --no-classify` for a first run that brings in invoices already booked by hand. One exception, once: at the first start of 0.11.0 the issued invoices saved before, `--no-classify` ones included, start waiting (see [issued invoices](#issued-invoices)); tick as imported those SAGA already has, or let its "Nr.+data" skip them.

**States** (`classification_status`)

| State | Meaning |
|---|---|
| `null` | Outside classification: saved before it existed or with `--no-classify`, not an invoice, or one that cannot be read (`classification_error` says why) |
| `pending` | Waiting. OpenRouter as a whole was failing (no connection, key, credit, rate limit); the next `sync` tries again. After such a failure the rest of that run is not sent to Jev either |
| `classified` | Account decided. The invoice is in a file for SAGA until it is marked as imported. `classification_method` says how: `rules`, `jev`, `jev_accepted` (a person accepted Jev's suggestion) or `human` |
| `review` | A person must decide |

Each invoice also carries `cont`, `classification_reason`, `suggested_cont` and `confidence` (Jev's pick and how sure it was), `confidence_threshold` (the level at the time), `saga_xml_path` (the file for SAGA the invoice is in while it waits for import, else `null`) and `classification_error`.

**Review**

```bash
uv run efactura review
```

lists the invoices to decide, each with Jev's suggestion, its confidence and the probability it gave every account. For an invoice decided line by line these are per line, in `line_accounts`, and `jev_probabilities` is `null`. Then either

```bash
uv run efactura set-cont 3001234567 --accept
```

```bash
uv run efactura set-cont 3001234567 --cont 628
```

Any account number is accepted, so analytic accounts such as `371.01` work. `set-cont` also corrects an invoice that is already classified; the SAGA file is rewritten.

An invoice marked as uploaded is left alone: `classify` and `set-cont` refuse it until the flag is cleared (`mark-uploaded <id> --undo`), and it no longer appears in `review`.

**The confidence level** is kept in the database, not in `config.toml`, so a flow can change it:

```bash
uv run efactura confidence 0.9
```

It starts at 0.80, which is a guess. `suggested_cont` and `cont` are both kept, so once some invoices have been reviewed you can compare what Jev suggested with what the accountant chose and move the level.

**Costs.** Every request to Jev is stored in the table `jev_calls`: the request, the reply, the tokens, the cost in USD, and the error if it failed. The API key is never stored.

```bash
uv run efactura costs --since 2026-11-01
```

gives calls, tokens and cost in total and per month (`--group` changes that to day, week or year), and the average per invoice. Jev charges for input tokens only (USD 0.042 per million when this was written; check [OpenRouter's model page](https://openrouter.ai/typesafe/jev-1.14)).

**What is sent to OpenRouter:** the supplier's name and fiscal code and, per line, its name and description, the supplier's article code, classification codes, unit, quantity, value and VAT rate. Not sent: your client company, addresses, bank accounts, phone numbers, e-mail addresses. For an invoice the client issued, not even a party: only its kind, its currency and its lines.

**Setting it up:** create a key at <https://openrouter.ai/settings/keys>, add credit, and put the key in `config.toml` under `[openrouter] api_key`. Without a key the rules still work and everything else goes to review.

**The SAGA files**

- **What a client's folder holds:** exactly the invoices SAGA has not got yet, which are those with an account that are not marked as imported. Nothing else the program wrote stays there, so SAGA's import screen lists only what is new.
- **One file per client** is the usual way: `data/SAGA Import/<name> - <CUI>/F_<supplier code>_<number>_<date>.xml` holds all of the client's waiting invoices, one `<Factura>` after another, the one that has waited longest first. SAGA's manual allows it (several invoices are imported at once by repeating `<Factura>`). The file carries the name of its first invoice, because that is the one shape of name SAGA has been seen to take for a file of many: the owner imported 100 invoices of one client that way on 2026-11-16. So the name changes when the first invoice leaves the file.
- **One file per invoice** is the other way, chosen in the "Folder SAGA" window or with `PUT /settings` and `{"saga_file_per": "invoice"}`. Each waiting invoice then has a file named after it. Characters a file name cannot hold are replaced by `-`. If two invoices would get the same name (`AB 12` and `AB/12`, or names differing only in letter case), the later one has its ANAF message id added to the number. Exactly one of the two ways is in force; choosing the other writes again what is waiting, for every client.
- **When the files are written:** after anything that changes what is waiting. That is a download's classification, an account chosen or changed, an invoice sent back to checking, the "imported" mark put on or taken off, a change of folder or of way, and once at every start of the program, which also covers an update and a backup put back. A file that already says the same is left alone.
- **Marking as imported takes the invoice out of its file.** When all are marked, the folder is empty until new invoices arrive. Taking the mark off puts the invoice back.
- **When the folder cannot be brought up to date** (a file is open in SAGA, the stick is unplugged, anything else goes wrong): the account stays as decided, the journal gets a line, and the client's screen says the folder is not up to date and offers "Încearcă din nou". Until it is, nothing is marked as imported from the client's list or from an invoice's screen, so that no invoice SAGA never got is marked; `mark-uploaded` and the API still do as they are told. The program tries again by itself at the next change and at the next start.
- **A folder that cannot be reached** (the stick is out) is not taken for an empty one: the files written there stay on record, and are removed once the folder is back. Only a folder that was left behind, by choosing another one while it could not be reached, is let go with what is in it.
- **Only its own files.** The program keeps a list of the files it wrote (table `saga_files`) and removes only those. A file put in the folder by hand is never touched.
- **A client's folder is named after the client and its CUI:** `Alfa Construct SRL - 12345674`.
  - What Windows refuses in a folder's name is taken out of the client's name: `/` and `\` become `-`; `: * ? " < > |` and control characters become a space; several spaces become one.
  - Spaces around the name and dots before it are dropped, and the name is cut to 60 characters, so the whole path stays within what Windows takes.
  - A name Windows keeps for a device (`CON`, `PRN`, `AUX`, `NUL`, `COM1`…`COM9`, `LPT1`…`LPT9`, also before a dot: `AUX.IT SRL`) gets a `_` in front.
  - The folder's name always ends with ` - <CUI>`, so a client's folder is found by its CUI (`* - 12345674`), whatever the client is called. `GET /saga-files/{cui}` and `saga-files <CUI>` answer it as `folder`.
  - A company that is not in the client list has a folder named by its CUI alone. A client taken off the list keeps the folder it had.
  - `POST /folders/open` with `{"cui"}` gives the client's folder its name of now before it shows it.
- **A renamed client's folder is renamed at once**, on screen ("Adaugă un client" with the same CUI) or from an imported client list.
  - The folder is renamed whole, so a file put there by hand goes with it, and the program's files are on record in their new place. A name changed only in capital letters is a rename too.
  - If the folder cannot be renamed (SAGA has one of its files open, another program holds it, both folders are there), the files are written in the new folder and removed from the old one, one by one. A file the program did not write is never deleted.
  - An old folder that is still there afterwards (it holds someone else's file, or another program holds it) is kept in mind and tried again at every later write and at every start: renamed whole if the new one is not there yet, removed once it is empty. The journal says once that it was left, and why. Until it goes, two folders end with the client's CUI.
  - A folder renamed by hand in Explorer is found by the CUI at the end of its name and given the client's name again. To call the folder something else, rename the client.
  - If the folder for SAGA cannot be reached at all (a stick taken out, a share that does not answer), nothing is moved and nothing on record changes; the client's screen says the folder is not up to date, and the move is made at the next try.
  - If the program is stopped, or the database refuses, between renaming a folder and noting where its files now are, the files are found in the renamed folder at the next write and put on record there before anything else is done.
  - Each move is a journal line, `saga.folder_moved`; a folder left behind is `saga.folder_left`.
- **Coming from 0.14.0 or earlier,** where a client's folder was named by its CUI alone (`SAGA Import\12345674`): at the first start every such folder of a client in the list is renamed once, with everything in it, also when it is empty. **What points at the old folders from outside the program has to be changed by hand:**
  - in SAGA, the import folder of each company ("Import date"), which now is `...\SAGA Import\<name> - <CUI>`;
  - in Power Automate, any flow that builds the path as `<SAGA folder>\<CUI>`. Let it look for the folder that ends with ` - <CUI>`, or ask the program (`GET /saga-files/{cui}` answers `folder`, and each file's `path`). The flow in [PAD Flows/flow-main.txt](PAD%20Flows/flow-main.txt) was changed this way (the folder that ends with ` - <CUI>`, and failing that the folder named by the CUI alone); that change has not been tried in Power Automate.
- **Coming from 0.6.1 or earlier:** at the first start, each client's waiting invoices are written the new way and the single-invoice files of the earlier version are removed, those of imported invoices too. Nothing is lost with them: an invoice's screen still shows its part for SAGA, made from the database.
- One folder per company on purpose. SAGA files an invoice under purchases whenever the supplier is not the open company, so a file imported into the wrong company would become a purchase there. Point SAGA's import screen at the folder of the company that is open.
- In SAGA, open the "Import date" screen and choose the folder. Synchronising on "Nr.+data" skips invoices already imported. Imported invoices are not validated; the accountant checks and validates them, and can still change the account there.
- Lines are imported on the type "Nedefinit" with the account. The supplier's article codes are left out so that SAGA does not match a stock article and take the account from it.
- VAT per line is calculated (ANAF's file has none). Where rounding line by line drifts from the invoice's VAT total, the gap is closed one cent per line, largest lines first, so the lines add up to the invoice and none moves by more than a cent. Invoice-level discounts and charges become extra lines. Credit notes are written with negative amounts.
- Quantity × price always gives the line value. ANAF's value already includes a discount on the line while its price does not, so in that case the price is written as value ÷ quantity. A line without a quantity is written as one unit at its value.
- SAGA's own e-Factura screen also lists the same invoices from SPV. Import each invoice one way only.
- To list the invoices waiting for SAGA: `uv run efactura invoices --classification classified --pending`. Each carries `saga_xml_path`, the file it is in; with one file per client they share it. After importing, `mark-uploaded <id>`.
- `GET /invoices?cui=...` and `GET /invoices/{id}/view` also answer `saga`, how that client's files stand: `{"file_per", "written_at", "problem"}`, where `problem` is `null` or `{"message", "at"}`.

### The files waiting for SAGA, on screen

**The "Fișiere pentru SAGA" tab** of a client's screen shows every file in the client's folder that still has to be imported. Its number is the number of files: one with a file per client, one for each waiting invoice with a file per invoice.

- **Each file** has its name, when it was written, its full path with "Copiază calea" and "Deschide folderul", how many invoices it holds and what they are worth together. The total is given by kind when the file holds received and issued invoices, and each currency has its own total.
- **"Vezi XML-ul"** opens the file as it is in the folder now, laid out as on an invoice's screen, with "Copiază XML-ul", which copies it exactly as it is on disk.
- **The table of its invoices** has the number (a link to the invoice), the kind, the supplier or the customer, the date, the total and the account, 25 invoices a page.
  - Each column's heading orders the table: text from A to Z and back (numbers inside a text in their own order, `FV-9` before `FV-10`), totals from the smallest, dates from the oldest, accounts as a chart of accounts lists them (`6022` before `626`). The order covers every invoice of the file, not only the page shown. "Înapoi la ordinea din fișier" returns to the order SAGA gets them in; the order on screen never changes the file.
  - The arrow in front of an invoice shows its lines in the rows under it, 10 a page: number, name and description, quantity, value, VAT and account, and then each discount or charge on the whole invoice, which SAGA gets as a line of its own.
- **An account is changed from an open invoice.** Where each line has its account, "Schimbă" on a line opens the window of the invoice's screen (the list of accounts and Jev's proposal), and "Același cont pe toate liniile" changes them all. Where the invoice has one account, "Schimbă contul" changes it. Only an account is chosen here; deciding again with the rules and Jev stays on the invoice's own screen ("Deschide factura"), because it can leave a line without an account and so take the invoice out of the file.
- **After a change the file is written again**, as after any change of account. If it had been imported into SAGA already, import it again; "Da, am importat" refuses when the file has changed since the page was opened.
- **A file gone from the folder** is marked "Fișierul lipsește din folder", and the tab says the folder is not up to date; "Încearcă din nou", under the files, writes it again.
- Under the files is the same card as under the lists of invoices, with "Da, am importat".

### Classifying again

An invoice stays "de verificat" (or "Așteaptă contul", when OpenRouter did not answer) until a person decides it. A rule added afterwards does not reach it by itself. "Clasifică din nou facturile de verificat" on a client's screen, and "Clasifică din nou, la toți clienții" on the client list, send these invoices back through the same steps as a download: the rules, then Jev, then a person. Use it after adding or changing a rule, after changing the accounts or Jev's questions, or once OpenRouter answers again.

- **What is classified again:** the client's invoices, received and issued, that are "de verificat" or waiting for Jev and not marked as imported in SAGA. Invoices with an account are not touched.
- **What stays:** a line a person chose keeps its account, and Jev is not asked about it; a line Jev was sure of keeps its account unless a rule now matches it. Jev is asked again only about the lines that have no account.
- **"Întreabă-l din nou și pe Jev"**, ticked to begin with. Unticked, only the rules run: free, in seconds, and what Jev said before stays, its proposal included; an account a rule gave that no rule gives now does not stay; an invoice waiting for Jev goes on waiting. When OpenRouter stops answering partway through an invoice, the lines Jev answered are kept, so they are not paid for again. Ticked, each question to Jev is paid again, and an invoice Jev was unsure of is often unsure again when nothing about it changed.
- **Still to check either way:** an invoice saved twice, and one whose parties do not fit its kind; the program holds them back on purpose.
- **For every client**, the page takes the clients one at a time and shows how each went. When Jev stops answering (credit, key, connection), the invoices after stay as they were and the clients after are classified with the rules alone.
- **The journal** gets one line per client ("classification.again"); an invoice that gets an account has its own line, as always, and one that stays "de verificat" is a detail.
- **While a download runs** it is refused with `busy`, and the other way round: the two take turns.
- **The per-line switch.** An invoice decided line by line stays so, whatever the client's switch says now: a person may have split it. The lines a person chose, and those kept from the invoice when it was split, keep their accounts.

### Changing an account, splitting an invoice into lines, deciding again

- **Another account** for the whole invoice is "Schimbă contul" on its card; for one line of an invoice decided line by line, "Schimbă" on that line. Received and issued invoices alike, each with the accounts of its kind.
- **"Împarte pe linii"**, on an invoice that has an account, more than one line and is not imported, turns it into one decided line by line, whatever the client's switch: at once and at no cost. The largest line keeps how the account was chosen (the rule and what it found, or Jev, or a person); a discount or a line worth nothing takes the largest line's account, as always; every other line keeps the invoice's account as its own ("contul facturii, păstrat la împărțire", method `invoice`). The file for SAGA says the same until a line gets another account. Then each line is changed by hand or decided again, one by one. There is no way back to one account; "Pune același cont pe toate liniile" gives SAGA the same file.
- **"Hotărăște din nou…"** on the account card opens a window with two ways: "Cu regulile, apoi Jev", as a download does, or "Doar cu Jev", which skips the rules. The invoice is decided from the start, the lines a person chose included, and keeps its shape: one decided line by line stays so, one with one account stays whole. With "Doar cu Jev", a discount still takes the largest line's account. Without an OpenRouter key, "Doar cu Jev" is off and says why.
- **One line decided again**, in the line's window, under "Sau hotărăște din nou această linie": the same two ways, for that line alone; the other lines stay as they are, except those that follow it when it is the largest. "Doar cu Jev" asks Jev about that line whatever it is, a discount included. A line that only follows the largest line has nothing of its own to decide, so its window offers the choice of an account alone. An invoice held back for a person (the same invoice saved twice, or parties that do not fit its kind) stays held back: the line waits for a person, with the reason; choosing its account by hand is the way past it.
- **When Jev fails** as a whole (no connection, key, credit), the invoice stays as it was and the screen says why; nothing is written in its history.
- **An invoice imported in SAGA** keeps its account here, since SAGA has it already. Its card says how to change it all the same: delete it in SAGA, untick "Am importat factura în SAGA", choose the account, import it again. `classify`, `split` and `set-cont` refuse it until the mark is taken off.

### The history of an invoice's account

The tab "Cum s-a ales contul" on an invoice's screen shows every change of its account, the newest first: when, and how ("La descărcare", "Clasificată din nou", "Hotărâtă din nou: regulile, apoi Jev" or "doar Jev", "Ales de dumneavoastră", "Împărțită pe linii de dumneavoastră"). Under each, the lines that changed (or the whole invoice, for one with one account), each with its account and why: the rule and what it found, in the name or the description ("în descrierea liniei scrie „cartuse”, iar regula caută cuvinte care conțin „cartus”"); Jev's choice and how sure it was against the level, with, folded, how likely it found each account; what Jev proposed for a line that waits, or why nobody could choose; and what the line had before. Lines that got the same thing at once are one row; a change of more than 6 rows shows 6 and "Arată toate".

- **Written** when an account, or the lack of one, actually changes: a "Clasifică din nou" that leaves forty invoices as they were writes nothing, nor does one where Jev is only a little more or less sure than before. What a person asked to have decided again is written even when it comes out the same. The words a rule found are shown as the line writes them, diacritics included.
- **Kept** in its own table, `decisions`, as long as the invoice, not in the journal, which is emptied after 30 days. Restoring a copy of the database brings back the history as it was then. Jev's full answers stay in `jev_calls`.
- **Invoices decided before 0.14.0** have no history; theirs starts at their next change.
- **Route:** `GET /invoices/{id}/decisions`.

## Using it from Power Automate Desktop

These steps have not been tried in Power Automate from the machine this was built on; the action names are the standard ones.

**As a command**

1. *Run DOS command*: command `uv run efactura sync 12345674`, working folder = this folder. It produces `CommandOutput` (the JSON), `CommandErrorOutput` and `CommandExitCode`.
2. Branch on `CommandExitCode`: `0` continue, `3` ask someone to log in, anything else stop and report.
3. *Convert JSON to custom object* on `CommandOutput`, then loop over `new` (for example `%JsonAsCustomObject['new']%`). Each item has `xml_path` (ANAF's file) and, once classified, `saga_xml_path` (the file for SAGA it is in; with one file per client, the same file for all of that client's waiting invoices).
4. Invoices classified by a later run or by a person are not in `new`. To get everything waiting for SAGA, run `uv run efactura invoices --classification classified --pending`.
5. If `classification.review` is above zero, tell someone: `uv run efactura review` lists what to decide.
6. After SAGA has imported a client's file, confirm it, as below. Or, for one invoice, run `uv run efactura mark-uploaded <id>`; the invoice then leaves its file.

**As a web request**

1. Make sure the API is running: *Invoke web service* `GET http://127.0.0.1:8765/health`; if it fails, *Run application* `start-api.bat` (window style hidden) and wait a few seconds.
2. *Invoke web service*: `POST http://127.0.0.1:8765/sync`, content type `application/json`, custom header `X-API-Key: <key>`, body `{"cui": "12345674"}`.
   - Raise the timeout: a sync with hundreds of new invoices can take minutes.
   - Turn off "Fail on error status" so the flow can read the JSON of a failure, and branch on the status code instead.
3. *Convert JSON to custom object* on the response.

### Finding a client's folder and files

A client's folder is `<SAGA folder>\<name> - <CUI>`, so a flow that knows only the CUI must not build the path itself.

- **Ask the program:** `GET /saga-files/{cui}` (or `saga-files <CUI>`) answers `folder` and, for each waiting file, its `path`. `GET /saga-files` gives the same for every client with a file.
- **Or look in the SAGA folder** for the folder whose name ends with ` - <CUI>`: *Get subfolders in folder*, with the folder filter `* - 12345674`. There is one, except while an earlier folder of the client could not be removed (see [the SAGA files](#classification-and-saga)); then only asking the program says which is the right one. A company that is not in the client list has a folder named by its CUI alone, as before.
- A flow written for 0.14.0 or earlier, which opened `<SAGA folder>\<CUI>`, finds nothing there after the update: change it one of these two ways.

### Confirming an import in SAGA

A desktop automation that imports each client's file into SAGA tells the program when it is done:

1. `GET /saga-files` (or `saga-files`) lists the clients with a file, each with the `path` of every file and a `version`.
2. The automation imports the files into SAGA.
3. `POST /saga-files/{cui}/imported` with `{"version": "<the version from step 1>"}` (or `saga-imported <cui> --version <v>`).
   - Every invoice the files held is marked as imported.
   - The files, byte for byte, move to `data/saga-archive/<CUI>/<date and time>/`.
   - The import is recorded, and shown on the client's "Arhivă" tab.
4. If the answer is 409 `saga_files_changed`, nothing was marked. An automatic download or a finished review added an invoice to the file after step 1. Take that client again from step 1. SAGA skips the invoices it already has (by number and date), so importing the file again does not double them.

- **Without a version** (`{}`), whatever the files hold at that moment is confirmed.
- **Refused with 409 `saga_files_stale`** when the client's files are not up to date: the program could not write or delete one, and what SAGA read is not known. Bring the folder up to date (`POST /saga-files/write`, or "Încearcă din nou" on screen), import again and confirm then.
- **Nothing waiting:** the answer's `archive` is `null`, so the automation can go through every client.
- **On screen:** "Da, am importat" does the same with the version the page read.
- **Removing the file:** if SAGA still holds a file open, so that it cannot be deleted, the invoices are marked and archived all the same. The file is removed at the next try.
- **Each confirmation** is one journal line, `saga.imported`.

**The "Arhivă" tab** of a client's screen lists the confirmed imports, the newest first:

- Each shows when it was confirmed, "Din automatizare" or "De pe ecran", how many invoices of each kind, and the file.
- "Descarcă fișierul" and "Deschide folderul" reach the file. "Arată facturile" opens its invoices, each a link to its screen.
- An invoice taken off "imported" afterwards goes back into the client's file. It stays in the import, which then says how many of its invoices are no longer marked.
- An imported invoice's screen says which import it went in, with a link to it.
- Invoices marked as imported before 0.13.0 have no import in the archive.

**The yearly login from a flow**

1. Call `login-start` (or `POST /auth/login/start`) and open `authorize_url` in Edge.
2. The accountant chooses the certificate and types the PIN.
3. When the browser shows "can't reach this page", read the address bar (for example send `Ctrl+L`, `Ctrl+C`, then *Get clipboard text*) and hand it back within a minute.
   - Prefer the API for this step: `POST /auth/login/finish` with body `{"address": "<the address>"}`. The address travels as JSON, so nothing needs quoting.
   - If you use the command instead, put the address in double quotes (`login-finish "<address>"`): it contains `?`, `=` and possibly `&` or `%`, which the Windows command line would otherwise split or expand.

Or simply have a person run `uv run efactura login` when a flow reports exit code 3.

## Where things are kept

```
data/
  efactura.db          SQLite database
  efactura.log         activity log
  server.log           what the program printed while running in the background
  update.log           what the last update printed
  last-update.json     how the last update ended
  restore.log          what the last restore printed
  last-restore.json    how the last restore ended
  efactura.db.replaced-…   a database that a restore replaced and could not copy to the backup folder
  backups/             copies of the database made before each update (the last three)
  invoices/
    11-11-2026/        the day the messages were saved (not the invoice date)
      12345674_primita_3001234567.xml      <CUI>_<type>_<message id>.xml
  SAGA Import/         (or the folder chosen on screen)
    Alfa Construct SRL - 12345674/         one folder per client: its name and its CUI
      F_87654321_FV-1042_09.11.2026.xml    the invoices waiting for SAGA, named after the first
  saga-archive/
    12345674/                              by CUI alone: the program's own, not for SAGA
      2026-11-17_10-42-00/                 one confirmed import: its files as SAGA got them
```

- **Database:** table `messages` (one row per ANAF message: list details, invoice fields read from the XML, the full invoice XML and ANAF's signature XML, `uploaded_to_accounting`, `uploaded_at`, the classification fields), `sync_runs` (one row per run), `jev_calls` (every request to Jev with its reply and cost), `clients`, `accounts`, `issued_accounts` (the income accounts for issued invoices), `rules` (each with its kind, `direction`), `events` (the [journal](#the-journal)), `technical` (its [technical side](#the-technical-view)), `decisions` (the [history of each invoice's account](#the-history-of-an-invoices-account)), `saga_files` (the files written for SAGA that are still there), `saga_problems` (why a client's files could not be brought up to date, until they are), `saga_imports` and `saga_import_invoices` (each confirmed import, its archive folder and files, and the invoices it held), and `settings` (the confidence level, the question for Jev, the schedule `auto_sync` and the record of the last automatic download `auto_sync_last_run`, and what was changed on screen: the SAGA folder, one file per client or per invoice `saga_file_per`, the name each client's folder for SAGA last had, and after a `/` any earlier folder of its that is still there, `saga_folder:<CUI>`, issued invoices shown or not `show_issued`, the backup folder and the keys). Any SQLite tool can read it. A database made by an earlier version gains the new columns when it is first opened; nothing is lost.
- **Saved login:** `%LOCALAPPDATA%\efactura\tokens.json`, in the Windows user's private folder and outside this project. Treat it like the token and PIN: whoever copies it can read e-Factura data for every company the certificate covers until it expires.
- **`config.toml`** holds the client secret, the API key and the OpenRouter key. It is ignored by git; do not share it.
- **Keys changed on screen** are stored in the database as plain text, like those in `config.toml`. Treat `data/efactura.db` as a secret too, and with it every copy in the backup folder.
- **The backups** are in the folder chosen on the "Copii de siguranță" screen, outside this project: `autosaga-<date>-<time>-<auto|manual|before-restore|before-wipe>.zip`, 25 at most.
- **Changing the SAGA folder** moves what is waiting for SAGA: the files are written in the new folder, and the program's own files are removed from the old one. A client's folder left empty there is removed too.
- **The archive of imports** stays by CUI (`saga-archive\<CUI>\`). It is the program's own, opened from the "Arhivă" tab, and each import keeps its place on record; a client's new name does not move it.
- The folder name format can be changed in `config.toml` (`DD-MM-YYYY` or `YYYY-MM-DD`, which sorts by date in Explorer).

## Limits to know about

- ANAF keeps messages for 60 days. Older ones cannot be fetched.
- A new invoice can take up to about 15 minutes to appear in ANAF's list.
- ANAF allows 10 downloads a day per message; skipping saved messages keeps the tool far below that.
- ANAF's test system (`environment = "test"`) only lists what was uploaded to it, so real invoices can only be read with `environment = "prod"`.

## Not yet confirmed against the real services

Everything is covered by automated tests against a stand-in for ANAF. One thing was checked against the real service on 2026-11-11 with placeholder credentials: ANAF's token call accepts the client ID and secret as a Basic header and needs no certificate.

The first real run on the Windows PC should confirm:

- a complete login, and the one-minute lifetime of the login code (reported by open-source clients, not by ANAF's own document)
- the file names inside ANAF's ZIP, and what a buyer-message ZIP contains (it is saved as-is either way)
- the one-sync-at-a-time lock on Windows (tested on macOS only)
- that a negative paid amount is always an earlier unpaid balance: this reading comes from one supplier's invoice, where the supplier's own comment says so and the sums agree, not from the standard's text
- the Power Automate steps above

For the demo and the certificate login:

- **`efactura demo`** was run on macOS only.
- **The certificate helper**: its steps were run by hand on the Windows PC on 2026-11-15 (Windows PowerShell 5.1, the token in), and ANAF answered with an address containing `code=`. That run showed:
  - ANAF's login address answers in several hops on its own host (`/anaf-oauth2/v1/authorize`, `/my.policy` twice, `/my.policy_nonce`) before it sends the request to the callback. The cookies have to be kept from hop to hop and the certificate offered at each.
  - With no certificate ANAF ends on `<callback>?error=access_denied` after three hops, which is what the browser on that PC gets: it never shows its certificate window.
  - A wrong Client ID is answered at once with HTTP 400 and `invalid_client`; a callback that differs from the registered one with HTTP 400 and `invalid_request` ("Redirect-URI ... does not match").
  - With the certificate, the first run ended in `access_denied` and the second brought a code, twice. The first run is the one during which the PIN is typed. The helper therefore opens the token first and tries once more by itself; whether the first step alone is enough is not known.

  Still open: the script file as it is now (the owner's run used the same steps, typed by hand), the program starting it by itself without a console window, where Windows puts the certificate and PIN windows then, and the one refusal nobody could explain.

For classification, not everything has run against the real OpenRouter and the real SAGA:

- **Jev.** The request and reply shapes follow OpenRouter's published reference for `POST /api/alpha/decisions`, read on 2026-11-13. The endpoint is marked alpha. If its shape changes, Jev calls fail, invoices wait as `pending`, and the rules keep working. The first real call (`classify <id>`, then `costs`) confirms the shape and the price.
- **SAGA's formats.** The tags and their order are from SAGA's manual. The manual does not state the date format (`dd.mm.yyyy` is assumed, as elsewhere in SAGA), the decimal format (a point), the text encoding (UTF-8), whether the fiscal code carries `RO` (written as on the invoice), or how the file name's parts are used. Confirmed by the owner on 2026-11-16: the real SAGA imported one file holding 100 invoices of one client, named after one of them. They are constants at the top of [src/efactura/saga.py](src/efactura/saga.py). To check them, print an outgoing invoice in SAGA with "Formular PDF": SAGA puts its own XML next to the PDF in `TEMP\Facturi`. Compare that file with one from `SAGA Import`.
- **The files for SAGA on Windows.** The one file per client, and the tidying of the folder, have run only on a Mac. Not yet seen on Windows: replacing a file while SAGA's import window has it open (it is expected to fail and to be shown as "not up to date"), two parts of the program writing at once (the second waits for the first, with the same kind of lock a download uses), a SAGA folder on a network share, and the removal of an earlier version's files at the first start.
- **`<Cont>` on import.** The manual lists the tag but does not say that the account lands on the "Nedefinit" line. Import one file into a test company or a backup first.
- **Foreign-currency invoices** are written with their currency; SAGA books those in a separate screen and the import is untried.
- **Jev's accuracy** on Romanian invoices is unknown until its suggestions are compared with the accountant's choices.

For the installer:

- **`install.ps1` has had one run on Windows**, which reached the last step. It is plain Windows PowerShell 5.1 and was otherwise checked by reading only.
- **Starting without a window** (`start`, `open`, the two shortcuts) uses Windows-only process flags that could not be tried on a Mac. The same commands start and stop the program correctly on macOS. If the background start fails on Windows, `start.bat` still works.
- **The port** is chosen at install time: 8765, or the next free one. If another program takes it later, the program will not start; change `[api] port` in `config.toml`. A double click on the Desktop shortcut then shows the reason in a message box.
- **First run on Windows, 2026-11-14:** `install.ps1` ran as far as starting the program, which then reported the port as taken, for port 80 and for a free port alike. The cause was this program's own check: Windows takes about two seconds to refuse a connection to a port nobody listens on, and that wait was read as another program holding the port. Fixed in 0.1.1; the start itself is still to be confirmed.
- **Updating from the page or with `efactura update`** was run for real on macOS (page button and terminal, with a running program, the database kept and copied). On Windows, `uv run efactura update` was tried on 2026-11-14, from 0.2.0 to 0.4.0, and failed on "Access is denied" removing `efactura.exe`: the command ran through the file it had to replace. From 0.4.1 that way of starting it is refused at once, and `update.bat` and the page's button start the update through Python. Neither of those two has been confirmed on Windows yet; running `install.ps1` again remains the fallback, and that one has updated a copy there.
- **`winget`** is needed only when Git is missing; on a Windows without it the script stops and names the Git download page.

For backups and the journal:

- **Making copies, the 25 limit, the 24-hour rule and a missing folder** are covered by tests and were run for real on macOS.
- **Restoring from the page** was run for real on macOS, with a running program: a client added after the copy was gone afterwards, the copy made before the restore held it, the program came back by itself and went on backing up to the same folder. On Windows it has not been run. There a file that some program still holds open cannot be replaced; if that happens the restore must fail, keep the database it had and say so. That path is tested, but with a stand-in for the failure.
- **Stopping the program for a restore or an update** waits until it no longer answers, not until its process has gone. A request still being served at that moment finishes afterwards. A download is refused beforehand and a file still in use is tried again for a few seconds; anything slower than that makes the restore fail and keep the database it had. On macOS and Linux nothing refuses a file in use, so there a restore should not be started while something else works on the database.
- **The job that makes the daily copy** runs inside the program started without a window. That start is itself unconfirmed on Windows (see above); if the program runs, the job runs.
- **The folder dialog** for the backup folder is the same one the SAGA folder uses, with the same caveat.

For the automatic download:

- **The thread** that looks at the schedule runs inside the program started without a window. That start is itself unconfirmed on Windows; if the program runs, the thread runs.
- **A run made up after sleep:** a PC that wakes from sleep is expected to make up the moment it slept through within half a minute. Not yet seen on Windows.
- **The period:** a run with the last days and a run with two chosen days were watched on macOS against made-up data. Neither has asked the real ANAF.
- **The date fields** (here and in the download window) are the browser's own, so they show the day and the month in the order of the PC's regional settings. How they look on the Windows PC has not been seen; the sentence under them always writes the days as `zz.ll.aaaa`.

For the screen:

- **The folder dialog and "Deschide folderul"** use Windows itself and were only tried as far as this Mac allows. The dialog may open behind the browser window; typing the path always works.
- **The page was checked against a made-up database** (see [The screen](#the-screen)), not against real ANAF data.
- **Other Windows accounts on the same PC** could open the page while the program is running.

Not covered: partial VAT deduction (`TipDeducere`), stock articles, sent invoices, encrypting the stored keys.

## Development

Everything, with one command (API and page, both reloading as the code changes):

```bash
uv run efactura dev
```

Tests:

```bash
uv run pytest
```

```bash
pnpm --dir frontend test
```

The page's code is in `frontend/src`, one folder per screen. All text on screen is Romanian and written in the components; the program's own error messages are English and are translated per error code in `frontend/src/errorMessages.ts`.
