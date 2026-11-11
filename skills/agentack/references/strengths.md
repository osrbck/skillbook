# Provider strengths

Tiers say how capable a model is. Strengths say what a provider is good *at*. Agentack keeps a
rating from 1 to 5 for each provider and each kind of work, and uses it to keep every provider on
the work it does well.

**Scale:** 5 leads the field · 4 strong · 3 adequate, or not yet rated · 2 weak: last resort ·
1 do not use.

Ratings describe a provider's model for that work **run headless through its own CLI**, because
that is how workers run. A model can score well in a chat benchmark and still be a weak worker if
its agent loop is unreliable.

## Ratings (reviewed 2026-11-11)

| Provider | decide | plan | review | visual | backend | frontend | test | mechanical |
|---|---|---|---|---|---|---|---|---|
| Claude Code | 5 | 5 | 5 | 4 | 5 | 4 | 5 | 4 |
| Codex | 5 | 4 | 4 | 4 | 4 | 4 | 4 | 3 |
| Antigravity | 4 | 4 | 4 | 5 | 2 | 2 | 2 | 2 |
| Cursor | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 |
| Kiro | 3 | 3 | 3 | 3 | 3 | 3 | 3 | 3 |

Roles map to kinds of work: decider → decide · architect → plan · reviewer → review ·
backend (be-go, be-java …) → backend · frontend (fe-angular, fe-next, fs-next …) → frontend · qa → test ·
scout, contract-guard → mechanical · backend-architect → plan · designer → visual. `visual` is a specialty: the designer
always runs on the provider rated best at it, and a review can ask for it with `--skill visual`.

## How ratings are used

1. **Your provider order decides**, with corrections:
2. **Weak fits go last.** A provider rated 2 or lower for a kind of work is moved to the end of
   that role's chain. It does that work only when no better provider is selected or available,
   and the roster and the closing report say so (`weak_fit`).
3. **Review stays independent.** The reviewer starts on a different vendor than the builders,
   as long as that vendor is not weak at review.
4. **Specialties go to the best.** `dispatch --skill visual` sends a run to the provider rated
   highest for that skill, whatever the order.
5. **Setup shows the scorecard** and suggests an order, so the choice is yours and informed.

Change a rating with `setup --rate agy:backend=3`. A chain you set by hand
(`setup --role backend=agy,claude`) always wins.

## Evidence

Benchmarks move monthly and most numbers are vendor-reported, so ratings are deliberately coarse.
Each one below names what it rests on. "Inferred" means there is no direct benchmark.

**Claude Code** (Fable · Opus 5.5 · Sonnet 5.5 · Haiku 5.5)
- backend 5, test 5: Sonnet 5.5 leads Terminal-Bench 4.0 (70.6%); Opus 5.5 66.4%. Recommended for
  long agent runs, refactors, scoped fixes and test generation.
- plan 5, review 5: Opus 5.5 tops the Artificial Analysis index among generally available models
  (58). Review is inferred from that and from its use in CI review bots.
- frontend 4, visual 4: Fable is second in the Frontend Code Arena; build work runs on Sonnet.
- mechanical 4: Haiku 5.5 is the strongest small model on agentic work (Terminal-Bench 4.0 39.2%).

**Codex** (GPT-6 Astra · GPT-6.1 Sol · GPT-6 Luna)
- decide 5: Astra is level with the other frontier models on the intelligence index and leads
  FrontierSWE 2.
- plan 4, review 4: Astra plans and reviews (Sol only where an account has no Astra). It matches
  the frontier on the intelligence index but trails Claude on Terminal-Bench 4.0 (57.9%), so it
  is not rated 5.
- backend 4, test 4: Sol builds; it is the Codex default and reported "near" Astra on agentic
  coding, with no independent Terminal-Bench figure.
- frontend 4, visual 4: Astra leads the Frontend Code Arena, but build work runs on Sol.
- mechanical 3: Luna is cheap and scores well on DeepSWE (66.6%) but low on Terminal-Bench 4.0
  (16.4%): fine for rule-following batches, not for open-ended loops.

**Antigravity** (Gemini 4 Karbon · Argon · 3.1 Pro · 3.8 Flash)
- visual 5: native image, video and PDF input; Argon places near the top of SWE-bench Multimodal.
- decide 4, plan 4, review 4: Argon leads several reasoning and analysis boards (Vals index,
  DeepSWE 77.9%) and handles very long inputs well. Review is inferred from that.
- backend 2, frontend 2, test 2: Argon trails on terminal agent loops (Terminal-Bench 4.0 57%
  against 66–71% for Claude), reviewers find the Antigravity harness behind Claude Code and
  Codex, and the build tier runs on 3.1 Pro (SWE-bench Pro 46%).
- mechanical 2: 3.8 Flash scores 19% on Terminal-Bench 4.0.
- Flash-Lite class models are never used.
- Karbon (also written Carbon) is limited to selected partners at the time of review. Where an
  account has it, it takes the S4 seat.

**Cursor, Kiro:** 3 throughout. Composer and the Auto routers have no comparable public numbers;
rate them yourself after some use.

Sources (read 2026-11-11):
layer3labs.io/guides/gemini-4-argon-for-coding · morphllm.com/best-ai-model-for-coding ·
developersdigest.tech/blog/budget-ai-coding-models-compared-2026 ·
widelai.com/blog/gemini-4-carbon-vs-opus-5-5-gpt-6-astra-fable-5-1-argon

## Keeping this current

`RATINGS_REVIEWED` in `providers.py` carries the review date; `doctor` and `roster` point out when
it is more than 90 days old. To update: change the `ratings` of a provider in `providers.py`, this
table, the evidence line, and the date. A rating change needs a source or a described real run.
