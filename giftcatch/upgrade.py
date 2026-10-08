"""Шансы на нужный фон и улучшение своих подарков."""

from __future__ import annotations

from telethon.errors import RPCError
from telethon.tl import functions, types

from .catalog import all_attributes, fetch_catalog, find_gift
from .config import Config
from .models import Collectible, rarity_label, rarity_permille, unique_gifts_in
from .rules import evaluate, name_matches


async def show_chances(client, cfg: Config, name: str) -> None:
    gift = find_gift(await fetch_catalog(client), name)
    backdrops = [a for a in await all_attributes(client, gift.id) if isinstance(a, types.StarGiftAttributeBackdrop)]
    wanted = [b for b in backdrops if name_matches(b.name, cfg.search.backdrops)]

    print(f"{gift.title}: всего фонов {len(backdrops)}, подходят под {cfg.search.backdrops}: {len(wanted)}")
    for b in sorted(wanted, key=lambda b: rarity_permille(b.rarity) or 0):
        print(f"  {b.name:<24} {rarity_label(b.rarity)}")

    chance = sum(rarity_permille(b.rarity) or 0 for b in wanted) / 1000
    if chance:
        tries = 1 / chance
        print(f"Шанс получить такой фон при улучшении: {chance:.2%} — в среднем 1 из {tries:.0f} улучшений.")
        if gift.upgrade_stars:
            line = f"Одно улучшение стоит {gift.upgrade_stars} ⭐"
            if not gift.sold_out:
                per_try = gift.stars + gift.upgrade_stars
                line += f", с покупкой подарка {per_try} ⭐ → в среднем ≈ {per_try * tries:.0f} ⭐ до успеха"
            print(line + ".")
    print("Фон и номер при улучшении выбирает сервер Telegram случайно — повлиять на них нельзя.")

    if wanted:
        try:
            res = await client(functions.payments.GetResaleStarGiftsRequest(
                gift_id=gift.id, offset="", limit=1, sort_by_price=True,
                attributes=[types.StarGiftAttributeIdBackdrop(backdrop_id=b.backdrop_id) for b in wanted]))
        except RPCError as e:
            print(f"Вторичку проверить не удалось: {e}")
            return
        cheapest = [Collectible.from_tl(g) for g in res.gifts if isinstance(g, types.StarGiftUnique)]
        if cheapest:
            print(f"Самый дешёвый с таким фоном на вторичке (всего {res.count}):\n  {cheapest[0].describe()}")
        else:
            print("На вторичке с таким фоном сейчас ничего нет.")


async def my_upgradable(client) -> list[types.SavedStarGift]:
    gifts, offset = [], ""
    while True:
        res = await client(functions.payments.GetSavedStarGiftsRequest(
            peer=types.InputPeerSelf(), offset=offset, limit=100,
            exclude_unique=True, exclude_unupgradable=True))
        gifts += res.gifts
        offset = res.next_offset
        if not offset:
            break
    return [g for g in gifts if g.msg_id and isinstance(g.gift, types.StarGift)]


async def list_mine(client) -> None:
    gifts = await my_upgradable(client)
    if not gifts:
        print("Неулучшенных подарков, которые можно улучшить, нет.")
        return
    print(f"{'msg_id':>8}  {'подарок':<26} {'№':>7}  улучшение")
    for saved in gifts:
        g = saved.gift
        num = f"#{saved.gift_num}" if saved.gift_num else "—"
        price = "оплачено" if saved.upgrade_stars else f"{g.upgrade_stars} ⭐"
        print(f"{saved.msg_id:>8}  {g.title or g.id!s:<26} {num:>7}  {price}")
    print("\nУлучшить: python -m giftcatch upgrade <msg_id>")


async def upgrade_gift(client, cfg: Config, msg_id: int, yes: bool) -> None:
    ref = types.InputSavedStarGiftUser(msg_id=msg_id)
    res = await client(functions.payments.GetSavedStarGiftRequest(stargift=[ref]))
    if not res.gifts:
        raise SystemExit(f"Подарок с msg_id={msg_id} не найден. Список: python -m giftcatch mine")
    saved = res.gifts[0]
    if isinstance(saved.gift, types.StarGiftUnique):
        raise SystemExit("Этот подарок уже улучшен.")
    title = saved.gift.title or f"подарок {saved.gift.id}"
    keep = cfg.upgrade.keep_original_details

    if saved.upgrade_stars:
        confirm(f"Улучшить {title}? Улучшение уже оплачено отправителем.", yes)
        updates = await client(functions.payments.UpgradeStarGiftRequest(stargift=ref, keep_original_details=keep))
    else:
        invoice = types.InputInvoiceStarGiftUpgrade(stargift=ref, keep_original_details=keep)
        form = await client(functions.payments.GetPaymentFormRequest(invoice=invoice))
        total = sum(p.amount for p in form.invoice.prices)
        if form.invoice.currency != "XTR" or (cfg.upgrade.max_price and total > cfg.upgrade.max_price):
            raise SystemExit(f"Улучшение стоит {total} {form.invoice.currency} — выше [upgrade] max_price.")
        confirm(f"Улучшить {title} за {total} ⭐?", yes)
        result = await client(functions.payments.SendStarsFormRequest(form_id=form.form_id, invoice=invoice))
        updates = getattr(result, "updates", None)

    unique = unique_gifts_in(updates)
    if not unique:
        print("Подарок улучшен, но в ответе нет деталей — посмотрите его в профиле.")
        return
    c = Collectible.from_tl(unique[0])
    print(f"Готово: {c.describe()}")
    hits = evaluate(c.num, c.backdrop, cfg.search.backdrops, cfg.numbers, "any")
    print(f"🎉 Повезло: {', '.join(hits)}" if hits else "Не повезло: фон и номер обычные.")


def confirm(question: str, yes: bool) -> None:
    if yes:
        return
    if input(f"{question} [y/N] ").strip().lower() not in ("y", "yes", "д", "да"):
        raise SystemExit("Отменено.")
