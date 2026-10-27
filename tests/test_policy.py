import importlib
import unittest


def module(name):
    try:
        return importlib.import_module("plugins.mansui_companion." + name)
    except ModuleNotFoundError as exc:
        raise AssertionError(f"Missing implemented capability: {name}") from exc


class PolicyTests(unittest.TestCase):
    def test_owner_private_group_and_mention_routes(self):
        d, p = module("domain"), module("policy")
        cases = [
            ("10001", None, (), "required"),
            ("10002", None, (), "drop"),
            ("10001", "30001", (), "required"),
            ("10002", "30001", ("90001",), "required"),
            ("10002", "30001", (), "optional"),
            ("10001", "39999", ("90001",), "drop"),
            ("90001", "30001", (), "drop"),
        ]
        for sender, group, mentions, want in cases:
            with self.subTest(sender=sender, group=group, mentions=mentions):
                msg = d.Message(
                    "90001", sender, group, "7", "你好", frozenset(mentions), 1
                )
                self.assertEqual(
                    p.decide(msg, "10001", frozenset({"30001"})).value, want
                )

    def test_private_rejection_reads_identity_only(self):
        p = module("policy")

        class Event(dict):
            def get(self, key, default=None):
                if key in ("message", "raw_message"):
                    raise AssertionError("Unauthorized content was inspected")
                return super().get(key, default)

        event = Event(
            post_type="message",
            message_type="private",
            sub_type="group",
            self_id=90001,
            user_id=10002,
            group_id=30001,
        )
        self.assertFalse(p.admit(event, "10001", frozenset({"30001"}), "90001"))

    def test_required_media_and_repeated_text_not_filtered(self):
        d, p = module("domain"), module("policy")
        for mid in ("1", "2"):
            msg = d.Message("90001", "10001", "30001", mid, "", frozenset(), 1, True)
            self.assertEqual(
                p.decide(msg, "10001", frozenset({"30001"})).value, "required"
            )

    def test_invalid_identity_closed_and_scope_independent(self):
        d, p = module("domain"), module("policy")
        self.assertFalse(
            p.admit({"post_type": "notice"}, "10001", frozenset(), "90001")
        )
        self.assertFalse(
            p.admit(
                {
                    "post_type": "message",
                    "message_type": "private",
                    "self_id": 90002,
                    "user_id": 10001,
                },
                "10001",
                frozenset(),
                "90001",
            )
        )
        a = d.Message("90001", "10001", None, "1", "", frozenset(), 1)
        b = d.Message("90001", "10001", "30001", "1", "", frozenset(), 1)
        self.assertNotEqual(a.scope, b.scope)

    def test_settings_validate_accounts_endpoint_limits_and_secret_repr(self):
        s = module("settings")
        valid = {
            "owner_qq": "10001",
            "bot_qq": "90001",
            "allowed_groups": ["30001"],
            "ready": True,
        }
        settings = s.Settings.from_dict(valid, {"deepseek_api_key": "private-test-key"})
        self.assertNotIn("private-test-key", repr(settings))
        for change in (
            {"owner_qq": "abc"},
            {"allowed_groups": [""]},
            {"base_url": "http://evil.example"},
            {"max_concurrency": 0},
            {"owner_qq": "90001"},
            {"queue_size": True},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                s.Settings.from_dict(dict(valid, **change), {})


if __name__ == "__main__":
    unittest.main()
