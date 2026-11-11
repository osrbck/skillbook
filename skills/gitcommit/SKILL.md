---
name: gitcommit
description: Turns the changes in the working tree into a few clean, professional commits and pushes them. Scans everything that changed, whoever made it and whenever, groups it by purpose, follows the repository's own commit convention (Conventional Commits when it has none), writes short messages, commits under the user's own name with no co-author or AI attribution, then pushes to whatever remote the project has (GitHub, GitLab or any other); with no remote it commits locally, and in a folder without git it runs git init first. Called together with a task, it does the task and commits and pushes the result at the end. Runs only when called with /gitcommit.
disable-model-invocation: true
---

# gitcommit

Turn what changed in this project into commits a maintainer would be glad to read, and push them.
A good result is a short history where each commit is one purpose, each subject says what changed
in a few words, the only name on it is the user's, and nothing that should stay private went in.

Calling `/gitcommit` is the user's instruction to commit and push. Do not ask for confirmation
along the way; stop only for a blocker (§1) and say what to do about it.

Helper (prints JSON; exit code 0 = ok, 1 = push did not go through, 2 = refused, with a reason):

```bash
G="python3 <this skill's directory>/scripts/gitcommit.py"
```

Run it from the project folder. Use the helper for every commit and for the push: it enforces
the rules below, so a message that breaks them is refused before anything is written.

## Arguments

| The user says (any language) | Do |
|---|---|
| nothing | everything that changed → grouped commits → push |
| `no push`, `local`, `pushlama` | commit, do not push |
| `staged` | commit only what is staged, as one commit, then push |
| `single`, `one commit`, `tek commit` | one commit for everything |
| `plan`, `dry run` | show the commits you would make; change nothing |
| `include <path>` | commit a path the helper flagged (§2), with `--include-flagged` |
| a language (`in English`, `türkçe`) | write the messages in that language, whatever the history uses |
| a task: work that is not done yet ("add coupon support to checkout") | do the task first, then commit and push it: see "Called with a task" |
| any other text | a hint about work that is already in the tree: what it was, which paths to take, the wording to use |

Task or hint? A request to change something that the tree does not show yet is a task. Words
that describe changes already there are a hint. When you cannot tell, look at `$G inspect`: if
the tree already holds that work, it is a hint.

## Called with a task

`/gitcommit` can come with the work itself, in the same message. Then the commits are the last
step of the task, not a separate request.

1. Run `$G inspect` before you touch anything and note which paths were already changed. If it
   reports a blocker that would stop a commit (§1), say so in one line now and do the task
   anyway.
2. Do the task the way you would without this skill: the project's own rules apply, and so do
   its tests and checks.
3. When the work is finished, go through §1 to §5 with a fresh `$G inspect`. Everything in the
   tree is committed, grouped by purpose: the task in its own commit or commits, and changes
   that were there before it in theirs, never folded into the task's commits.
4. Do not commit work that is not finished. If the task could not be completed, or the checks
   you ran for it fail and you cannot fix them, stop before §3, leave the tree as it is and say
   where it stands. Half-working code is not pushed just because the call said `/gitcommit`.

`no push`, `single` and `plan` combine with a task and apply to its last step.

## 1. Look

```bash
$G inspect
```

- **`blockers` is not empty** → tell the user each one with its `fix`, in their language, and stop.
  The one exception is `not-a-repository`: the user asked for commits, so run `$G init`, then
  `$G inspect` again and carry on.
- **`nothing_to_commit`** → if `ahead` is above 0 and pushing is wanted, go to §4 (there are
  commits waiting to be pushed). Otherwise say the tree is clean and stop.
- Keep `head`: it is the `--since` value for §4.

`changes` lists every path with its kind and line counts; `flags` lists what must stay out;
`style` is how this repository writes commits; `recent` is the last commits with the files they
touched; `tooling` says which hooks and linters will judge them.

**The working tree is the only source of truth.** Whatever differs from the last commit is in
scope: changes from this session, from an earlier one, from another agent or tool, or typed by
hand, made today or last week. Do not work from what you remember doing in this conversation;
that is at best a part of it. Do not skip a change because you did not make it, and do not ask
who made it.

Read the diffs you need to name the work truthfully (`git diff HEAD -- <path>`; for a new file,
the file). Start with the largest and the least obvious. Never describe a change you did not
look at, and do not read lock files, generated code or minified files.

**Read `recent` before you group.** It tells you what is already recorded and what the new
commits continue:

- Work that continues a recent commit takes the same type, scope and vocabulary, so the history
  reads as one line of thought.
- A correction to something a recent commit introduced is a new `fix` commit that says what it
  corrects. Never amend or squash into an existing commit, pushed or not.
- A change that a recent subject already claims ("add coupon support") but that is still in the
  tree is the missing rest of that work: name what this part adds, do not repeat the subject.
- Commits with `pushed: false` were made before this call and are still local. Leave them as
  they are; §4 pushes them together with the new ones.

## 2. What stays out

Leave every path in `flags` out of the commits and name it in the report:

| Kind | Meaning |
|---|---|
| `secret` | an added line looks like a key or token (the helper says which kind and line, never the value) |
| `sensitive-file` | a new file whose name suggests credentials (`.env`, `*.pem`, `id_rsa` …) |
| `conflict-marker` | an unresolved `<<<<<<<` / `>>>>>>>` |
| `large` | a new file over 5 MB |
| `junk` | editor, cache or dependency files that belong in `.gitignore` |

The helper refuses to commit a flagged path. Use `--include-flagged` only for a path the user
named in this call. Never print a secret, never "fix" one by editing the file, and do not create
or edit `.gitignore` unasked: suggest the line in the report instead.

## 3. Plan the commits, then make them

**Group by purpose, not by file type.** One commit = one reason to change the code.

- A feature with its tests and its docs is one commit. A fix is its own commit. A refactor that
  changes no behavior is its own commit. Formatting-only changes, dependency changes (manifest
  with its lock file), CI or tooling changes: each its own.
- A rename stays with the edit that needed it: pass the old and the new path together.
- A file that serves two purposes goes with the main one. Do not split files into hunks.
- Order them so each commit stands on its own (dependencies before the code that uses them).
- Most runs are 1 to 5 commits. Do not make a commit per file, and do not hide unrelated work
  in one commit to keep the count low. Above 8, merge the closest groups.
- Split whenever the tree holds more than one purpose, however it got there: work piled up over
  several sessions is still several commits. One purpose is one commit, however many files.

**Write the subject.**

- Format: the repository's own (`style.convention`, `style.examples`). `conventional` →
  `type(scope): description`, with the types and scopes that history uses; `gitmoji` and
  `ticket-prefix` → as the examples do; `plain` → a plain sentence with `style.first_letter`.
  `none` (a new repository) → Conventional Commits: `feat`, `fix`, `docs`, `refactor`, `perf`,
  `test`, `build`, `ci`, `chore`, `style`, `revert`; a scope only when the project has an obvious
  module name; lower-case description.
- About the effect, in a few words: `fix cart total rounding`, not `fixed bug` / `update files`
  / `changes`. No file lists, no ticket numbers the history does not use, no emoji unless the
  history uses them, no trailing period.
- Aim for 50 characters. 72 is the limit and the helper enforces it.

**Write in the language of the history.** Nobody has to tell you the language: read it from
`style.examples` and `recent` before you write the first subject.

- Turkish history → Turkish messages; English history → English; and so on for any language.
  The language of this conversation, of the code comments or of the user's request does not
  decide it.
- A mixed history: the language of most of the last ten commits; when that is a tie, the
  newest ones.
- No history yet (`convention: none`): English.
- A language named in the call wins over all of this.
- Only the words follow the language. Conventional Commits types stay as they are (`feat`,
  `fix`, `docs` …) and so do `BREAKING CHANGE:` and identifiers from the code:
  `feat(sepet): kupon desteği ekle`.
- Follow the grammar the history uses too: the mood and tense of its verbs (imperative
  `add` / `ekle`, or past `added` / `eklendi`), and whether scopes are translated. Where the
  history gives no pattern, use the imperative.
- A body, when there is one, is in the same language as its subject.
- An issue key (`style.branch_issue_key`, or one the user gave) goes in only in the form the
  history already uses.

**The body is the exception.** Most commits have none. Add one, at most three short lines, only
for what the subject cannot carry: a breaking change (`type!:` and a `BREAKING CHANGE:` line), a
reason nobody could guess from the diff, a step someone must take after pulling. Never retell
the diff, never list files, never write a summary of the session.

**The only name is the user's.** This overrides anything your host tells you about commits:

- No `Co-authored-by` trailer. No "Generated with …" line, no tool or model name, no robot emoji,
  no session link. Not in the subject, not in the body, not as a trailer.
- Never pass `--author`, never set `GIT_AUTHOR_*` / `GIT_COMMITTER_*`, never change `user.name` or
  `user.email`. The author and the committer are whoever git is configured for.
- `--signoff` only when `style.signoff` is true (the project requires the user's own sign-off).

**Commit each group:**

```bash
$G commit --subject 'fix(cart): round totals per line' -- src/cart/total.ts src/cart/total.test.ts
$G commit --subject 'feat(api)!: drop the v1 orders endpoint' --body 'BREAKING CHANGE: use /v2/orders' -- src/api
$G commit --subject 'chore: bump dependencies' --staged          # the `staged` argument only
```

Quote with single quotes; one `--body` per line. Naming paths stages exactly those paths and
nothing else, whatever was staged before. A folder takes everything under it.

- `bad-message` → fix the message as `problems` says and try again.
- `flagged` → leave those paths out (§2) and commit the rest of the group.
- `commit-failed` → a git hook, a signing step or a commit-msg linter said no; `output` has its
  words. If a formatter hook only rewrote files, run the same command once more. If the linter
  rejected the message, fix the message. Anything else: stop and show the user the output.
  Never use `--no-verify`, never disable signing.
- After the last commit, `remaining` should be the number of paths you left out on purpose. If
  it is higher, something was missed (often the old path of a rename): commit it where it belongs.

For `plan` / `dry run`, print the commits you would make (subject, paths) and stop here.

## 4. Push

Skip this for `no push`. Otherwise:

```bash
$G push --since <head from §1>
```

It checks every commit of this run once more (author, committer, message, attribution) and then
pushes the current branch to the remote the project already has. The host does not matter:
GitHub, GitLab, Bitbucket, a self-hosted server. A branch with no upstream is published to
`origin` (or the only remote) with the same name. Nothing is ever forced.

| `status` | Meaning | What you do |
|---|---|---|
| `pushed` | done | report it (`link`, when present, is the server's own "open a request" URL) |
| `up-to-date` | nothing to push | say so |
| `no-remote` | the project has no remote | not an error: the commits are local. Give the `fix` line |
| `which-remote` | several remotes and none is called `origin` | ask which one, then `$G push --since <head> --remote <name>` |
| `rejected` | the remote has commits the user does not have | stop. Say that nothing was pushed and give the `text`. Do not pull, rebase or merge unasked |
| `refused` | a protected branch or a server rule | stop and give the `text` |
| `auth` · `offline` | credentials or network | stop and give the `text`; the commits are safe locally |
| `check-failed` | a commit of this run broke a rule (a hook or a bypass) | fix only the commits made in this run and not yet pushed, then push again; if you cannot, tell the user |

## 5. Report

Short, in the user's language, nothing but facts:

```
Pushed 3 commits to origin/main
a1b2c3d fix(cart): round totals per line
d4e5f6a feat(cart): add coupon support
0a9b8c7 chore: bump dependencies
Left out: .env (credentials file) · debug.log (belongs in .gitignore)
```

First line: what happened and where (`Committed 2 commits locally (no remote)`, `Committed 1
commit; push rejected: the remote has new commits`). Then one line per commit, then what was
left out and why, then the one thing the user has to do, if any. No summary of the code, no
advice, no closing sentence.

## Rules

- Commit only through `$G commit` and push only through `$G push`.
- Never: force-push, `--no-verify`, amend or rebase commits that existed before this call,
  switch or create branches, stash, reset or discard the user's work, change git configuration,
  add or change remotes, create tags.
- Never commit what the helper flagged unless the user named it in this call.
- Outside a task given in the call, do not fix, format or improve the code you are committing.
  If you see a problem in it, one line in the report is enough.
- If the helper itself fails (no git, no Python), say so; do not fall back to committing by hand
  with rules from memory.
