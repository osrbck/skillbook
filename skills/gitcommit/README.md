# gitcommit

**Turn your working tree into clean commits and push them, under your name only, for a handful
of tokens.** `/gitcommit` runs one command. A helper scans what changed, the smallest current
model of the provider you are using writes the commit messages, and the result is pushed to
whatever server the project is connected to. The agent you are talking to only prints the
report.

> 🇹🇷 Türkçe: [README.tr.md](README.tr.md)

```
/gitcommit
```

```
Pushed 3 commits to origin/main
a1b2c3d fix(cart): round totals per line
d4e5f6a feat(cart): add coupon support
0a9b8c7 chore: bump dependencies
Left out: .env (credentials file) · debug.log (belongs in .gitignore)
```

Works in **Claude Code, Codex, Antigravity and Kiro**.

## What it does

- **The whole working tree, whoever changed it.** Everything that differs from the last commit
  is in scope: work from this session, an earlier one, another agent, or typed by hand.
- **One purpose per commit.** A feature goes in with its tests and docs; a fix, a refactor, a
  dependency bump or a formatting pass each get their own. Work that piled up over several
  sessions is split into the commits it should have been.
- **Your convention and your language.** It reads the recent history and continues it:
  Conventional Commits with your types and scopes, gitmoji, ticket prefixes or plain sentences;
  Turkish history gets Turkish messages, English gets English. A new repository gets
  Conventional Commits in English.
- **Short messages.** A subject of about 50 characters (72 at most), no period. No body unless
  there is a breaking change or a reason nobody could guess.
- **Only your name.** No `Co-authored-by`, no "Generated with …", no tool or model name. Author
  and committer are whoever `git config` says you are.
- **Nothing private goes in, and nothing private is shown to a model.** Keys and tokens on added
  lines, new credential files (`.env`, `*.pem`, `id_rsa` …), unresolved conflict markers, new
  files over 5 MB and junk (`node_modules`, `.DS_Store`, caches) are taken out before the model
  sees anything, left out of the commits and listed in the report.
- **Any server.** A plain `git push` to the remote the project already has: GitHub, GitLab,
  Bitbucket, self-hosted. With no remote it commits locally; in a folder without git it runs
  `git init` first. It never opens a password window on its own.
- **Task and commit in one call.** `/gitcommit add coupon support to checkout` does the work
  with the model you chose, then commits and pushes it with the small one.

## Few tokens, on the smallest current model

Writing commit messages does not need the model you do your real work with. The priorities are
**task, context, tokens**: the commits must be right, the model must see enough to name them
truthfully, and only then is everything else cut.

| You are in | The plan is written by |
|---|---|
| Claude Code | the current Haiku (the `haiku` alias) |
| Codex | the newest Luna your account lists (else nano / mini) |
| Antigravity | the newest Flash-Lite your account lists, else Flash at its lightest effort |
| Kiro | the newest Haiku-class model it lists, else its lowest-rate model, else Auto |

The model is found by asking the provider's own CLI for its model list, so a new release is
picked up without an update here. Override it with `GITCOMMIT_MODEL=<model>`.

- **Your main model** reads a skill file of under 4 KB, runs one command and prints a few lines.
  It does not read diffs.
- **The small model** is called once, through the provider's CLI, with no tools, no permissions
  and an empty folder. It gets the rules, the recent history, the list of changes and a bounded
  diff (lock files, generated and binary files by name only), and answers with a JSON plan.
- **The helper** does the rest in plain code: it checks the plan (every path exactly once, the
  message rules), sends it back once if it is wrong, commits, pushes and writes the report.
- If the provider's CLI is missing or fails, your main model writes the plan from the same
  brief, so the job is always finished.

## What it never does

Force-push · skip hooks (`--no-verify`) · rewrite commits that existed before the call · switch
branches, stash or discard your work · change git configuration or remotes · pull, rebase or
merge on its own · ask for a password or token. If the remote has commits you do not have, it
stops and says so; your commits stay local.

## Install

Requirements: git, Python 3.8+, and one of Claude Code, Codex, Antigravity or Kiro, in
the desktop app, the IDE or the CLI. The provider's CLI only has to be installed: the small model
is reached through it in the background, and without it the agent you called writes the plan
itself. macOS, Linux and WSL.

```bash
git clone https://github.com/osrbck/skillbook.git ~/skillbook
~/skillbook/install.sh gitcommit          # Claude Code
~/skillbook/install.sh gitcommit --codex  # Codex (also: --agy for Antigravity, --kiro for Kiro)
~/skillbook/install.sh gitcommit --all    # all four
```

The installer shows the name and email your commits will carry. Update with
`cd ~/skillbook && git pull && ./install.sh gitcommit`, remove with
`./install.sh gitcommit --uninstall`.

## Usage

```
/gitcommit                      everything that changed → commits → push
/gitcommit no push              commit only
/gitcommit staged               only what you staged, as one commit
/gitcommit single               one commit for everything
/gitcommit plan                 show the commits it would make; change nothing
/gitcommit include .env.test    commit a path that was left out
/gitcommit in English           this language, whatever the history uses
/gitcommit ask                  let your system's password window ask you when a sign-in is missing
/gitcommit the coupon feature   a hint about work that is already in the tree
/gitcommit add coupon support to checkout
                                a task: do the work, then commit and push it
```

It runs only when you call it, asks nothing along the way, and says nothing but the report. It
stops only when something blocks a commit: no `user.name` / `user.email`, a merge or rebase in
progress, unresolved conflicts, a detached HEAD.

## Messages

| Repository history | Subject it writes |
|---|---|
| Conventional Commits | `fix(cart): round totals per line` (your types and scopes) |
| Turkish history | `feat(sepet): kupon desteği ekle` |
| gitmoji | as your history does |
| ticket prefix | `SHOP-42 Round totals per line` (as your history does) |
| plain sentences | `Round cart totals per line` |
| none yet | Conventional Commits, in English |

`Signed-off-by` is added, as you, only in repositories whose history uses it.

## When the server wants a sign-in

An agent's shell is not always signed in where you are. A project can be connected in your IDE
or a desktop app and still have no sign-in for plain `git push`. In that case git would fall
back to your desktop's password program and open a username and password window in the middle of
the run. gitcommit does not let that happen. The commits are made, the push stops, and you get
the reason and your options:

```
Committed 4 commits; push stopped: git has no saved sign-in for github.com here
1. Use the SSH key this machine already has for github.com: git remote set-url origin git@github.com:you/app.git
2. Let your desktop's password window ask you: call the skill again with `ask`
3. Save a sign-in for git yourself: run `git push` once in your own terminal
```

What you set up for git on purpose is always used as it is: credential helpers, `GIT_ASKPASS`,
`core.askPass`, SSH keys and agents.

## Claude Code and the co-author line

Claude Code adds a `Co-Authored-By` trailer to commits by default. This skill never does, and
refuses any message that carries one. To turn it off everywhere, also outside this skill, add
this to `~/.claude/settings.json`:

```json
{
  "attribution": { "commit": "", "pr": "", "sessionUrl": false }
}
```

## The helper by hand

```bash
G="python3 ~/.claude/skills/gitcommit/scripts/gitcommit.py"
$G run --in claude                # the whole job; add --dry-run to see the plan only
$G run --in codex --json          # with the details: model used, commits, push result
$G inspect                        # changes, style, flags, blockers (JSON)
$G commit --subject 'fix: handle empty carts' -- src/cart
$G push --since <commit>          # check, then push; never forced
```

## Privacy

The helper runs git on your machine and talks to your own remote when it pushes. The small
model is reached through the CLI of the provider you are already using, with your existing
login; it is sent the commit history subjects, the changed paths and a bounded diff, never a
path that was flagged. When a push is refused for a missing sign-in, the helper asks the same
server once whether it accepts your SSH key (`ssh -T`). It makes no other network request and
never reads or stores a credential.

## License

[MIT](../../LICENSE). gitcommit is a community project and is not affiliated with Anthropic,
OpenAI, Google, AWS, GitHub or GitLab.
