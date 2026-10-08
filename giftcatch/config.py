"""Загрузка config.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .rules import MATCH_MODES, NumberRules


@dataclass
class Search:
    gifts: list[str] = field(default_factory=lambda: ["*"])
    backdrops: list[str] = field(default_factory=lambda: ["*Black*"])
    match: str = "both"
    interval: float = 10
    request_delay: float = 1.5
    page_size: int = 50
    first_scan_pages: int = 20


@dataclass
class Buy:
    auto_buy: bool = False
    max_price: int = 0
    budget: int = 0
    max_count: int = 1


@dataclass
class Upgrade:
    keep_original_details: bool = True
    max_price: int = 0


@dataclass
class Config:
    api_id: int
    api_hash: str
    session: str
    search: Search
    numbers: NumberRules
    buy: Buy
    upgrade: Upgrade


def load(path: str | Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise SystemExit(f"Нет файла {path}. Скопируйте config.example.toml в {path} и заполните.")
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    tg = raw.get("telegram", {})
    if not tg.get("api_id") or not tg.get("api_hash"):
        raise SystemExit("Заполните [telegram] api_id и api_hash (https://my.telegram.org → API development tools).")
    cfg = Config(
        api_id=int(tg["api_id"]),
        api_hash=str(tg["api_hash"]),
        session=str(tg.get("session", "giftcatch")),
        search=Search(**raw.get("search", {})),
        numbers=NumberRules(**raw.get("numbers", {})),
        buy=Buy(**raw.get("buy", {})),
        upgrade=Upgrade(**raw.get("upgrade", {})),
    )
    if cfg.search.match not in MATCH_MODES:
        raise SystemExit(f"[search] match должен быть одним из: {', '.join(MATCH_MODES)}")
    if cfg.buy.auto_buy and (cfg.buy.max_price <= 0 or cfg.buy.budget <= 0):
        raise SystemExit("Для auto_buy задайте [buy] max_price и budget больше нуля.")
    return cfg
