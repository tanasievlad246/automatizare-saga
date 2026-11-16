# An account for every line, and issued invoices in the process — design

Date: 2026-11-16. Approved by the owner on that day, as the plan below. Items under "My calls" were decided by Claude and can be changed; the rest is the owner's.

Where it stands is said at the end, under "Progress".

## Context

Two things, which belong together:

1. **Issued invoices.** Since 0.8.0 the invoices a client issued (`FACTURA TRIMISA`) are saved, counted and can be looked at. They get no account, nothing for SAGA, no marking as imported. You asked for them to be classified with a `cont` and managed like the received ones.
2. **An account per line.** Today the largest line of an invoice decides one account for the whole invoice. You asked for every line to go through the rules or Jev by itself, with a switch per client that is on by default, so that each line carries its own account in the XML for SAGA.

The goal: for every client, every line of every invoice, received or issued, gets its own account from your rules, from Jev or from you, and the client's file for SAGA holds each line with that account.

## What is known, and from where

- **SAGA takes an account on every line.** Its import format has `<Cont>` inside each `<Linie>`. The program writes it today, the same account on all lines.
- **SAGA takes issued invoices in the same format.** Its manual: *"Dacă tag-ul `<FurnizorCIF>` reprezintă codul fiscal al societății, factura se va importa în ecranul «Ieșiri». Altfel, importul se va efectua în ecranul «Intrări»."* The program already writes the supplier and the client from the invoice itself, so for an issued invoice the client is the `Furnizor`. Not tried in SAGA.
- **The files need no new code for issued invoices.** Invoices are picked for the file by state, not by kind.
- **A rule already reads one line.** Today it is given only the largest one.
- **Not known:** whether SAGA accepts one file that mixes received and issued invoices.
- **Not known:** whether Jev's service answers several questions in one request. Today it is asked one question per invoice.
- **Not known:** whether ANAF gives one invoice the same message id in the seller's list and in the buyer's. The program keys every message on that id alone.

## Decisions

**Yours** (your request, your four answers and your note on this plan)
- Every client's issued invoices are classified. No switch per client for that.
- A client's screen has a toggle between received and issued.
- The issued invoices already downloaded enter too, all of them.
- With one file per client, the same file holds received and issued invoices.
- Each line goes through the rules, then Jev, and has its own account in the XML.
- A switch per client, "Clasificare pe fiecare linie", ticked by default.

**My calls — say if you want something else**

*An account per line*
1. **It covers received and issued invoices alike.** That is how I read "for that client".
2. **On for every client, the ones you already have too.** With the switch off a client works as today: the largest line decides one account for the whole invoice.
3. **It applies to invoices decided from then on.** Invoices that already have an account keep it. "Clasifică din nou" on an invoice decides it again, line by line.
4. **Per line: your rules, then Jev, then you.** A rule on a supplier still gives every line of that supplier its account.
5. **Jev is asked only for the lines no rule decided,** and lines with the same text once. That is more questions than today (one per invoice), so it costs more; "Costuri Jev" will show it.
6. **A line Jev is unsure of is the only one left to you.** The invoice is "de verificat" until every line has an account; the other lines keep theirs.
7. **Discounts follow the largest line.** A line with a negative value on an ordinary invoice, and a discount or charge written on the invoice as a whole, take the account of the largest line unless a rule matches. Jev cannot judge the word "Discount".
8. **Jev gets a question written for one line.** Today's question stays for clients with the switch off.
9. **Other programs keep working.** `cont` on an invoice stays, as the account of its largest line; a new `lines` field carries each line's account, who chose it and how sure Jev was.
10. **The journal gets one line per invoice** ("3 linii: 2 după reguli, una de Jev"), not one per line.

*Issued invoices*
11. **Accounts for issued invoices are a list of their own** (701, 704, 707…), and Jev gets questions of its own for them. How sure Jev must be stays one setting.
12. **A rule is for one kind.** A rule for received invoices never decides an issued one. Rules for issued invoices look at words, article codes and classification codes; no rule by buyer in the first version, because a buyer can be a person.
13. **Jev is sent the lines and totals of an issued invoice, never the buyer's name or code.** If you would rather not send invoices issued to persons to Jev at all, say so: they would go to a rule or to you.
14. **The buyer's phone and e-mail are left out of the file for SAGA** on issued invoices.
15. **An invoice whose parties do not fit its kind goes to you**: one listed as issued whose supplier is not the client, or a client's invoice to itself. SAGA sorts by `FurnizorCIF` and could file it on the wrong side.
16. **One SAGA card, one button:** "12 facturi gata: 7 primite și 5 emise" in one file; "Da, am importat cele 12 facturi" marks both kinds.
17. **The backlog is decided at each client's next download.** At the first start after that update, every saved issued invoice that can be read and is not marked as imported starts waiting.
18. **Counts name the kinds apart:** "3 primite noi · 2 emise noi". "De verificat" counts both and opens the right list.
19. **The 0.8.0 switch "Arată facturile emise" goes away;** the toggle replaces it. `show_issued` stays accepted by `/settings` and does nothing.
20. **Value only, no stock.** Article codes stay out of the file, so SAGA takes nothing out of a warehouse.

*Order*
21. **The account per line is built first, issued invoices second.** It changes how an account is kept and written; issued invoices then have it from their first day, and nothing is built twice.
22. **"Reguli propuse" and "Testează regulile" follow last,** for lines and for issued invoices. Until then they work as today, from received invoices and their largest line.

## Design

On the canvas: **https://claude.ai/artifact/VSxb2ocdWVd9UtMUcuWukH**, last row, board **"Propunere: facturile emise, luate în lucru"**. I drew it before your answers, and plan mode does not let me change it. **Redrawing it is the first step after approval, and I show it to you before any screen is built.**

What still holds on it: the toggle "Facturi primite / Facturi emise", the issued list with account and state, an issued invoice's screen, the two tabs on the rules screen.

What no longer holds: the card that takes a client's issued invoices in (section 2), the separate file and button for issued invoices and "Nu le mai lua în lucru" (section 3), "contul obișnuit al clientului" (section 4), the rule by buyer (section 5).

What is missing and will be drawn:
- **The switch** on a client's screen, beside its name: "Clasificare pe fiecare linie", on, with one sentence saying what off means.
- **An invoice's lines with their accounts:** in the table of lines, a column "Cont" with the account, a mark for who chose it, and "Schimbă" on the line; a line to check is highlighted with "Alege contul".
- **The account card as a summary:** "605 · 2 linii, 6581 · o linie", "o linie de verificat", and "Pune același cont pe toate liniile".
- **The lists:** "Cont" shows "605" or "605 +1".

## Four checks before I build

1. **A trial in SAGA.** Send me one issued and one received invoice of the same client (their XML from ANAF). With the program as it is I make four files: the received one with two different accounts on its lines; the issued one alone with account 704; both in one file; the mixed file again, to import twice. To look at: are the accounts per line kept; does the issued one land in "Ieșiri" with account and VAT; does the mixed file work; does SAGA mind `FurnizorCIF` with "RO"; does it try to send the sale to e-Factura again; what does it do with a buyer who is a person.
   - If accounts per line are not kept, or the issued one fails, I stop and come back with what SAGA wants.
   - If only the mixed file fails, a client gets two files and two buttons.
2. **One call to Jev with three questions,** from a small script you run once on the PC that has the key. If the service answers all three, an invoice is one request; if not, the program asks line by line, which is slower.
3. **Two `SELECT`s on the real database:** is one upload saved under the same id for seller and buyer, and do invoices one client issued to another client of yours have the buyer's copy? If ANAF shares the id, 0.8.0 already loses one of the two, and that fix goes first.
4. **Your view of the redrawn board.**

## How it will work

| Step | Today | After |
|---|---|---|
| Saved by a download | a received invoice waits for an account | an invoice of either kind waits |
| Rules | read the largest line | read every line, with the rules of the invoice's kind |
| No rule | Jev, one question for the invoice | Jev, a question for each line left, with the accounts of that kind |
| Jev unsure | the invoice is to check | that line is to check; the invoice with it |
| Has an account | every line the same | every line its own |
| File for SAGA | received invoices | both kinds in the client's file |
| Client with the switch off | — | as today: the largest line decides for the invoice |

## The work

Tests first throughout. `service.py` is one file, so its steps run one after another.

### Phase A — an account per line (0.9.0)

| # | Part | Where |
|---|---|---|
| A1 | The client's switch; where a line's decision is kept | `store.py`: `clients.per_line` (default on), `messages.line_decisions` (`_migrate`); `Service.set_client_per_line`; `PUT /clients/{cui}/per-line` |
| A2 | Deciding lines | `classify.py`: a `Subject` for each line, rules per line, the request to Jev with a question per undecided line (same text once), reading several answers, the question for a line |
| A3 | The invoice's state from its lines | `service.py`: `_classify_one` (per line when the switch is on; discounts follow the largest line), `_finish`, `_to_review`, `set_cont` with a line, accepting Jev's proposal per line, one journal line per invoice |
| A4 | The account on each line of the file | `saga.py`: `Entry` carries the lines' accounts; `_add_factura` writes them; discounts on the invoice take the largest line's |
| A5 | For other programs | `lines` on every invoice returned; `POST /invoices/{id}/cont` takes `line`; CLI the same |
| A6 | The page | `invoices/ClientInvoicesPage` (the switch), `RenderedInvoice` (account per line), `AccountCard` (summary, same account for all), `InvoicesTable`, texts in plain modules with tests |
| A7 | Demo with invoices on several accounts, README, design note, version | `demo.py`, `README.md`, `docs/superpowers/specs/` |

### Phase B — issued invoices in the process (0.10.0)

| # | Part | Where |
|---|---|---|
| B1 | The second list of accounts, the questions for issued, a rule's kind, moving a rule within its kind | `store.py`: table `issued_accounts`, `rules.direction` (`_migrate`), settings keys with the default texts as fallback |
| B2 | Proposals stay on received invoices; counts and "new" per kind | `store.py`: `decided_without_rule`, `classified_subjects`, `IS_NEW_SQL`, `LATEST_RUN_JOIN`, `Store.clients()` |
| B3 | What a rule and Jev read from an issued invoice | `classify.py`: no buyer in a `Subject`, neither party in the request |
| B4 | The backlog, once | `store.py`: readable issued invoices not marked as imported start waiting; a flag in `settings` |
| B5 | Deciding an issued invoice | `service.py`: `_save_message`, `_classifiable`, `_classify_one` (duplicate → parties fit → rules of its kind → Jev → to check), `_rulebook_for(store, cui, kind)`, journal lines without the buyer |
| B6 | The buyer's phone and e-mail out of the file; tests for `FurnizorCIF` and for one file with both kinds | `saga.py` |
| B7 | Rules, accounts and questions by kind over the API; `review` says the kind | `service.py`, `api.py` |
| B8 | The page | `ClientInvoicesPage` (toggle, replaces `IssuedInvoicesCard`), `InvoicesTable` (buyer), `InvoicePage`, `ImportedInSagaCard`, `rules/RulesPage` and its cards (two tabs), `clients/ClientRow`, `ClientsPage`, `clients/syncOutcome`, `costs/JevCallsTable`, texts |
| B9 | Demo answers for sales, README, design note, version | `demo.py`, `standins.py`, `README.md` |

### Phase C — the helpers (0.11.0)

- Rules proposed from decisions on single lines, and from issued invoices (`suggestions.py`, `ProposedRulesSection`).
- "Testează regulile" line by line and for a made-up issued invoice (`rules/test/`).
- A rule by buyer, if phase B shows it is missed.

## Verification

1. `uv run pytest`, `pnpm --dir frontend test`, type check and build at every step. Today's tests stay as the proof that a client with the switch off works as before.
2. **Per line, against the stand-ins:** an invoice with three lines decided by a rule, by Jev and by nobody: two accounts kept, one line to check, the invoice to check; after the choice, the file has three `<Cont>` values on the right lines; a discount line carries the largest line's account; the same invoice for a client with the switch off gets one account as today.
3. **Issued, against the stand-ins:** a download bringing both kinds; an issued invoice never decided by a rule for received invoices; one file per client holding both, the issued ones with the client as `FurnizorCIF`; marking as imported empties it.
4. **The backlog:** a database made by 0.8.0 with issued invoices; after the update they wait, and the next download decides them, once.
5. **Nothing about the buyer leaves:** the requests to Jev for an issued invoice and every journal line are searched for the buyer's name and code and must hold neither.
6. **In the built-in browser on made-up data:** every section of the redrawn board.
7. **An independent review per phase**, fixed before the release.
8. **Yours:** the first real file imported in SAGA before a release is called done.

## What cannot be checked here

- SAGA itself, and Jev's real service: both rest on the checks above.
- Windows.
- Real ANAF data: invoices with a hundred lines, issued to persons, in foreign currency, storno invoices.

## Limits to know about

- **Jev costs and takes more.** One question per line no rule decides. An invoice with sixty different lines is sixty questions; rules are what keeps that down.
- **Double booking.** A client whose invoices are issued from SAGA already has them there. SAGA's option "Nr.+data" skips what it has; or tick those invoices as imported without importing them.
- **A long backlog makes a client slow for a while.** Every change writes the client's whole file again. It passes once the old ones are ticked as imported.
- **Lists are not cut.** The issued list becomes the same table as the received one; the "first 200" of 0.8.0 goes with the old card.

## Not included

- Stock: articles, warehouses, quantities leaving stock in SAGA.
- Partial VAT deduction per line (`TipDeducere`).
- Receipts and payments (SAGA's `I_` and `P_` files).
- Changing the Power Automate flows: the file stays one per client.

## Publishing

Nothing is pushed without your word. Each phase gets its own branch, review and an offer to release.

## Progress

- 2026-11-16: the board is redrawn on the canvas ("Plan: cont pe fiecare linie și facturile emise în lucru"). The owner has not yet said it is right.
- 2026-11-16: the three checks for the real programs are in `scripts/trials/` (`saga_trial.py`, `jev_trial.py`, `id_check.sql`). None has been run yet.
- 2026-11-16: A1 is built: the client's switch (`clients.per_line`, on by default, `PUT /clients/{cui}/per-line`). Nothing reads it yet.
