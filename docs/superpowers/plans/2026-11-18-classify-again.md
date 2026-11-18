# The invoices to check, classified again: for one client or for all at once — plan

## Context

An invoice is "de verificat" when neither your rules nor Jev could give it an account. It is "Așteaptă contul" when Jev did not answer (no credit, no connection) at the last download. Today such an invoice stays that way until a person decides it, or, for "Așteaptă contul" only, until the next download. Nothing applies a rule added afterwards to the invoices already waiting.

You asked for buttons that send these invoices back through the rules and Jev, all of them at once:
- one button on a client's screen for that client;
- one button on the client list for every client.

Design: canvas https://claude.ai/artifact/VSxb2ocdWVd9UtMUcuWukH, last board, "Clasifică din nou facturile de verificat".

## Evaluation

**When it helps**
- **After a rule is added or changed.** The new rule applies to every invoice that waits. This is the main use. It costs nothing and takes seconds.
- **After the accounts or Jev's question change.** Jev is asked with the new list or the new wording.
- **After Jev was unreachable.** "Așteaptă contul" invoices get their answer now, not at the next download.
- **After OpenRouter is set up** for the first time, or when its key is replaced.

**When it does not help, and costs**
- **Jev unsure, and nothing changed.** If Jev was unsure and its question is the same, it is usually unsure again. Each question is paid again.
- **On purpose:** an invoice sent twice, or one whose parties do not fit its kind. The program holds these back deliberately, and they come back "de verificat".

**What it must never do**
- **Undo your work.** A line you already chose keeps your account.
- **Touch decided invoices.** It never touches an invoice that has an account or is marked as imported in SAGA.

## Decisions

**Yours**
- **Which invoices:** the ones the rules and Jev could not classify.
- **Pass:** they go through the rules and Jev again, all at once.
- **Per client:** a button for one client.
- **All clients:** a button for all clients.

**My calls, say if you want something else**
1. **Which invoices.** Those of the client, received and issued, that are "de verificat" or "Așteaptă contul", and not marked as imported in SAGA.
2. **The same path as a download.** Rules first, then Jev, then you. An invoice that gets an account goes into the client's file for SAGA straight away.
3. **What is kept on an invoice decided line by line.**
   - A line you chose keeps its account, and Jev is not asked about it.
   - A line Jev was sure about keeps its account, unless one of your rules now matches it; rules always come first.
   - Jev is asked again only about the lines with no account.
4. **A tick "Întreabă-l din nou și pe Jev", on by default.**
   - Unticked, only the rules run: free, in seconds.
   - Unticked, what Jev said before stays as it was, including its proposal.
   - You did not ask for this. I add it because re-asking Jev about the same invoice usually gets the same uncertain answer and is paid every time.
5. **If Jev stops answering mid-way** (credit, key, connection):
   - The invoices after that stay as they were.
   - For the clients after that, only the rules run.
   - The window says so.
6. **All clients: one client at a time from the page,** like "Descarcă facturile pentru toți clienții". The window shows each client's progress and result. Clients that are switched off are included too: classifying does not contact ANAF.
7. **Where the buttons go:**
   - **Clients:** in the yellow card that already says "12 facturi sunt de verificat", beside "Vezi facturile de verificat".
   - **Client's screen:** in a card of the same kind above the tabs.
   - Both carry one sentence on when to use it.
8. **The journal:**
   - one line per client with the totals;
   - the invoices that get an account have their own line, as today;
   - those that stay "de verificat" are written as details, so forty unchanged invoices do not fill the journal.
9. **"Se descarcă deja facturi" becomes "Programul descarcă sau clasifică deja facturi."** The two share one lock, so a download pressed during a rerun is refused with that sentence.

## How it works

| Step | |
|---|---|
| What is waiting | `Store.to_classify_again(cui)`: "review" or "pending", not imported, oldest first. `Store.clients()` adds `waiting_count` ("pending", not imported) beside `review_count`. |
| One client | `Service.classify_again(cui, jev=True)`, under the same lock as a download: each invoice through `_classify_one(..., again=True)`; then the files for SAGA; then one journal line, `classification.again`. |
| The answer | `ok`, `cui`, `client`, `total`, `classified`, `review`, `waiting`, `skipped`, `jev_asked`, `jev_calls`, `jev_cost_usd`, `jev_stopped`. |
| All clients | `Service.classify_again_all(jev=True)`, for the command line: every client with something waiting. Jev is not asked again after one client reports `jev_stopped`. |
| For other programs | `POST /clients/{cui}/classify-again`, body `{"jev": false}` optional. Command line: `classify-again CUI [--no-jev]`, `classify-again --all [--no-jev]`. |

### Inside `_classify_one` with `again`

**The checks before the rules are the same as a download.**
- An invoice sent twice and one whose parties do not fit go back to "de verificat".
- On an invoice decided line by line, the lines you chose are kept there too.

**Whole invoice**
- A rule decides: it gets an account.
- No rule, Jev allowed: Jev is asked.
- No rule, Jev not allowed: the invoice is left exactly as it was, with no note.

**Line by line**
1. The lines you chose are filled in first.
2. The rules run on every other line; then the lines that follow the largest one.
3. A line Jev was sure about, that no rule matches now, keeps Jev's account.
4. The lines left:
   - Jev allowed: asked again, one question per distinct line.
   - Jev not allowed: they keep what they had, Jev's earlier proposal included.

**An invoice that waits for Jev ("Așteaptă contul")**
- Jev not allowed: it stays waiting, untouched. It must not become "de verificat" because a tick was off.
- Jev allowed: its lines already answered are reused, as today.

**A download is unchanged:** `again` is off.

**Clicking "Clasifică din nou, pe fiecare linie" on one invoice is unchanged:** it still decides everything again from the start.

## The work, tests first

| # | Part | Where |
|---|---|---|
| 1 | `to_classify_again`, `waiting_count` | `store.py`, `tests/test_store.py` |
| 2 | One loop for a download and for a rerun (`_classify_each`); `again` in `_classify_one` and `_classify_lines`; the journal as details; `classify_again`, `classify_again_all` | `service.py`, `tests/test_classify_again.py` |
| 3 | Route, command line, README | `api.py`, `cli.py`, `README.md`, `tests/test_ui_api.py`, `tests/test_cli.py` |
| 4 | Page: the call and its types; `ClassifyAgainDialog` (before, running, after) with its texts in a plain module with tests; the card on the client list and on the client's screen; the journal line; the "busy" sentence | `frontend/src/classifyAgain/…`, `clients/ClientsPage.tsx`, `invoices/ClientInvoicesPage.tsx`, `journal/eventTexts.ts`, `errorMessages.ts`, `types.ts`, `api.ts` |

## Verification

1. `pytest`, `vitest`, the type check, lint and the build.
2. **Tests on made-up invoices:**
   - A rule added after the download decides an invoice "de verificat", whole and line by line, without Jev being asked.
   - A line you chose keeps its account, and Jev is asked nothing about it.
   - A line Jev was sure about is not asked again; a rule that now matches it wins.
   - Unticked: no call to Jev, and Jev's earlier proposal stays. A "pending" invoice stays "pending".
   - Jev failing mid-way: the invoices after it stay as they were; `jev_stopped` is said; `--all` does not ask Jev for the next clients.
   - Invoices with an account, or imported, are not touched; one sent twice comes back "de verificat".
   - The invoice that gets an account is in the client's file for SAGA.
   - A download running at the same time: `busy`, nothing changed.
3. **In the demo, in the built-in browser:**
   - add a rule;
   - the button on the client's screen, ticked and unticked;
   - the button for all clients with its progress;
   - the lists and the counts after "Gata".
4. **An independent review before release.**

## Limits

- **Time.** With Jev ticked, a client with many invoices to check takes as long as the questions do, a few seconds each. The window stays open meanwhile.
- **The automatic download.** If it starts while a client is being classified again, it waits up to a minute. Past that, that client is downloaded at the next scheduled time.
- **The per-line switch turned off since.** On an invoice that was being decided line by line, the lines you chose are not kept: the invoice is decided whole, as the switch now says.
- **No cost estimate before starting.** The window says that Jev is paid per question and shows what it cost at the end, per client.
