# gitcommit

**Turn your working tree into clean commits and push them, under your name only.** `/gitcommit`
reads what changed, groups it into a few commits by purpose, writes short messages in your
repository's own convention, and pushes to whatever server the project is connected to.

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

## What it does

- **The whole working tree, whoever changed it.** It scans everything that differs from the last
  commit: work from this session, from an earlier one, from another agent or typed by hand. It
  does not matter when or where a change was made.
- **One purpose per commit.** A feature goes in with its tests and docs; a fix, a refactor, a
  dependency bump or a formatting pass each get their own commit. Work that piled up over
  several sessions is split into the commits it should have been. Usually 1 to 5 commits.
- **It reads the history first.** New commits continue the recent ones: same types, scopes and
  vocabulary. A correction becomes a new `fix` commit; existing commits are never amended.
- **Task and commit in one call.** Write the task after `/gitcommit` and the agent does the
  work, then commits and pushes it as the last step. Unfinished or failing work is not pushed.
- **Your convention, not ours.** It reads the last 50 commits and follows what it finds:
  Conventional Commits with your types and scopes, gitmoji, ticket prefixes or plain sentences.
  A new repository gets Conventional Commits.
- **Short messages.** A subject of about 50 characters (72 at most), imperative, no period. No
  body unless there is a breaking change or a reason nobody could guess, and then three lines
  at most.
- **Only your name.** No `Co-authored-by`, no "Generated with …", no tool or model name. The
  author and the committer are whoever `git config` says you are, even when the agent's
  environment sets something else.
- **Nothing private goes in.** Keys and tokens on added lines, new credential files (`.env`,
  `*.pem`, `id_rsa` …), unresolved conflict markers, new files over 5 MB and junk
  (`node_modules`, `.DS_Store`, caches) are left out and listed.
- **Any server.** GitHub, GitLab, Bitbucket, a self-hosted remote: it is a plain `git push` to
  the remote the project already has. A new branch is published with the same name.
- **No remote, no problem.** Without a remote it commits locally and tells you how to add one.
  In a folder that is not a repository yet, it runs `git init` first.

## What it never does

Force-push · skip hooks (`--no-verify`) · rewrite commits that existed before the call · switch
branches, stash or discard your work · change git configuration or remotes · pull, rebase or
merge on its own. If the remote has commits you do not have, it stops and says so; your commits
stay local.

## How it works

```
/gitcommit
   │
   ├─ 1. inspect   what changed, the recent commits, how this repository writes them,
   │               what must stay out
   ├─ 2. the agent reads the diffs, groups them by purpose and writes the subjects
   ├─ 3. commit    one call per group; a message that breaks a rule is refused before anything
   │               is written (attribution, length, someone else's sign-off)
   └─ 4. push      every commit of this run is checked again, then pushed; never forced
```

The grouping and the wording are the agent's judgment. The rules are code: a small Python
helper (standard library only) makes the commits and the push, so they hold in every agent.

## Install

Requirements: git, Python 3.8+, and Claude Code, Codex or Antigravity. macOS, Linux and WSL.

```bash
git clone https://github.com/osrbck/skillbook.git ~/skillbook
~/skillbook/install.sh gitcommit          # Claude Code
~/skillbook/install.sh gitcommit --codex  # Codex
~/skillbook/install.sh gitcommit --all    # Claude Code, Codex and Antigravity
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
/gitcommit include .env.test    commit a path that was flagged
/gitcommit in English           this language, whatever the history uses
/gitcommit the coupon feature   a hint about work that is already in the tree
/gitcommit add coupon support to checkout
                                a task: do the work, then commit and push it
```

It runs only when you call it. It asks nothing along the way and stops only when something
blocks a commit: no `user.name` / `user.email`, a merge or rebase in progress, unresolved
conflicts, a detached HEAD.

## Messages

| Repository history | Subject it writes |
|---|---|
| Conventional Commits | `fix(cart): round totals per line` (your types and scopes) |
| gitmoji | as your history does |
| ticket prefix | `SHOP-42 Round totals per line` (as your history does) |
| plain sentences | `Round cart totals per line` |
| none yet | Conventional Commits |

**The language follows your history, without being told.** If your past commits are in Turkish,
the new ones are in Turkish (`feat(sepet): kupon desteği ekle`); if they are in English, in
English, whatever language you speak to the agent. A new repository gets English, and a language
you name in the call (`/gitcommit in English`) wins. The verb form follows the history as well
(`add` or `added`). An issue key from the branch name is used only in the form your history already uses.
`Signed-off-by` is added, as you, only in repositories whose history uses it.

## Claude Code and the co-author line

Claude Code adds a `Co-Authored-By` trailer to commits by default. This skill overrides that for
its own commits and refuses any message that carries one. To turn it off everywhere, also
outside this skill, add this to `~/.claude/settings.json`:

```json
{
  "attribution": { "commit": "", "pr": "", "sessionUrl": false }
}
```

## The helper by hand

```bash
G="python3 ~/.claude/skills/gitcommit/scripts/gitcommit.py"
$G inspect                                             # changes, style, flags, blockers (JSON)
$G commit --subject 'fix: handle empty carts' -- src/cart
$G check --since <commit>                              # author, message and attribution
$G push --since <commit>                               # check, then push; never forced
```

## Privacy

The helper runs git on your machine and talks to your own remote when it pushes. It makes no
other network request. The agent reads the diffs it needs to name the work, so they become part
of your conversation with that agent; flagged secrets are reported by kind and line, never by
value.

## License

[MIT](../../LICENSE). gitcommit is a community project and is not affiliated with Anthropic,
OpenAI, Google, GitHub or GitLab.
