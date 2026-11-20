# Server mode and the NAS — plan

**Goal:** the program can run as a server that every computer on the office network opens in its browser, on a Synology NAS in a container or on any PC, started separately from today's local mode.

**What the user decided:**
- Build it, as planned in the earlier `README-NAS.md` (Part A).
- **No login.** The page is reached only from the local network.
- **Server mode starts separately from local mode** on a local PC. Today's start, shortcuts and `efactura serve` stay as they are.
- **The PCs (Mac and Windows) only need the paths to the XML files.** The NAS only hosts the program.
- **The READMEs say all this.** A NAS guide gives the steps one by one, from cloning the repo on the NAS onward.

## Decisions (mine; each is a ruling)

1. **How to start server mode:**
   - `efactura serve --network`, the same command with one flag.
   - `start-server.bat` on Windows.
   - `efactura keep-serving` in the container.

   Local mode is unchanged: it still listens on `127.0.0.1` only. Both modes use `[api] port`, and only one may run at a time: starting either while the program already answers on the port is refused, naming the mode it runs in. Two copies would download the same invoices twice.
2. **Network mode listens on every address, with no login.** The page's calls are accepted from any computer, but never from another website. Its requests must meet four conditions:
   - **Host:** an IP address, `localhost` or `*.localhost`, this computer's own name (also with `.local`), or a name in `[server] names`. This stops DNS rebinding.
   - **Origin:** when the browser sends it, it must match Host.
   - **Changes carry `X-AutoSaga-Page`:** every request other than GET or HEAD does. The page always sends it; another site cannot without CORS, and none is allowed.
   - **Sec-Fetch-Site:** when it is sent, it must be `same-origin`.

   Programs such as Power Automate still send the key. Local mode keeps its check exactly as it is.
3. **Windows on "this computer" only.** These open a window on the computer the program runs on:
   - the folder picker;
   - "Deschide folderul" (the SAGA folder, an import, the backups);
   - the certificate login.

   They are allowed only for a browser on that same computer, meaning a request from `127.0.0.1` or `::1`. Any other request gets `not_on_this_computer` (409). The page hides those buttons there:
   - it shows the path with "Copiază calea";
   - it offers a field where the folder is typed;
   - the certificate login is not offered.
4. **Paths as the PCs see them.**
   - `[server] saga_folder_windows`, for example `\\192.168.1.50\AutoSaga-SAGA`, and `saga_folder_mac`, for example `/Volumes/AutoSaga-SAGA`.
   - The page turns every path inside the SAGA folder into the viewer's form, picking Windows or Mac by the browser.
   - The API keeps the server's paths. Power Automate builds its own paths from `SagaImportFolderPath`.
5. **A saved folder that is not a full path on this system is ignored**, for example `C:\…` on the NAS. The program then uses the folder from config.toml, or asks for the backup folder again. This is how a database moved from a Windows PC starts on the NAS without writing into a folder named `C:\…`.
6. **Restore inside a container.**
   - `keep-serving` runs `serve --network` as its child, with `EFACTURA_KEEPER=1`.
   - A restore started under the keeper does not start the program itself. When the server stops, the keeper waits until no restore runs and nothing answers on the port, then starts it again. A child that keeps crashing is retried after a growing pause.
   - On SIGTERM it stops its child and stops.
   - `tini` is PID 1 in the image, so orphaned processes are collected.
   - Outside a container, a restore or an update starts the program again in the mode it was running in. `/health` names the mode.
7. **Updates in a container** are refused with `why_not_kind: "container"` (`EFACTURA_IN_CONTAINER=1` is set in the image). The page says how to update on the NAS. Without a Git copy in the image, the program cannot look for a newer release there; README-NAS.md points to the releases page.
8. **Image:** `Dockerfile` (Python 3.12 slim, `uv sync --frozen --no-dev`, the built page is already in the repo, tini). The compose file is `deploy/nas/docker-compose.yml`, copied beside the clone. It mounts `/config`, `/data`, `/saga` and `/backups`, and sets `TZ=Europe/Bucharest`.

## Work

1. `config.py`: `[server]` holds `names`, `saga_folder_windows` and `saga_folder_mac`. `config.example.toml` gets the section.
2. `cli.py`:
   - `serve --network`, `keep-serving`, and the refusal while the program already runs;
   - `background.start(network=)`, and `/health` naming `mode`;
   - restore and update start the program again in its mode.
3. `api.py`: `create_app(network=)`, the page check in network mode, `here` for the five window routes, and `GET /where` (mode, here, the SAGA folder with its Windows and Mac forms).
4. `service.py` and `backup.py`: saved folders that are not full paths are ignored.
5. `keeper.py`, `update.py` (container), `Dockerfile`, `.dockerignore`, `deploy/nas/docker-compose.yml`, `start-server.bat`.
6. The page:
   - `X-AutoSaga-Page` on every call;
   - `useWhere`;
   - `pathOnThisPC`;
   - the folder buttons in the seven places that have them;
   - the certificate login;
   - the update card's container text.
7. `README.md`: a "Server mode" section. `README-NAS.md` becomes the step-by-step NAS guide.
8. Check it:
   - tests first throughout;
   - server mode on this Mac, opened at its LAN address in the built-in browser;
   - `docker build` if Docker is available here;
   - an independent review.

## Not included

- HTTPS, a login, more than one copy at a time, and a published image (ghcr). The image is built on the NAS from the clone.
