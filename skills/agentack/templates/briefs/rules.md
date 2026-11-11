# Brief · <role>

<!-- Style: rules. For mechanical-class models (Haiku, GPT-6 Luna, Gemini 3.8 Flash). An exact rule set
     with input/output examples, a small batch, and a result the conductor can spot-check.
     Keep one brief to about 10 files or 25 items; split bigger jobs into several briefs. -->

**Job:** <one sentence, one kind of change or one question>

## Rules (apply exactly; do not add, skip or reinterpret)
1. <rule>
2. <rule>
3. If an item does not match any rule, leave it unchanged and list it under "Skipped".

## Examples
Input:
```
<a real before-case from this repo>
```
Output:
```
<the exact after-case>
```
Not to be changed:
```
<a look-alike that must stay as it is, and why>
```

## This batch
- `<file or item 1>`
- `<file or item 2>`
(nothing outside this list)

## Check
Run `<command>` when done. Expected: <result>

## Output (exactly this shape)
```
Done: <n> items
- <item>: <what changed, one line>
Skipped: <item + which rule did not fit>
Check: <pass/fail + the relevant line>
```
