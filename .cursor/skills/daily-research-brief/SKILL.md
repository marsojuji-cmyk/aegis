---
name: daily-research-brief
title: Research Brief & Action Triage
description: An intelligence brief for the work that matters today. It synthesizes high-signal research into concise, source-linked findings; separates verified facts from interpretation; surfaces deadlines and decisions; and converts noise into a prioritized action queue.
icon: book-open
color: blue
disable-model-invocation: true
notifications: true
---

# Daily Research Brief

Turn high-signal evidence into a short action-oriented briefing. Do not imply access to mail, calendar, documents, or live data unless it was actually retrieved in the current task.

## Workflow

1. Establish the date, timezone, decision horizon, and sources actually available.
2. Retrieve only primary or authoritative sources required for the question.
3. Deduplicate and prioritize by deadline, impact, reversibility, and attention cost.
4. Label items as verified, inferred, or unverified.

## Output template

### Today

List the 1–5 highest-value actions, each with why it matters and a source.

### Watch

List emerging issues or dependencies that do not yet require action.

### Unavailable

Name sources not retrieved rather than fabricating coverage.

### Next action

Give one concrete, user-controlled next move.

Never send messages, schedule events, or create external tasks without confirmation.

## Grok session setup

Select a Grok/xAI model in Cursor's model picker before starting. Pin this bot with Option+Enter after `/daily-research-brief`. If Grok is unavailable, continue with the selected model and state the limitation.
