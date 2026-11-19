# Line descriptions, accounts changed and decided again, the history of an invoice's account, and `*` on both sides — plan

> For agentic workers: build it task by task, tests first (write the test, watch it fail, make it pass). Nothing is committed until the user asks.

## Context

Six requests, for received and issued invoices alike:

1. A line's description (`cac:Item/cbc:Description`) counts when the rules and Jev decide a line.
2. The description shows on the invoice's screen, on its line.
3. A person can change the account of a line, or of the whole invoice. An invoice classified whole, with one account, can be turned into one decided line by line, and then each line chosen by hand or decided again.
4. A person can have an invoice, or one line of it, decided again: with the rules and Jev, or with Jev alone.
5. Each invoice keeps a history of its account, on its own screen: what was chosen and why, which rule and which words, what Jev answered and how sure it was, what a person changed.
6. In a keyword, `*` also works at the start of a word and on both sides.

Design: canvas https://claude.ai/artifact/VSxb2ocdWVd9UtMUcuWukH, last board, "Descrieri, conturi schimbate, hotărâte din nou și istoricul".

Before any code: the fixes of the code review and the readable XML view are uncommitted work in the main checkout (branch `review-fixes`, no new commits yet). They touch `_classify_one`, `_classify_lines`, `_record_lines`, `classify.py`, `invoice.py`, `saga.py`, the same places as this plan. This branch is rebased onto `review-fixes` once that work is committed there.

## What is there today

**1. The description.** `invoice._line` keeps `cbc:Name or cbc:Description`: a line that has both is decided on its name alone. Everything else reads that one text:

| Reads the line's text | Today | From now on |
|---|---|---|
| `classify.subject_of`, `line_subject` (what a rule reads) | name | name and description |
| `rules.py` keywords (`Subject.text`) | name | name and description, each a text of its own: a phrase never runs from one into the other |
| `classify.same_question` (lines asked about once) | name | name and description: two lines with one name and two descriptions are two questions |
| `classify._describe` (what Jev is sent, whole invoice and one line) | `descriere`: name | `descriere`: name, and `detalii`: the description, only when the line has one. A line without a description is sent exactly as today |
| `suggestions.propose`, the proposed rule's card | words of the name | words of the name, then of the description; the card shows both |
| The rule test | one text per line | name and an optional description per line; "O factură salvată…" brings both |
| `saga.py`, SAGA's `<Descriere>` | name | unchanged: the name (the description when there is no name). See decision 2 |

**2. On screen.** `RenderedInvoice` shows `line.description` only.

**3. Changing an account.** Checked in the code and in the demo:
- **Works:** "Schimbă contul" on an invoice with one account, received and issued, each with the accounts of its kind. "Schimbă" on each line of an invoice decided line by line, and "Pune același cont pe toate liniile", received and issued (seen on the demo's issued AC-2030).
- **Missing:** one line of an invoice that has one account for all its lines. `set_cont(line=…)` refuses ("Classify it again to decide it line by line"), and "Clasifică din nou, pe fiecare linie" shows only when the client's switch is on, asks Jev again and drops the account.
- **Blocked on purpose:** an invoice imported in SAGA. Unticking "Am importat factura în SAGA" opens it again, but the account card says only that the account no longer changes, not how.

**4. Deciding again.** `POST /invoices/{id}/classify` with `force` decides one invoice from the start, rules then Jev, following the client's switch. The page offers it only as "Clasifică din nou, pe fiecare linie". There is no "Jev only", and nothing for one line.

**5. What is kept today.**
- **The journal** (`account.by_rule`, `account.by_jev`, `account.to_review`, `account.by_lines`) holds the invoice id. But:
  - it is emptied after 30 days and past 50,000 lines;
  - a line is dropped when the database is busy;
  - a line by line decision is one line with counts, not each line;
  - it never says which word of a rule matched;
  - finding one invoice in it means searching the text of every line.
- **`jev_calls`** keeps every question and answer forever, but says nothing of the rules or of a person.
- **`line_accounts`** on the invoice holds only the latest decision.

**6. Keywords.** `_keyword_regex` puts a word start before every keyword and a word end after it, unless it ends in `*`.

## Decisions

**Yours (the requests)**
- The description counts for the rules and for Jev, and shows on its line.
- A line or a whole invoice can get another account; an invoice or a line can be decided again, with the rules and Jev or with Jev only.
- An invoice classified with one account can be split into lines, each then chosen by hand or decided again.
- A history per invoice, on its screen.
- `*` at the start, at the end, or both; case and diacritics still ignored.

**My calls, say if you want something else**

1. **Name and description stay apart in the code.**
   - `Line.description` keeps what it holds today: the name, or the description when there is no name.
   - A new `Line.details` holds `cbc:Description` when the line has a name too and the two do not say the same (compared the way keywords compare: case and diacritics ignored). So an invoice that repeats its name as description is not sent to Jev twice.
   - This way the SAGA file and the API's `description` keep their meaning.

2. **SAGA keeps the name only.**
   - `<Descriere>` is what SAGA shows in its lists, and a long description would make them hard to read.
   - SAGA's line also has an empty `<InformatiiSuplimentare>`. The description could go there, but you did not ask for it, and how SAGA shows and cuts that field has not been checked. Say if you want it.

3. **Jev's questions stay as they are.** The line already reaches Jev as data; the description arrives as `detalii` beside `descriere`. Questions you changed on the rules screen are not touched.

4. **"Împarte pe linii": an invoice classified with one account becomes one decided line by line.**
   - **Where:** a button on the account card of an invoice that has an account, more than one line, and is not imported. Beside it, one sentence: the lines start with the invoice's account; then each can be changed or decided again.
   - **What it does:** at once, with no window and no cost, the invoice is split into lines.
     - The largest line keeps how the account was chosen (the rule, Jev and how sure it was, or you).
     - Every other line keeps the invoice's account as its own, marked "contul facturii, păstrat la împărțire" (method `invoice`).
     - A discount or a line worth nothing takes the largest line's account, as anywhere else.
     - Nothing changes in SAGA's file until a line gets another account.
   - **Then, per line**, "Schimbă" in the "Cont" column opens the line window: choose an account by hand, or "Sau hotărăște din nou această linie" (decision 7).
   - **All lines decided again at once:** after splitting, "Hotărăște din nou…" (decision 6) decides every line, with the rules and Jev or with Jev only.
   - **A line kept from the invoice counts as kept by you.** A later "Clasifică din nou facturile de verificat" leaves it as it is, as it does with a line you chose.
   - **The client's switch** keeps deciding how the program chooses by itself, at a download. It does not limit what you do on one invoice.
   - **Before it has an account,** an invoice with one account is decided from the account card, as today; once it has one, it can be split.
   - **Going back to one account** is not offered. "Pune același cont pe toate liniile" gives SAGA the same file.
   - **For other programs:** `POST /invoices/{id}/split`, and `efactura split <id>`. Until it is split, `set-cont --line` on such an invoice still refuses, now pointing to `split`.

5. **An imported invoice stays closed.** Its account card gives the way out in steps instead of a dead end: delete it in SAGA, untick "Am importat factura în SAGA" below, choose the account, import it again. Nothing changes on the program's side.

6. **Deciding again, the whole invoice: "Hotărăște din nou…"**
   - It is an outline button on the account card, offered in every state except imported or unreadable. It opens a window with two choices:
     - **"Cu regulile, apoi Jev"**: as a download does;
     - **"Doar cu Jev"**: the rules are skipped.
   - The window says what happens: the invoice is decided from the start, the lines you chose included.
   - The invoice keeps its shape: one decided line by line stays so, one with one account stays whole. Splitting is "Împarte pe linii" (decision 4).
   - With "Doar cu Jev", a discount or a line worth nothing still takes the largest line's account, as in the rule test.
   - "Clasifică din nou, pe fiecare linie" goes: "Împarte pe linii", then "Hotărăște din nou…", does the same in two plain steps.
   - `classify` from the command line or the API without the new `per_line` keeps following the client's switch, as today.

7. **Deciding again, one line.**
   - The line window gets "Sau hotărăște din nou această linie", with "Cu regulile, apoi Jev" and "Doar cu Jev".
   - Only that line changes, plus the lines that follow it when it is the largest.
   - "Doar cu Jev" asks Jev about that line whatever it is, a discount included: you pointed at the line and asked for Jev.
   - It is there on every invoice decided line by line: decided so by a download, or split by you (decision 4).
   - A line that only follows the largest line has nothing of its own to decide, so the window offers the choice of an account alone, as today.

8. **The history is a small table of its own, `decisions`, not the journal.**
   - The journal is for finding out why something failed: it is cleared after 30 days, it may drop a line, and it holds counts where you need lines.
   - The history must last as long as the invoice, say for a check months later, and hold what the journal never had: the word a rule found.
   - Jev's full answers stay in `jev_calls`; the history keeps the choice, how sure Jev was, the threshold and the likelihood of each account, the same figures the invoice row keeps today.
   - It is written only when an account, or the lack of one, actually changes. A "Clasifică din nou" that leaves forty invoices as they were writes nothing.
   - It is not cleared, it is in the backups and restored with them, and the journal stays as it is.

9. **Where the history shows:** a fourth tab beside "Factura", "Fișierul de la ANAF" and "XML pentru SAGA", called **"Cum s-a ales contul"**.
   - The newest moment comes first. Each moment says when and how it happened:
     - "La descărcare";
     - "Clasificată din nou";
     - "Hotărâtă din nou: regulile, apoi Jev" or "Hotărâtă din nou: doar Jev";
     - "Împărțită pe linii de dumneavoastră";
     - "Ales de dumneavoastră".
   - Under it come the lines that changed. Each gives the account and why:
     - which rule, and what it found and where ("în descrierea liniei scrie «cartușe»");
     - Jev's choice, how sure it was against the threshold, and, folded, how likely it found each account;
     - what it had before.
   - Lines that got the same thing in the same moment (account, who, and why) are one row: "Liniile 2 și 3".
   - A moment with more than 6 rows shows 6 and "Arată toate cele N linii".
   - Invoices decided before this version have no history; the tab says so.

10. **`*` at the start and the end.**
    - The forms: `transport*` (starts with), `*cartus` (ends with), `*cartus*` (contains).
    - A `*` in the middle stays a plain character, as today.
    - A keyword made only of `*` is dropped, as an empty keyword is today, so no rule ever matches every line.
    - Proposed rules still offer plain words.

## How it works

### Backend

| Part | What |
|---|---|
| `invoice.Line` | new field `details: str \| None = None`, see decision 1 |
| `rules.Subject` | new field `details: str \| None = None`. `text` is the name, `" · "`, the description, both normalised. `to_json` writes `details`; `from_json` reads it with `.get`, so subjects saved before keep working |
| `rules.RuleMatch` | two new fields: `matched: str \| None` (the word or words of the line the keyword found, normalised, such as `cartuse`) and `in_details: bool` (found in the description, not the name) |
| `rules._keyword_regex(keyword)` | a leading `*` allows any letters before, a trailing one any after; otherwise a word start and a word end. `Rule._any_keyword` puts the word start into each keyword's own part. `Rule.__post_init__` drops keywords with nothing left once the `*` at both ends are taken off |
| `classify` | `Decision` gains `match: RuleMatch \| None`. `rules_by_line` returns `dict[int, tuple[Rule, RuleMatch]]`. `subject_of`, `line_subject` pass `details`. `same_question` adds `normalise(details)`. `_describe` adds `"detalii"` only when there is one |
| `suggestions.propose` | reads the words of the name, then of the description (at most 6 together, as today) |
| Line entries (`line_accounts`) | gain `"match": {condition, found, prefix, matched, in_details} \| null`, so the screen and the history can say which words decided |
| Store | table `decisions` (below), `add_decisions(rows: list[dict])`, `decisions(message_id) -> list[dict]` newest first |
| Who decided | `source` is one of `download`, `again`, `redecide`, `person`, `split`. With `jev_only` it travels with the way a decision is made, beside `again`, from `_classify_each` and `classify` down to `_finish`, `_to_review` and `_record_lines` |
| Writing the history | `_finish` and `_to_review` write one row with `line` null when the invoice's account, method, reason or Jev's proposal differ from what the row held. `_record_lines` writes one row per line whose entry differs from the stored one; an invoice that was whole before writes every line. `before` is the account it had |
| `Service.classify(message_id, force=False, ask="rules_then_jev", line=None, per_line=None)` | `ask` is one of `TRIAL_ASKS`. Whole invoice: from the start; `jev_only` skips the rules (line by line: no rule on any line; whole: no `decide_by_rules`). `per_line`: `True` line by line, `False` one account, `None` the client's switch, as today. `line`: only that line of an invoice decided line by line, see decision 7. Refused for an imported invoice, as today |
| `Service.split_into_lines(message_id)` | decision 4. Refused (`invalid_input`) without an account, with one line, or already line by line; refused (`not_classifiable`) when imported. Recorded through `_record_lines`, so the file for SAGA and the history follow |
| Method `invoice` | a line that kept the whole invoice's account when a person split it. Added to `BY_A_PERSON`, so `classify_again` keeps it; `_lines_summary` says "as the whole invoice" |
| `Service.decision_history(message_id)` | `{"ok", "decisions": [...]}`, each row with its `said` read back as an object |
| Routes | `POST /invoices/{id}/classify` body gains `ask`, `line` and `per_line`. New `POST /invoices/{id}/split` and `GET /invoices/{id}/decisions` |
| Command line | `classify <id> [--force] [--jev-only] [--line N]`, and `split <id>` |
| Rule test | each trial line takes an optional `details` (at most 500 characters, like the description); each answered line returns it |

```sql
-- How an invoice got its account, each time it changed: by whom, why, and what it had before.
CREATE TABLE IF NOT EXISTS decisions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT NOT NULL,
    at         TEXT NOT NULL,
    source     TEXT NOT NULL,              -- download | again | redecide | person | split
    line       INTEGER,                    -- NULL: the whole invoice
    cont       TEXT,                       -- NULL: no account, it waits for a person
    method     TEXT,                       -- rules | jev | jev_accepted | human | follows | invoice; NULL while it waits
    reason     TEXT NOT NULL DEFAULT '',   -- the program's English explanation
    said       TEXT NOT NULL DEFAULT '{}'  -- JSON: rule, match, suggested_cont, confidence,
                                           -- confidence_threshold, probabilities, jev_only, before
);
CREATE INDEX IF NOT EXISTS idx_decisions_message ON decisions (message_id, id);
```

### Page

| Part | What |
|---|---|
| `RenderedInvoice` | `line.details` under the name, smaller and grey |
| `LineAccountDialog` | the line's description under its name. "Sau hotărăște din nou această linie" with the two buttons and one sentence on the cost |
| `AccountCard` | "Împarte pe linii" with its sentence (decision 4) and a toast after it; "Hotărăște din nou…" (opens `DecideAgainDialog`); the steps for an imported invoice; "Clasifică din nou, pe fiecare linie" goes |
| `LineAccountsCard` | "Hotărăște din nou…"; the steps for an imported invoice |
| `invoices/lineAccounts.ts` | `whoChoseLine` for `invoice`: "contul facturii, păstrat la împărțire" |
| `invoices/DecideAgainDialog.tsx` (new) | the two choices as radio buttons with a line each, what is lost, Jev's cost, one main button "Hotărăște din nou". Its texts in `invoices/decideAgainTexts.ts` with tests. Without an OpenRouter key (`jev_configured` of `GET /classification/settings`), "Doar cu Jev" is off here and in the line window, with "Jev nu este pornit. Puneți cheia OpenRouter la «Chei și parole»." |
| `invoices/history/DecisionHistory.tsx` (new) | the tab's content, from `GET /invoices/{id}/decisions`, fetched when the tab opens |
| `invoices/history/decisionTexts.ts` (new, with tests) | the moments and each row in Romanian: `moments(rows)`, `rowSentence(row)` |
| `rules/JevOdds.tsx` (new, out of `JevSaid`) | the bars of how likely Jev found each account, shared by the rule test and the history |
| `rules/test/ruleReason.ts` | the words for `*` at the start and on both sides, and "în descrierea liniei". Its `because(…)` becomes `matchWords(match)`, also used by the history |
| Rule test | each line gets an optional "Descrierea de pe factură" field, in the fold that holds the codes, now called "Mai multe de pe factură (descriere, coduri)"; `fromDocument` brings `details`; `lineInWords` shows Jev's `detalii` |
| Proposed rule card | the line's description under its name; "Sunt din linia…" says both |
| `RuleDialog` | the hint for keywords: `transport*`, `*cartus`, `*cartus*` |

## The work, tests first

| # | Part | Where | Tests that pin it |
|---|---|---|---|
| 1 | `*` at the start, the end and both; `RuleMatch.matched` | `rules.py`, `README.md` | `tests/test_classify.py`: `*cartus` matches `tonercartus` and `cartus`, not `cartuse`; `*cartus*` matches `tonercartusul`; `transport*` unchanged; `*`, `**` and `* ` dropped; `car*us` matches only a literal `car*us`; `MOTORINĂ*` still matches `motorinei`; `match()` gives the whole word found |
| 2 | `Line.details`, the subject, Jev's request, the same question, proposed rules, the rule test | `invoice.py`, `rules.py`, `classify.py`, `suggestions.py`, `service.py` (trial) | `test_invoice.py`: name and description apart; a description equal to the name gives none; no name: the description, as today. `test_classify.py`: a keyword found only in the description decides the line, whole and line by line, received and issued; a phrase does not run from name into description; `detalii` in Jev's request only when there is one, and a line without one is sent as before; two lines with one name and two descriptions are two questions. `test_suggestions.py`: words from the description after those of the name. `test_rule_suggestions.py`: a subject saved without `details` still proposes. `test_rule_test.py`: `details` in and out, and the 500-character limit |
| 3 | The `decisions` table, written on every change and only then; `match` in line entries; `GET /invoices/{id}/decisions` | `store.py`, `service.py`, `api.py` | `tests/test_decision_history.py` (new): a download writes what each line got (rule with its word, Jev with how sure, waiting with its reason); a person's line choice writes that line alone with `before`; accepting Jev's proposal writes `jev_accepted`; a rerun that changes nothing writes nothing; issued invoices too. `test_store.py`: a database of 0.13.0 gains the table. `test_ui_api.py`: the route |
| 4 | Split into lines; decided again, whole or one line, rules and Jev or Jev only | `service.py`, `api.py`, `cli.py` | `tests/test_split_lines.py` (new): every line starts with the invoice's account, the largest with how it was chosen, the others `invoice`, a discount `follows`; SAGA's file is the same; one line changed afterwards changes that line alone, the largest included; refused without an account, with one line, twice, or when imported; `classify_again` keeps the `invoice` lines; issued invoices with their own accounts. `tests/test_decide_again.py` (new): `jev_only` asks Jev even where a rule matches, whole and line by line; the shape is kept with `per_line`, and without it the client's switch decides, as today; one line changes only that line, and the lines following it when it is the largest; Jev only on a discount line asks Jev; Jev failing leaves the invoice as it was, with no history row; no key: the line waits, with "The rules were skipped"; imported: refused; a download running: `busy`. `test_cli.py`, `test_ui_api.py`: the options, the bodies and the new route |
| 5 | Page: the description shown; the rule test and proposed rule card; the keyword hint and `ruleReason` | `RenderedInvoice.tsx`, `LineAccountDialog.tsx`, `rules/test/*`, `rules/ProposedRuleCardBody.tsx`, `rules/RuleDialog.tsx`, `types.ts` | `trialInvoice.test.ts` (`fromDocument` carries `details`), `jevSent.test.ts`, `ruleReason.test.ts` (each `*` form, in the description) |
| 6 | Page: "Împarte pe linii", the imported steps, `DecideAgainDialog`, the line window's section | `invoices/*`, `api.ts`, `types.ts` | `decideAgainTexts.test.ts`, `lineAccounts.test.ts` (the `invoice` method) |
| 7 | Page: the history tab, `JevOdds` shared | `invoices/history/*`, `rules/JevOdds.tsx`, `rules/test/JevSaid.tsx`, `InvoicePage.tsx` | `decisionTexts.test.ts`: each source and method in words; `before`; moments grouped and newest first; lines with the same outcome in one row; more than 6 rows folded; the empty tab |
| 8 | Demo, README, the build | `demo.py`, `standins.py` (the stand-in Jev reads `detalii` too), `README.md`, `src/efactura/ui` | `test_demo.py`: the demo has an invoice with descriptions and a rule with `*cartus*`, and its invoices have a history |

## Review focus

The cases no request names that a person will meet:

1. **The description repeats the name, or there is no name.** Jev gets one text, not two; the screen shows it once.
2. **Invoices saved before this version.** Their kept subjects have no description: proposed rules and "how the rule would have done" keep working. Their history tab says it starts with this version.
3. **An odd keyword.** `*`, `**`, `* `, `car*us`: none may match every line.
4. **You split an invoice, then change its largest line.** Only that line changes (and a discount that follows it); the other lines keep the account they started with.
5. **Jev fails mid-way on "Hotărăște din nou".** The invoice stays exactly as it was, the screen shows why, and the history writes nothing.

## Verification

1. `uv run pytest`; from `frontend/`: `pnpm vitest run`, `pnpm exec tsc -b`, `pnpm lint` (the 3 known warnings only), `pnpm build`.
2. **In the demo**, on port 8771, in the built-in browser, received and issued:
   - an invoice with descriptions;
   - a rule with `*cartus*`, tried in "Testează regulile";
   - "Împarte pe linii" on an invoice with one account, then one line chosen by hand and another decided again;
   - "Hotărăște din nou…" both ways, on the invoice and on one line;
   - the history after each;
   - the steps on an imported invoice.
3. **An independent review** of the whole branch before calling it done.
4. **The README:** the keyword sentence (line 513), the description, splitting into lines and the method `invoice`, the history, deciding again, the routes, `classify`'s options and `split`, the `decisions` table.
5. **The version** goes to 0.14.0 with the release, when you ask for it.

## Limits

- **Old decisions have no history.** The invoices decided before this version start theirs at their next change.
- **The history follows the account, not everything.** Marking as imported, a proposed rule created, or a failed call to Jev stay in the journal and in "Costuri Jev".
- **Deciding the whole invoice again asks Jev again** about every line no rule decides, and each question is paid. The window says so.
- **A keyword `*` in the middle** is a plain character, as today.

## Changes made while building

- **"Doar cu Jev" knows whether Jev is set up** from `GET /rules` (`jev_configured`), which the invoice screen reads already, instead of a second request to `GET /classification/settings`.
- **What a person asks to have decided again is written in the history even when it comes out the same.** Seen in the demo: Jev unsure again of a line left no trace of the click. The line window also says "Linia N a fost hotărâtă din nou."
- **"Clasifică din nou" keeps an invoice decided line by line on lines**, whatever the client's switch: otherwise an invoice a person split would be made whole again. This replaces the limit of the 2026-11-18 plan ("with the switch off since, the invoice is decided whole").
- **The history has a fifth source, `split`**, so the moment reads "Împărțită pe linii de dumneavoastră"; lines that got the same thing in one moment are one row.
- **`POST /rules/test` carries `details`.** The route's model dropped it; found in the demo, now tested at the route.
- **Tests** for the description are in `tests/test_line_descriptions.py` and for keywords in `tests/test_keywords.py`, rather than spread over the older files.

### After the independent review

- **After a split, the line Jev decided is marked as asked of Jev**, so "Clasifică din nou" keeps its account and does not pay for the question again.
- **One line decided again keeps the hold** of an invoice saved twice or whose parties do not fit: that line waits for a person, with the reason, instead of letting the invoice into SAGA's file.
- **`classify` without `per_line` keeps an invoice on lines on lines** everywhere, not only in "Clasifică din nou", so `efactura classify <id> --force` cannot undo a split.
- **The history**: a person's choice keeps no old rule; it is written after the invoice is saved; an invoice on lines made whole says what it had; a download or "Clasifică din nou" where only Jev's figures move writes nothing.
- **The words a rule found are kept as the line writes them** ("Cartușe", not "cartuse").
- **`ask` on `POST /invoices/{id}/classify`** accepts only its two values.
