"""End-to-end tests against throwaway repositories.  Run:  python3 -m unittest discover -s tests/gitcommit -v"""

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "gitcommit" / "scripts" / "gitcommit.py"

NAME, EMAIL = "Ada Lovelace", "ada@example.com"
# Built at run time so that no scanner (ours or a host's) sees a token in this file.
AWS_KEY = "AKIA" + "ABCDEFGHIJKLMNOP"
GH_TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0" * 2


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="gitcommit-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        (self.tmp / "home").mkdir()
        self.env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(self.tmp / "home"),
            "XDG_CONFIG_HOME": str(self.tmp / "home" / ".config"),
            "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": str(self.tmp / "home" / ".gitconfig"),
        }
        self.repo = self.new_repo("app")

    # -- helpers --
    def git(self, *args, cwd=None, env=None, check=True):
        p = subprocess.run(["git", *args], cwd=str(cwd or self.repo), env={**self.env, **(env or {})},
                           capture_output=True, text=True, encoding="utf-8")
        if check and p.returncode != 0:
            self.fail("git %s failed: %s" % (" ".join(args), p.stderr))
        return p.stdout.strip()

    def new_repo(self, name, identity=True, commits=("chore: start the project",)):
        path = self.tmp / name
        path.mkdir()
        self.git("init", "-q", "-b", "main", cwd=path)
        if identity:
            self.git("config", "user.name", NAME, cwd=path)
            self.git("config", "user.email", EMAIL, cwd=path)
        for i, subject in enumerate(commits):
            (path / ("seed%d.txt" % i)).write_text("seed %d\n" % i)
            self.git("add", "-A", cwd=path)
            self.git("-c", "user.name=" + NAME, "-c", "user.email=" + EMAIL, "commit", "-qm", subject, cwd=path)
        return path

    def run_cli(self, *args, cwd=None, env=None):
        p = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], cwd=str(cwd or self.repo),
                           env={**self.env, **(env or {})}, capture_output=True, text=True, encoding="utf-8")
        try:
            return p.returncode, json.loads(p.stdout)
        except json.JSONDecodeError:
            self.fail("not JSON (exit %s): %s\n%s" % (p.returncode, p.stdout, p.stderr))

    def write(self, rel, text="x\n", repo=None):
        path = (repo or self.repo) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def head(self, repo=None):
        return self.git("rev-parse", "HEAD", cwd=repo)

    def log(self, fmt="%s", repo=None, rev="HEAD"):
        return self.git("log", "--format=" + fmt, rev, cwd=repo).splitlines()

    def remote(self, name="origin.git"):
        """A bare repository standing in for GitHub, GitLab or any other server."""
        path = self.tmp / name
        self.git("init", "-q", "--bare", "-b", "main", str(path), cwd=self.tmp)
        return path


class InspectTest(Base):
    def test_a_plain_folder_is_initialised_on_request(self):
        folder = self.tmp / "fresh"
        folder.mkdir()
        self.write("main.py", "print(1)\n", repo=folder)
        code, d = self.run_cli("inspect", cwd=folder)
        self.assertEqual([b["code"] for b in d["blockers"]], ["not-a-repository"])
        code, d = self.run_cli("init", cwd=folder)
        self.assertEqual((code, d["branch"]), (0, "main"))
        self.git("config", "user.name", NAME, cwd=folder)
        self.git("config", "user.email", EMAIL, cwd=folder)
        code, d = self.run_cli("inspect", cwd=folder)
        self.assertEqual((d["head"], d["first_commit"], d["can_push"], d["blockers"]), ("root", True, False, []))
        code, c = self.run_cli("commit", "--subject", "feat: add the entry point", "--", "main.py", cwd=folder)
        self.assertEqual((code, c["author"]), (0, "%s <%s>" % (NAME, EMAIL)))
        code, p = self.run_cli("push", "--since", "root", cwd=folder)
        self.assertEqual((code, p["status"], p["pushed"]), (0, "no-remote", False))

    def test_init_refuses_a_folder_that_is_already_in_a_repository(self):
        (self.repo / "sub").mkdir()
        code, d = self.run_cli("init", cwd=self.repo / "sub")
        self.assertEqual((code, d["error"]), (2, "already-a-repository"))

    def test_missing_identity_is_a_blocker(self):
        repo = self.new_repo("anon", identity=False, commits=())
        self.write("a.txt", repo=repo)
        code, d = self.run_cli("inspect", cwd=repo)
        self.assertEqual([b["code"] for b in d["blockers"]], ["no-identity"])
        code, d = self.run_cli("commit", "--subject", "feat: add a", "--", "a.txt", cwd=repo)
        self.assertEqual((code, d["error"]), (2, "no-identity"))

    def test_changes_and_totals(self):
        self.write("seed0.txt", "seed 0\nmore\n")
        self.write("src/new.py", "a\nb\nc\n")
        self.write("notes.md", "one\n")
        self.git("add", "notes.md")
        code, d = self.run_cli("inspect")
        by = {c["path"]: c for c in d["changes"]}
        self.assertEqual((by["seed0.txt"]["change"], by["seed0.txt"]["added"]), ("modified", 1))
        self.assertEqual((by["notes.md"]["change"], by["notes.md"]["staged"]), ("added", True))
        self.assertEqual((by["src/"]["change"], by["src/"]["files"]), ("untracked", 1))
        self.assertEqual((d["staged"], d["nothing_to_commit"], d["flags"], d["blockers"]), (1, False, [], []))
        self.assertEqual(d["head"], self.head())

    def test_recent_history_says_what_is_recorded_and_what_is_pushed(self):
        origin = self.remote()
        self.git("remote", "add", "origin", str(origin))
        self.git("push", "-q", "-u", "origin", "main")
        self.write("src/cart.py")
        self.git("add", "-A")
        self.git("commit", "-qm", "feat(cart): add the cart")      # made earlier, by anyone, not pushed
        self.write("src/cart.py", "changed in another session\n")
        code, d = self.run_cli("inspect")
        self.assertEqual([(c["subject"], c["pushed"], c["files"]) for c in d["recent"]],
                         [("feat(cart): add the cart", False, ["src/cart.py"]),
                          ("chore: start the project", True, ["seed0.txt"])])
        self.assertEqual((d["ahead"], [c["path"] for c in d["changes"]]), (1, ["src/cart.py"]))

    def test_merge_in_progress_and_detached_head_block(self):
        self.git("checkout", "-q", "--detach")
        code, d = self.run_cli("inspect")
        self.assertEqual([b["code"] for b in d["blockers"]], ["detached-head"])
        self.write("b.txt")
        code, d = self.run_cli("commit", "--subject", "feat: add b", "--", "b.txt")
        self.assertEqual(d["error"], "detached-head")


class FlagTest(Base):
    def flags(self):
        code, d = self.run_cli("inspect")
        return {(f["path"], f["kind"]) for f in d["flags"]}, d

    def test_what_must_stay_out_is_flagged(self):
        self.write(".env", "DB=1\n")
        self.write(".env.local", "DB=2\n")
        self.write(".env.example", "DB=\n")
        self.write("deploy/id_rsa", "x\n")
        self.write(".DS_Store")
        self.write("node_modules/pkg/index.js")
        self.write("config.py", "TOKEN = '%s'\n" % GH_TOKEN)
        self.write("seed0.txt", "seed 0\naws = %s\n" % AWS_KEY)
        self.write("merge.txt", "<<<<<<< HEAD\nmine\n=======\ntheirs\n>>>>>>> other\n")
        self.git("add", "merge.txt")
        with open(self.repo / "video.bin", "wb") as fh:
            fh.truncate(6 * 1024 * 1024)
        flags, d = self.flags()
        self.assertEqual(flags, {
            (".env", "sensitive-file"), (".env.local", "sensitive-file"), ("deploy/id_rsa", "sensitive-file"),
            (".DS_Store", "junk"), ("node_modules/", "junk"), ("config.py", "secret"), ("seed0.txt", "secret"),
            ("merge.txt", "conflict-marker"), ("video.bin", "large")})
        self.assertNotIn(GH_TOKEN, json.dumps(d), "a secret is never repeated")
        self.assertNotIn(AWS_KEY, json.dumps(d))
        line = next(f for f in d["flags"] if f["path"] == "seed0.txt")
        self.assertEqual((line["detail"], line["line"]), ("AWS access key", 2))

    def test_files_the_project_already_tracks_are_not_judged_by_name(self):
        self.write(".env", "MODE=dev\n")
        self.git("add", "-f", ".env")
        self.git("commit", "-qm", "chore: track the dev env")
        self.write(".env", "MODE=test\n")
        flags, d = self.flags()
        self.assertEqual(flags, set())

    def test_commit_refuses_flagged_paths_unless_told(self):
        self.write(".env", "DB=1\n")
        self.write("ok.txt")
        before = self.head()
        code, d = self.run_cli("commit", "--subject", "chore: add settings", "--", ".env", "ok.txt")
        self.assertEqual((code, d["error"], d["flags"][0]["path"]), (2, "flagged", ".env"))
        self.assertEqual(self.head(), before)
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "", "the index is left clean")
        code, d = self.run_cli("commit", "--subject", "chore: add settings", "--include-flagged", "--", ".env")
        self.assertEqual((code, d["files"]), (0, 1))


class StyleTest(Base):
    def test_conventional_history_is_recognised(self):
        repo = self.new_repo("conv", commits=("feat(cart): add coupons", "fix(cart): round totals", "docs: explain setup",
                                              "feat(api): list invoices", "Merge stuff by hand"))
        self.git("switch", "-qc", "feat/SHOP-42-coupons", cwd=repo)
        code, d = self.run_cli("inspect", cwd=repo)
        s = d["style"]
        self.assertEqual((s["convention"], s["types"][0], s["scopes"][0], s["first_letter"]),
                         ("conventional", "feat", "cart", "lower"))
        self.assertEqual((s["branch_issue_key"], s["signoff"]), ("SHOP-42", False))

    def test_the_language_of_the_history_reaches_the_agent_and_the_commit(self):
        subjects = ("feat(sepet): kupon desteği ekle", "fix(sepet): toplam yuvarlamasını düzelt",
                    "docs: kurulum adımlarını açıkla")
        repo = self.new_repo("tr", commits=subjects)
        code, d = self.run_cli("inspect", cwd=repo)
        self.assertEqual(d["style"]["convention"], "conventional")
        self.assertEqual(d["style"]["examples"], list(reversed(subjects)), "verbatim, newest first")
        self.assertEqual(d["recent"][0]["subject"], subjects[-1])
        self.write("odeme.py", repo=repo)
        subject = "feat(ödeme): taksit seçeneği ekle"
        code, c = self.run_cli("commit", "--subject", subject, "--", "odeme.py", cwd=repo)
        self.assertEqual((code, c["subject"]), (0, subject))
        self.assertEqual(self.log(repo=repo)[0], subject)

    def test_plain_history_and_new_repository(self):
        repo = self.new_repo("plain", commits=("Add the parser", "Fix a crash on empty input", "Update the readme"))
        code, d = self.run_cli("inspect", cwd=repo)
        self.assertEqual((d["style"]["convention"], d["style"]["first_letter"]), ("plain", "upper"))
        code, d = self.run_cli("inspect")
        self.assertEqual(d["style"]["convention"], "none")

    def test_sign_off_is_learned_and_added_as_the_user(self):
        repo = self.new_repo("dco", commits=())
        for i in range(3):
            self.write("f%d" % i, repo=repo)
            self.git("add", "-A", cwd=repo)
            self.git("commit", "-qsm", "feat: add part %d" % i, cwd=repo)
        code, d = self.run_cli("inspect", cwd=repo)
        self.assertTrue(d["style"]["signoff"])
        self.write("g", repo=repo)
        code, c = self.run_cli("commit", "--subject", "feat: add g", "--signoff", "--", "g", cwd=repo)
        self.assertEqual(code, 0, c)
        self.assertIn("Signed-off-by: %s <%s>" % (NAME, EMAIL), self.git("log", "-1", "--format=%b", cwd=repo))
        self.assertNotIn("problems", c)


class CommitTest(Base):
    def test_only_the_named_paths_are_committed(self):
        self.write("a.txt")
        self.write("b.txt")
        self.git("add", "b.txt")                       # staged by hand before the run
        code, d = self.run_cli("commit", "--subject", "feat: add a", "--", "a.txt")
        self.assertEqual((code, d["files"], d["remaining"]), (0, 1, 1))
        self.assertEqual(self.git("show", "--name-only", "--format=", "HEAD"), "a.txt")
        self.assertEqual(self.log("%an <%ae>|%cn <%ce>")[0], "%s <%s>|%s <%s>" % (NAME, EMAIL, NAME, EMAIL))

    def test_identity_comes_from_git_config_whatever_the_host_exports(self):
        self.write("a.txt")
        robot = {"GIT_AUTHOR_NAME": "Robot", "GIT_AUTHOR_EMAIL": "robot@example.com",
                 "GIT_COMMITTER_NAME": "Robot", "GIT_COMMITTER_EMAIL": "robot@example.com"}
        code, d = self.run_cli("commit", "--subject", "feat: add a", "--", "a.txt", env=robot)
        self.assertEqual(code, 0, d)
        self.assertEqual(self.log("%an|%ae|%cn|%ce")[0], "|".join((NAME, EMAIL, NAME, EMAIL)))

    def test_messages_that_break_the_rules_are_refused(self):
        self.write("a.txt")
        before = self.head()
        cases = [
            (["--subject", "feat: add a", "--body", "Co-Authored-By: Claude <noreply@anthropic.com>"], "Co-authored-by"),
            (["--subject", "feat: add a", "--body", "co-authored-by: Someone Else <s@example.com>"], "Co-authored-by"),
            (["--subject", "feat: add a", "--body", "Generated with Claude Code"], "AI attribution"),
            (["--subject", "feat: add a", "--body", "\U0001f916 made by a bot"], "AI attribution"),
            (["--subject", "feat: add a", "--body", "Signed-off-by: Other <other@example.com>"], "someone else"),
            (["--subject", "feat: add a."], "period"),
            (["--subject", "feat: " + "a" * 80], "characters"),
            (["--subject", "feat: add a"] + [x for i in range(6) for x in ("--body", "line %d" % i)], "body is 6 lines"),
            (["--subject", "  "], "empty"),
        ]
        for args, expect in cases:
            code, d = self.run_cli("commit", *args, "--", "a.txt")
            self.assertEqual((code, d["error"]), (2, "bad-message"), args)
            self.assertIn(expect, " ".join(d["problems"]), args)
        self.assertEqual(self.head(), before, "nothing was committed")

    def test_a_short_body_is_allowed(self):
        self.write("a.txt")
        code, d = self.run_cli("commit", "--subject", "feat(api)!: drop the v1 endpoint",
                               "--body", "BREAKING CHANGE: use /v2/orders", "--", "a.txt")
        self.assertEqual(code, 0, d)
        self.assertEqual(self.git("log", "-1", "--format=%B").splitlines(),
                         ["feat(api)!: drop the v1 endpoint", "", "BREAKING CHANGE: use /v2/orders"])

    def test_rename_deletion_and_folder(self):
        (self.repo / "seed0.txt").rename(self.repo / "renamed.txt")
        self.write("pkg/one.py")
        self.write("pkg/two.py")
        code, d = self.run_cli("commit", "--subject", "refactor: rename the seed", "--", "seed0.txt", "renamed.txt")
        self.assertEqual((code, d["files"], d["remaining"]), (0, 2, 1))
        code, d = self.run_cli("commit", "--subject", "feat: add pkg", "--", "pkg")
        self.assertEqual((code, d["files"], d["remaining"]), (0, 2, 0))

    def test_staged_mode_commits_the_index_as_it_is(self):
        self.write("a.txt")
        self.write("b.txt")
        self.git("add", "a.txt")
        code, d = self.run_cli("commit", "--subject", "feat: add a", "--staged")
        self.assertEqual((code, d["files"], d["remaining"]), (0, 1, 1))
        code, d = self.run_cli("commit", "--subject", "feat: add nothing", "--staged")
        self.assertEqual(d["error"], "nothing-staged")

    def test_a_failing_hook_is_reported_and_not_bypassed(self):
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\necho 'lint: 2 errors' >&2\nexit 1\n")
        hook.chmod(hook.stat().st_mode | stat.S_IEXEC)
        self.write("a.txt")
        before = self.head()
        code, d = self.run_cli("commit", "--subject", "feat: add a", "--", "a.txt")
        self.assertEqual((code, d["error"]), (2, "commit-failed"))
        self.assertIn("lint: 2 errors", d["output"])
        self.assertEqual(self.head(), before)
        code, d = self.run_cli("inspect")
        self.assertEqual(d["tooling"]["hooks"], ["pre-commit"])

    def test_paths_without_changes(self):
        code, d = self.run_cli("commit", "--subject", "feat: nothing", "--", "seed0.txt")
        self.assertEqual((code, d["error"]), (2, "nothing-staged"))
        code, d = self.run_cli("commit", "--subject", "feat: nothing", "--", "no-such-file")
        self.assertEqual((code, d["error"]), (2, "bad-path"))


class PushTest(Base):
    def linked(self, push_seed=True):
        origin = self.remote()
        self.git("remote", "add", "origin", str(origin))
        if push_seed:
            self.git("push", "-q", "-u", "origin", "main")
        return origin

    def remote_log(self, origin, branch="main"):
        return self.git("log", "--format=%s", branch, cwd=origin, check=False).splitlines()

    def test_push_to_the_tracked_branch(self):
        origin = self.linked()
        since = self.head()
        self.write("a.txt")
        self.run_cli("commit", "--subject", "feat: add a", "--", "a.txt")
        code, d = self.run_cli("push", "--since", since)
        self.assertEqual((code, d["status"], d["commits"], d["upstream"], d["set_upstream"]),
                         (0, "pushed", 1, "origin/main", False))
        self.assertEqual(self.remote_log(origin)[0], "feat: add a")
        code, d = self.run_cli("push", "--since", self.head())
        self.assertEqual((code, d["status"], d["pushed"]), (0, "up-to-date", False))

    def test_a_new_branch_is_published(self):
        origin = self.linked()
        self.git("switch", "-qc", "feat/coupons")
        since = self.head()
        self.write("a.txt")
        self.run_cli("commit", "--subject", "feat: add a", "--", "a.txt")
        code, d = self.run_cli("inspect")
        self.assertEqual((d["upstream"], d["remote"], d["can_push"], d["ahead"]), (None, "origin", True, 1))
        code, d = self.run_cli("push", "--since", since)
        self.assertEqual((code, d["status"], d["upstream"], d["set_upstream"]),
                         (0, "pushed", "origin/feat/coupons", True))
        self.assertEqual(self.remote_log(origin, "feat/coupons")[0], "feat: add a")

    def test_first_push_of_a_new_project(self):
        origin = self.linked(push_seed=False)
        code, d = self.run_cli("push", "--since", "root")
        self.assertEqual((code, d["status"], d["commits"], d["upstream"]), (0, "pushed", 1, "origin/main"))
        self.assertEqual(self.remote_log(origin), ["chore: start the project"])

    def test_a_remote_that_moved_on_rejects_and_nothing_is_forced(self):
        origin = self.linked()
        other = self.tmp / "other"
        self.git("clone", "-q", str(origin), str(other), cwd=self.tmp)
        self.write("theirs.txt", repo=other)
        self.git("add", "-A", cwd=other)
        self.git("-c", "user.name=Bob", "-c", "user.email=bob@example.com", "commit", "-qm", "feat: theirs", cwd=other)
        self.git("push", "-q", cwd=other)
        since = self.head()
        self.write("mine.txt")
        self.run_cli("commit", "--subject", "feat: mine", "--", "mine.txt")
        code, d = self.run_cli("push", "--since", since)
        self.assertEqual((code, d["status"], d["pushed"], d["unpushed"]), (1, "rejected", False, 1))
        self.assertEqual(self.remote_log(origin)[0], "feat: theirs")
        self.assertEqual(self.log()[0], "feat: mine", "the local commit is kept")

    def test_a_commit_with_attribution_is_never_pushed(self):
        origin = self.linked()
        since = self.head()
        self.write("a.txt")
        self.git("add", "-A")
        self.git("commit", "-qm", "feat: add a", "-m", "Co-Authored-By: Claude <noreply@anthropic.com>")
        code, d = self.run_cli("check", "--since", since)
        self.assertEqual((code, d["ok"]), (1, False))
        code, d = self.run_cli("push", "--since", since)
        self.assertEqual((code, d["error"]), (2, "check-failed"))
        self.assertIn("Co-authored-by", d["commits"][0]["problems"][0])
        self.assertEqual(self.remote_log(origin), ["chore: start the project"])

    def test_a_commit_under_another_name_is_never_pushed(self):
        self.linked()
        since = self.head()
        self.write("a.txt")
        self.git("add", "-A")
        self.git("-c", "user.name=Robot", "-c", "user.email=robot@example.com", "commit", "-qm", "feat: add a")
        code, d = self.run_cli("push", "--since", since)
        self.assertEqual(d["error"], "check-failed")
        self.assertIn("the author is Robot", " ".join(d["commits"][0]["problems"]))

    def test_commits_from_before_the_run_are_the_users_business(self):
        origin = self.linked()
        self.write("old.txt")
        self.git("add", "-A")
        self.git("commit", "-qm", "Pairing session, a subject that is long and ends with a period, as people write.",
                 "-m", "Co-authored-by: Grace Hopper <grace@example.com>")
        since = self.head()
        self.write("new.txt")
        self.run_cli("commit", "--subject", "feat: add new", "--", "new.txt")
        code, d = self.run_cli("push", "--since", since)
        self.assertEqual((code, d["status"], d["commits"]), (0, "pushed", 2))
        self.assertEqual(len(self.remote_log(origin)), 3)

    def test_an_unreachable_remote_keeps_the_commits_local(self):
        self.git("remote", "add", "origin", str(self.tmp / "gone.git"))
        code, d = self.run_cli("push", "--since", "root")
        self.assertEqual((code, d["pushed"]), (1, False))
        self.assertIn(d["status"], ("offline", "error", "auth"))
        self.assertTrue(d["output"])

    def test_several_remotes_without_origin_need_a_choice(self):
        a, b = self.remote("a.git"), self.remote("b.git")
        self.git("remote", "add", "github", str(a))
        self.git("remote", "add", "gitlab", str(b))
        code, d = self.run_cli("push", "--since", "root")
        self.assertEqual((d["status"], d["pushed"], sorted(d["remotes"])), ("which-remote", False, ["github", "gitlab"]))
        code, d = self.run_cli("push", "--since", "root", "--remote", "gitlab")
        self.assertEqual((code, d["status"], d["remote"]), (0, "pushed", "gitlab"))
        self.assertEqual(self.remote_log(b), ["chore: start the project"])


if __name__ == "__main__":
    unittest.main()
