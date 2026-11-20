# A client's files waiting for SAGA, and client folders named `Nume client - CUI`: plan

## Context

You asked for two things.

1. **A view of a client's files that still have to be imported into SAGA.**
2. **Client folders named like `${clientName} - ${CUI}`.**

**How it works today.**
- Each client's files for SAGA are in `<SAGA folder>\<CUI>\`. With "one file per client" there is one file; with "one file per invoice" there is one per invoice.
- The client's screen shows the path of that file in the "Ați importat facturile în SAGA?" card. Nothing shows what is inside the file, apart from each invoice's own part of it on the invoice's screen.

Design: canvas https://claude.ai/artifact/VSxb2ocdWVd9UtMUcuWukH, last board, "Fișierele de importat și folderul cu numele clientului".

## Decisions

**Yours**
- The view lists every file waiting in the client's folder. For each file it shows:
  - its invoices;
  - their total;
  - when it was written;
  - its XML, in the same viewer with the "Copiază XML-ul" button.
- The folder is `Nume client - CUI`.

**My calls, say if you want something else**

1. **Where the view goes.** It is a new tab on the client's screen, "Fișiere pentru SAGA (n)", between "Facturi emise" and "Arhivă".
   - "Ați importat facturile în SAGA?" gets a link to it: „Vezi ce este în fișier”.
   - The card stays under the new tab too, so you can confirm the import from there.
2. **One card per file.** Each card has:
   - the file's name and "Scris: azi, 10:02";
   - the file's full path on disk, with "Copiază calea" and "Deschide folderul" (you asked for the path after seeing the first board);
   - how many invoices, received and issued, and the total. The total is split by currency when there is more than one.
   - a table of its invoices: number (a link), received or issued, supplier or customer, date, total, account;
   - a "Vezi XML-ul" button. It opens a window with the file exactly as it is in the folder, laid out by the existing viewer with its copy button.

   With one file per invoice there are many small cards, 20 to a page, as in the archive.

   **The table, as you asked after seeing the board:**
   - **Rows that open.** Each invoice has an arrow in front. Pressing it shows the invoice's lines in the rows below: number, name (with its description), quantity, value, VAT and account. Several invoices can stay open.
   - **Pages.** The table has 25 invoices to a page, as the invoice lists do. An open invoice's lines have 10 to a page, with their own page buttons.
   - **Order.** Every column heading is a button: the first press orders ascending, the second descending.
     - Text columns (invoice number, kind, supplier or customer, account) go A to Z, with numbers inside the text in their own order (`FV-9` before `FV-10`).
     - "Total" goes from the smallest; "Data" from the oldest.
     - The order covers every invoice in the file, not just the page shown, and returns to the first page.
     - "Înapoi la ordinea din fișier" brings back the order SAGA gets them in. The order on screen never changes the file.
     - A table with one invoice has plain headings.
   - **Changing the account from an open row.** My reading of "per invoice row": each line of the invoice.
     - An invoice with an account on each line: every line has "Schimbă", which opens the window the invoice's screen already has (the account list and, when there is one, Jev's proposal). "Același cont pe toate liniile" is there too.
     - An invoice with one account for all its lines: one "Schimbă contul" above its lines.
     - In this tab the window has no "Sau hotărăște din nou această linie". Deciding again can leave a line without an account, which takes the invoice out of the file while you look at it. That stays on the invoice's screen, one press away with "Deschide factura".
     - The program writes the file again after a change, as it does today for any change of account. "Da, am importat" already refuses when the file changed since the page was opened, so an import made before the change cannot be confirmed by mistake.
3. **When the folder is not up to date**, a line at the top says so, and the card below has "Încearcă din nou" as today. A file missing from the folder is marked "Fișierul lipsește din folder" instead of its XML.
4. **The folder's name** is `<name> - <CUI>`, for example `Alfa Construct SRL - 12345674`.
   - The characters Windows refuses (`\ / : * ? " < > |` and control characters) are taken out: `/` and `\` become `-`, the others become a space. Repeated spaces become one.
   - Spaces at the start and end of the name, and dots at its start, are dropped. A dot at its end stays (`S.R.L.`): the folder's name ends with the CUI, never with a dot or a space, which Windows would drop.
   - The name is cut to 60 characters, so long names stay within Windows' path limit.
   - A folder name whose part before the first dot is a name Windows keeps for devices (`CON`, `PRN`, `AUX`, `NUL`, `COM1`…`COM9`, `LPT1`…`LPT9`) gets a `_` in front: `AUX.IT SRL` gives `_AUX.IT SRL - 12345674`.
   - A name left empty after this gives just the CUI.
5. **No name known.** A client in the list always has a name. A client taken off the list keeps the folder its files are already in, so removing a client never moves anything. If it has no files on record, the folder is just the CUI.
6. **A renamed client.** Renaming it (on screen, or by importing the client list) moves its folder at once.
   - The folder is renamed as a whole, so files the program did not write go with it and nothing is left behind.
   - The program then knows its files by their new place.
   - A change only in capital letters is a rename too.
7. **Existing `<CUI>` folders** are renamed once, at the next start, for every client in the list and every client with files. Until a client has something waiting, its folder stays empty, as today.
8. **When the folder cannot be moved.** This happens when SAGA has a file open or the NAS is away.
   - The files are written in the new folder, and the old ones are removed when they can be, with "Folderul pentru SAGA nu este la zi" and "Încearcă din nou" as today.
   - The old folder is removed only once it is empty. A file the program did not write stays in it, so nothing is lost.
   - If the SAGA folder cannot be reached at all, nothing changes on record. The move happens at the next try.
9. **Finding a folder by CUI.**
   - The name always ends in ` - <CUI>`, so `* - 12345674` finds it.
   - `GET /saga-files/{cui}` now also returns `folder`, and `written_at` for each file.
   - A new `GET /saga-files/{cui}/files/{name}` returns one waiting file's XML. Only the names the program wrote are served.
   - Opening a client's folder from the screen finds it by CUI as before.
10. **The archive stays `saga-archive\<CUI>\<date and time>\`.**
    - It is inside the program's data folder and only reached from the program, so SAGA and the automation never look there.
    - Each import keeps its own path on record. Moving them with every rename would risk losing that link, for no gain.
11. **The folder named now, not the one this run started with.**
    - The "open the client's folder" button and the folder named after a download used the folder as it was when the request started (`self.cfg.saga_dir`).
    - The files themselves go where the setting says at the moment of writing.
    - Both will read the setting at that moment, with tests.
12. **What has to change outside the program.**
    - SAGA's import path for each company must point at the new folder.
    - The Power Automate flow in `PAD Flows/flow-main.txt` looks in `%SagaImportFolderPath%\%CurrentItem['CUI']%`. I will change it to find the folder by `* - <CUI>` (`Folder.GetSubfolders`). I cannot run Power Automate here, so it is untested; the README and the PR say so.
    - The README, the "Fișierele pentru SAGA" window and the PR say all of this plainly.

## Building it

### Backend (test-first)

- `saga.client_folder_name(name, cui)`: the rules in 4, with tests for each rule.
- `Service._client_folder(store, cui)` gives the folder now, with the fallbacks in 5. It is used by:
  - `_saga_files_now`, which writes the files;
  - `open_saga_folder(cui)`;
  - the `saga_folder` named after a download;
  - `choose_folder`'s starting point.
- `_place_saga_files`:
  - before writing, it renames an earlier folder of the client (`<CUI>`, a name given by a rename, or the folder its files are on record in) into place, when the new one is not there yet or differs only by capital letters;
  - the records follow, with each file's time of writing kept;
  - after the old files are removed, an earlier folder that is now empty is removed too.
- A file that already holds what it should, but is not on record under its new path, goes on record there, with its old time.
- `save_client` and `import_clients` bring a renamed client's folder up to date at once, naming the old folder so it can be moved even when nothing waits.
- The start pass (`write_saga_files()` without a CUI) also goes through every client in the list.
- `GET /saga-files/{cui}` gains `folder` and per-file `written_at`; `GET /saga-files/{cui}/files/{name}` is new.
- No change to the database's tables, so `SCHEMA_VERSION` stays.

Tests:
- the name rules;
- a client's first files land in `Nume - CUI`;
- an old `<CUI>` folder, with a file the program did not write, is renamed at the start and both files are there;
- a rename moves the folder and the records;
- a rename with a file held open is finished at a later try, and the old folder goes once empty;
- an unreachable SAGA folder loses nothing and moves at the next try;
- a client taken off the list keeps its folder;
- confirming an import after a move;
- the two `cfg.saga_dir` fixes;
- the new routes, including a refused name such as `../x.xml`.

### Page

- `api.sagaFiles(cui)` returns the files with `written_at` and `folder`; `api.sagaFileXml(cui, name)` is new.
- `SagaFilesTab` (new, in `frontend/src/sagaFiles/`) is the tab. `SagaFileCard`'s name is taken by the invoice screen's card, so the new card is `WaitingFileCard`. The window that shows the XML is `FileXmlDialog`.
- The texts and the total are pure functions with tests: `fileCountsLine` and `fileTotals`, which sums by currency in cents.
- The table is `FileInvoicesTable`, with `InvoiceLinesRows` for an open invoice.
  - The order is a pure function with tests, `sortFileInvoices(invoices, column, direction)`.
  - Both page sizes use the existing `pageOf` and `Pager`.
  - An open row reads the invoice with the existing `GET /invoices/{id}/view`, which has its lines and each line's account.
- Changing an account reuses `LineAccountDialog`, with a new switch that leaves out its "decide again" part. A one-account invoice gets a small `InvoiceAccountDialog` around the existing `AccountChooser`. Both refresh the files, the lists and the invoice afterwards.
- The "Fișiere pentru SAGA" tab joins `clientTabs`, with `?fel=saga` in the address.
- `ImportedInSagaCard` gets the link „Vezi ce este în fișier”.
- The "Fișierele pentru SAGA" window says how the folders are named.

### Docs

README:
- "Output";
- "Classification and SAGA";
- "Using it from Power Automate Desktop";
- the API table;
- "Where things are kept".

Each says the new folder name, what has to be changed in SAGA and in the flow, and the new routes.

### Checks

- `uv run pytest`;
- `pnpm --dir frontend test`, `lint` and `build`;
- the demo on port 8774, at desktop and phone width.

Then an independent review of the whole branch.

## Changes made while building

- **The folder's last name is kept in the settings**, as `saga_folder:<CUI>`, with no change to the tables.
  - The plan had `save_client` name the old folder at the moment of the rename. That is lost when the SAGA folder is away and nothing waits, so the old empty folder would never be renamed.
  - The kept name also says which folder a client taken off the list keeps, once nothing of its is on record.
  - It is updated only while the SAGA folder can be reached.
- **A pending move does not write while the SAGA folder is away.** Where the path can simply be made again (a local folder that was moved), writing would have made a new, empty SAGA folder and forgotten the files in the old one. The client's files are now said to be not up to date until the folder is back.
- **A folder renamed by hand** to its new name before the program got to it is taken as it is: the files in it go on record there.
- **An empty client folder left in an earlier SAGA folder** (after "Schimbă" on the SAGA folder) is removed too, by the same step that removes an emptied folder under an old name.
- **`GET /saga-files/{cui}` also has `present`** for each file, so the tab can say "Fișierul lipsește din folder" without reading every file.
- **The start pass goes through the whole client list**, so `POST /saga-files/write` with `{}` counts every client in `clients`, not only those with files.
- **The rows under an open invoice end with the discounts and charges on the whole invoice**, since SAGA gets each as a line of its own on the invoice's account.
- **The account column is ordered as a chart of accounts lists it** (`6022` before `626`), not as numbers.
- **On a narrow screen** the invoice table scrolls sideways, as the other tables do, and the lines of an open invoice stay in sight at the width that is seen.
- **`XmlViewer` has an `inWindow` switch** for its margins and height inside the window.
- **`LineTarget` and `lineTarget()` moved to `lineAccounts.ts`**, so the invoice's screen and the new tab build the window's subject the same way.
