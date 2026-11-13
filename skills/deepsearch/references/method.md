# Method

Read this once per run, before you write the plan. It is the part of the work only the
orchestrator can do.

## 1. Survey before you cut (medium and hard)

You cannot cut a question into good angles without knowing the terrain. Before you write the
plan, spend a few searches of your own (five to ten, no more) and write `survey.md` in the run
folder:

- the two or three sources everyone in the field starts from
- the schools of thought or competing answers, and who holds them
- what is settled, what is disputed, what nobody seems to have looked at (the gaps)
- the terms the field uses, where they differ from the user's words

This is a map, not research: no conclusions, and nothing from it goes into the final document
unless a researcher finds and cites it too. At `low`, or when you have no web tool, skip it.

## 2. The plan

- **Question and scope**: precise enough that two people would research the same thing. If the
  request is too vague for that, ask the user one question before you go on.
- **Angles**: cut the question so that the angles together cover it and no two overlap
  (mutually exclusive, collectively exhaustive). Cut along what a specialist would own (the
  evidence, the mechanism, the economics, the history, the practice in the field, the opposing
  school), not into "part 1, part 2". Aim an angle at each gap the survey found. With four or
  more researchers, one owns the strongest case *against* the expected answer.
- **An assignment a stranger could carry out.** Each researcher starts with a clean context and
  sees only the plan. Write for each: the **Angle** as an objective (what their notes must
  cover), **Not yours** (what the others cover: the boundary that prevents two researchers from
  running the same searches), **Sources** (where to start: which registries, journals, filings,
  datasets or documentation), and every constraint of the user's request that applies (period,
  region, version, currency). Vague assignments are the main cause of duplicated work and gaps.
- **Personas**: for each researcher, the acclaimed master researcher of the field their angle
  belongs to: the discipline, the speciality, what their work is known for. For each reviewer,
  the professor who wrote the standard book on the topic: their field and what they are strict
  about. A persona is a role and a standard of work. **Never use a real person's name**, and do
  not invent a name, a university or a prize either.
- **Hypothesis**: for each researcher, the answer you expect on that angle, why, and what
  evidence would refute it ("X, because Y; refuted if Z"). It is written before anyone searches,
  and the plan is copied as it stands when the research starts, so nobody can fit the question
  to the answer afterwards. A hypothesis that turns out wrong is a finding.
- **Questions**: three to six per researcher, each answerable and each worth answering.
- Write the plan in English; set `Language:` to the language of the user's request.

## 3. Notes: what the run knows

After each cycle, before you decide anything, read the digest the helper wrote (`digest.md`:
every researcher's takeaways, hypotheses and gaps, and the reviews' overall judgements, cut from
the documents without a model) and write `notes.md` in the run folder (rewrite it,
do not append). Four short sections:

```
## Established        what the reviewed research supports, each point with its source [researcher-n]
## Patterns           what explains the findings taken together; which hypotheses held and which fell
## Dead ends          what was looked at and led nowhere, and claims the review rejected: do not repeat
## Open questions     what is still unanswered, most important first
```

Not a copy of the findings: the test is that someone could write the answer's first paragraph
from this file alone. A later cycle's researchers are given it, and a session that resumes the
run starts from it.

## 4. Reflect: conclude or look again

Then choose one direction and record it with `reflect --direction … --reason '…'`:

| Direction | When | What happens |
|---|---|---|
| `conclude` | the question is answered as well as the sources allow, or what is open would not change the answer | you write the final document |
| `deepen` | a finding is solid but raises a follow-up the answer depends on | new researchers get sub-questions of that finding |
| `broaden` | the angles left a part of the question uncovered | new researchers get the missing angles |
| `pivot` | a key assumption of the plan failed, or the real question turned out to be another | you rewrite Question and Scope, new researchers start from there |

A new cycle adds one to four researchers (`--researchers N`, default 2) and one reviewer, and
you write their sections at the end of the plan. The degree caps the number of cycles (`low` 1,
`medium` 2, `hard` 3 by default), so a run cannot loop without end. Do not open a cycle to be
thorough: open one when you can name what it would change in the answer. Negative results count:
"the evidence does not exist" is an answer.

## 5. The final document

At medium and hard a writer agent writes it, in a clean context, from the reviewed notes, the
reviews and your `notes.md`; so what you put in the notes steers the document. At low you write
it yourself, following `roles/writer.md`. Either way `check` then compares it with what the team
cited and opens its links: a source nobody on the team cited, or a link that does not open, is
listed for you to fix.

## 6. Why it is built this way (cost)

Tokens are what a research run costs, and most of them are spent reading. So:

- the team is sized to the question, not to the degree: a researcher without an angle of their
  own only repeats searches
- researchers return dense notes (one fact per bullet with its link), not prose, and work to a
  budget of searches: the reviewer, the writer and you all read less
- breadth runs on cheaper models, judgement on the strongest: the reviewer is the one seat that
  is never downgraded
- only what the review sends back is revised, and a further cycle is opened only for a named gap
- what needs no model gets none: the plan's lock, the log, the digest you reflect on, the check
  that links open and that the document cites only what the team cited
- you read digests, not every document: your context is the most expensive one in the run
