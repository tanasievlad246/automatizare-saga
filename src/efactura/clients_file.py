"""Reading a list of clients (name and CUI) from a CSV or Excel file.

The file is whatever the accountant has: columns in any order, with or without a header
row, a CSV saved by Excel on a Romanian computer (semicolons, Windows-1250) or a real .xlsx.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile

from .anaf import normalize_cui
from .errors import INVALID_INPUT, EfacturaError
from .rules import normalise

MAX_FILE_BYTES = 5 * 1024 * 1024
# A title or an empty line may sit above the header, so it is looked for in the first rows.
HEADER_SEARCH_ROWS = 5
NAME_HEADERS = ("nume", "denumire", "client", "firma", "societate", "partener", "name")
_DELIMITERS = ";,\t|"
_LOOKS_LIKE_A_CUI = re.compile(r"^(RO)?\d{2,13}$", re.IGNORECASE)
_NOT_A_LETTER_OR_DIGIT = re.compile(r"[^a-z0-9]")


def read_client_rows(filename: str, content: bytes) -> list[tuple[int, str, str]]:
    """(row number in the file, name, CUI as written) for every row that is not empty.

    Nothing is checked here beyond finding the two cells; the caller validates the CUI.
    """
    if len(content) > MAX_FILE_BYTES:
        raise EfacturaError(INVALID_INPUT, "The file is too large for a list of clients.")
    rows = [(number, cells) for number, cells in _table(filename, content) if any(cells)]
    if not rows:
        raise EfacturaError(INVALID_INPUT, "The file has no rows.")

    for position, (_, cells) in enumerate(rows[:HEADER_SEARCH_ROWS]):
        headers = [_header_key(cell) for cell in cells]
        cui_column = next((i for i, header in enumerate(headers) if _is_cui_header(header)), None)
        if cui_column is not None:
            name_column = next(
                (i for i, header in enumerate(headers) if header.startswith(NAME_HEADERS)), None
            )
            return [
                (number, _name_in(cells, name_column, cui_column), _cell(cells, cui_column))
                for number, cells in rows[position + 1 :]
            ]
    return [(number, *_guess_name_and_cui(cells)) for number, cells in rows]


def _header_key(cell: str) -> str:
    """A header reduced to its letters: "C.U.I." and "Cod fiscal" become "cui", "codfiscal"."""
    return _NOT_A_LETTER_OR_DIGIT.sub("", normalise(cell))


def _is_cui_header(header: str) -> bool:
    return header == "cif" or header.startswith(("cui", "cifcui", "codfiscal", "codulfiscal", "codunic"))


def _name_in(cells: list[str], name_column: int | None, cui_column: int) -> str:
    """The name cell; when its column has no recognisable header, the first cell with
    words in it. A cell of digits is a row number, never a name."""
    if name_column is not None:
        return _cell(cells, name_column)
    return next(
        (cell for i, cell in enumerate(cells) if i != cui_column and cell and not cell.isdigit()), ""
    )


def _guess_name_and_cui(cells: list[str]) -> tuple[str, str]:
    """Without a header: the CUI is the cell that passes the CUI check, and the name is the
    first other cell with words in it.

    Small numbers such as 19 or 27 pass the check too, and lists often start with a row
    number, so among several candidates one written with RO wins, then the longest.
    """
    filled = [cell for cell in cells if cell]
    candidates = [cell for cell in filled if _is_cui(cell)] or [
        cell for cell in filled if _LOOKS_LIKE_A_CUI.match("".join(cell.split()))
    ]
    cui = max(candidates, key=lambda cell: (cell.upper().startswith("RO"), len(cell)), default="")
    name = next((cell for cell in filled if cell != cui and not cell.isdigit()), "")
    return name, cui


def _is_cui(text: str) -> bool:
    try:
        normalize_cui(text)
    except EfacturaError:
        return False
    return True


def _cell(cells: list[str], column: int) -> str:
    return cells[column] if column < len(cells) else ""


def _table(filename: str, content: bytes) -> list[tuple[int, list[str]]]:
    """The file as (row number, cells as text), whatever its format."""
    extension = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if extension in ("csv", "txt"):
        return _csv_rows(content)
    if extension in ("xlsx", "xlsm"):
        return _xlsx_rows(content)
    raise EfacturaError(
        INVALID_INPUT, "The file must be an Excel workbook (.xlsx) or a CSV file (.csv)."
    )


def _csv_rows(content: bytes) -> list[tuple[int, list[str]]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("cp1250", errors="replace")  # Excel on a Romanian Windows
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    delimiter = max(_DELIMITERS, key=first_line.count)
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    return [(number, [cell.strip() for cell in cells]) for number, cells in enumerate(reader, start=1)]


def _xlsx_rows(content: bytes) -> list[tuple[int, list[str]]]:
    import openpyxl  # only needed when an Excel file is imported

    try:
        book = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheet = book.worksheets[0]
        return [
            (number, [_text(value) for value in values])
            for number, values in enumerate(sheet.iter_rows(values_only=True), start=1)
        ]
    except (zipfile.BadZipFile, KeyError, ValueError, IndexError, OSError) as exc:
        raise EfacturaError(INVALID_INPUT, f"The Excel file could not be read: {exc}") from None


def _text(value) -> str:
    """A cell as text. Excel stores a CUI typed as a number as 12345674.0."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()
