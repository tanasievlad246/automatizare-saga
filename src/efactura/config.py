"""Settings read from config.toml."""

from __future__ import annotations

import os
import re
import sys
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .errors import CONFIG_ERROR, EfacturaError

DEFAULT_REDIRECT_URI = "https://localhost/callback"
DEFAULT_PORT = 8765
# A fixed version rather than "~typesafe/jev-latest": the confidence level is tuned to one
# model's probabilities and would lose its meaning if the model changed underneath it.
DEFAULT_JEV_MODEL = "typesafe/jev-1.14"
SAGA_IMPORT_FOLDER = "SAGA Import"
# The name the page is opened under. Browsers open any name ending in .localhost on this
# computer by themselves, and treat it as they treat localhost; nothing has to be set up.
PAGE_HOSTNAME = "autosaga.localhost"
MAX_DAYS = 60  # ANAF lists and serves messages for 60 days

_DATE_TOKENS = (("YYYY", "%Y"), ("MM", "%m"), ("DD", "%d"))
_SAFE_FOLDER_NAME = re.compile(r"^[0-9._-]+$")


@dataclass(frozen=True)
class Config:
    client_id: str
    client_secret: str
    redirect_uri: str
    environment: str
    token_file: Path
    data_dir: Path
    folder_date_format: str  # strftime pattern
    default_days: int
    api_key: str
    api_port: int
    openrouter_api_key: str = ""  # empty: classification runs on the rules alone
    jev_model: str = DEFAULT_JEV_MODEL
    saga_import_dir: Path | None = None  # None: "SAGA Import" inside the data folder

    @property
    def saga_dir(self) -> Path:
        return self.saga_import_dir or self.data_dir / SAGA_IMPORT_FOLDER

    @property
    def db_path(self) -> Path:
        return self.data_dir / "efactura.db"

    @property
    def invoices_dir(self) -> Path:
        return self.data_dir / "invoices"

    @property
    def log_path(self) -> Path:
        return self.data_dir / "efactura.log"

    @property
    def lock_path(self) -> Path:
        return self.data_dir / "efactura.lock"

    @property
    def api_base(self) -> str:
        return f"https://api.anaf.ro/{self.environment}/FCTEL/rest"

    def folder_name(self, when: datetime) -> str:
        return when.strftime(self.folder_date_format)

    def require_oauth(self) -> None:
        missing = [
            name
            for name in ("client_id", "client_secret", "redirect_uri")
            if not getattr(self, name)
        ]
        if missing:
            raise EfacturaError(
                CONFIG_ERROR,
                f"Missing [anaf] setting(s) in config.toml: {', '.join(missing)}. "
                "They come from the application registered in the ANAF portal.",
            )

    def require_api_key(self) -> None:
        if not self.api_key:
            raise EfacturaError(
                CONFIG_ERROR,
                "Set [api] key in config.toml before starting the local API.",
            )


def page_address(port: int) -> str:
    """Where a person opens the page. Port 80 is left out, as browsers leave it out."""
    return f"http://{PAGE_HOSTNAME}" + ("" if port == 80 else f":{port}") + "/ui/"


def default_token_file() -> Path:
    """A per-user private folder, never the project or data folder."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state")
    return Path(base) / "efactura" / "tokens.json"


def _folder_format(user_format: str) -> str:
    pattern = user_format
    for token, directive in _DATE_TOKENS:
        pattern = pattern.replace(token, directive)
    sample = datetime(2026, 11, 11).strftime(pattern)
    if "%" not in pattern or not _SAFE_FOLDER_NAME.match(sample):
        raise EfacturaError(
            CONFIG_ERROR,
            f"folder_date_format {user_format!r} is not usable. "
            "Use DD, MM and YYYY separated by '-', '.' or '_', e.g. DD-MM-YYYY.",
        )
    return pattern


def _beside(config_path: Path, value: str) -> Path:
    """A relative path in the settings file is relative to that file, not to the folder
    the command happened to be started from."""
    path = Path(value)
    return path if path.is_absolute() else config_path.parent / path


def load_config(path: str | os.PathLike | None = None) -> Config:
    config_path = Path(path or os.environ.get("EFACTURA_CONFIG") or "config.toml").resolve()
    try:
        # Windows Notepad may save with a byte-order mark, which TOML does not allow.
        text = config_path.read_bytes().removeprefix(b"\xef\xbb\xbf").decode("utf-8")
        raw = tomllib.loads(text)
    except FileNotFoundError:
        raise EfacturaError(
            CONFIG_ERROR,
            f"Settings file not found: {config_path}. Copy config.example.toml to config.toml.",
        ) from None
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as exc:
        raise EfacturaError(
            CONFIG_ERROR, f"{config_path} could not be read as UTF-8 TOML: {exc}"
        ) from None

    anaf = raw.get("anaf", {})
    storage = raw.get("storage", {})
    sync = raw.get("sync", {})
    api = raw.get("api", {})

    environment = str(anaf.get("environment", "prod"))
    if environment not in ("prod", "test"):
        raise EfacturaError(CONFIG_ERROR, 'environment must be "prod" or "test".')

    default_days = sync.get("default_days", 7)
    if not isinstance(default_days, int) or not 1 <= default_days <= MAX_DAYS:
        raise EfacturaError(CONFIG_ERROR, f"default_days must be a number from 1 to {MAX_DAYS}.")

    token_file = anaf.get("token_file")
    openrouter = raw.get("openrouter", {})
    data_dir = _beside(config_path, str(storage.get("data_dir", "data")))
    saga_dir = raw.get("saga", {}).get("import_dir")

    return Config(
        client_id=str(anaf.get("client_id", "")).strip(),
        client_secret=str(anaf.get("client_secret", "")).strip(),
        redirect_uri=str(anaf.get("redirect_uri", DEFAULT_REDIRECT_URI)).strip(),
        environment=environment,
        token_file=(
            _beside(config_path, str(token_file)) if token_file else default_token_file()
        ),
        data_dir=data_dir,
        folder_date_format=_folder_format(str(storage.get("folder_date_format", "DD-MM-YYYY"))),
        default_days=default_days,
        api_key=str(api.get("key", "")).strip(),
        api_port=int(api.get("port", DEFAULT_PORT)),
        openrouter_api_key=str(openrouter.get("api_key", "")).strip(),
        jev_model=str(openrouter.get("model", DEFAULT_JEV_MODEL)).strip() or DEFAULT_JEV_MODEL,
        saga_import_dir=(
            _beside(config_path, str(saga_dir)) if saga_dir else data_dir / SAGA_IMPORT_FOLDER
        ),
    )
