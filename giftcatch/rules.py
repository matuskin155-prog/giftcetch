"""Правила отбора без сети: «красивые» номера и подходящие фоны."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field

MATCH_MODES = ("both", "backdrop", "number", "any")


@dataclass
class NumberRules:
    max_number: int = 100      # номер <= этого считается красивым (0 — выключить)
    repdigits: bool = True     # 77, 777, 8888
    round: bool = True         # 100, 2000, 50000
    sequences: bool = True     # 123, 1234, 4321
    palindromes: bool = False  # 1221, 12321
    repeats: bool = False      # 1212, 123123
    extra: list[int] = field(default_factory=list)  # свои номера: 69, 420, 1337


def _is_straight(s: str) -> bool:
    steps = {int(b) - int(a) for a, b in zip(s, s[1:])}
    return steps in ({1}, {-1})


def _is_repeat(s: str) -> bool:
    n = len(s)
    return any(n % p == 0 and s == s[:p] * (n // p) for p in range(2, n // 2 + 1))


def number_reasons(num: int, rules: NumberRules) -> list[str]:
    """Почему номер красивый. Пустой список — номер обычный."""
    s = str(num)
    reasons = []
    if num in rules.extra:
        reasons.append("номер из списка")
    if rules.max_number and num <= rules.max_number:
        reasons.append(f"номер ≤ {rules.max_number}")
    if len(s) >= 2:
        if rules.repdigits and len(set(s)) == 1:
            reasons.append("одинаковые цифры")
        if rules.round and len(s) >= 3 and set(s[1:]) == {"0"}:
            reasons.append("круглый номер")
        if rules.sequences and len(s) >= 3 and _is_straight(s):
            reasons.append("лесенка")
        if rules.palindromes and len(s) >= 4 and s == s[::-1] and len(set(s)) > 1:
            reasons.append("зеркальный")
        if rules.repeats and len(s) >= 4 and len(set(s)) > 1 and _is_repeat(s):
            reasons.append("повтор")
    return reasons


def name_matches(name: str | None, patterns: list[str]) -> bool:
    """Сравнение без учёта регистра, поддерживает маски: "*Black*", "Onyx Black"."""
    if not name:
        return False
    n = name.casefold()
    return any(fnmatch.fnmatchcase(n, p.casefold()) for p in patterns)


def evaluate(num: int, backdrop: str | None, backdrops: list[str],
             numbers: NumberRules, match: str) -> list[str]:
    """Причины, по которым подарок нам подходит. Пустой список — не подходит."""
    backdrop_ok = name_matches(backdrop, backdrops)
    num_reasons = number_reasons(num, numbers)
    ok = {
        "both": backdrop_ok and bool(num_reasons),
        "backdrop": backdrop_ok,
        "number": bool(num_reasons),
        "any": backdrop_ok or bool(num_reasons),
    }[match]
    if not ok:
        return []
    return ([f"фон {backdrop}"] if backdrop_ok else []) + num_reasons
