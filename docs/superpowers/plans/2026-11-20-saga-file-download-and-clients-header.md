# The file for SAGA downloaded from the browser, "Fișier importat" on each file, and a header on the client list: plan

Status: approved on 2026-11-20 and built as written, except for what "As built" lists at the end.

## Context

You asked for two things.

1. **The XML for SAGA can be downloaded in the browser**, for people who cannot reach the paths the screen lets them copy. In the same place on the "Fișiere pentru SAGA" tab, a **"Fișier importat"** button marks that file and its invoices as imported in SAGA.
2. **A header on the client list** with a check that switches every client on or off, as each client's own switch does, and the list shows **the clients that are on first**.

**How it works today.**
- A waiting file is reached by its path: "Copiază calea", and "Deschide folderul" on the program's own computer. `GET /saga-files/{cui}/files/{name}` already serves the file, but the page only uses it for "Vezi XML-ul".
- An import is confirmed for the whole client: "Da, am importat cele N facturi" marks every invoice in every waiting file and moves the files to the archive (`POST /saga-files/{cui}/imported`). One invoice can be ticked on its own screen.
- The confirmation carries the version of the file as the person saw it. If the file changed since, nothing is marked.
- Each client has a switch (`PUT /clients/{cui}/enabled`). The list is ordered by name. A line under the buttons says how many are off.

Design: canvas https://claude.ai/artifact/VSxb2ocdWVd9UtMUcuWukH, the last two boards:
- "Fișierul pentru SAGA: descărcat din browser și „Fișier importat”"
- "Clienți: antetul listei și clienții porniți primii"

## Decisions

**Yours**
- A button that downloads the XML file, nothing more.
- "Fișier importat" beside it on the "Fișiere pentru SAGA" tab: it marks the file and its invoices as imported.
- A header on the client list with a check that switches all clients on or off.
- Clients that are on come first.

**My calls, say if you want something else**

1. **"Fișier importat" does what "Da, am importat" does, for one file.** The file's invoices are marked as imported, the file moves to the archive as one import ("De pe ecran"), and it leaves the client's folder. No window opens, as today. Undo is the tick on the invoice's screen, as today.
2. **The card "Ați importat facturile în SAGA?" under the files tab** is hidden when the client has one file, because the file's own button does the same thing. It stays:
   - under the invoice lists, unchanged;
   - under the files tab when there are several files (one file per invoice), to mark all of them in one press;
   - under the files tab when the folder is not up to date, for "Încearcă din nou".
3. **"Descarcă fișierul" is in three places**, wherever the screen shows a file's path: the file's card on the tab (what you asked for), the card under the invoice lists, and "Fișierul pentru SAGA" on an invoice's screen. The last two are my addition.
4. **The download is fetched by the page and then saved**, not a plain link. This way a file that is gone is said on the page in Romanian, and server mode's rule that every call carries the page's header stays as it is.
5. **The version confirmed is the version downloaded.** The download answers with the file's version, and "Fișier importat" sends that one. A downloaded copy does not follow the folder: if the file was written again since, nothing is marked and the card says to download it again.
6. **Both new buttons are off while the folder is not up to date.** A file that is missing has no download button.
7. **A second download of the same file** shows a line about the "(1)" the browser adds to the name. I do not know whether SAGA takes a file named `F_… (1).xml`. If it does, I drop the line.
8. **The header is a strip above the search field**, about all clients, never only the ones found. It takes the place of the line "Se descarcă 3 din cei 4 clienți. Un client este oprit."
9. **The check has three states**: ticked (all on), a dash (some on), empty (all off). A press on a dash switches everyone on; a press on a tick switches everyone off.
10. **The program asks before switching everyone.** One press changes every client and cannot be taken back in one step. A single client's switch stays without a question.
11. **"On first" is an order, not a filter.** On first by name, then off by name, also in search results and across pages.
12. **A client switched on its row stays where it is** until the list is opened again. A row that jumped to the last page at a press could not be switched back in one press.

## What changes

The two halves do not touch the same files. Each can be its own commit.

### A. The file for SAGA

**1. The program: a version for each file, and the download says which version it gave**
- `service.py`, `_saga_waiting`: each file in the answer gets `version`, the fingerprint of that file alone. It is worked out from the same read as the client's `version`.
- `service.py`: `saga_file` gives the file's bytes and their version from one read, so what is served is what was fingerprinted.
- `api.py`, `GET /saga-files/{cui}/files/{name}`: answers those bytes with the header `X-AutoSaga-File-Version`. Still an attachment with the file's name.

**2. The program: confirm one file**
- `api.py`: `SagaImportedRequest` gets `file: str | None`. With it, `POST /saga-files/{cui}/imported` confirms that file alone, and `version` is that file's version.
- `service.py`, `confirm_saga_import(cui, version, source, file=None)` and `_archive_saga_files`:
  - a name that is not waiting for this client: 404 `not_found`;
  - the client's files not up to date: 409 `saga_files_stale`, as today;
  - the file changed since `version`: 409 `saga_files_changed`, as today;
  - otherwise the file is copied to a new archive folder, one `saga_imports` row is written with that file and its invoices, and the folder is brought up to date. The other files stay.
- `cli.py`: `saga-imported <cui> --file <name>`, to keep the command and the API the same.
- The journal line `saga.imported` names the file, as it does today.

**3. The page: "Descarcă fișierul"**
- `api.ts`: `sagaFile(cui, name)` answers the file as a blob with its version.
- `saveFile.ts` (new): hands a blob to the browser under a name.
- `sagaFiles/useFileDownload.ts` (new): fetch, save, the toast, and how many times this file was downloaded.
- The button goes in `sagaFiles/WaitingFileCard.tsx`, `invoices/ImportedInSagaCard.tsx` (only with one file per client, where the path is a file) and `invoices/SagaFileCard.tsx`.
- Texts in `sagaFiles/waitingFiles.ts`.

**4. The page: "Fișier importat"**
- `types.ts`: `WaitingFile.version`.
- `api.ts`: `confirmSagaImport(cui, version, file?)`.
- **One owner for "what the person has seen".** Today that is state inside `ImportedInSagaCard`. It moves to a hook on the client's screen, with its rules in a pure module that is tested:
  - `sagaFiles/seenFiles.ts` (new, pure) and `sagaFiles/useSeenFiles.ts` (new);
  - it keeps the version seen of all the files together (what the card under the lists sends) and of each file (what "Fișier importat" sends);
  - a version is taken when a file is first shown, and again when the person downloads it, opens its XML, copies its path or opens its folder. The page reloading by itself never changes it;
  - with one file per client the file is the same file whatever its name: when its first invoice changes and the file is renamed, the version seen is still the old one, so the confirmation is refused;
  - a confirmation from either button clears what was seen, so the other button does not refuse by mistake afterwards.
- `sagaFiles/WaitingFileCard.tsx`: the button, the line under the buttons with the count, the "changed meanwhile" notice, the "(1)" line.
- `sagaFiles/SagaFilesTab.tsx`: the intro text, and the props passed down.
- `invoices/ImportedInSagaCard.tsx`: takes what was seen from the hook, and shows nothing under the files tab when the file's own button is there (decision 2).
- `invoices/ClientInvoicesPage.tsx`: the hook, and the rule for when the card shows.

### B. The client list

**5. The program: switch every client**
- `store.py`: `set_all_clients_enabled(enabled)`, answering how many changed.
- `service.py`: `set_all_clients_enabled(enabled)`, one journal line (`clients.switched_all`, with how many changed), answering the client list.
- `api.py`: `PUT /clients/enabled` with `{"enabled": true}` or `false`.

**6. The page: the header and the order**
- `api.ts`: `setAllClientsEnabled(enabled)`.
- `clients/switchedOff.ts`: which of the three states the list is in, and the header's words.
- `clients/clientSearch.ts`: `onFirst(clients, onAtOpen)`, the order.
- `clients/ClientsHeader.tsx` (new): the strip with the check and the counts.
- `clients/SwitchAllDialog.tsx` (new): the question, in its two forms, with the extra sentence when a search hides some clients.
- `components/ui/checkbox.tsx`: a dash for the mixed state. It only draws a tick today.
- `clients/ClientsPage.tsx`: the header above the search, the order, who was on when the list was opened (taken again after everyone is switched), and the line under the buttons removed.

### C. Around them

**7.** `README.md`: the `file` field and the per-file `version` in the `saga-files` rows, the download's header, `PUT /clients/enabled`, `saga-imported --file`, and the two places in the screen's description.

**8.** The version: 0.16.0, in its own commit, as the last releases were.

## Tests

**pytest**
- `tests/test_saga_archive.py`:
  - each waiting file has its own version, and with one file it equals the client's;
  - the download's header is the version listed for that file;
  - confirming one file marks only its invoices, archives only that file, and leaves the others in the folder;
  - a changed file, an unknown name, and a folder not up to date are each refused and change nothing;
  - with one file per client, confirming the file gives the same result as confirming the client;
  - the same over the API and with `saga-imported --file`.
- `tests/test_clients.py`: everyone off, everyone on, the count in the journal, an empty list.
- `tests/test_server_mode.py`: the waiting file is still refused without the page's header.

**vitest**
- `sagaFiles/seenFiles.test.ts`: first sight, a look, a download, a reload that changes nothing, the renamed file with one file per client, a new file with one file per invoice, after a confirmation, after a refusal.
- `clients/switchedOff.test.ts`: the three states and their words.
- `clients/clientSearch.test.ts`: on first, by name inside each group, a client switched since the list was opened stays in place, the order of search results.

**By hand, in the demo** (`efactura demo`), in the app's browser:
- download a file, check its name and that it equals the file in the folder;
- "Fișier importat" with one file per client and with one per invoice; the archive entry; the tick taken off an invoice afterwards;
- change an account after downloading, then press "Fișier importat": refused, with the notice;
- the header in its three states, the two questions, the order after reopening the list.

## Not included

- A ZIP with all of a client's files. With one file per invoice each file is downloaded from its card.
- "Fișier importat" outside the files tab. An invoice's screen keeps its tick; the card under the lists keeps "Da, am importat".
- Switching only the clients found by a search.
- A filter that hides the clients that are off.

## Open questions for you

1. Does SAGA import a file named `F_… (1).xml`? (decision 7)
2. Should the card under the files tab stay even with one file? (decision 2)
3. Should a client switched off on its row move to the end at once, instead of at the next opening of the list? (decision 12)

## As built

The three open questions were left as the plan had them. What differs from the plan:

- **`switchedOffLine` stays.** The schedule's screen still uses it.
- **The header's hint** reads "Când deschideți lista, clienții porniți sunt primii." A client switched just now is still in its place, so "sunt primii în listă" would be untrue for a moment.
- **The question before switching off** says "Se opresc toți cei 5 clienți." It is only asked when every client is on, so it never has "3 din 5" to say.
- **`sagaFiles/useFileDownload.ts` was not made.** The fetch, the save, the toast and the "(1)" line are inside `sagaFiles/DownloadFileButton.tsx`, the one component the three places use.
- **A file's name is never percent-encoded in the download.** The program only gives names made of letters, digits, `.`, `-` and `_`.
- **Found by the review of the finished change, and fixed:**
  - After a refused confirmation the page asks the program for the file as it is now and keeps that version, as the card under the lists did before. A first build dropped this, and a file written once more after a refusal would have been accepted.
  - With a file per invoice, "Da, am importat" for all the files could have accepted a file a colleague had written again, after one file was confirmed on its own or looked at. Now the program answers a confirmation with how all the client's files stood (`versions`: `before`, `after`), and looking at one file or saving it counts for that file alone.
- **Released as 0.16.0** on 2026-11-20, the version in a commit of its own.
