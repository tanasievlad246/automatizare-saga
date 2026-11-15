# Automatic download on a schedule, and clients switched on or off — design

Date: 2026-11-15. Branch: `automatic-download`, cut from `certificate-login` (0.5.0, not yet published). Both features go out in the same 0.5.0.

## What was asked

1. "A page that sets a cronjob for syncing all clients saved with e factura and classifying the invoices with jev."
2. "Each client should have a toggle with a enabled/disabled flag. Enabled by default, this is used to filter out clients that are disabled when being synced with e factura."

Both are to be planned and built with subagents before 0.5.0 is published.

## Why

Today invoices arrive only when the accountant presses "Descarcă facturile". The schedule makes the program do that by itself, so the invoices and their SAGA files are there when she sits down. The switch lets her keep a client and its saved invoices in the list while leaving it out of every download: a client she no longer books for, or one whose SPV rights lapsed and that fails every time.

## Who uses it

A non-technical accountant, on one Windows PC, in Romanian. The screens are on the design canvas (version 22), artboards **"Descărcare automată"** and **"Clienți: pornit sau oprit"**: https://claude.ai/artifact/VSxb2ocdWVd9UtMUcuWukH. The built page follows them. A builder cannot open the canvas, so every sentence on screen is written out in the implementation plan, which is the authority for the texts. On screen the feature is never called a schedule or a cron job: it is "Descărcare automată".

## Decisions

Only the two quoted requests are the owner's words. Everything else below is a call made while designing; each is marked **(call)** once, here, and listed for the owner at the end of the work.

### Clients switched on or off

- A client is on or off. New clients are on. Existing databases get every client on. Renaming a client, or importing a file that contains it, leaves the switch as it is.
- **(call)** Off means not downloaded, anywhere: not by "Descarcă facturile pentru toți clienții", not by the schedule, not by its own row's button, not by `POST /sync` or `efactura sync` for that CUI. One meaning is easier to explain than "left out of the group, but still downloadable alone". To download it, switch it on. A CUI that is not in the client list is not affected (the terminal and the Power Automate flow may download any CUI, as today).
- A client that is off keeps its row, its invoices and "Vezi facturile". Its row is drawn muted, says "Oprit: facturile lui nu se descarcă până îl porniți.", and its download button cannot be pressed.
- The switch takes effect at once (no save button) and is written in the journal.
- Under the page's buttons, when at least one client is off: "Se descarcă 3 din cei 4 clienți. Un client este oprit." When all are off, the button for all cannot be pressed.

### The schedule

- **(call)** It runs inside the program that is already running in the background (the one that starts with Windows), not as a Windows scheduled task. That is how the daily backup already works, it needs nothing installed, and it can be tested here. The cost: the program has to be running. The page says so.
- **(call)** What can be chosen: off or on; the days of the week; one to four times a day (hour and minute). Nothing else. Defaults for a database that has never saved one: off, Monday to Friday, 08:00. Off by default because each new invoice may cost a Jev call.
- **(call)** No cron expression, no "every N hours", no period to choose, no schedule per client.
- What a run does: for every client that is on, in the order of the list, exactly what `sync` does when no period is given (the default days, widened back to that client's last complete run; rules, then Jev, then the SAGA file).
- **(call)** A moment that was missed (PC off, asleep, program stopped) is made up once, as soon as the program looks again: only the latest missed moment, however many were missed.
- **(call)** Saving the schedule never starts a run for a moment that has already passed.
- **(call)** The program looks every 30 seconds, so a run starts within half a minute of its time.
- **(call)** When one client fails, the run goes on to the next. Four failures end the run, because every later client would fail the same way:
  - no ANAF login (`login_needed`), ANAF's daily limit of requests reached (`anaf_limit_reached`), or a missing setting (`config_error`): the run ends as failed; nothing is retried until the next scheduled moment;
  - ANAF out of reach (`network_error`): the run ends as unreachable and is tried again 15 minutes later, at most three more times for that moment.
- **(call)** Only the latest moment is ever considered: when the next moment arrives, attempts still owed to the one before it are dropped.
- **(call)** With no client switched on, a run still happens and is recorded as fine, with 0 clients. The page says "Niciun client nu este pornit" from the count of clients, not from the run.
- **(call)** If another download holds the program's lock (someone is downloading by hand), the run waits for it, up to a minute per client, before counting that client as failed. The wait is a loop around `sync` inside `sync_all`, on `busy` only; the lock itself and the downloads made by hand are unchanged. A restore or an update that gets in between two clients stops the program, so the run is cut off like any other; nothing more is done about it.
- **(call)** A run that was cut off (PC shut down in the middle) is tried again like an unreachable one.
- **(call)** There is no "run now" button: the page's button for all clients already does that.
- **(call)** While a run is in progress the Clients page says so and its download buttons cannot be pressed; the menu entry says "Se descarcă acum". If the last run failed or could not reach ANAF, the menu entry says "Ultima nu a reușit". The page learns this by asking the program every 30 seconds while the schedule is on (every 3 seconds during a run); those requests are not written in the journal.
- **(call)** `efactura sync-all` does one such run from the terminal, now. It is not a scheduled run: it writes no record of a last run and no `sync.auto_*` journal lines (each client's own `sync.*` lines are written as always), it changes nothing about what is due, and the page does not show it as running.
- **(call)** The schedule works on demo settings too, against the stand-ins.

### Anti-goals

- A failed automatic run that nobody notices. Every run leaves its outcome on the schedule page, in the menu when it failed, and in the journal.
- A run that spends Jev money in a way the manual download would not.
- A switched-off client that is downloaded anyway, by any path.
- The real ANAF or OpenRouter contacted on demo settings (`Service` already chooses the stand-ins there; the scheduled run must go through `Service`).

## How it is built

### Database

- `clients.enabled INTEGER NOT NULL DEFAULT 1`: in the schema for new databases, added by `Store._migrate` to existing ones.
- Two rows in the existing `settings` table, each one JSON:
  - `auto_sync`: `{"enabled": bool, "days": [0..6], "times": ["HH:MM", …], "saved_at": "YYYY-MM-DDTHH:MM:SS"}`. Days: 0 is Monday. Times sorted, unique.
  - `auto_sync_last_run`: how the last run went (below).
- All of the schedule's moments are the PC's own clock, written without a time zone, to the second.

### Program

- `store.py`: the column; `clients()` returns `enabled` as a boolean; `set_client_enabled(cui, enabled)` (`not_found` for an unknown CUI); `client_enabled(cui) -> bool | None` (`None`: not in the list).
- `errors.py`: `CLIENT_OFF = "client_off"`; `api.py` maps it to 409.
- `service.py`:
  - `set_client_enabled(cui, enabled) -> dict` (the client list, like `save_client`); journal `client.switched` with `cui`, `client`, `enabled`.
  - `sync` raises `client_off` for a client that is in the list and off, before it takes the lock.
  - `sync_all(progress=None) -> dict`: every client that is on, one after another. `progress(done, total)` is called before each client and once at the end. Returns `{"ok": True, "status", "clients", "failed_clients", "new", "review", "stopped_by", "results"}` where `status` is `ok`, `partial` (a client failed, or a client's download left messages behind), `failed` (stopped by `login_needed`, `anaf_limit_reached` or `config_error`) or `unreachable` (stopped by `network_error`); `results` has one entry per client tried: `{"cui", "name", "ok", "new_count", "failed_count", "review"}` or `{"cui", "name", "ok": False, "error": {"code", "message"}}`. A client switched off while the run is in progress is skipped without a result. An unexpected exception for one client is logged and counted as that client's failure (`internal_error`).
  - `schedule() -> dict` and `set_schedule(enabled, days, times) -> dict`: what the page reads and saves; `set_schedule` writes journal `schedule.saved`.
- new `schedule.py`: the rules, with no I/O of their own except the settings table:
  - reading and saving the schedule, with validation (`invalid_input`): days are whole numbers 0–6, no repeats; times are one to four `HH:MM` (00:00–23:59), no repeats; an enabled schedule needs at least one day;
  - `latest_slot(schedule, clock)`: the latest scheduled moment not after `clock`, looking back up to seven days; `next_slot(schedule, clock)`: the earliest after it;
  - `due(schedule, last_run, clock)`: the moment to run now and the number of the attempt, or nothing;
  - `run_if_due(cfg, now=None, make_service=None)`: what the running program calls. Never raises. Writes the run's record when it starts and when it ends, keeps the progress of the run in progress in memory, and writes journal `sync.auto_started` and `sync.auto_finished`, all under one journal trace;
  - `status(cfg, now=None)`: everything the page shows.
- The record of the last run: `{"slot", "attempt", "started_at", "finished_at", "status", "clients", "failed_clients", "new", "review", "error", "trace"}`. `status` is `running` while it runs (and stays so if the program dies), else what `sync_all` returned. `error` is `{"code", "message"}` of the failure that stopped the run, else `null`.
- When a run is due:
  - the schedule is on, and has a latest moment that is after `saved_at`;
  - and either no run is recorded for that moment (a record for a later moment means the clock was moved back: nothing is due),
  - or the recorded run for that moment is `unreachable` or `running` (cut off), has made fewer than 4 attempts, and ended (or, cut off, started) at least 15 minutes ago.
- `cli.py`: `run_server` starts a second background thread beside the housekeeping one; it calls `schedule.run_if_due(cfg)` 30 seconds after the start and every 30 seconds. One bad round must not be the last. New command `sync-all`.
- `api.py`: `PUT /clients/{cui}/enabled` with `{"enabled": bool}`; `GET /sync/schedule`; `PUT /sync/schedule` with `{"enabled", "days", "times"}`. `GET /sync/schedule` is not written in the journal as a page request.
- `GET /sync/schedule` answers `{"ok", "enabled", "days", "times", "next_at", "running", "last_run", "clients_on", "clients_off"}`: `next_at` is the next moment (null when off); `running` is `{"started_at", "done", "total"}` or null; `last_run` is the record above with `status` shown as `interrupted` when the record says `running` and no run is in progress, plus `retry_at` (when the next attempt for that moment will be made, else null), or null when there has been none.

### Journal

Codes, each with its Romanian sentence on the journal page: `client.switched` (area `clients`), `schedule.saved` (area `settings`), `sync.auto_started` and `sync.auto_finished` (area `sync`; finished is `info` when ok, `warning` when partial, `error` when failed or unreachable). Nothing new may put a key, a token or a login address in the journal.

### Page

- New `frontend/src/schedule/`: the page at `/descarcare-automata`, menu entry "Descărcare automată" directly under "Clienți". As on the artboard: the state card first, then "Când să descarce" (Oprită/Pornită, the seven days, the times, "Salvează"), then "Bine de știut". The form changes nothing until "Salvează" is pressed; the state card always shows what is saved.
- The state card has the seven states on the artboard: on and fine, off, running, failed (login), unreachable with the next attempt, not complete, no client on.
- The sentences that depend on data (days in words, counts, which state) are plain functions with tests, as elsewhere on the page.
- Clients page: a switch on each row; the muted row; the count line; the notice and the blocked buttons while a run is in progress; the list refreshed when a run ends.
- "Descarcă facturile" window for all clients: only the clients that are on; "Pentru cei 3 clienți porniți" when some are off.
- New shadcn-style `Switch` component (`radix-ui` is already a dependency).
- `client_off` gets its sentence: "Clientul este oprit. Porniți-l din lista de clienți ca să îi descărcați facturile."

### Documentation and version

README: the two features for a person, the routes, the command, the error code, what is not yet confirmed on Windows. The version stays 0.5.0 (not published yet); the built page is rebuilt and committed.

## What cannot be checked here

Windows: the background thread under the window-less start, and a run made up after the PC sleeps. The same code runs on macOS, and the rules are tested with a clock that is moved by hand.

## Not included

Windows Task Scheduler; a schedule per client; e-mail or pop-up notifications; a spending limit for Jev; choosing the period of an automatic download; a "run now" button.
