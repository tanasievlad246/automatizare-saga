# One file for SAGA per client — design

Date: 2026-11-16. Items marked **(call)** were decided by Claude and can be changed; the rest is the owner's.

## Why

SAGA's import screen is pointed at a client's folder and lists every file in it. Up to 0.6.1 the program wrote one file per invoice and never removed any, so the folder grew for good and SAGA listed every invoice ever written, relying on "Nr.+data" to skip the old ones.

SAGA's manual for "Import date" says several invoices are imported at once by repeating `<Factura>` inside `<Facturi>`. The owner tried it on 2026-11-16: one file with 100 invoices of one client, named after one of those invoices, was imported by the real SAGA.

## What the owner asked for

- One XML file per client, with all its invoices, instead of one per invoice.
- If it stays simple: a setting on the page to choose between one file per invoice and one file per client, with exactly one of them in force.

## The rule

A client's folder for SAGA holds exactly the invoices SAGA has not got yet: those with an account that are not marked as imported. This holds in both ways of writing.

- **One file per client** (the way a new or updated copy starts with): one file with every waiting invoice, the one that has waited longest first.
- **One file per invoice:** a file each.
- **(call)** In both ways an invoice leaves the folder when it is marked as imported. Before, a file stayed for good. Keeping the earlier behaviour for one way only would have meant two sets of rules.
- **(call)** The files are derived from the database. A decision is recorded first; then one function makes the client's folder match what is recorded. It runs after anything that changes what is waiting, and once at every start.
- **(call)** The client's file carries the name of its first invoice, `F_<supplier code>_<number>_<date>.xml`: the one shape of name the real SAGA has been seen to accept for a file of many. A name that says what the file is (`…_12-facturi_…`) was not tried in SAGA, so it is not used.
- **(call)** Changing the folder moves what is waiting: written in the new folder, removed from the old. Before, earlier files stayed behind.
- **(call)** Nothing that goes wrong while the folder is brought up to date undoes or blocks the decision. It is recorded per client, shown on the client's screen and on its invoices' screens ("Folderul pentru SAGA nu este la zi", with "Încearcă din nou"), written to the journal, and tried again at the next change and at the next start. While it lasts, nothing is marked as imported from the page; the command line and the API still do as told. Before, an invoice whose file could not be written stayed `pending` and was sent to Jev again at the next download.
- **(call)** A SAGA folder that cannot be reached is not taken for an empty one: its files stay on record until it is back. A folder left behind by choosing another one while it was away is let go.
- **(call)** The program removes only files it has on record (table `saga_files`, plus the paths earlier versions kept on each invoice). A file put in the folder by hand is never touched.
- **(call)** Coming from an earlier version, the first start writes each client's file and removes the single-invoice files that version left, those of imported invoices too. They can be made again from the database.
- **(call)** The button that marks invoices as imported names how many it marks, so a difference from what SAGA showed is seen before it is pressed.
- **(call)** An invoice's screen shows its own part for SAGA, made from the database, whichever file it is in and also after import.
- Never one file for several clients: SAGA books an invoice as a purchase of whichever company is open.

## Where it is

| Part | Where |
|---|---|
| Several invoices in one file; which files a set of waiting invoices makes | `saga.build_file`, `saga.files_for` |
| The files on record, a client's problem, the waiting invoices | `Store.saga_ledger`, `note_saga_file`, `forget_saga_file`, `place_in_saga_files`, `saga_problem`, `waiting_for_saga` |
| Making a client's folder match | `Service._write_saga_files`, `_place_saga_files`, `_note_saga_outcome`; one writer at a time (`saga-files.lock`, waited for) |
| The setting and its routes | `saga_file_per`, `"client"` or `"invoice"`: `Service.set_saga_output`, `write_saga_files`; `PUT /settings`, `POST /saga-files/write`; `saga` in `GET /invoices?cui=` and in an invoice's view |
| At the start of the program | `cli._bring_saga_files_up_to_date` |
| The page | `invoices/sagaFiles.ts` (texts), `ImportedInSagaCard`, `SagaFileCard`, `layout/SagaFilesDialog` |
| The drawing | board "Fișierul pentru SAGA: unul pentru fiecare client" on the canvas |

## Not done, on purpose

- No copy is kept of what was imported. An earlier idea, moving each imported file to an "Importate" folder, was left out: SAGA may read subfolders, and the database already has every invoice.
- No setting in `config.toml` for the way; it is chosen on the page or through the API.
- Nothing closes the small window in which an automatic download adds an invoice to the file between the import in SAGA and the press of the button. The count on the button is what makes it visible.

## After the review (2026-11-16)

A second reader found no way to lose an invoice or to delete a file the program did not write. What it did find was fixed, each with a test that fails without the fix:

- An invoice's own screen now says when its client's folder is not up to date, and does not tick it as imported meanwhile.
- A file was forgotten when its folder could not be reached; now it stays on record.
- The paths an earlier version kept on each invoice are put on record before the invoices forget them, so a first start that is cut short loses none.
- Any failure, not only one about a file, is noted as the client's problem; none fails the action, and one client's failure does not stop the others.
- The folder is read from the database at each write, so a long download does not write to a folder changed meanwhile.
- The waiting lock is the same kind as the download's, tried again every 50 ms for up to 30 seconds, in place of a Windows-only call.
- The setting is named `saga_file_per` (`client` or `invoice`), so that `saga_files` means one thing: the table of files.

Left as they are:

- After a backup is put back, a file written since that copy was made is no longer on record and stays in the folder. The README says to look through the SAGA folder after a restore.
- Every change writes the client's whole file again: about 0.6 s for 300 waiting invoices on the Mac.
- After a start with the SAGA folder away, each client keeps its notice until its next change or until "Încearcă din nou" is pressed on its screen; there is no button for all at once.
- The three page components have no tests of their own; the project tests the page's plain functions only.

## Not seen on Windows

Replacing a file while SAGA's import window has it open, two writers at once, a SAGA folder on a network share (where two files may look like one to the check that keeps a just-written file from being removed), and the removal of an earlier version's files at the first start.
