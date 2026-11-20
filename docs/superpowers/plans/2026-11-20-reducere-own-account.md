# A discount on the whole invoice ("Reducere") with its own account: plan

Date: 2026-11-20. The owner said "dive in", so this was built from this plan without a round of approval. Everything under "My calls" can be changed.

## Context

You asked for two things.

1. **The "Reducere" of an issued invoice must be able to have its own account.** Your example: a ride invoice with one line, "Tarif de călătorie" 16,10 lei, and a discount written on the invoice as a whole (`AllowanceCharge`), "Reducere" 4,30 lei. The fare goes on 704, the discount on 729.
2. **The quantity of that line showed as "1 e48".**

**How it worked before.**
- SAGA gets such a discount as a line of its own, after the invoice's lines, so the totals match. That line always took the invoice's account: on screen it said "ca linia cea mai mare" and had no "Schimbă".
- An invoice with one line was decided whole: one account for everything on it.
- `E48` is the code for "service unit". The program had no name for it, so the code itself was shown, in small letters.

Design: canvas https://claude.ai/artifact/VSxb2ocdWVd9UtMUcuWukH, board "Reducerea de pe factură, cu contul ei".

## Decisions

**Yours**
- The Reducere has its own account, and it goes through the rules, then Jev, then you, like a line.
- In your example the fare is 704 and the Reducere 729.
- The demo gets a ride-sharing client with such invoices, to try Jev on.

**My calls, say if you want something else**

1. **The Reducere is a line like the others, numbered after the invoice's own lines**: line 2 on an invoice with one line. That is the number it already has in SAGA's file. So everything a line has, it has: its account in the table, "Schimbă", the window with Jev's proposal, "Sau hotărăște din nou această linie", its rows in "Cum s-a ales contul".
2. **An extra charge written on the whole invoice ("Taxă suplimentară") is treated the same way.** One kind of row, one way of deciding it.
3. **An invoice with one line and a Reducere is decided line by line**, for a client with "Clasificare pe fiecare linie" on: it has two rows to book. It shows the summary card ("704 · o linie, 729 · o linie") and "704 +1" in the lists.
4. **A client with the switch off keeps one account per invoice**, the Reducere included, as before. "Împarte pe linii" is now offered when the invoice has a line and a Reducere, and then the Reducere can be changed.
5. **Nothing already decided is decided again by itself.** No surprise questions to Jev, no file for SAGA rewritten.
   - An invoice already on lines, whose Reducere was on the largest line's account, keeps it, shows it as "ca linia cea mai mare" and now has "Schimbă" on it.
   - An invoice with one account stays so until you split it or decide it again.
   - "Clasifică din nou" and "Hotărăște din nou" decide the Reducere the new way.
6. **What Jev is told**: the row as a line (its name, the value with a minus) and that it is a discount, or a charge, on the whole invoice. Not the other lines, as for any line.
7. **A discount written as a line of the invoice stays as it is**: it takes the largest line's account unless a rule matches it, and Jev is not asked. You spoke of the Reducere on the invoice; say if lines with a minus should go to Jev too.
8. **"Testează regulile" stays as it is**: a trial is the invoice's lines, without what is written on the whole invoice. It tries received invoices only, so it could not try a ride's invoice anyway. To see what Jev alone makes of a Reducere, use "Sau hotărăște din nou această linie" → "Doar cu Jev" in its window.
9. **"1 e48"**: `E48` is written `SERV`, on screen ("1 serv") and in SAGA's file (`<UM>SERV</UM>`).
10. **The demo**: a fourth client, "Drum Bun Ride SRL", with issued ride invoices: with a Reducere Jev is sure of, with a "Cod promoțional" Jev is unsure of (it waits for you), and one without a discount. The account 729 is in the demo's list for issued invoices. Each second download brings it another ride invoice. Asked for after the first round: a ride with three lines and one discount, one with two discounts of different names, and one with two lines and three discounts (the same one twice, asked of Jev once, and one Jev is unsure of).

## How it works

| Step | Before | After |
|---|---|---|
| The rows that get an account | the invoice's lines | the lines, then each discount or charge on the whole invoice |
| A Reducere | the largest line's account, always | a rule, else Jev, else you |
| One line and a Reducere, switch on | one account for the invoice | two rows, each with its account |
| The file for SAGA | the Reducere on the invoice's account | on its own |
| Jev unsure of the Reducere | — | the invoice is "de verificat" until you choose |

## The work

Tests first throughout.

| # | Part | Where |
|---|---|---|
| 1 | `E48` → `SERV` | `saga.py` (`UNITS`) |
| 2 | The rows of an invoice: `Invoice.rows` (lines, then each adjustment as a `Line` numbered after them), `Invoice.on_whole_invoice(number)` | `invoice.py` |
| 3 | Rules read every row; such a row never "follows the largest line"; Jev's question says what the row is (`fel`) | `classify.py`: `rules_by_line`, `follows_largest`, `jev_line_request` |
| 4 | Deciding by rows: line by line when there is more than one row; a person's choice, one row decided again, splitting, keeping answers when OpenRouter stops | `service.py`: `_classify_one`, `_classify_lines`, `classify`, `split_into_lines`, `_aligned`, `_merged`, `_keep_answered` |
| 5 | Invoices decided before: a row without a stored account follows the largest line | `service.py`: `_aligned` |
| 6 | The row's account in the file | `saga.py`: `_rows` numbers the row, `Entry.cont_for` |
| 7 | What the screen is given: each adjustment with its number, name and value; the accounts lined up with the rows | `service.py`: `_as_json`, `invoice_view` |
| 8 | The page: the account cell on the Reducere row, the window, the rows under a file's invoice, "Împarte pe linii" counted by rows, the history's names | `invoices/RenderedInvoice.tsx`, `lineAccounts.ts`, `LineAccountDialog.tsx`, `InvoicePage.tsx`, `sagaFiles/waitingFiles.ts`, `sagaFiles/InvoiceLines.tsx`, `types.ts` |
| 9 | The demo's ride-sharing client | `demo.py`, `standins.py` (a buyer who is a person) |
| 10 | README, the built page | `README.md`, `src/efactura/ui/` |

## What to look at closely

1. **An invoice decided line by line before this version, with a Reducere.** It must keep its accounts, and choosing another line's account must not send it back to "de verificat" because of the Reducere.
2. **A client with the switch off, and a company that is not in the client list.** Nothing changes: one account, the same file.
3. **"Clasifică din nou" while Jev cannot be asked.** The Reducere of an older invoice stays as it was.
4. **A credit note with a discount on it.** The row is still a discount: its value has the other sign than the lines.
5. **A Reducere without a reason written.** It is named "Reducere", and a rule on that word matches it.
6. **An invoice with a Reducere and no line at all.** It goes to a person, as before.
7. **Jev unsure of the Reducere.** The invoice waits, is out of the file for SAGA, and comes back into it once the account is chosen.

## Verification

1. `uv run pytest` and `pnpm --dir frontend test`, type check and build.
2. Your invoice's XML through the program: two rows, 704 and 729, in SAGA's file.
3. In the built-in browser on the demo: the ride client's invoices, the Reducere row with its account, the window, the row that waits, the file for SAGA.

## What cannot be checked here

- SAGA itself: that it books the Reducere line on 729 as it books any line on its account. The line was already in the file; only its account changes.
- Jev's real service on the word "Reducere": the demo's Jev answers from a list.

## Not included

- Discounts written as lines of the invoice: unchanged (call 7).
- A discount on the whole invoice in "Testează regulile" (call 8), and trying issued invoices there at all.
- Deciding again, in bulk, the invoices that already have an account.
- Telling Jev what the discount was given on (the other lines are not sent).
