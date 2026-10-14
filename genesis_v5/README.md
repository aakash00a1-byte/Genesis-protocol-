# Genesis V5

Genesis V5 is a Kernel-orchestrated, multi-agent AI system with a memory
fabric, a sandboxed tool gateway, a security core, and production readiness
support. It is designed to run fully **offline** with no API keys: real
provider adapters stay disabled unless explicitly configured.

## Quick start

```bash
pip install -e ".[dev]"
python -m pytest tests/ -q
```

Run the offline end-to-end scenario:

```bash
python -m pytest tests/integration/test_end_to_end.py -q
```

## Architecture

See `docs/GENESIS_V5_ARCHITECTURE.md` and `docs/GENESIS_V5_ROADMAP.md`.

## Principles

- The **Kernel is the authority** — no model, agent, tool, or provider has
  implicit authority (zero trust).
- Tools are executed only through the **Tool Gateway**, which enforces
  policy, permission, sandbox, timeout, and audit.
- Memory writes are **scope- and policy-controlled** and secret-sanitized.
- Reflection is **bounded**; QA is **independent**.
- Providers are **configuration-driven** and **fallback-bounded**. No
  infinite fallback loops.
- External integrations remain **unverified until their APIs are verified**;
  adapters never fabricate success.

## Security

Never commit credentials. See `docs/GENESIS_V5_ARCHITECTURE.md#security` for
the security core, audit events, and validation rules.