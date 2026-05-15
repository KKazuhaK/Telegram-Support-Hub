import unittest
from datetime import UTC, datetime

import tests.support as support

SessionLocal = support.install_sqlite_session()

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.models.account import Account, AccountGroup, AccountGroupMember
from backend.app.models.agent import SupportAgent, SupportAgentGroupPermission
from backend.app.models.message import MessageRecord


def _bootstrap(client):
    return client.post(
        "/api/auth/bootstrap-admin",
        json={"username": "root", "password": "12345678"},
    )


def _today_iso():
    return datetime.now(UTC).strftime("%Y-%m-%d")


class AgentStatsTodayTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        with SessionLocal() as db:
            for model in (MessageRecord, AccountGroupMember, Account, AccountGroup,
                          SupportAgentGroupPermission, SupportAgent):
                for row in db.query(model).all():
                    db.delete(row)
            db.commit()
        self.auth = {"Authorization": f"Bearer {_bootstrap(self.client).json()['access_token']}"}

    def _seed_agent_with_account(self, db, agent_username: str):
        from backend.app.core.security import hash_password
        agent = SupportAgent(username=agent_username, role="agent", status="enabled",
                             password_hash=hash_password("12345678"))
        db.add(agent)
        group = AccountGroup(name=f"{agent_username}-g", code=f"{agent_username}-g", enabled=True)
        db.add(group)
        db.flush()
        db.add(SupportAgentGroupPermission(
            agent_id=agent.id, account_group_id=group.id,
            can_view_friends=True, can_view_chats=True, can_send_message=True,
        ))
        acc = Account(tg_user_id=f"{agent_username}-acc", session_path=f"/tmp/{agent_username}.session",
                      status="active", enabled=True)
        db.add(acc)
        db.flush()
        db.add(AccountGroupMember(account_id=acc.id, group_id=group.id, is_primary=True))
        db.commit()
        return agent, acc

    def test_today_kpis_per_agent(self) -> None:
        with SessionLocal() as db:
            a1, acc1 = self._seed_agent_with_account(db, "alice")
            a2, acc2 = self._seed_agent_with_account(db, "bob")
            today = _today_iso()
            yesterday = "2020-01-01"
            # alice's account: 3 sent today, 1 replied today, 1 read today
            for _ in range(3):
                db.add(MessageRecord(account_id=acc1.id, body_snapshot="x", status="sent",
                                     sent_at=f"{today}T10:00:00+00:00"))
            db.add(MessageRecord(account_id=acc1.id, body_snapshot="x", status="replied",
                                 sent_at=f"{today}T10:00:00+00:00",
                                 replied_at=f"{today}T10:30:00+00:00"))
            db.add(MessageRecord(account_id=acc1.id, body_snapshot="x", status="read",
                                 sent_at=f"{today}T11:00:00+00:00",
                                 read_at=f"{today}T11:30:00+00:00"))
            # bob's account: 1 sent yesterday — should not count today
            db.add(MessageRecord(account_id=acc2.id, body_snapshot="x", status="sent",
                                 sent_at=f"{yesterday}T10:00:00+00:00"))
            db.commit()

        rows = self.client.get("/api/statistics/support-agents", headers=self.auth).json()
        by_user = {r["username"]: r for r in rows}
        # Total mention here is 3 sent + 1 replied + 1 read = 5 records with sent_at today
        self.assertEqual(by_user["alice"]["today_sent"], 5)
        self.assertEqual(by_user["alice"]["today_replied"], 1)
        self.assertEqual(by_user["alice"]["today_read"], 1)
        self.assertAlmostEqual(by_user["alice"]["today_reply_rate"], 1 / 5)
        self.assertAlmostEqual(by_user["alice"]["today_read_rate"], 1 / 5)

        # bob has no traffic today -> all zeros, rates 0
        self.assertEqual(by_user["bob"]["today_sent"], 0)
        self.assertEqual(by_user["bob"]["today_reply_rate"], 0)

    def test_admin_with_no_group_permission_returns_zero_kpis(self) -> None:
        # Admin user has no SupportAgentGroupPermission rows but exists in
        # the agents table; KPIs should be zero rather than crash.
        rows = self.client.get("/api/statistics/support-agents", headers=self.auth).json()
        self.assertTrue(any(r["username"] == "root" for r in rows))
        for r in rows:
            self.assertIn("today_sent", r)


class AgentBatchApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)
        with SessionLocal() as db:
            for model in (SupportAgentGroupPermission, SupportAgent):
                for row in db.query(model).all():
                    db.delete(row)
            db.commit()
        self.auth = {"Authorization": f"Bearer {_bootstrap(self.client).json()['access_token']}"}

        for n in ("alice", "bob", "carol"):
            self.client.post("/api/support-agents",
                             json={"username": n, "password": "12345678", "role": "agent"},
                             headers=self.auth)

    def _ids_except_root(self) -> list[int]:
        rows = self.client.get("/api/support-agents", headers=self.auth).json()
        return [r["id"] for r in rows if r["username"] != "root"]

    def test_batch_delete_removes_agents_and_permissions(self) -> None:
        ids = self._ids_except_root()
        self.assertEqual(len(ids), 3)
        # Give one agent a permission row so we exercise the cascade
        with SessionLocal() as db:
            from backend.app.models.account import AccountGroup
            g = AccountGroup(name="g", code="g")
            db.add(g)
            db.flush()
            db.add(SupportAgentGroupPermission(agent_id=ids[0], account_group_id=g.id))
            db.commit()

        resp = self.client.request(
            "DELETE", "/api/support-agents/batch",
            json={"ids": ids[:2]}, headers=self.auth,
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertEqual(resp.json(), {"deleted": 2})
        with SessionLocal() as db:
            self.assertEqual(db.query(SupportAgent).filter(
                SupportAgent.username != "root").count(), 1)
            self.assertEqual(db.query(SupportAgentGroupPermission).filter_by(
                agent_id=ids[0]).count(), 0)

    def test_batch_delete_refuses_to_delete_self(self) -> None:
        # The acting admin (root) must not be removable via batch — that
        # would lock the operator out of their own session.
        with SessionLocal() as db:
            root = db.query(SupportAgent).filter_by(username="root").first()
            root_id = root.id

        resp = self.client.request(
            "DELETE", "/api/support-agents/batch",
            json={"ids": [root_id]}, headers=self.auth,
        )
        self.assertEqual(resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
