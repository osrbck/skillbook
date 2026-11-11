# Brief · <role>

<!-- Style: explicit. For models that follow instructions literally (GPT-6.1 Sol, "auto" routers).
     Spell out every step in order. Leave nothing implicit: no "as usual", no "similar to X". -->

**Task:** <one sentence>

## Before you start
- Working directory: `<path>` · Branch state: do not commit, stash or reset
- Files you will change: `<path>`, `<path>` (no others)
- Files to read first, in this order: `<path>` (what to look for: <...>), `<path>` (<...>)
- Contract: `<contract file>`, operation `<...>` · generated types at `<path>`

## Steps (do them in order; each has a visible result)
1. <action> in `<file>`: <exactly what to add or change>. Result: <what exists afterwards>
2. <action> in `<file>`: <...>. Result: <...>
3. Add tests in `<test file>` covering: <case 1>, <case 2>, <error case>
4. Run `<lint command>`. Expected: no errors
5. Run `<test command>`. Expected: all pass

## Rules
- If a step cannot be done as written, stop at that step and report why. Do not improvise around it.
- Do not touch: other modules or services, contract files, generated code, files not listed above.
- Conventions to follow: <naming, error handling, the existing file to imitate: `<path>`>

## Done when
- [ ] <behavior 1, phrased as something a test or command shows>
- [ ] <behavior 2>
- [ ] Steps 4 and 5 gave the expected result

## Output (exactly these sections)
1. Changed files (path + one line each)
2. Result of each command in steps 4–5
3. Assumptions you had to make
4. Anything you could not do, with the step number
