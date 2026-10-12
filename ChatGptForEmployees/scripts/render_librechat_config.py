#!/usr/bin/env python3
"""
Validates librechat.yaml and renders the PBI-08 ROMChat CXOne modelSpec into it.

The CXOne spec is NOT stored in config/librechat.yaml: its agent_id only exists
after the server-side provisioning command has created the agent in that
environment, and a placeholder ID must never reach a working picker. Rendering is
deterministic text insertion (comments and YAML anchors are preserved), and the
result is validated before it is written.

Usage:
  python render_librechat_config.py --config ../config/librechat.yaml --validate
  python render_librechat_config.py --config ../config/librechat.yaml \
      --agent-id agent_xxxxxxxxxxxxxxxxxxxxx --out /tmp/librechat_cxone.yaml

Exit code 0 = valid/rendered, 1 = validation failure (reasons on stderr).
"""

import argparse
import re
import sys

import yaml

SPEC_NAME = "romtech-cxone"
SERVER_NAME = "romtech-cxone"
CXONE_CONTEXT_CAP = 128000
SHARED_CAP = 64000
BASELINE_SPECS = ("romtech-ai-standard", "romtech-ai-fast")
AGENT_ID_PATTERN = re.compile(r"^agent_[A-Za-z0-9_-]{21}$")
INSERT_BEFORE = "# Feature governance"
REQUIRED_CAPABILITIES = {"file_search", "artifacts"}

SPEC_TEMPLATE = """    # PBI-08: dedicated CXOne reporting agent. agent_id is rendered per environment
    # from the provisioning command's output; do not hand-edit it. The agent owns its
    # model configuration; this spec only selects it. 128000 is the CXOne-specific
    # cap and is separate from the 3000-token tool-response budget.
    - name: "{name}"
      label: "ROMChat CXOne"
      preset:
        endpoint: "agents"
        agent_id: "{agent_id}"
        maxContextTokens: {cap}

"""


def _specs(config):
    return {s.get("name"): s for s in (config.get("modelSpecs") or {}).get("list") or []}


def validate(config, require_cxone_spec=False):
    problems = []
    specs = _specs(config)

    for name in BASELINE_SPECS:
        spec = specs.get(name)
        if spec is None:
            problems.append(f"baseline modelSpec {name} is missing")
        elif (spec.get("preset") or {}).get("maxContextTokens") != SHARED_CAP:
            problems.append(f"{name} must keep maxContextTokens {SHARED_CAP}")

    agents = (config.get("endpoints") or {}).get("agents") or {}
    if agents.get("disableBuilder") is not True:
        problems.append("endpoints.agents.disableBuilder must remain true")
    iface_agents = (config.get("interface") or {}).get("agents")
    if iface_agents is not False:
        # USE is required for the persistent CXOne agent to be reachable; nothing else may be granted.
        if not isinstance(iface_agents, dict) or iface_agents.get("use") is not True:
            problems.append("interface.agents must be false or {use: true, create/share/public: false}")
        elif any(iface_agents.get(k) is not False for k in ("create", "share", "public")):
            problems.append("interface.agents must keep create, share and public false")
    missing = REQUIRED_CAPABILITIES - set(agents.get("capabilities") or [])
    if missing:
        problems.append(f"agents capabilities lost: {sorted(missing)}")

    server = (config.get("mcpServers") or {}).get(SERVER_NAME)
    if server is not None:
        url = str(server.get("url", ""))
        headers = {k.lower() for k in (server.get("headers") or {})}
        if server.get("type") != "streamable-http":
            problems.append(f"{SERVER_NAME} must use type streamable-http")
        if "x-romchat-user-id" not in headers:
            problems.append(f"{SERVER_NAME} must send x-romchat-user-id from the session")
        if "x-romchat-conversation-id" not in headers:
            problems.append(f"{SERVER_NAME} must send x-romchat-conversation-id")
        if "${" not in url and not url.startswith("https://"):
            problems.append(f"{SERVER_NAME} url must be an env reference or https URL")

    cxone = specs.get(SPEC_NAME)
    if cxone is None:
        if require_cxone_spec:
            problems.append(f"modelSpec {SPEC_NAME} is required but absent")
        return problems

    preset = cxone.get("preset") or {}
    if preset.get("endpoint") != "agents":
        problems.append(f"{SPEC_NAME} must select the agents endpoint")
    if not AGENT_ID_PATTERN.match(str(preset.get("agent_id", ""))):
        problems.append(f"{SPEC_NAME} agent_id is not a provisioned agent ID")
    if preset.get("maxContextTokens") != CXONE_CONTEXT_CAP:
        problems.append(f"{SPEC_NAME} must set maxContextTokens {CXONE_CONTEXT_CAP}")
    if server is None:
        problems.append(f"{SPEC_NAME} requires mcpServers.{SERVER_NAME}")
    defaults = [s for s in specs.values() if s.get("default")]
    if len(defaults) != 1 or cxone.get("default"):
        problems.append("exactly one default spec is required and it must not be CXOne")
    return problems


def render(text, agent_id):
    if not AGENT_ID_PATTERN.match(agent_id):
        raise ValueError("agent id does not look like a provisioned agent ID")
    if f'name: "{SPEC_NAME}"' in text:
        raise ValueError(f"{SPEC_NAME} spec is already present; refusing to render twice")
    marker = text.find(INSERT_BEFORE)
    if marker == -1:
        raise ValueError(f'insertion marker "{INSERT_BEFORE}" not found')
    newline = "\r\n" if "\r\n" in text else "\n"
    block = SPEC_TEMPLATE.format(name=SPEC_NAME, agent_id=agent_id, cap=CXONE_CONTEXT_CAP)
    return text[:marker] + block.replace("\n", newline) + text[marker:]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate or render librechat.yaml")
    parser.add_argument("--config", required=True)
    parser.add_argument("--agent-id")
    parser.add_argument("--out")
    parser.add_argument("--validate", action="store_true")
    args = parser.parse_args(argv)

    with open(args.config, encoding="utf-8", newline="") as handle:
        text = handle.read()

    if args.validate or not args.agent_id:
        problems = validate(yaml.safe_load(text))
        for problem in problems:
            print(f"FAIL: {problem}", file=sys.stderr)
        print("librechat.yaml valid" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0

    if not args.out:
        parser.error("--out is required when rendering")
    try:
        rendered = render(text, args.agent_id)
    except ValueError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    problems = validate(yaml.safe_load(rendered), require_cxone_spec=True)
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}", file=sys.stderr)
        return 1
    with open(args.out, "w", encoding="utf-8", newline="") as handle:
        handle.write(rendered)
    print(f"rendered {SPEC_NAME} spec for {args.agent_id[:10]}... to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
