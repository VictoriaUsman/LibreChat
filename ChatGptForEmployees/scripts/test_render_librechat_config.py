import os
import unittest

import yaml

import render_librechat_config as r

CONFIG = os.path.join(os.path.dirname(__file__), "..", "config", "librechat.yaml")
AGENT_ID = "agent_" + "a" * 21


def load():
    with open(CONFIG, encoding="utf-8", newline="") as handle:
        return handle.read()


class RenderTests(unittest.TestCase):
    def test_committed_config_is_valid_and_has_no_cxone_spec(self):
        config = yaml.safe_load(load())
        self.assertEqual(r.validate(config), [])
        self.assertNotIn(r.SPEC_NAME, r._specs(config))

    def test_rendered_spec_has_real_id_cap_and_leaves_baselines_untouched(self):
        before = yaml.safe_load(load())
        after = yaml.safe_load(r.render(load(), AGENT_ID))
        self.assertEqual(r.validate(after, require_cxone_spec=True), [])
        preset = r._specs(after)[r.SPEC_NAME]["preset"]
        self.assertEqual(
            preset, {"endpoint": "agents", "agent_id": AGENT_ID, "maxContextTokens": 128000}
        )
        for name in r.BASELINE_SPECS:
            self.assertEqual(r._specs(after)[name], r._specs(before)[name])
        self.assertEqual(after["fileConfig"], before["fileConfig"])
        self.assertEqual(after["endpoints"], before["endpoints"])

    def test_default_spec_is_unchanged(self):
        after = yaml.safe_load(r.render(load(), AGENT_ID))
        defaults = [n for n, s in r._specs(after).items() if s.get("default")]
        self.assertEqual(defaults, ["romtech-ai-fast"])

    def test_rejects_placeholder_and_malformed_ids(self):
        for bad in ("<actual-provisioned-agent-id>", "agent_short", "", "AGENT_" + "a" * 21):
            with self.assertRaises(ValueError):
                r.render(load(), bad)

    def test_refuses_double_render(self):
        with self.assertRaises(ValueError):
            r.render(r.render(load(), AGENT_ID), AGENT_ID)

    def test_validation_catches_regressions(self):
        config = yaml.safe_load(load())
        config["endpoints"]["agents"]["disableBuilder"] = False
        config["endpoints"]["agents"]["capabilities"] = ["mcp"]
        config["modelSpecs"]["list"][0]["preset"]["maxContextTokens"] = 128000
        joined = " ".join(r.validate(config))
        self.assertIn("disableBuilder", joined)
        self.assertIn("capabilities lost", joined)
        self.assertIn("romtech-ai-standard must keep", joined)

    def test_cxone_spec_requires_the_mcp_server(self):
        config = yaml.safe_load(r.render(load(), AGENT_ID))
        del config["mcpServers"]
        self.assertIn("requires mcpServers", " ".join(r.validate(config)))

    def test_interface_agents_may_grant_use_but_never_create_share_or_public(self):
        config = yaml.safe_load(load())
        self.assertEqual(
            config["interface"]["agents"],
            {"use": True, "create": False, "share": False, "public": False},
        )
        for key in ("create", "share", "public"):
            broken = yaml.safe_load(load())
            broken["interface"]["agents"][key] = True
            self.assertIn("create, share and public", " ".join(r.validate(broken)))
        broken = yaml.safe_load(load())
        broken["interface"]["agents"] = True
        self.assertTrue(r.validate(broken))

    def test_mcp_server_sends_session_identity_headers(self):
        server = yaml.safe_load(load())["mcpServers"][r.SERVER_NAME]
        self.assertEqual(server["headers"]["x-romchat-user-id"], "{{LIBRECHAT_USER_ID}}")
        self.assertIn("CONVERSATIONID", server["headers"]["x-romchat-conversation-id"])
        self.assertGreater(server["timeout"], 20000)


if __name__ == "__main__":
    unittest.main()
