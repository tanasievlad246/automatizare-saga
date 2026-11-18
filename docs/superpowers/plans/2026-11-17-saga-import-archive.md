# The import in SAGA confirmed by the automation, and an archive of what was imported — plan

## Context

You have a desktop automation that imports each client's file for SAGA into SAGA. After an import it needs to tell the program "SAGA has these", so the invoices are marked as imported and the file leaves the SAGA folder. You also want a record of every import: the file exactly as SAGA got it and the invoices in it, on a new "Arhivă" tab of the client's screen.

Today the program keeps, for each client, a file (or a file per invoice) in `SAGA Import\<CUI>\` with exactly the invoices that have an account on every line and are not marked as imported. "Da, am importat cele N facturi" marks them, and the program then deletes the file. Nothing of the import is kept.

Design: canvas https://claude.ai/artifact/VSxb2ocdWVd9UtMUcuWukH, last board, "Arhiva importurilor în SAGA".

## Decisions

**Yours**
- An endpoint takes a client's CUI, marks every invoice in that client's file as imported in SAGA, and moves the file to an archive.
- The automation imports first and calls the endpoint after.
- The screen's "Da, am importat" archives the file too.
- Archived files go in the program's data folder.
- The client's screen gets an "Arhivă" tab with the archived imports and their invoices.

**My calls, say if you want something else**
1. **A version guards the race.** Between the automation reading a client's file and confirming it, an automatic download or a finished review can add an invoice to the file. Marking "whatever is in the file now" would then mark an invoice SAGA never got. So:
   - `GET /saga-files` gives each client's file with a short version (a fingerprint of its contents).
   - The automation sends that version back with the confirmation.
   - If the file has changed since, the answer is 409 and nothing is marked; the automation takes the client again from the start.
   - The version is optional, so a call with the CUI alone works as you described, without the guard. The README will recommend sending it.
   - Re-importing a file is safe, since SAGA skips invoices it already has (by number and date).
2. **The screen uses the same guard.** If a download added an invoice while you were importing by hand, the button refuses and shows the file as it is now, instead of marking what you never saw.
3. **A file that is not up to date is refused.** If the program could not rewrite the client's file the last time (a file open in SAGA, the folder unreachable), what is on disk may not be what the program thinks. The endpoint answers 409 and marks nothing, as the screen already warns today.
4. **One archive entry per confirmation.** With a file per invoice, all the client's files go together into one entry.
5. **Nothing waiting is not an error.** The answer is `archive: null`, so the automation can loop over every client.
6. **Where:** `<data folder>\saga-archive\<CUI>\<date and time>\`, with the files byte for byte as they were in the SAGA folder.
7. **Marking one invoice at a time stays as it is**, without an archive entry: `POST/DELETE /invoices/{id}/uploaded` and `mark-uploaded`. Archiving part of a file would not be a file SAGA got.
8. **Unmarking an archived invoice** puts it back into the client's file as today. The archive entry stays as history and shows "nu mai este marcată ca importată" beside it.
9. **The invoice's screen** says when and how it was imported, with a link to its archive entry.

## How it works

### For the automation

| Step | Call |
|---|---|
| What is waiting | `GET /saga-files`: every client with a file for SAGA. Each has `cui`, `client`, `file_per`, `files` (`name`, `path`, `invoices`), `invoices`, `up_to_date` and `version`. Also `GET /saga-files/{cui}` for one client. |
| Import | The automation imports `path` into SAGA. |
| Confirm | `POST /saga-files/{cui}/imported` with `{"version": "…"}`. The answer has `archive`: `id`, `cui`, `imported_at`, `source`, `invoices`, `ids`, `files` (`name`, `path`). It is `null` when nothing was waiting. |
| Refused | 409 `saga_files_changed`: the version no longer matches. 409 `saga_files_stale`: the files are not up to date. `busy`: another part of the program is writing the files. 404: no such client. In every case nothing is marked or moved. |
| Archive | `GET /saga-archive?cui=` lists the entries. `GET /saga-archive/{id}` gives one entry with its invoices. `GET /saga-archive/{id}/files/{name}` downloads a file. `POST /saga-archive/{id}/open` opens its folder. |
| Command line | `saga-files [CUI]`, `saga-imported CUI [--version V]`, `saga-archive CUI [--id N]`. |

### Inside the confirmation

Everything happens under the same file lock every writer of the SAGA files takes, so a download cannot rewrite the file in the middle.

1. The files and their invoices are those the program recorded when it last wrote them (`saga_xml_path`), which is what SAGA read. If a failure is noted or a file is gone, refuse with `stale`. Read each file once; if the version of those bytes differs from the one given, refuse with `changed`. The bytes read are the bytes archived.
2. Copy the files into a new archive folder.
3. In one database transaction: the archive entry, its invoices, and the "imported" marks. If this fails, the copied folder is removed and nothing changes.
4. Bring the client's SAGA folder up to date, as after any marking. The archived files leave it.
   - If a file cannot be deleted (Windows keeps it locked while SAGA has it open), the invoices are already marked and archived. The leftover file is noted and removed at the next try, as today.
5. One journal line, `saga.imported`.

### Storage

- **New tables, added when an older database is opened:**
  - `saga_imports`: `id`, `cui`, `imported_at`, `source` (`api` or `screen`), `folder`, `files` (as JSON).
  - `saga_import_invoices`: `import_id`, `message_id`.
- **Untouched:** the invoices' own rows, apart from the "imported" mark.

### On the screen

- **Client screen:** tabs "Facturi primite · Facturi emise · Arhivă". The tab is in the address (`?fel=arhiva`, beside the existing `?fel=emise`), and `&import=12` opens one entry, as the invoice's link does and as opening an entry writes.
- **Archive list, newest first.** Each entry shows:
  - "Import din azi, 10:42", "Din automatizare" or "De pe ecran", and "12 facturi: 7 primite, 5 emise";
  - the file name, with "Descarcă fișierul" and "Deschide folderul";
  - "Arată facturile", which opens a table: invoice (a link), kind, supplier or client, date, total, account ("704 +1" for several accounts).
- **Empty archive:** "Nu există încă niciun import în arhivă" and one sentence on how entries get there.
- **The SAGA card** (under "Facturi primite"):
  - same button, plus the sentence "Facturile se marchează ca importate, iar fișierul se mută în arhivă";
  - after pressing: "Cele 12 facturi sunt marcate ca importate. Fișierul este acum în arhivă.";
  - if the file changed: "Fișierul s-a schimbat de când ați deschis pagina", nothing marked, and the list reloaded.
- **An imported invoice's screen:** "Importată în SAGA azi, 10:42, din automatizare" and "Vezi importul în arhivă".

## The work, tests first

| # | Part | Where |
|---|---|---|
| 1 | Tables, keeping and reading entries, a migration test on a database made by 0.12 | `store.py`, `tests/test_store*.py` |
| 2 | Files and version for a client, from what the writer recorded | `service.py` (`_saga_waiting`, `_saga_version`, `_version_of`) |
| 3 | Confirming an import: all the refusals, both file modes, the lock, a failed delete, the journal | `service.py`, `tests/test_saga_archive.py` |
| 4 | Archive entries, their invoices, downloading a file, opening its folder; the invoice says which entry it is in | `service.py` |
| 5 | Routes, the command line, error codes | `api.py`, `cli.py`, `errors.py` |
| 6 | Page: types and calls; the "Arhivă" tab; the entries list; the SAGA card sending the version; the line on the invoice's screen; texts in plain modules with tests | `frontend/src/invoices/…`, `frontend/src/archive/…`, `errorMessages.ts` |
| 7 | Demo with two archive entries, the README (Power Automate steps and routes), version 0.13.0 | `demo.py`, `README.md` |

## Verification

1. `pytest`, `vitest`, the type check, lint and the build at every step.
2. **Against made-up files in tests:**
   - After a confirmation, the archive holds the same bytes as SAGA had, and the SAGA folder no longer holds them.
   - Only the invoices that were in the file are marked; one added after the version was read is neither marked nor archived.
   - A file that is not up to date is refused and nothing changes.
   - With a file per invoice, every file goes into one entry.
3. **In the demo, in the built-in browser:** confirming from the screen, the "Arhivă" tab with an entry opened, downloading a file, the "changed meanwhile" message (forced by marking an invoice between reading and confirming), and the invoice's line.
4. **An independent review before release.**
5. **Yours:** the automation's call on the real PC.

## Limits

- **Earlier imports:** invoices marked as imported before 0.13.0 have no archive entry.
- **Backups:** the copies on "Copii de siguranță" hold the database, not the archive folder. Restoring an older copy can leave archived files no entry points to, or an entry whose files were removed by hand. Its download then says the file is gone.
- **The archive is never cleaned.** Files are small; nothing is deleted from it.
- **Windows:** not tried. In particular, the file SAGA has open after an import may be locked, which the plan handles as above.
