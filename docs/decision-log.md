# Decision log

## 2026-09-13 — Shared contracts use stdlib dataclasses

- **Decision:** Use frozen, slotted dataclasses with explicit `to_dict()` JSON
  serialization and lightweight validation; keep runtime dependencies empty.
- **Why:** Offline/mock execution must work without a paid service, and contracts
  should not leak provider-specific types into analytics or outputs.
- **Alternatives:** Pydantic (richer validation but adds a runtime dependency) and
  untyped dictionaries (too easy to produce silent schema drift).
- **Trade-off:** Validation is intentionally focused on required fields and ISO
  dates; domain-specific checks remain in the quality layer.
- **Impact:** Workers can import stable contracts from
  `recruitment_intelligence.domain` while retaining unknown Airtable fields.

## 2026-09-14 — Preserve contract immutability and verify offline integration

- **Decision:** Keep `Serializable` as a lightweight mixin while using frozen,
  slotted dataclasses for concrete contracts; avoid adding mutable slots or
  provider-specific state to the shared domain layer.
- **Why:** The earlier serialization/slots adjustment preserves dataclass
  immutability and deterministic JSON output without changing worker-facing
  field names or adding runtime dependencies.
- **Decision:** Treat the offline CLI path backed by cached/fixture data and the
  mock provider as the integration gate before any optional live Airtable run.
- **Why:** It gives a reproducible end-to-end check (ingestion → normalization →
  quality → analytics → findings/briefing) when no Gemini credentials are
  available, while keeping external systems read-only.
- **Trade-off:** Live-provider behavior remains an explicitly separate check and
  cannot be claimed from the offline run alone.
- **Impact:** Final handoff must include a clean-environment offline CLI run,
  passing tests/compile checks, evidence-bearing findings, and human-review
  language on candidate actions.

## 2026-09-15 — Verification and Completion of Milestones M1–M6

- **Decision:** Validate the entire offline pipeline across clean, dirty, and sparse fixtures; verify 100% test pass rate across all tiers (Tiers 1–5), complete objective questions Q1–Q5 deterministically, and enforce strict evidence attachment and human-review guards.
- **Why:** Ensures offline reproducibility, adherence to executive requirements, and zero risk of automated rejections or credential leaks.
- **Impact:** All 483 unit, integration, adversarial, and end-to-end tests pass cleanly. Full offline pipeline executes deterministically and renders structured multi-format output artifacts.

## 2026-09-15 — Founder release gate

- **Decision:** Make `recruitment-intelligence` the public console entry point,
  route it through the complete executive pipeline, and require a pinned
  `--as-of` date for reproducible release checks.
- **Why:** The founder should run the same quality, analytics, sensitivity,
  advisory, and rendering path that CI verifies.
- **Trade-off:** A live run without an explicit reference date keeps a current
  timestamp; release verification uses a temporary clean virtual environment
  and a fixed date.
- **Impact:** `scripts/release_check.py` now verifies installation, deterministic
  artifacts, required output files, and common secret markers before handoff.
