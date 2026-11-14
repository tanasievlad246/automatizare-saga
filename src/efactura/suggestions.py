"""Proposing a rule from an invoice that no rule decided.

Jev or a person chose the account. The proposal is the rule that would have chosen it:
one that looks for a word of the deciding line, or, when that line says nothing telling
("Servicii conform contract"), one for everything from that supplier.

The two word lists below are a judgement about Romanian invoices, not a fact. They only
set what is offered and what starts ticked; the person decides what the rule looks for.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from .rules import Subject, normalise

MAX_WORDS = 6  # more would not fit on the card, and the first words say the most
MIN_WORD_LENGTH = 3

# Never offered: they are on every kind of invoice, so they tell nothing about the account.
STOP_WORDS = frozenset(
    # link words
    "din pentru sau ori prin catre fara sub peste intre dupa pana ale unei unui cel cea cei "
    "cele care este sunt cat tip per "
    # units and money
    "buc bucata bucati litri litru ltr kgm tona tone ora ore zile kwh mwh gcal lei ron eur "
    "euro usd "
    # time
    "luna lunii lunile luni anul anului trimestrul perioada saptamana ianuarie februarie "
    "martie aprilie mai iunie iulie august septembrie octombrie noiembrie decembrie ian feb "
    "mar apr iun iul aug sep sept oct noi nov dec "
    # words about the document itself
    "numar numarul conform contract contractul contractului ctr factura facturii fact aviz "
    "avizul comanda comenzii cod art seria serie data tva total cota anexa act aditional"
    .split()
)

# Offered, but not ticked to begin with: a rule on "servicii" alone would catch far too much.
GENERAL_WORDS = frozenset(
    "servicii serviciu serviciul prestari prestare abonament abonamente produse produs marfa "
    "marfuri materiale material diverse alte taxa taxe contravaloare cheltuieli lucrari "
    "lucrare plata avans livrare achizitie furnizare articole".split()
)

# What a keyword has to match from end to end: letters, digits and _ that stand together.
_RUN = re.compile(r"\w+")


@dataclass(frozen=True)
class Proposal:
    """A rule the person could create: this account for these words, or for this supplier."""

    cont: str
    keywords: tuple[str, ...] = ()
    supplier_cuis: tuple[str, ...] = ()

    @property
    def key(self) -> tuple:
        """Equal for proposals that would make the same rule, however the word is written."""
        return self.cont, tuple(normalise(word) for word in self.keywords), self.supplier_cuis


def words_of(description: str) -> tuple[str, ...]:
    """The words of a line that a rule could look for: as written, in lower case, in order.

    Only words a keyword would find on this very line. "Office365" is one run to a keyword,
    so "office" is not offered: a rule looking for it would miss the invoice it came from.
    """
    findable = set(_RUN.findall(normalise(description)))  # the line as keywords are compared with it
    written = unicodedata.normalize("NFC", description or "").lower()  # an accent stays on its letter
    offered: dict[str, str] = {}  # how keywords are compared -> how the invoice writes it
    for word in _RUN.findall(written):
        plain = normalise(word)
        if (
            word.isalpha()  # "42,5R" and "A4" carry no word
            and len(plain) >= MIN_WORD_LENGTH
            and plain not in STOP_WORDS
            and plain in findable
        ):
            offered.setdefault(plain, word)
    return tuple(offered.values())[:MAX_WORDS]


def ticked_words(words: tuple[str, ...]) -> tuple[str, ...]:
    """The words ticked to begin with: the first one that tells what was bought."""
    telling = next((word for word in words if normalise(word) not in GENERAL_WORDS), None)
    return (telling,) if telling else ()


def propose(subject: Subject, cont: str) -> Proposal | None:
    """The rule to propose for an invoice booked on `cont`; None when nothing sets it apart."""
    words = ticked_words(words_of(subject.description))
    if words:
        return Proposal(cont, keywords=words)
    if subject.supplier_cui:
        return Proposal(cont, supplier_cuis=(subject.supplier_cui,))
    return None
