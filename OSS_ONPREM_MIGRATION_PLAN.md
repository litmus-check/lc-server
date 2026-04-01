# OSS On-Prem Migration Plan (Frontend/Agent + Service Integration)

## Goal
Transition the current SaaS-oriented QA automation platform into an open-source, on-prem deployable product for first public GitHub launch.

This plan focuses on this repository and repo-level productization work. A separate backend plan can expand backend-only internals in detail.

## Current SaaS Coupling Found In Repo
- Multi-tenant organization scoping is embedded across core models and APIs (`org_id` on `Suite`, `Credits`, `Subscription`, org-based auth checks).
- SaaS billing and quota logic is wired to Lemon Squeezy and per-org credits (`service_subscription`, `utils_lemon_squeezy`, `service_credits`, `reset_credits` cron).
- External identity and tenancy dependencies exist (`security/auth.py` uses `OCR_BASE_URL`, Clerk/JWKS, `DEFAULT_ORG_ID` fallback behavior).
- Cloud-specific runtime/deployment assumptions are present (Azure queue/AKS helpers, gateway YAML pinned to Azure image and namespace).
- OSS readiness artifacts are missing at root (`LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, docs folder).

## Principles For OSS + On-Prem Edition
- Single-tenant by default: one installation equals one tenant boundary.
- Security-by-default: explicit auth modes, secure secrets handling, least privilege.
- Reproducible deployment: local Docker Compose first, Kubernetes second, clear environment contract.
- No SaaS lock-in in core runtime: optional adapters for cloud/billing integrations.
- Launch with stable defaults, then add extension points.

## Phase 1 (Critical For First Launch)
These are blockers and must land before public OSS release.

1. Single-tenant mode and data model simplification
- Introduce an installation-scoped tenant model (`instance` or implicit singleton) and stop requiring runtime `org_id` input for core flows.
- Refactor auth context to installation user scope, not cross-org scope.
- Remove or gate org-level authorization branches that assume multiple organizations in one deployment.
- Provide DB migration scripts to preserve existing SaaS data by mapping one selected `org_id` to the default on-prem instance.

2. Remove SaaS billing/credits from critical path
- Remove or feature-flag APIs and services tied to subscriptions, checkout, and plan management.
- Replace hard credit enforcement with optional local quotas/rate limits controlled via config.
- Disable Lemon Squeezy webhook processing and related cron jobs by default.

3. Decouple from external identity dependency
- Replace mandatory `OCR_BASE_URL` user lookup with pluggable auth providers.
- Ship at least one on-prem first-party mode (local admin bootstrap + API tokens).
- Keep OIDC/JWKS integration optional and clearly documented.

4. On-prem deployment baseline
- Provide a root-level Docker Compose that runs required services with minimal setup.
- Remove hardcoded cloud image references and namespace assumptions from deployment manifests.
- Add `.env.example` with every required variable and secure defaults guidance.

5. OSS legal and governance essentials
- Add `LICENSE`, `README` overhaul, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`.
- Add issue/PR templates and a minimal CI workflow for tests/lint.

## Phase 2: Product Hardening For Self-Hosted Operators
1. AuthN/AuthZ hardening
- Enforce token audience/issuer verification paths; avoid permissive bypasses.
- Remove broad role bypasses and implement explicit permission checks per operation.
- Add API key rotation and expiration support.

2. Secrets and sensitive data controls
- Eliminate plaintext storage for sensitive suite credentials; use encrypted-at-rest fields or external secret references.
- Document secret injection patterns for Docker/Kubernetes.
- Add startup checks that fail fast when required secrets are missing.

3. Runtime isolation and safety
- Review container execution boundaries for test runs and browser agents.
- Add configurable resource limits and timeout ceilings for worker processes.
- Document safe defaults for untrusted test execution in enterprise environments.

4. Observability baseline
- Add structured logs with correlation IDs.
- Standardize health/readiness endpoints and startup diagnostics.
- Make error reporting providers optional (Sentry off by default unless configured).

## Phase 3: Multi-Tenancy Removal Workstream (Deep Cleanup)
1. API surface cleanup
- Deprecate org-scoped routes and payload fields not needed in on-prem single-tenant mode.
- Remove invite/team-size SaaS workflow coupling from runtime APIs.
- Provide a compatibility window with deprecation warnings if needed.

2. Domain model cleanup
- Remove or repurpose `Plan`, `Subscription`, and org queue config entities where not relevant for OSS.
- Convert org-specific queue/rate-limit settings to installation-level config.
- Update serialization and service methods to stop returning org metadata by default.

3. Integration boundary cleanup
- Move SaaS-only integrations behind optional adapters/extensions.
- Keep core test generation, triage, healing, and execution flows provider-agnostic.

## Phase 4: Deployment and Documentation Completion
1. Deployment docs (must be complete for launch)
- `docs/deployment/docker-compose.md`: prerequisite matrix, ports, persistent volumes, backup/restore.
- `docs/deployment/kubernetes.md`: manifests, secrets, ingress, scaling, upgrades, rollbacks.
- `docs/configuration/env-vars.md`: required/optional vars, defaults, security notes.
- `docs/operations/troubleshooting.md`: common failure modes, diagnostics, log locations.

2. Upgrade and migration docs
- `docs/migrations/saas-to-onprem.md`: schema migration and data mapping steps.
- Release notes template with breaking changes and config diffs.

3. Reference architecture
- Single-node developer setup.
- Production-grade on-prem topology with external DB/Redis and recommended networking.

## Phase 5: OSS Launch Readiness
1. Quality gates
- Minimum smoke/integration tests for core user journeys: create suite, run tests, triage/heal flows.
- Security checks in CI (dependency scan + static checks).
- Reproducible release artifact generation and checksum publication.

2. Community readiness
- Public roadmap and support model (issues/discussions/response expectations).
- Maintainer guidelines and triage process.
- Versioning policy and deprecation policy.

## Suggested Execution Order (8-12 Weeks)
1. Weeks 1-2: Phase 1 design freeze + migration scaffolding.
2. Weeks 3-5: Implement single-tenant/auth/billing decoupling and deployment baseline.
3. Weeks 6-7: Security hardening and runtime safety.
4. Weeks 8-9: Documentation completion and migration rehearsal.
5. Weeks 10-12: Release candidate, security review, public launch.

## Risks and Mitigations
- Breaking existing SaaS workflows during extraction.
  - Mitigation: feature flags and compatibility shims during transition.
- Hidden org-level assumptions in business logic.
  - Mitigation: org-field audit and automated tests around authorization and data filtering.
- On-prem security misconfiguration by adopters.
  - Mitigation: secure-by-default configs and explicit hardening checklist in docs.
- Operational burden after OSS launch.
  - Mitigation: clear support boundaries and documented troubleshooting paths.

## Acceptance Criteria For First OSS Launch
- Core workflows run in single-tenant mode without org provisioning dependencies.
- SaaS billing/subscription flows are removed from required runtime path.
- Default on-prem deployment works from documented steps on a clean machine.
- Security docs and OSS governance docs are present and actionable.
- CI validates lint/tests for primary code paths and publishes release artifacts.

