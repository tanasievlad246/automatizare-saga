"""How a rule decides: the matching itself. The rules and accounts live in the database.

The accountant defines them on the "Reguli de clasificare" screen:

    accounts   the accounts Jev may choose from, each with a description Jev reads
    rules      checked in order against an invoice line; the first match gives its account

A rule reads a Subject: the invoice's supplier and its deciding line. It matches when ANY
of its conditions holds:

    keywords            words or phrases in the line description. Case and diacritics are
                        ignored ("MOTORINĂ" matches "motorina"). Whole words only; a * stands
                        for any letters where it is: "transport*" (starts with), "*cartus"
                        (ends with), "*cartus*" (contains). A * in the middle is a plain
                        character.
    item_codes          the supplier's article code or the barcode, exactly as on the invoice.
    commodity_prefixes  the start of a CPV or NC classification code ("0913" covers 09134200).
    supplier_cuis       fiscal codes, without RO; every line from these suppliers matches.

A rule belongs to every client unless it names one; a client's own rules are checked first.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from functools import cached_property

CONDITIONS = ("keywords", "item_codes", "commodity_prefixes", "supplier_cuis")


@dataclass(frozen=True)
class Subject:
    """What a rule reads from an invoice: who sent it, and its deciding line.

    Kept beside each invoice as text, so rules can be tried on saved invoices without
    reading their XML again.
    """

    supplier_cui: str | None
    description: str  # the line's name, as the invoice parser keeps it
    seller_code: str | None = None
    barcode: str | None = None
    commodity_codes: tuple[str, ...] = ()
    details: str | None = None  # the line's description beside its name, if it has one

    @cached_property
    def text(self) -> str:
        """The name and the description as keywords are compared with them: each a text of
        its own, so a phrase never runs from one into the other."""
        return _BETWEEN.join(normalise(part) for part in (self.description, self.details) if part)

    def in_details(self, at: int) -> bool:
        """Whether a place in `text` is in the description rather than the name."""
        return bool(self.details) and at > len(normalise(self.description))

    def written(self, start: int, end: int) -> str:
        """What stands between two places of `text`, as the line writes it: with its
        diacritics and its capitals ("Cartușe" where `text` has "cartuse")."""
        part, offset = self.description, 0
        if self.in_details(start):
            part, offset = self.details, len(normalise(self.description)) + len(_BETWEEN)
        places = _places(part)
        return part[places[start - offset]:places[end - offset - 1] + 1]

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, text: str) -> "Subject":
        """Reads what to_json wrote, and what another version of it wrote: only the
        description has to be there, and anything not known here is ignored."""
        stored = json.loads(text)
        return cls(
            supplier_cui=stored.get("supplier_cui"),
            description=stored["description"],
            seller_code=stored.get("seller_code"),
            barcode=stored.get("barcode"),
            commodity_codes=tuple(stored.get("commodity_codes") or ()),
            details=stored.get("details"),  # not kept before 0.14.0
        )


@dataclass(frozen=True)
class RuleMatch:
    """Which condition of a rule a line meets, and with what."""

    condition: str  # supplier_cui, seller_code, barcode, commodity_code or keyword
    found: str  # the supplier's CUI, the code on the line, or the keyword as the rule has it
    prefix: str | None = None  # for a classification code: the start of it the rule names
    # For a keyword: the whole words of the line it found, as the line writes them
    # ("Tonercartușul" for "*cartus*"), and whether they are in the line's description.
    matched: str | None = None
    in_details: bool = False


@dataclass(frozen=True)
class Rule:
    name: str
    cont: str
    keywords: tuple[str, ...] = ()
    item_codes: tuple[str, ...] = ()
    commodity_prefixes: tuple[str, ...] = ()
    supplier_cuis: tuple[str, ...] = ()
    # The client the rule is for; None: every client. Only said, never matched on: the
    # rulebook of a client already holds just the rules that apply to it.
    client_cui: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        # A lone string is one entry, not its letters; an empty entry would match every line.
        for name in CONDITIONS:
            given = getattr(self, name)
            entries = (given,) if isinstance(given, str) else tuple(given or ())
            kept = tuple(str(entry).strip() for entry in entries if str(entry).strip())
            if name == "keywords":  # a keyword of stars alone would match every line
                kept = tuple(keyword for keyword in kept if normalise(keyword.strip("*")))
            object.__setattr__(self, name, kept)

    def matches(self, subject: Subject) -> bool:
        if self.supplier_cuis and subject.supplier_cui in self.supplier_cuis:
            return True
        if self.item_codes and (
            subject.seller_code in self.item_codes or subject.barcode in self.item_codes
        ):
            return True
        if any(code.startswith(self.commodity_prefixes) for code in subject.commodity_codes):
            return True
        return bool(self._any_keyword and self._any_keyword.search(subject.text))

    def match(self, subject: Subject) -> RuleMatch | None:
        """Why the rule matches: the first condition that holds, checked in the order
        `matches` checks them; None when it does not match."""
        if self.supplier_cuis and subject.supplier_cui in self.supplier_cuis:
            return RuleMatch("supplier_cui", subject.supplier_cui)
        for condition, code in (("seller_code", subject.seller_code), ("barcode", subject.barcode)):
            if self.item_codes and code in self.item_codes:
                return RuleMatch(condition, code)
        for code in subject.commodity_codes:
            prefix = next((prefix for prefix in self.commodity_prefixes if code.startswith(prefix)), None)
            if prefix is not None:
                return RuleMatch("commodity_code", code, prefix)
        for keyword in self.keywords:
            found = re.search(_keyword_start(keyword) + _keyword_regex(keyword), subject.text)
            if found:
                start, end = _whole_words(subject.text, found)
                return RuleMatch(
                    "keyword", keyword, matched=subject.written(start, end), in_details=subject.in_details(start),
                )
        return None

    @cached_property
    def _any_keyword(self) -> re.Pattern | None:
        """One pattern that finds any of the keywords, so the line is read once. Most
        keywords start where a word starts; that is checked once per place for all of
        them, not once per keyword. Those that start with a * are tried anywhere."""
        if not self.keywords:
            return None
        at_word = [_keyword_regex(keyword) for keyword in self.keywords if not keyword.startswith("*")]
        anywhere = [_keyword_regex(keyword) for keyword in self.keywords if keyword.startswith("*")]
        parts = ([rf"(?<!\w)(?:{'|'.join(at_word)})"] if at_word else []) + anywhere
        return re.compile("|".join(parts))


@dataclass(frozen=True)
class Rulebook:
    """What one client's invoices are decided with."""

    accounts: dict[str, str]  # account -> what belongs on it; this is also what Jev is told
    rules: tuple[Rule, ...]  # in the order they are checked
    instructions: str  # the question put to Jev about a whole invoice
    line_instructions: str = ""  # the question about one line; empty: the default one
    # For the invoices the client issued: Jev is told neither party, and asked what was sold.
    issued: bool = False

    def rule_for(self, subject: Subject) -> Rule | None:
        # Most invoices match no rule at all. One look settles that, instead of one per rule.
        if not self._rules_together.matches(subject):
            return None
        return next((rule for rule in self.rules if rule.matches(subject)), None)

    def rules_for(self, subject: Subject) -> list[Rule]:
        """Every rule that matches, in the order they are checked: the first decides."""
        if not self._rules_together.matches(subject):
            return []
        return [rule for rule in self.rules if rule.matches(subject)]

    @cached_property
    def _rules_together(self) -> Rule:
        return any_of(self.rules)


def any_of(rules) -> Rule:
    """One rule that matches exactly the subjects that at least one of `rules` matches.
    It holds every condition of every rule, and a rule matches when any condition holds."""
    return Rule("", "", *(
        tuple(entry for rule in rules for entry in getattr(rule, name)) for name in CONDITIONS
    ))


def normalise(text: str) -> str:
    """Lower case, no diacritics, single spaces."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(plain.lower().split())


def _keyword_regex(keyword: str) -> str:
    """The keyword as a pattern for a line written as `normalise` writes it: up to the end
    of a word, or, with a * at its end, whatever follows. Where it may start is
    _keyword_start's part."""
    words = re.escape(normalise(keyword.strip("*")))
    return words + ("" if keyword.endswith("*") else r"(?!\w)")


def _keyword_start(keyword: str) -> str:
    """Where a keyword may start: where a word starts, or, with a * at its start, anywhere."""
    return "" if keyword.startswith("*") else r"(?<!\w)"


def _whole_words(text: str, found: re.Match) -> tuple[int, int]:
    """Where a keyword found something, widened to the words it stands in: a * found part
    of a word."""
    start, end = found.span()
    while start > 0 and _WORD.match(text[start - 1]):
        start -= 1
    while end < len(text) and _WORD.match(text[end]):
        end += 1
    return start, end


def _places(text: str) -> list[int]:
    """For each character of `normalise(text)`, the place in `text` it comes from, worked
    out the same way: decomposed, without its accents, in lower case, single spaces."""
    places, pending = [], False
    for at, character in enumerate(text or ""):
        for part in unicodedata.normalize("NFKD", character):
            if unicodedata.combining(part):
                continue
            for lower in part.lower():
                if lower.isspace():
                    pending = bool(places)
                    continue
                if pending:
                    places.append(at)  # the single space normalise writes
                    pending = False
                places.append(at)
    return places


_WORD = re.compile(r"\w")
_BETWEEN = " · "  # between the name and the description, in Subject.text: no word runs across it


# --- what a new database starts with: examples, to be replaced on the rules screen -------

EXAMPLE_ACCOUNTS = {
    "6022": "Combustibil pentru vehicule: motorină, benzină, GPL, alimentări la stația de carburanți.",
    "626": "Telefonie, internet, servicii poștale și de curierat.",
    "628": "Alte servicii prestate de terți care nu au un cont propriu în această listă.",
}

# For the invoices a client issued itself: what it sold.
EXAMPLE_ISSUED_ACCOUNTS = {
    "701": "Vânzarea produselor finite, făcute de client.",
    "704": "Servicii prestate și lucrări executate.",
    "707": "Vânzarea mărfurilor cumpărate pentru a fi revândute.",
}

EXAMPLE_RULES = (
    {"name": "combustibil", "cont": "6022", "keywords": ["motorina", "benzina", "gpl auto"]},
    {"name": "telecom", "cont": "626", "keywords": ["abonament telefon*", "internet"]},
)

DEFAULT_JEV_INSTRUCTIONS = (
    "Pe ce cont contabil se înregistrează această factură primită de la furnizor? "
    "Toate liniile facturii primesc același cont. Hotărăște după linia cu valoarea cea mai "
    "mare (numărul ei este în linia_cu_valoarea_cea_mai_mare); celelalte linii și numele "
    "furnizorului sunt doar context. Dacă niciun cont din listă nu se potrivește cu ceea ce "
    "s-a cumpărat, alege varianta care spune acest lucru."
)

DEFAULT_JEV_LINE_INSTRUCTIONS = (
    "Pe ce cont contabil se înregistrează această linie a unei facturi primite de la furnizor? "
    "Hotărăște după ce s-a cumpărat pe linie (descrierea, codurile și unitatea de măsură); "
    "numele furnizorului este doar context. Dacă niciun cont din listă nu se potrivește cu "
    "ceea ce s-a cumpărat pe această linie, alege varianta care spune acest lucru."
)

DEFAULT_JEV_ISSUED_INSTRUCTIONS = (
    "Pe ce cont de venituri se înregistrează această factură emisă de client? "
    "Toate liniile facturii primesc același cont. Hotărăște după linia cu valoarea cea mai "
    "mare (numărul ei este în linia_cu_valoarea_cea_mai_mare); celelalte linii sunt doar context. "
    "Dacă niciun cont din listă nu se potrivește cu ceea ce s-a vândut, alege varianta care "
    "spune acest lucru."
)

DEFAULT_JEV_ISSUED_LINE_INSTRUCTIONS = (
    "Pe ce cont de venituri se înregistrează această linie a unei facturi emise de client? "
    "Hotărăște după ce s-a vândut pe linie (descrierea, codurile și unitatea de măsură). "
    "Dacă niciun cont din listă nu se potrivește cu ceea ce s-a vândut pe această linie, "
    "alege varianta care spune acest lucru."
)
