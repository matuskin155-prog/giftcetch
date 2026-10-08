"""Разбор объектов Telegram API в удобный вид."""

from __future__ import annotations

from dataclasses import dataclass

from telethon.tl import types


@dataclass
class Collectible:
    title: str
    slug: str
    num: int
    issued: int
    total: int
    model: str | None
    backdrop: str | None
    pattern: str | None
    price: int | None  # цена на вторичке в звёздах, None — не продаётся за звёзды

    @property
    def link(self) -> str:
        return f"https://t.me/nft/{self.slug}"

    @classmethod
    def from_tl(cls, gift: types.StarGiftUnique) -> Collectible:
        attrs = {type(a): a for a in gift.attributes}
        model = attrs.get(types.StarGiftAttributeModel)
        backdrop = attrs.get(types.StarGiftAttributeBackdrop)
        pattern = attrs.get(types.StarGiftAttributePattern)
        return cls(
            title=gift.title,
            slug=gift.slug,
            num=gift.num,
            issued=gift.availability_issued,
            total=gift.availability_total,
            model=model.name if model else None,
            backdrop=backdrop.name if backdrop else None,
            pattern=pattern.name if pattern else None,
            price=None if gift.resale_ton_only else stars_price(gift.resell_amount),
        )

    def describe(self) -> str:
        price = f"{self.price} ⭐" if self.price is not None else "не продаётся за звёзды"
        return (f"{self.title} #{self.num} — фон {self.backdrop}, модель {self.model}, "
                f"узор {self.pattern} — {price}\n{self.link}")


def stars_price(amounts: list | None) -> int | None:
    for a in amounts or []:
        if isinstance(a, types.StarsAmount):
            return a.amount
    return None


def rarity_permille(rarity) -> int | None:
    """Шанс выпадения в промилле; у редкостей-уровней (Rare, Epic…) числа нет."""
    return rarity.permille if isinstance(rarity, types.StarGiftAttributeRarity) else None


def rarity_label(rarity) -> str:
    permille = rarity_permille(rarity)
    if permille is not None:
        return f"{permille / 10:g}%"
    return type(rarity).__name__.removeprefix("StarGiftAttributeRarity")


def unique_gifts_in(updates) -> list[types.StarGiftUnique]:
    """Достаёт улучшенные подарки из ответа на улучшение/покупку."""
    found = []
    for update in getattr(updates, "updates", None) or []:
        action = getattr(getattr(update, "message", None), "action", None)
        if (isinstance(action, types.MessageActionStarGiftUnique)
                and isinstance(action.gift, types.StarGiftUnique)):
            found.append(action.gift)
    return found
