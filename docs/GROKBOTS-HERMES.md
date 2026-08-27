# GrokBots + Hermes

## Assignment

| Application | Bots | Job |
| --- | --- | --- |
| Hermes | Conductor, Memory Steward, Evidence Arbiter, Workflow Closer | private context, policy, qualification, handoffs, and outcome records |
| Grok | Signal Scout, Market Mapper, Value-Case Drafter, Contrarian | public-signal research, candidate drafts, fit hypotheses, and challenge |

## Truth boundary

Grok may produce an opportunity candidate from public or explicitly supplied
evidence. Hermes alone may qualify it. A candidate remains a hypothesis until
the evidence record contains a URL, observed date, claim, organization, fit
hypothesis, and a concrete next verification step.

No bot may contact a person, publish, spend money, submit a form, change
permissions, or create an external record without explicit approval.

## Cognition

- **Micro:** current signal, evidence freshness, uncertainty, permission, and
  smallest next verification.
- **Meso:** campaign/open-loop state, duplicate candidates, dependencies, and
  active outcome.
- **Macro:** explicitly confirmed ICP/offer/constraints plus measured outcome
  calibration. It is never silently rewritten from a single candidate.

## Economics

`priority_score` ranks human review effort. It is intentionally labeled as an
estimate, not ROI. Production ROI requires observed accepted outcomes and
incremental acquisition/delivery cost evidence.

## First validation route

The proposed first offer is an **AI Continuity & Workflow Yield Diagnostic**
for knowledge-intensive teams already using multiple AI tools. It tests a
specific operational promise—less context loss, duplicate work, and unmeasured
AI workflow effort—before attempting a wider sales motion.

The `ingest_public_signals` adapter accepts only explicitly supplied public
HTTPS records. It creates no-contact hypotheses for Hermes qualification; it
does not scrape, discover contacts, or perform outreach. The pilot success
metric is **accepted diagnostic conversations per verified review hour**.

## Pilot evaluation gate

The first 20 candidates are reviewed twice against the same candidate IDs:
once using the current manual process and once with the governed Hermes/Grok
workflow. A human records acceptance for a future follow-up decision and review
minutes. The system may recommend a small, operator-approved outreach trial
only if the governed path preserves or improves acceptance and saves review
time. It never authorizes outreach itself.

## Operator experience

1. You select the active outcome: qualify opportunities for the diagnostic.
2. Grok receives public source records and creates no-contact hypotheses.
3. Hermes presents the evidence, freshness, disqualifiers, uncertainty, and
   one next verification—not a vague lead score.
4. You accept, reject, or request more evidence. Hermes records the decision
   and preserves the reason for future calibration.
5. After 20 matched reviews, Hermes reports quality and review-time change.
6. Only then does it prepare an outreach draft for your explicit approval.

## Review-minimizing claim validation

Grok's Claim Verifier gathers public evidence and counterevidence. Hermes then
checks it mechanically. A low-impact internal classification is automatically
accepted only with two fresh, independent supporting domains and no conflict.
Hermes sends only these exceptions to you: missing proof, stale sources,
contradictions, and medium/high-impact claims. External actions remain blocked.

## Data immune system

Hermes quarantines incomplete, stale, invalid, and duplicate evidence before it
can affect qualification or memory. It calculates a provisional source
reliability score from later verified outcomes, becoming calibrated only after
five outcomes. Circuit breakers pause a source or agent when its observed
rejection rate or cost per accepted result crosses the configured threshold.

## Evidence-to-yield runtime

`/v1/aegis/evidence-yield` is the rebuildable operational projection: active
outcome, evidence health, review queue, source reliability, paused circuits,
calibration state, and measured yield. `POST /v1/aegis/evidence-yield/govern`
admits/quarantines evidence and issues a Hermes decision; no endpoint authorizes
outreach. Later verified outcomes, including provider-observed cost only when a
request ID and source are supplied, are recorded through the outcome endpoint.

## Live-provider bootstrap

The local router can load an existing xAI key from the logged-in macOS user's
Keychain at every start. After creating a key in the xAI account console, run
`scripts/configure_xai_keychain.sh` locally. It asks for confirmation, accepts
the key through a hidden prompt, stores it as `aegis.xai.api-key`, reloads the
router, and never prints the secret. Account creation, key issuance, terms, and
billing remain the operator's action.

## Bounded autoscan

AEGIS 1.3.1 starts an idle scheduler with the router. It remains paused until
the operator resumes it and approves individual local paths or HTTPS sources.
Local files are fingerprinted and parsed locally; hidden files, credential
paths, symlinks, unsupported types, and oversized items are excluded. Ordinary
documents enter review, while structured JSON evidence can enter Hermes claim
governance after the 20-case calibration gate passes.

`GET /v1/aegis/autoscan` reports scheduler state, approved sources, scan health,
observed cost, calibration, and quarantine status. The control endpoint supports
pause/resume, source approval/removal, one bounded scan, quarantine enable or
disable, evidence restoration, and explicit source-circuit recovery. Public
fetches require passing calibration and a positive daily cost ceiling. All
controls keep outbound action unauthorized.
