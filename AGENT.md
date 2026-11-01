# AGENT.md — Autonomous Agent Operating Guide & Custom ArtBOT Engineering Contract

This file governs autonomous coding agents (Hermes Agent, Claude Code, Codex) and engineers working in or deploying from the `marketing-bot` repository. `AGENTS.md` is a symlink to this file so Hermes loads it automatically.

`marketing-bot` is a **Custom ArtBOT** built on top of the reusable upstream [`InnodataAgenticResearch/artbot`](https://github.com/InnodataAgenticResearch/artbot) foundation (`v0.2.0-artbot`) and structured as a [`Dannyzen/eliezer-weekly-roundup-public`](https://github.com/Dannyzen/eliezer-weekly-roundup-public)-style category-first intelligence repository for **Innodata (`NASDAQ: INOD`) PR, Competitive Intelligence, and Enterprise AI Strategy**.

---

## 1. Read First

- `README.md`: Dynamic daily roundup landing page, category navigation (`BrandAndPositioning/`, `CompetitiveIntelligence/`, `MarketTrends/`, `roundups/`), Microsoft Teams Workflows webhook setup, and runtime commands.
- `UPSTREAM_ARTBOT.json` & `checks/api_contract.star`: Upstream ArtBOT version pin (`v0.2.0-artbot`, commit `b3fbc3b87fd7b1e561f1d78f179ba31dcf64cb81`) and the public API surface lock enforced by `shac`.
- `config/marketing_strategy.json`: Innodata's 6-Pillar Full-Stack Engineering Taxonomy, 5 Proprietary Accelerators (`Beacon`, `Goldengate`, `ai.Prep`, `Automated Red Teaming`, `Domain Evaluation Benchmarks`), GTM Wedge (`Solving Pilot Purgatory via Accelerator-Led De-Risking & FDE`), 5 Competitive Cohorts, and 17+ Agility PR Saved Topic IDs.
- `config/PERSONA.md`: Marketing-Bot's executive PR & market intelligence identity (`@marketing-bot` / `@pr-bot`), mention-only discipline, and `STANDARDS.md`.
- `checks/policy.star` & `shac.star`: Machine-enforced security, secret-hygiene, API-contract, and coding-standard gates.

---

## 2. How an Agent Sets Up or Clones an ArtBOT Instance

When asked by a human to provision `marketing-bot` (or another custom Teams webhook bot extending upstream `artbot`) on a machine:

1. **Verify Upstream ArtBOT Pin (`UPSTREAM_ARTBOT.json` & `checks/api_contract.star`):**
   - `marketing-bot` pins upstream `https://github.com/InnodataAgenticResearch/artbot` at tag `v0.2.0-artbot` (`b3fbc3b87fd7b1e561f1d78f179ba31dcf64cb81`) in `UPSTREAM_ARTBOT.json`.
   - Custom ArtBOT code under `src/marketing_bot/` must import **only** from the top-level public `artbot` package (`from artbot import ArtbotConfig, HttpTransport, ...`) listed in `public_api_allowlist`.
   - `checks/api_contract.star` (`no_private_artbot_apis` and `upstream_artbot_pin_valid`) blocks any import of internal submodules (`from artbot.<submodule> import ...`) or private underscore-prefixed symbols (`from artbot import _...`), guaranteeing that upgrading to a newer tagged `artbot` release never breaks `marketing-bot`.
   - Verify the pin at any time with:
     ```bash
     just upstream-status
     ```

2. **Create the Hermes Profile:**
   ```bash
   hermes profile create --clone marketing-bot \
     --description "Marketing-Bot (Custom ArtBOT) for Innodata PR, Competitive Intelligence, and Daily Roundups"
   cp config/SOUL.md ~/.hermes/profiles/marketing-bot/SOUL.md
   ```

3. **Configure Environment Credentials (`~/.hermes/profiles/marketing-bot/.env`):**
   - Never hardcode webhook URLs, bearer tokens, or Agility PR API keys in source files, tests, or git-tracked configs.
   - Copy `config/env.example` to `~/.hermes/profiles/marketing-bot/.env` (`chmod 600`).
   - Populate `TEAMS_WEBHOOK_URL`, `AGILITYPR_API_KEY`, `AGILITY_MCP_URL` (`https://apigateway.agilitypr.com/api/mcp`), and generate a unique `API_SERVER_KEY`:
     ```bash
     python3 -c "import secrets; print('API_SERVER_KEY=' + secrets.token_urlsafe(32))" >> ~/.hermes/profiles/marketing-bot/.env
     ```

4. **Query Agility PR MCP & Update Daily Roundups:**
   - `marketing-bot` connects to the **Agility PR MCP Server** (`https://apigateway.agilitypr.com/api/mcp`) and the **Agility PR Media Intelligence REST API** (`https://mediaintelligence.agilitypr.com/api/v1` with header `apiKey: <AGILITYPR_API_KEY>`) across Innodata's 49 Saved Topics (`1. B&R - Innodata` through `49. AI Topic Trends - ...`).
   - Generate or refresh the daily roundup (`roundups/YYYY-MM-DD.md`) and verify category links with:
     ```bash
     just roundup
     # Or for a specific date:
     just roundup 2026-11-01
     ```
   - When adding or updating evergreen intelligence notes, place them in the three `eliezer-weekly-roundup-public`-style category directories (`BrandAndPositioning/`, `CompetitiveIntelligence/`, `MarketTrends/`) and link them from both the category `README.md` and the root `README.md`.

5. **Install and Manage the `systemd --user` Service (`marketingbot-teams-bridge.service`):**
   ```bash
   mkdir -p ~/.config/systemd/user
   cp systemd/marketingbot-teams-bridge.service ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable --now marketingbot-teams-bridge.service
   systemctl --user status marketingbot-teams-bridge.service --no-pager
   ```

---

## 3. Interaction & Behavioral Invariants

1. **Speak Only When Spoken To (`@marketing-bot`, `@pr-bot`, or `@artbot`):**
   - Mention detection checks for case-insensitive `@marketing-bot\b`, `@pr-bot\b`, or `@artbot\b` triggers.
   - Never post an outbound Teams webhook message for unmentioned channel chatter.
2. **Read Everything & Keep Notes Silently:**
   - Unmentioned channel messages are forwarded to the Hermes Gateway session silently (`[SILENT]`) so Marketing-Bot retains full situational awareness of campaign discussions, analyst inquiries, and competitor sightings.
3. **Always Reply In-Thread (Never Start New Root Chats):**
   - Outbound Adaptive Card payloads must attach `replyToId` and `messageId` whenever a parent `message_id` is present.
4. **Ground Every Claim in Primary Sources & Strategy Taxonomy:**
   - Every daily roundup and battlecard response must map media signals to Innodata's 6 Engineering Pillars, 5 Proprietary Accelerators, and Accelerator-Led FDE + Agent Reliability Engineering (ARE) GTM wedge.
5. **Never Commit Secrets or Hardcoded Webhook URLs:**
   - `checks/policy.star` blocks `.env`, `.pem`, `.key`, private keys, `.beads/`, and any hardcoded live Power Platform webhook URLs.

---

## 4. Engineering Standards (`STANDARDS.md`)

Every change to this repository must adhere to the following non-negotiable rules:

1. **100% Deterministic Line & Branch Coverage:**
   - Enforced by `pytest -p randomly --cov=marketing_bot --cov-branch --cov-report=term-missing --cov-fail-under=100`.
   - Never lower `fail_under = 100`.
   - Every `# pragma: no cover` exclusion must have an inline `- <reason>` comment on the same line (e.g. `# pragma: no cover - CLI entrypoint`), enforced by `no_unexplained_pragma_or_disable` in `checks/policy.star`.
2. **Pure Dependency Injection (No `unittest.mock`):**
   - Inject `HttpTransport` (`FakeHttpTransport` in tests, `UrllibHttpTransport` in production), `environ` mappings, `Path` objects (`tmp_path`), and `io.StringIO` streams.
   - Importing `unittest.mock` inside `tests/` is forbidden by `no_unittest_mock_in_tests` in `checks/policy.star`.
   - The test suite must pass in random order (`-p randomly`) twice in a row.
3. **Public ArtBOT API Contract Lock (`checks/api_contract.star`):**
   - Never import private `artbot._*` symbols or internal `artbot.<submodule>` modules. Only import from top-level `artbot` symbols listed in `UPSTREAM_ARTBOT.json`.
4. **Zero Linter or Type Warnings:**
   - `ruff format --check .`
   - `ruff check .`
   - `mypy --strict src tests`
5. **No Runtime Heap-Limit Band-Aids (`--max-old-space-size`):**
   - Never paper over memory leaks or OOM crashes by inflating runtime heap limits (`NODE_OPTIONS=--max-old-space-size=...`), enforced by `no_heap_limit_bandaids` in `checks/policy.star`.
6. **Shac Policy & Starlark Tests:**
   - Every policy rule in `checks/policy.star` and `checks/api_contract.star` has a corresponding unit test in `checks/policy_test.star`.
   - Run `shac test` and `shac check --all` before every commit.

---

## 5. Verification (`just check`)

Before claiming any task is complete or pushing to `origin`, run:

```bash
just check
```

If running on a Nix-enabled host without global Python tools on `PATH`, run inside the repo's dev shell:

```bash
nix develop -c just check
```

Both local `just check` and `.github/workflows/ci.yml` execute the exact same sequence:
1. `ruff format --check .`
2. `ruff check .`
3. `mypy --strict src tests`
4. `shac test`
5. `shac check --all`
6. `pytest` (run twice in random order with `100%` line and branch coverage gate).
