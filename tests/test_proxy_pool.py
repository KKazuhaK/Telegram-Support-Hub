import unittest

import tests.support as support

SessionLocal = support.install_sqlite_session()

from backend.app.models.account import Account
from backend.app.models.proxy import ProxyEndpoint
from backend.app.services.proxy_pool import (
    PoolError,
    auto_assign_proxy,
    pick_proxy_for_account,
)


def _seed_proxy(db, *, name, status="active", country=None, max_accounts=None, host="1.2.3.4", port=1080):
    proxy = ProxyEndpoint(
        name=name, protocol="socks5", host=host, port=port,
        country=country, status=status, max_accounts=max_accounts,
    )
    db.add(proxy)
    db.flush()
    return proxy


def _seed_account(db, *, phone=None, status="active", proxy_id=None, tg_user_id="u1"):
    acc = Account(
        tg_user_id=tg_user_id, phone=phone, session_path=f"/tmp/{tg_user_id}.session",
        status=status, enabled=True, proxy_id=proxy_id,
    )
    db.add(acc)
    db.flush()
    return acc


class ProxyPoolTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = SessionLocal()
        for model in (Account, ProxyEndpoint):
            for row in self.db.query(model).all():
                self.db.delete(row)
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()

    def test_picks_only_active_proxy(self) -> None:
        _seed_proxy(self.db, name="bad", status="error")
        ok = _seed_proxy(self.db, name="ok", status="active")
        self.db.commit()
        chosen = pick_proxy_for_account(self.db, _seed_account(self.db))
        self.assertEqual(chosen.id, ok.id)

    def test_country_match_preferred(self) -> None:
        any_proxy = _seed_proxy(self.db, name="any", status="active", country="US")
        cn_proxy = _seed_proxy(self.db, name="cn", status="active", country="CN")
        self.db.commit()
        acc = _seed_account(self.db, phone="+8613800000000")
        chosen = pick_proxy_for_account(self.db, acc, prefer_country="CN")
        self.assertEqual(chosen.id, cn_proxy.id)
        # falls back to any active when no country match
        chosen2 = pick_proxy_for_account(self.db, acc, prefer_country="ZZ")
        self.assertIn(chosen2.id, {any_proxy.id, cn_proxy.id})

    def test_respects_max_accounts(self) -> None:
        full = _seed_proxy(self.db, name="full", status="active", max_accounts=1)
        free = _seed_proxy(self.db, name="free", status="active", max_accounts=2)
        _seed_account(self.db, tg_user_id="taken", proxy_id=full.id)
        self.db.commit()
        chosen = pick_proxy_for_account(self.db, _seed_account(self.db, tg_user_id="newone"))
        self.assertEqual(chosen.id, free.id)

    def test_raises_when_pool_empty(self) -> None:
        self.db.commit()
        with self.assertRaises(PoolError):
            pick_proxy_for_account(self.db, _seed_account(self.db))

    def test_round_robin_balances_load(self) -> None:
        a = _seed_proxy(self.db, name="a", status="active")
        b = _seed_proxy(self.db, name="b", status="active")
        accs = [_seed_account(self.db, tg_user_id=f"acc{i}") for i in range(4)]
        self.db.commit()
        for acc in accs:
            auto_assign_proxy(self.db, acc)
        self.db.commit()
        counts = {a.id: 0, b.id: 0}
        for acc in self.db.query(Account).all():
            if acc.proxy_id in counts:
                counts[acc.proxy_id] += 1
        self.assertEqual(set(counts.values()), {2})


if __name__ == "__main__":
    unittest.main()
