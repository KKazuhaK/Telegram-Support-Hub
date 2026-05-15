import json
import unittest
from unittest.mock import MagicMock, patch

import tests.support  # noqa: F401  configures env

from backend.app.services.reply_bus import REPLY_CHANNEL, publish_reply


class ReplyBusTestCase(unittest.TestCase):
    def test_publish_serialises_payload(self) -> None:
        fake_redis = MagicMock()
        with patch("backend.app.services.reply_bus.get_redis", return_value=fake_redis):
            publish_reply({"text": "hi", "account_id": 1, "tg_user_id": "9"})

        fake_redis.publish.assert_called_once()
        channel, payload = fake_redis.publish.call_args.args
        self.assertEqual(channel, REPLY_CHANNEL)
        decoded = json.loads(payload)
        self.assertEqual(decoded["text"], "hi")
        self.assertEqual(decoded["account_id"], 1)


if __name__ == "__main__":
    unittest.main()
