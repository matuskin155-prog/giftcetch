import asyncio
import unittest

from telethon.tl import types

from giftcatch.config import Buy, Config, Search, Upgrade
from giftcatch.models import Collectible, rarity_label, unique_gifts_in
from giftcatch.rules import NumberRules, evaluate, name_matches, number_reasons
from giftcatch.sniper import Sniper


def unique_gift(num=777, backdrop="Onyx Black", stars=500, ton_only=False):
    rarity = types.StarGiftAttributeRarity(permille=15)
    return types.StarGiftUnique(
        id=1, gift_id=2, title="Plush Pepe", slug=f"PlushPepe-{num}", num=num,
        availability_issued=5000, availability_total=10000, resale_ton_only=ton_only,
        attributes=[
            types.StarGiftAttributeModel(name="Gold", document=types.DocumentEmpty(id=1), rarity=rarity),
            types.StarGiftAttributeBackdrop(name=backdrop, backdrop_id=7, center_color=0, edge_color=0,
                                            pattern_color=0, text_color=0, rarity=rarity),
            types.StarGiftAttributePattern(name="Frog", document=types.DocumentEmpty(id=2), rarity=rarity),
        ],
        resell_amount=[types.StarsAmount(amount=stars, nanos=0), types.StarsTonAmount(amount=10**9)],
    )


class NumberTest(unittest.TestCase):
    rules = NumberRules(max_number=100, palindromes=True, repeats=True, extra=[1337])

    def test_beautiful(self):
        for num in (1, 100, 777, 8888, 2000, 50000, 1234, 4321, 1221, 12321, 1212, 123123, 1337):
            self.assertTrue(number_reasons(num, self.rules), num)

    def test_ordinary(self):
        for num in (101, 1235, 2025, 4096, 98766, 1002):
            self.assertEqual(number_reasons(num, self.rules), [], num)

    def test_rules_can_be_disabled(self):
        off = NumberRules(max_number=0, repdigits=False, round=False, sequences=False)
        for num in (7, 777, 1000, 1234, 1221):
            self.assertEqual(number_reasons(num, off), [], num)


class MatchTest(unittest.TestCase):
    def test_backdrop_masks(self):
        self.assertTrue(name_matches("Onyx Black", ["*Black*"]))
        self.assertTrue(name_matches("black", ["Black"]))
        self.assertFalse(name_matches("Midnight Blue", ["*Black*"]))
        self.assertFalse(name_matches(None, ["*"]))

    def test_modes(self):
        rules = NumberRules()
        self.assertEqual(evaluate(777, "Black", ["*Black*"], rules, "both"), ["фон Black", "одинаковые цифры"])
        self.assertEqual(evaluate(5123, "Black", ["*Black*"], rules, "both"), [])
        self.assertEqual(evaluate(5123, "Black", ["*Black*"], rules, "backdrop"), ["фон Black"])
        self.assertEqual(evaluate(777, "Gold", ["*Black*"], rules, "number"), ["одинаковые цифры"])
        self.assertEqual(evaluate(5123, "Gold", ["*Black*"], rules, "any"), [])


class ModelsTest(unittest.TestCase):
    def test_from_tl(self):
        c = Collectible.from_tl(unique_gift())
        self.assertEqual((c.num, c.backdrop, c.model, c.pattern, c.price), (777, "Onyx Black", "Gold", "Frog", 500))
        self.assertEqual(c.link, "https://t.me/nft/PlushPepe-777")
        self.assertIsNone(Collectible.from_tl(unique_gift(ton_only=True)).price)

    def test_rarity_label(self):
        self.assertEqual(rarity_label(types.StarGiftAttributeRarity(permille=15)), "1.5%")
        self.assertEqual(rarity_label(types.StarGiftAttributeRarityLegendary()), "Legendary")

    def test_unique_gifts_in_updates(self):
        msg = types.MessageService(id=1, peer_id=types.PeerUser(1), date=None,
                                   action=types.MessageActionStarGiftUnique(gift=unique_gift(), upgrade=True))
        updates = types.Updates(updates=[types.UpdateNewMessage(message=msg, pts=1, pts_count=1)],
                                users=[], chats=[], date=None, seq=0)
        self.assertEqual([g.num for g in unique_gifts_in(updates)], [777])
        self.assertEqual(unique_gifts_in(None), [])


class FakeClient:
    """Отвечает на запросы оплаты и запоминает, что бот отправил."""

    def __init__(self, invoice_total):
        self.invoice_total = invoice_total
        self.requests, self.messages = [], []

    async def __call__(self, request):
        self.requests.append(type(request).__name__)
        if type(request).__name__ == "GetPaymentFormRequest":
            invoice = types.Invoice(currency="XTR", prices=[types.LabeledPrice(label="", amount=self.invoice_total)])
            return types.payments.PaymentFormStarGift(form_id=42, invoice=invoice)
        return types.payments.PaymentResult(updates=types.Updates([], [], [], None, 0))

    async def send_message(self, entity, text, **kwargs):
        self.messages.append(text)


def make_config(**buy):
    return Config(api_id=1, api_hash="x", session="s", search=Search(), numbers=NumberRules(),
                  buy=Buy(**buy), upgrade=Upgrade())


class SniperTest(unittest.TestCase):
    def consider(self, client, cfg, gift):
        sniper = Sniper(client, cfg)
        asyncio.run(sniper.consider(Collectible.from_tl(gift)))
        return sniper

    def test_notify_only(self):
        client = FakeClient(500)
        self.consider(client, make_config(), unique_gift())
        self.assertEqual(client.requests, [])
        self.assertIn("Plush Pepe #777", client.messages[0])

    def test_buys_within_limits(self):
        client = FakeClient(500)
        sniper = self.consider(client, make_config(auto_buy=True, max_price=600, budget=1000), unique_gift())
        self.assertEqual(client.requests, ["GetPaymentFormRequest", "SendStarsFormRequest"])
        self.assertEqual((sniper.bought, sniper.spent), (1, 500))
        self.assertTrue(sniper.done)

    def test_skips_listing_above_limit(self):
        client = FakeClient(500)
        self.consider(client, make_config(auto_buy=True, max_price=400, budget=1000), unique_gift())
        self.assertEqual(client.requests, [])

    def test_checks_invoice_not_listing_price(self):
        client = FakeClient(900)  # продавец поднял цену после того, как мы увидели лот
        sniper = self.consider(client, make_config(auto_buy=True, max_price=600, budget=1000), unique_gift())
        self.assertEqual(client.requests, ["GetPaymentFormRequest"])
        self.assertEqual(sniper.bought, 0)

    def test_ignores_ordinary(self):
        client = FakeClient(500)
        self.consider(client, make_config(auto_buy=True, max_price=600, budget=1000), unique_gift(num=5123))
        self.assertEqual((client.requests, client.messages), ([], []))


if __name__ == "__main__":
    unittest.main()
