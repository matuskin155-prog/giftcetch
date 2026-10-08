"""Каталог коллекций и их атрибуты."""

from __future__ import annotations

from telethon.errors import RPCError
from telethon.tl import functions, types

from .rules import name_matches


async def fetch_catalog(client) -> list[types.StarGift]:
    """Все коллекции подарков, у которых есть название (лимитированные)."""
    res = await client(functions.payments.GetStarGiftsRequest(hash=0))
    return [g for g in res.gifts if isinstance(g, types.StarGift) and g.title]


def find_gift(gifts: list[types.StarGift], name: str) -> types.StarGift:
    exact = [g for g in gifts if g.title.casefold() == name.casefold()]
    if exact:
        return exact[0]
    similar = [g for g in gifts if name.casefold() in g.title.casefold()]
    if len(similar) == 1:
        return similar[0]
    hint = ", ".join(g.title for g in similar[:10]) or "ничего похожего"
    raise SystemExit(f"Коллекция «{name}» не найдена. Похожие: {hint}. Полный список: python -m giftcatch catalog --all")


async def all_attributes(client, gift_id: int) -> list:
    """Все возможные модели/фоны/узоры коллекции с шансами выпадения."""
    try:
        res = await client(functions.payments.GetStarGiftUpgradeAttributesRequest(gift_id=gift_id))
        return res.attributes
    except RPCError:
        # Запасной путь: атрибуты, которые сейчас встречаются на вторичке.
        res = await client(functions.payments.GetResaleStarGiftsRequest(
            gift_id=gift_id, offset="", limit=1, attributes_hash=0))
        return res.attributes or []


async def matching_backdrops(client, gift_id: int, patterns: list[str]) -> list[types.StarGiftAttributeBackdrop]:
    return [a for a in await all_attributes(client, gift_id)
            if isinstance(a, types.StarGiftAttributeBackdrop) and name_matches(a.name, patterns)]
