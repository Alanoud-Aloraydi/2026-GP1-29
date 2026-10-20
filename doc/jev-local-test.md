# Jev-only judging

Jev is the only model judge. The old generative judge, response parser, majority voting,
and chat-judge system prompts have been removed. The existing synthetic-disclosure scorer
remains deterministic and requires no model. Target LLM connections are unchanged.

## Configuration

Set TYPESAFE_API_KEY securely in the same terminal that launches the CLI or worker.
Alternatively store it locally in the ignored .env file; never commit that file.
Only these judge settings are read:

- TYPESAFE_API_KEY (required)
- HARASS_JEV_MODEL (default jev-1.13.0)
- HARASS_JEV_MIN_CONFIDENCE (default 0.8)

No provider switch, old model endpoint, temperature, completion budget or vote count is used.
Restart workers after changing configuration. API and worker need matching configuration.

## Test

PowerShell:

```powershell
.\.venv\Scripts\python.exe tools/jev_check.py
```

This sends five small paid checks through the same builders used in production. It does
not call the target LLM. NEEDS_REVIEW is a normal abstention; MISMATCH is an accepted
judgment that disagrees with the example label. TECHNICAL_ERROR remains a technical failure.
This is an integration test, not an Arabic/dialect safety benchmark.

## Review and evidence

Below-threshold decisions retain their proposed label, probabilities, confidence and model
in Score metadata and the attempt request audit. They receive a NEEDS_REVIEW score marker,
not a response-category UNC: uncertainty about a judgment does not mean the target failed
to understand the question. PyRIT requires a boolean placeholder, but the executor rejects
that placeholder as a verdict and marks the outcome needs_review=true, with error text.

Review outcomes retain the target response. They are unscored, excluded from safety-rate
denominators and controller updates, and do not increment the consecutive technical-failure
counter. They do consume the submitted attempt budget. The JSON export and durable journal
retain needs_review; old records default to false. Existing UI displays them as unscored;
this change does not add a new human-review queue or dedicated UI badge.

0.8 is an uncalibrated experimental threshold, not an accuracy guarantee. Validate the judge
against independent human labels covering both axes and Arabic varieties. No generated
rationale is available; the stored rationale explicitly states this limitation.

Each scorer makes one TypeSafe request; ordinary adversarial attempts can need two calls.
HTTP errors and timeouts remain failures. There is no generative fallback.

## Windows dependency

Windows/Python 3.13 pins pandas 2.2.3, which imported successfully on the test laptop with
Smart App Control enabled; this does not guarantee the same trust decision on every PC.
No security controls are disabled. Other platforms keep the existing dependency lock.

## Scope of validation

Offline tests use mocked TypeSafe HTTP replies and a scripted target. They cover the real
PyRIT execution, score persistence, review evidence, metrics exclusion and provider removal.
Live accuracy and end-to-end execution against a real target require separate validation.
