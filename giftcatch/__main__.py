"""Запуск: python -m giftcatch <команда>."""

from __future__ import annotations

import argparse
import asyncio
import logging

from telethon import TelegramClient

from . import config
from .catalog import fetch_catalog
from .sniper import Sniper
from .upgrade import list_mine, show_chances, upgrade_gift


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="giftcatch", description="Ловец подарков Telegram с чёрным фоном и красивым номером")
    p.add_argument("-c", "--config", default="config.toml", help="путь к конфигу (по умолчанию config.toml)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("login", help="войти в аккаунт Telegram и сохранить сессию")
    cat = sub.add_parser("catalog", help="коллекции и сколько их на вторичке")
    cat.add_argument("--all", action="store_true", help="показать и те, которых нет на вторичке")
    ch = sub.add_parser("chances", help="шанс нужного фона при улучшении и цена на вторичке")
    ch.add_argument("gift", help="название коллекции, например \"Plush Pepe\"")
    sub.add_parser("snipe", help="следить за вторичкой и ловить подходящие подарки")
    sub.add_parser("mine", help="мои подарки, которые можно улучшить")
    up = sub.add_parser("upgrade", help="улучшить свой подарок и показать, что выпало")
    up.add_argument("msg_id", type=int, help="msg_id из команды mine")
    up.add_argument("-y", "--yes", action="store_true", help="не спрашивать подтверждение")
    return p.parse_args()


async def show_catalog(client, show_all: bool) -> None:
    gifts = sorted(await fetch_catalog(client), key=lambda g: -(g.availability_resale or 0))
    for g in gifts:
        if not show_all and not g.availability_resale:
            continue
        upgrade = f"{g.upgrade_stars} ⭐" if g.upgrade_stars else "—"
        sold = "  (распродан)" if g.sold_out else ""
        print(f"{g.title:<28} на вторичке: {g.availability_resale or 0:>6}   улучшение: {upgrade}{sold}")


async def run(args: argparse.Namespace) -> None:
    cfg = config.load(args.config)
    client = TelegramClient(cfg.session, cfg.api_id, cfg.api_hash, flood_sleep_threshold=120)
    await client.start()
    try:
        if args.cmd == "login":
            me = await client.get_me()
            print(f"Вошли как {me.first_name} (id {me.id}). Сессия сохранена в {cfg.session}.session")
        elif args.cmd == "catalog":
            await show_catalog(client, args.all)
        elif args.cmd == "chances":
            await show_chances(client, cfg, args.gift)
        elif args.cmd == "snipe":
            await Sniper(client, cfg).run()
        elif args.cmd == "mine":
            await list_mine(client)
        elif args.cmd == "upgrade":
            await upgrade_gift(client, cfg, args.msg_id, args.yes)
    finally:
        await client.disconnect()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
    logging.getLogger("telethon").setLevel(logging.WARNING)
    try:
        asyncio.run(run(parse_args()))
    except KeyboardInterrupt:
        print("\nОстановлено.")


if __name__ == "__main__":
    main()
