"""Слежение за вторичным рынком подарков и автопокупка."""

from __future__ import annotations

import asyncio
import logging
import time

from telethon.errors import FloodWaitError, RPCError
from telethon.tl import functions, types

from .catalog import fetch_catalog, matching_backdrops
from .config import Config
from .models import Collectible
from .rules import evaluate, name_matches

log = logging.getLogger("giftcatch")

CATALOG_TTL = 600  # как часто перечитывать список коллекций, сек


class Sniper:
    def __init__(self, client, cfg: Config):
        self.client = client
        self.cfg = cfg
        self.seen: set[tuple[str, int | None]] = set()  # (slug, цена): снижение цены покажем снова
        self.filters: dict[int, list | None] = {}
        self.scanned: set[int] = set()
        self.spent = 0
        self.bought = 0

    @property
    def done(self) -> bool:
        b = self.cfg.buy
        return b.auto_buy and (self.bought >= b.max_count or self.spent >= b.budget)

    async def run(self) -> None:
        s, b = self.cfg.search, self.cfg.buy
        mode = (f"автопокупка до {b.max_price} ⭐ за штуку, бюджет {b.budget} ⭐, максимум {b.max_count} шт."
                if b.auto_buy else "только уведомления (auto_buy = false)")
        log.info("Слежу за вторичкой: фоны %s, режим %s, %s", s.backdrops, s.match, mode)
        collections, catalog_at = [], 0.0
        while not self.done:
            if time.monotonic() - catalog_at > CATALOG_TTL:
                collections = await self.collections()
                catalog_at = time.monotonic()
            for gift in collections:
                try:
                    await self.scan(gift)
                except FloodWaitError as e:
                    log.warning("Telegram просит подождать %s с", e.seconds)
                    await asyncio.sleep(e.seconds + 1)
                except RPCError as e:
                    log.warning("%s: ошибка API %s", gift.title, e)
                if self.done:
                    break
                await asyncio.sleep(s.request_delay)
            await asyncio.sleep(s.interval)
        await self.notify(f"🛑 Лимит покупок достигнут: куплено {self.bought}, потрачено {self.spent} ⭐. Останавливаюсь.")

    async def collections(self) -> list[types.StarGift]:
        gifts = await fetch_catalog(self.client)
        chosen = [g for g in gifts if name_matches(g.title, self.cfg.search.gifts) and g.availability_resale]
        log.info("Коллекций на вторичке под фильтр: %d", len(chosen))
        if not chosen:
            log.warning("Ни одна коллекция не подошла под [search] gifts = %s", self.cfg.search.gifts)
        return chosen

    async def attribute_filter(self, gift: types.StarGift) -> list | None:
        """Фильтр по фонам для запроса. None — в коллекции нет нужных фонов."""
        if self.cfg.search.match in ("number", "any"):
            return []
        if gift.id not in self.filters:
            backdrops = await matching_backdrops(self.client, gift.id, self.cfg.search.backdrops)
            if backdrops:
                log.info("%s: фоны %s", gift.title, ", ".join(b.name for b in backdrops))
            else:
                log.info("%s: подходящих фонов нет, пропускаю", gift.title)
            self.filters[gift.id] = [types.StarGiftAttributeIdBackdrop(backdrop_id=b.backdrop_id)
                                     for b in backdrops] or None
        return self.filters[gift.id]

    async def scan(self, gift: types.StarGift) -> None:
        attrs = await self.attribute_filter(gift)
        if attrs is None:
            return
        # Первый проход по коллекции — глубокий, дальше хватает первой страницы:
        # без сортировки сверху идут свежие лоты.
        pages = 1 if gift.id in self.scanned else self.cfg.search.first_scan_pages
        offset = ""
        for page in range(pages):
            if page:
                await asyncio.sleep(self.cfg.search.request_delay)
            res = await self.client(functions.payments.GetResaleStarGiftsRequest(
                gift_id=gift.id, offset=offset, limit=self.cfg.search.page_size, attributes=attrs or None))
            for tl in res.gifts:
                if isinstance(tl, types.StarGiftUnique):
                    await self.consider(Collectible.from_tl(tl))
            offset = res.next_offset
            if not offset or self.done:
                break
        self.scanned.add(gift.id)

    async def consider(self, c: Collectible) -> None:
        key = (c.slug, c.price)
        if key in self.seen:
            return
        self.seen.add(key)
        s = self.cfg.search
        reasons = evaluate(c.num, c.backdrop, s.backdrops, self.cfg.numbers, s.match)
        if not reasons:
            return
        await self.notify(f"🎯 Нашёл: {c.describe()}\nПочему: {', '.join(reasons)}")
        if self.cfg.buy.auto_buy and not self.done:
            await self.buy(c)

    async def buy(self, c: Collectible) -> None:
        b = self.cfg.buy
        if c.price is None:
            return
        if c.price > b.max_price:
            log.info("%s #%d дороже лимита (%d > %d ⭐)", c.title, c.num, c.price, b.max_price)
            return
        if self.spent + c.price > b.budget:
            log.info("%s #%d не влезает в бюджет", c.title, c.num)
            return
        invoice = types.InputInvoiceStarGiftResale(slug=c.slug, to_id=types.InputPeerSelf())
        try:
            form = await self.client(functions.payments.GetPaymentFormRequest(invoice=invoice))
            total = sum(p.amount for p in form.invoice.prices)
            # Проверяем итоговый счёт, а не цену из списка: продавец мог её поменять.
            if form.invoice.currency != "XTR" or total > b.max_price or self.spent + total > b.budget:
                await self.notify(f"⚠️ Не покупаю {c.title} #{c.num}: счёт {total} {form.invoice.currency}")
                return
            await self.client(functions.payments.SendStarsFormRequest(form_id=form.form_id, invoice=invoice))
        except RPCError as e:
            await self.notify(f"❌ Не удалось купить {c.title} #{c.num}: {e}")
            return
        self.spent += total
        self.bought += 1
        await self.notify(f"✅ Купил {c.title} #{c.num} за {total} ⭐ "
                          f"(потрачено {self.spent}/{b.budget} ⭐)\n{c.link}")

    async def notify(self, text: str) -> None:
        log.info(text.replace("\n", " | "))
        try:
            await self.client.send_message("me", text, link_preview=False)
        except RPCError as e:
            log.warning("Не смог написать в «Избранное»: %s", e)
