"""Natural-language order parsing.

"I want two masala dosas and one coffee"
    -> [{"name": "Masala Dosa", "quantity": 2}, {"name": "Coffee", "quantity": 1}]

Strategy:
  1. If an LLM is configured, ask it to extract items as JSON, then validate
     every name against the real menu (the LLM can never invent items).
  2. Otherwise (or if the LLM fails) use the local rule-based parser:
     number words + menu aliases + plural forms + fuzzy matching for typos.
"""
import difflib
import re

from models.models import MenuItem, ParsedRequest
from services.llm_service import LLMService

NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "single": 1, "two": 2, "couple": 2, "pair": 2,
    "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "dozen": 12,
}

STOPWORDS = {
    "i", "want", "would", "like", "to", "have", "order", "get", "me", "please", "and",
    "with", "plus", "also", "give", "can", "could", "some", "the", "of", "need", "for",
    "my", "us", "we", "our", "friend", "friends", "cup", "cups", "plate", "plates",
    "glass", "glasses", "piece", "pieces", "pcs", "x", "add", "then", "one", "more",
    "just", "only", "lets", "let", "s", "im", "id", "hi", "hello", "bro", "hey", "is",
    "it", "be", "will", "take", "every", "each", "extra", "thanks", "thank", "you",
    "nos", "no", "qty", "quantity", "of", "all", "them", "make", "that", "this",
}

# Extra ways students refer to menu items (menu names themselves are added automatically)
ALIASES = {
    "Masala Dosa": ["masala dose", "masale dose", "masala dosai"],
    "Plain Dosa": ["plain dose", "sada dosa", "dosa", "dose"],
    "Set Dosa": ["set dose"],
    "Idli Vada": ["idly vada", "idli", "idly", "vada", "idli vade"],
    "Veg Pulao": ["pulao", "pulav", "veg pulav"],
    "Mini Meals": ["meals", "meal"],
    "Paneer Roll": ["paneer wrap"],
    "Veg Sandwich": ["sandwich"],
    "Gobi Manchurian": ["gobi", "manchurian"],
    "Coffee": ["filter coffee", "kaapi", "kapi"],
    "Tea": ["chai", "masala chai"],
    "Fresh Lime Juice": ["lime juice", "lime soda", "lime", "lemon juice", "nimbu", "fresh lime"],
    "Badam Milk": ["badam"],
}


def _normalize(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r"(\d+)\s*x\b", r"\1 ", text)          # "2x dosa"  -> "2 dosa"
    text = re.sub(r"\bx\s*(\d+)", r" x\1", text)         # "dosa x 2" -> "dosa x2" (postfix qty)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return text.split()


def _plural_forms(phrase: str) -> list[str]:
    words = phrase.split()
    last = words[-1]
    forms = {phrase, " ".join(words[:-1] + [last + "s"]), " ".join(words[:-1] + [last + "es"])}
    return list(forms)


def _quantity(word: str) -> int | None:
    if word.isdigit():
        return int(word)
    return NUMBER_WORDS.get(word)


class LocalOrderParser:
    """Rule-based parser that works fully offline."""

    def __init__(self, menu_items: list[MenuItem]):
        self.menu = {item.name: item for item in menu_items}
        self.alias_to_name: dict[tuple[str, ...], str] = {}
        for item in menu_items:
            for alias in [item.name.lower()] + ALIASES.get(item.name, []):
                for form in _plural_forms(alias):
                    self.alias_to_name.setdefault(tuple(form.split()), item.name)
        self.max_alias_len = max((len(k) for k in self.alias_to_name), default=1)
        self.single_words = {k[0]: v for k, v in self.alias_to_name.items() if len(k) == 1}

    def resolve_name(self, phrase: str) -> str | None:
        """Map any phrase (from LLM or user) to an exact menu name."""
        words = tuple(_normalize(phrase))
        if words in self.alias_to_name:
            return self.alias_to_name[words]
        match = difflib.get_close_matches(" ".join(words), [" ".join(k) for k in self.alias_to_name], n=1, cutoff=0.8)
        return self.alias_to_name[tuple(match[0].split())] if match else None

    def parse(self, text: str) -> ParsedRequest:
        words = _normalize(text)
        found: dict[str, int] = {}
        unrecognized: list[str] = []
        pending_qty: int | None = None
        unknown_run: list[str] = []
        last_added: tuple[str, int] | None = None     # (item, qty) - for postfix "x2"

        def flush_unknown():
            if unknown_run:
                unrecognized.append(" ".join(unknown_run))
                unknown_run.clear()

        i = 0
        while i < len(words):
            # 1) try the longest menu alias starting at position i
            matched_name, length = None, 0
            for n in range(min(self.max_alias_len, len(words) - i), 0, -1):
                key = tuple(words[i:i + n])
                if key in self.alias_to_name:
                    matched_name, length = self.alias_to_name[key], n
                    break
            # 2) fuzzy match single words (typos like "samosaa", "cofee")
            if not matched_name and len(words[i]) >= 4 and words[i] not in STOPWORDS:
                close = difflib.get_close_matches(words[i], list(self.single_words), n=1, cutoff=0.8)
                if close:
                    matched_name, length = self.single_words[close[0]], 1

            if matched_name:
                flush_unknown()
                qty = pending_qty or 1
                found[matched_name] = found.get(matched_name, 0) + qty
                last_added = (matched_name, qty)
                pending_qty = None
                i += length
                continue

            postfix = re.fullmatch(r"x(\d+)", words[i])
            if postfix and last_added:              # "dosa x2" -> replace the 1 we assumed
                name, prev = last_added
                found[name] += int(postfix.group(1)) - prev
                last_added = None
                i += 1
                continue

            qty = _quantity(words[i])
            if qty is not None:
                flush_unknown()
                pending_qty = qty
            elif words[i] in STOPWORDS:
                flush_unknown()
            else:
                unknown_run.append(words[i])
            i += 1
        flush_unknown()

        items = [
            {"menu_item_id": self.menu[name].id, "name": name, "quantity": qty}
            for name, qty in found.items()
        ]
        return ParsedRequest(items=items, unrecognized=unrecognized, parser="local")


class NaturalLanguageOrderParser:
    SYSTEM_PROMPT = (
        "You are the order-understanding module of a college canteen. "
        "Convert the student's message into JSON. Use ONLY item names from the menu, "
        "spelled exactly as in the menu. Quantities are positive integers (default 1). "
        "Anything that is not on the menu goes into 'unrecognized'. "
        'Reply with JSON only: {"items": [{"name": "<menu name>", "quantity": <int>}], '
        '"unrecognized": ["<text>"]}'
    )

    def __init__(self, llm: LLMService, menu_items: list[MenuItem]):
        self.llm = llm
        self.local = LocalOrderParser(menu_items)

    def parse(self, text: str) -> ParsedRequest:
        text = (text or "").strip()
        if not text:
            return ParsedRequest(items=[], unrecognized=[], parser="local", note="Empty request")
        if len(text) > 500:
            return ParsedRequest(items=[], unrecognized=[], parser="local", note="Request too long (max 500 characters)")

        if self.llm.available:
            parsed = self._parse_with_llm(text)
            if parsed is not None:
                return parsed
            fallback = self.local.parse(text)
            fallback.note = f"LLM unavailable ({self.llm.last_error}); used local parser"
            return fallback
        return self.local.parse(text)

    def _parse_with_llm(self, text: str) -> ParsedRequest | None:
        menu_list = "\n".join(f"- {name}" for name in self.local.menu)
        data = self.llm.complete_json(self.SYSTEM_PROMPT, f"Menu:\n{menu_list}\n\nStudent message: {text}")
        if not data or not isinstance(data.get("items"), list):
            return None

        found: dict[str, int] = {}
        unrecognized = [str(u) for u in data.get("unrecognized", []) if str(u).strip()]
        for entry in data["items"]:
            if not isinstance(entry, dict):
                continue
            name = self.local.resolve_name(str(entry.get("name", "")))  # guard against hallucinated items
            try:
                qty = int(entry.get("quantity", 1))
            except (TypeError, ValueError):
                qty = 1
            if name and qty > 0:
                found[name] = found.get(name, 0) + qty
            elif entry.get("name"):
                unrecognized.append(str(entry["name"]))

        if not found and not unrecognized:
            return None
        items = [{"menu_item_id": self.local.menu[n].id, "name": n, "quantity": q} for n, q in found.items()]
        return ParsedRequest(items=items, unrecognized=unrecognized, parser=f"llm:{self.llm.provider.name}")
