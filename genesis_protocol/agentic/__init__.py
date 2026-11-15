"""Agentic capability layer for GLUTEN.

Bounded, evidence-producing building blocks that sit on top of the existing
Genesis architecture (provider chain, task queue, tool registry):

* ``memory``    - durable, user-isolated fact memory (SQLite) with provenance,
                  verification status, confidence, freshness, conflict
                  detection and safe correction/revocation/deletion.
* ``memory_safety`` - the write/read boundary: refuses secret- and
                  instruction-shaped content and renders recall as untrusted
                  data, never as instructions.
* ``retrieval`` - ranked, context-aware recall with conflict and staleness
                  detection and a prompt-safe context block.
* ``reflection`` - evaluates completed tasks, records lessons as hypotheses, and
                  only ever proposes security-sensitive changes (never applies
                  them; owner approval required).
* ``sandbox``   - resource-bounded code execution (subprocess + rlimits).
* ``agent_loop``- a real plan -> tool -> policy -> execute -> verify loop.
* ``skills``    - run a skill through the tools it declares, policy-checked.
* ``tasks``     - durable task state and execution history.
* ``identity``  - provider/model/limit reporting read from runtime config.
* ``identity_registry`` - verifiable agent identities (id, role, owner,
                  provider/model, parent, status, tool grant) with fail-closed
                  verification, revocation and cascade.
* ``credentials`` - short-lived, revocable agent credentials (hash-only storage).
* ``boundaries`` - least-privilege gate: canonical policy AND the agent's grant.
* ``trust``     - evidence-based trust levels; never a permission.
* ``policy``    - fail-closed authorization for privileged operations.
* ``audit``     - append-only log of allowed and denied tool requests.

Nothing here grants itself permission, touches secrets, deploys, or writes to
main. Privileged operations require an explicit owner authorization.
"""
