# AutoSaga on a Synology NAS

The NAS runs AutoSaga all the time, in a container, in **server mode**. Every computer on the office network opens the page in the browser, Mac or Windows. The PCs reach the files for SAGA through a shared folder on the NAS. SAGA and Power Automate stay on the Windows PC.

```
Every PC (browser) ── http://192.168.1.50:8765/ui/ ──►  NAS · Container Manager · container "autosaga"
                                                         /config   ← docker/autosaga/config    config.toml, tokens.json
                                                         /data     ← docker/autosaga/data      database, invoices, archive, log
                                                         /saga     ← shared folder AutoSaga-SAGA
                                                         /backups  ← shared folder AutoSaga-Copii
SAGA PC ── \\192.168.1.50\AutoSaga-SAGA (drive S:) ──►   /saga
Power Automate ── http://192.168.1.50:8765 + X-API-Key ► the API
NAS ── internet ──► api.anaf.ro, logincert.anaf.ro, openrouter.ai
```

Everywhere below, replace `192.168.1.50` with your NAS's address, and `/volume1` with the volume your shared folders are on. [README.md](README.md#server-mode-one-program-for-the-whole-office) explains server mode itself.

**No login is asked.** Anyone on the office network has the whole program: the ANAF login of every client, the keys, "Șterge toate datele". Keep the program on the office network only (step 11).

## What you need

- **The NAS.** A model with an Intel or AMD processor and DSM 7.2 or newer. The DS220+ qualifies; its 2 GB of memory are enough. You also need an account in its **administrators** group. DSM 7 turns the account named `admin` off; use your own.
- **A computer on the same network** to set it up from: a Mac or a Windows PC.
- **The values for `config.toml`:**
  - the ANAF client ID and secret (see [README-ANAF.md](README-ANAF.md));
  - the OpenRouter key;
  - a key for the API (step 7 makes one).
- **For the ANAF login:** the PC with the USB token. You can skip this if you bring the login over from a PC (step 8).

---

## 1. Give the NAS a fixed address

In the router, reserve an address for the NAS (a DHCP reservation for its MAC address), then restart the NAS. Write the address down: every computer will open the program at it.

## 2. Install Docker and Git on the NAS

In DSM, open **Package Center** and install:
- **Container Manager**: this is Docker for Synology.
- **Git Server**: it gives the NAS the `git` command used in step 5. You do not have to set it up.

## 3. Turn on SSH

**Control Panel → Terminal & SNMP → Terminal → Enable SSH service** (port 22) → Apply. You can turn it off again at the end, and turn it on only for updates.

## 4. Make the folders

**Control Panel → Shared Folder → Create**, two shared folders:

| Shared folder | What it holds | Permissions |
|---|---|---|
| `AutoSaga-SAGA` | the files for SAGA, one folder per client | Read for the NAS users who run SAGA or look at the files (see below) |
| `AutoSaga-Copii` | the backups of the database | administrators only |

Then, in **File Station**, open the `docker` shared folder (Container Manager made it), create a folder named `autosaga`, and inside it two folders: `config` and `data`.

`docker/autosaga` will hold the ANAF login and every key. Keep the `docker` shared folder for administrators only.

**The PCs only read the files for SAGA.** The program writes them and moves them to its archive by itself; SAGA and Power Automate only read them. The container runs as root, so to the PCs the files it writes are read-only. That is enough. To have them belong to a NAS user instead, see the `user:` line in `docker-compose.yml`.

## 5. Clone the repository on the NAS

From the Mac (Terminal) or a Windows PC (PowerShell), log in to the NAS with your account from the administrators group (`maria` below):

```bash
ssh maria@192.168.1.50
```

Then fetch the program into `docker/autosaga/app`. Use the newest release; the [releases page](https://github.com/tanasievlad246/automatizare-saga/releases) names it. It has to be **v0.15.0 or newer**: earlier releases have no server mode and no `Dockerfile`.

```bash
cd /volume1/docker/autosaga
git clone https://github.com/tanasievlad246/automatizare-saga.git app
cd app
git checkout v0.15.0
cd ..
```

If `git` is not found, use Docker to run it instead:

```bash
sudo docker run --rm -v /volume1/docker/autosaga:/git alpine/git clone https://github.com/tanasievlad246/automatizare-saga.git /git/app
sudo docker run --rm -v /volume1/docker/autosaga/app:/git -w /git alpine/git checkout v0.15.0
```

## 6. Put the compose file beside the clone

```bash
cp app/deploy/nas/docker-compose.yml docker-compose.yml
```

Your copy stays yours: updating the clone never touches it. If your shared folders are not on `/volume1`, open `docker-compose.yml` (File Station → right-click → Open with Text Editor) and change the two `/volume1/...` lines. File Station → right-click the folder → **Properties** shows where it is.

## 7. Write config.toml

```bash
cp app/config.example.toml config/config.toml
openssl rand -hex 32
```

The second line prints a long random key for the API: copy it. Then open `docker/autosaga/config/config.toml` in File Station's Text Editor and set the lines below.

The paths are inside the container: keep `/config`, `/data` and `/saga` exactly as written. Keep `port = 8765` too, the number `docker-compose.yml` publishes.

```toml
[anaf]
client_id = "…"
client_secret = "…"
redirect_uri = "https://localhost/callback"
environment = "prod"
token_file = "/config/tokens.json"

[storage]
data_dir = "/data"

[api]
key = "…the key printed above…"
port = 8765

[openrouter]
api_key = "…"

[saga]
import_dir = "/saga"

[server]
# How the office's computers reach the folder for SAGA: the page then shows every path
# to an XML file the way that computer opens it.
saga_folder_windows = '\\192.168.1.50\AutoSaga-SAGA'
saga_folder_mac = "/Volumes/AutoSaga-SAGA"
# Only if you want to open the page by a name instead of the address:
# names = ["birou-nas", "birou-nas.local"]
```

If every Windows PC maps the share as the same drive (step 14), you may write `saga_folder_windows = 'S:\'` instead. The client ID, secret and OpenRouter key can also be filled in on the page later, under "Chei și parole".

## 8. Only if a Windows PC already has the data: bring it over

1. **Stop the program on the PC for good.** From now on only the NAS runs it: two copies would download the same invoices from ANAF and write two sets of files for SAGA.
   - In the program's folder, run `.venv\Scripts\python.exe -m efactura stop`.
   - Then run `powershell -ExecutionPolicy Bypass -File install.ps1 -Uninstall`. It removes the two shortcuts and keeps the folder.
2. **Copy the data.** Copy `efactura.db`, `invoices\` and `saga-archive\` from the PC's `data\` folder to `\\192.168.1.50\docker\autosaga\data\`.
3. **Copy the login.** Copy `%LOCALAPPDATA%\efactura\tokens.json` to `\\192.168.1.50\docker\autosaga\config\`. This saves you a new ANAF login.
4. **Leave the PC's `SAGA Import` folder alone.** The NAS writes every waiting file again into `AutoSaga-SAGA`, at its first start.

The database remembers the PC's folders, such as `C:\…`. On the NAS they are no full paths, so they are left aside: the folder for SAGA comes from `config.toml`, and the backup folder is asked for again (step 13).

## 9. Build and start the container

In DSM: **Container Manager → Project → Create**:
- **Project name:** `autosaga`.
- **Path:** `docker/autosaga`.
- **Source:** "Use existing docker-compose.yml". It finds the file from step 6.
- **Next → Next → Done.** The image is built, which takes a few minutes the first time, and the container starts. The project shows **Running**.

Or over SSH, in `/volume1/docker/autosaga`:

```bash
sudo docker compose up -d --build
```

(On an older Container Manager the command is `sudo docker-compose up -d --build`.)

The container starts by itself with the NAS from then on (`restart: unless-stopped`).

## 10. Check that it runs

On any computer, open **http://192.168.1.50:8765/ui/**. The client list appears.

If it does not, look at **Container Manager → Container → autosaga → Log**.

## 11. Keep it on the office network

- **Never forward port 8765 in the router**, and do not publish it through QuickConnect or DSM's reverse proxy to the internet.
- **If the DSM firewall is on** (Control Panel → Security → Firewall), add a rule that allows port 8765 from the office subnet only, for example `192.168.1.0/24`.
- **Keep guests on a separate Wi-Fi.** Over plain `http` nothing between the PCs and the NAS is encrypted.

## 12. Open it from every computer

Make a bookmark of `http://192.168.1.50:8765/ui/`, or a desktop shortcut, on each computer. It works the same from a Mac and from Windows.

**Windows only open on the computer that runs the program.** "Alege folderul", "Deschide folderul" and the certificate login would open their window there, and on the NAS nobody would see it. So on every computer:
- each path has "Copiază calea" instead;
- folders are typed;
- the ANAF login goes through the browser.

## 13. Turn on the backups

On the page: **Copii de siguranță**, type `/backups` in the folder field, then **Salvează**, then **Fă o copie acum**. From then on a copy is made every day into the `AutoSaga-Copii` shared folder.

## 14. Connect the computers to the folder for SAGA

**Windows:**
1. File Explorer → **This PC → Map network drive**.
2. Choose a drive letter, for example `S:`, and the folder `\\192.168.1.50\AutoSaga-SAGA`.
3. Tick **Reconnect at sign-in**, and enter the NAS user and password.

**Mac:** Finder → **Go → Connect to Server** (⌘K) → `smb://192.168.1.50/AutoSaga-SAGA` → Connect. To have it connected at every sign-in, add it in **System Settings → General → Login Items**. It appears at `/Volumes/AutoSaga-SAGA`.

On the page, every path to an XML file is now in the form your computer opens. Copy it with "Copiază calea" and paste it into File Explorer, Finder or SAGA.

## 15. SAGA and Power Automate (the SAGA PC)

- **SAGA:** each company's import folder ("Import date") is `S:\<client's name> - <CUI>`.
- **Power Automate:**
  - Set `SagaImportFolderPath` to `S:\` (or `\\192.168.1.50\AutoSaga-SAGA`).
  - Its web requests go to `http://192.168.1.50:8765/…`, with the `X-API-Key` from `config.toml`.
  - Remove the step that starts `start-api.bat`: the NAS is always on.

## 16. Log in to ANAF (about once a year)

Skip this if you copied `tokens.json` in step 8.
1. On the PC with the USB token, open the page and choose **Conectare la ANAF**. ANAF's page asks for the certificate and the PIN.
2. The browser then ends on an address that does not load: `https://localhost/callback?code=…`. That is expected.
3. Copy that whole address and paste it into the program's window, within a minute.

## 17. Keep a copy off the NAS

The NAS is now the only place the data lives. Use **Hyper Backup** to back up `docker/autosaga` and `AutoSaga-Copii` to a USB disk or to Synology C2, daily, with encryption on.

## 18. Optional: open it by a name, such as autosaga.ro

Typing a name instead of `192.168.1.50:8765` needs three things. Every computer must find the NAS under that name, the name must lead to port 8765, and the program must know the name.

**1. Choose the name.**
- **A domain you own** (you registered `autosaga.ro`) works, both in the office and, if you ever want it, outside.
- **A domain someone else owns** leads to their site outside the office. A browser that once saw that site over https may also refuse plain http to it.
- **A name for the office only** is the safe choice when you don't own the domain: `autosaga.lan`, or `autosaga.home.arpa` (reserved for home and office networks).

**2. Make every computer find the NAS under the name.** Pick one way:
- **In the router**, if it can (look for "Local DNS", "Static DNS", "DNS rewrite" or "Host names"). Add `autosaga.ro` → `192.168.1.50`. This is the simplest, and it covers every computer at once.
- **With the NAS's own DNS server**:
  1. Package Center → install **DNS Server**.
  2. Zones → Create → **Master zone**: domain `autosaga.ro`, master DNS server `192.168.1.50`.
  3. In the zone, create an **A** record for `autosaga.ro` with the address `192.168.1.50`.
  4. Under **Resolution**, turn on the forwarders (for example `1.1.1.1` and `8.8.8.8`), so every other name still works.
  5. In the router's DHCP settings, set the DNS server to `192.168.1.50`, and reconnect the computers.
- **On each computer**, for a few computers only: add the line `192.168.1.50  autosaga.ro` to the hosts file.
  - On Windows the file is `C:\Windows\System32\drivers\etc\hosts`; open Notepad as administrator to edit it.
  - On a Mac, run `sudo nano /etc/hosts`.

**3. Lead the name to the program, without `:8765`.** DSM → Control Panel → Login Portal → Advanced → **Reverse Proxy** → Create:
- **Source:** HTTP, hostname `autosaga.ro`, port `80`.
- **Destination:** HTTP, `localhost`, port `8765`.

DSM keeps port 80 for itself and hands this one name on to the program.

**4. Tell the program the name.** In `config.toml`, under `[server]`, set `names = ["autosaga.ro"]`, then restart the container (Container Manager → Container → autosaga → Action → Restart). Without this the page says "Pagina nu mai are voie să vorbească cu programul".

**5. Open it.** Open **http://autosaga.ro** on every computer. Type the `http://` the first time, or the browser may try https.

Power Automate can keep using the address. The shared folder can be reached by the name too (`\\autosaga.ro\AutoSaga-SAGA`) once the computers find it.

---

## Updating to a new release

The page does not update a container, and it cannot tell you that a new release exists: the container has no Git copy to ask with. Look at the [releases page](https://github.com/tanasievlad246/automatizare-saga/releases) now and then ("Watch → Custom → Releases" on GitHub sends an e-mail for each new one). These are the steps:

1. On the page: **Copii de siguranță → Fă o copie acum**.
2. Over SSH, fetch the new release. `v0.16.0` below is an example; the releases page names the newest.
   ```bash
   cd /volume1/docker/autosaga/app
   git fetch --tags
   git checkout v0.16.0
   ```
3. Build and start the container again. Either use **Container Manager → Project → autosaga → Action → Build**, or run:
   ```bash
   cd /volume1/docker/autosaga
   sudo docker compose up -d --build
   ```
4. Open the page. The version is at the foot of the menu.

To go back, check out the previous release the same way and build again. If the newer release had already changed the database, also restore the copy from step 1.

## Restoring a backup

On the page, under **Copii de siguranță**, press **Restaurează** on a copy. The program stops and the database is put back. Then the keeper inside the container starts the program again, and the page reloads by itself. The container itself keeps running.

## If something is wrong

- **The page does not open from a computer.**
  - Check that the project is **Running**, and that the firewall rule exists (step 11).
  - Check that the address is the NAS's. To open it by a name, list the name under `[server] names` in `config.toml`, then restart the container.
- **"Pagina nu mai are voie să vorbească cu programul"** means the page was opened under a name the program does not know. Open it by the address, or add the name as above.
- **Logs.** The container's own log is at **Container Manager → Container → autosaga → Log**. The program's log is `docker/autosaga/data/efactura.log`. The page's **Jurnal** has everything, with "Vizualizare tehnică" for the requests to ANAF.
- **A computer sees no files, or cannot open one.**
  - Check the permissions of `AutoSaga-SAGA` for that NAS user: Control Panel → Shared Folder → Edit → Permissions.
  - After changing them, apply them to the folder's sub-folders and files too.
- **The paths on the page do not open.** Check `saga_folder_windows` and `saga_folder_mac` in `config.toml` (step 7), then restart the container.
- **The automatic download runs at the wrong hour.** Check `TZ` in `docker-compose.yml`.
- **The container restarts again and again.** The log says why, often a mistake in `config.toml`. The program is tried less and less often while it keeps failing.

## Not yet confirmed

- **The DS220+ itself.** The image was built and run with Docker on a Mac, not on a NAS. Container Manager's project screens and the `docker compose` command may differ slightly from what is written here.
- **The paths from Windows.** A Mac was checked on the page. The Windows form (`\\…\AutoSaga-SAGA\…`) is covered by tests only.
- **The SAGA PC reading files over the network, and SAGA importing from `S:`.** Not tried.
- **Power Automate calling the NAS.** Not tried.
