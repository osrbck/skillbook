"""End-to-end tests against throwaway repositories.  Run:  python3 -m unittest discover -s tests/gitcommit -v"""

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "gitcommit" / "scripts" / "gitcommit.py"
FAKE = Path(__file__).resolve().parent / "fakecli.py"
sys.path.insert(0, str(SCRIPT.parent))
import gitcommit as helper  # noqa: E402

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

    def run_cli(self, *args, cwd=None, env=None, raw=False):
        p = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], cwd=str(cwd or self.repo),
                           env={**self.env, **(env or {})}, capture_output=True, text=True, encoding="utf-8")
        if raw:
            return p.returncode, p.stdout
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


class _Refuse(BaseHTTPRequestHandler):
    """A git server over HTTP that wants a sign-in and accepts none."""

    def _no(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="git"')
        self.send_header("Content-Length", "0")
        self.end_headers()

    do_GET = do_POST = _no

    def log_message(self, *args):
        pass


class SignInTest(Base):
    """A push must not open a password window nobody asked for, and must say why it failed."""

    def setUp(self):
        super().setUp()
        self.server = HTTPServer(("127.0.0.1", 0), _Refuse)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.git("remote", "add", "origin", "http://127.0.0.1:%d/team/app.git" % self.server.server_port)
        self.asked = self.tmp / "asked.txt"
        self.window = self.tmp / "password-window"       # stands in for ksshaskpass, ssh-askpass …
        self.window.write_text("#!/bin/sh\necho \"$1\" >> %s\necho someone\n" % self.asked)
        self.window.chmod(self.window.stat().st_mode | stat.S_IEXEC)

    def test_the_desktop_password_window_is_not_opened_by_a_push(self):
        code, d = self.run_cli("push", "--since", "root", env={"SSH_ASKPASS": str(self.window)})
        self.assertEqual((code, d["status"], d["pushed"], d["unpushed"]), (1, "auth", False, 1))
        self.assertFalse(self.asked.exists(), "nothing was asked")
        s = d["sign_in"]
        self.assertEqual((s["transport"], s["host"], s["credential_helpers"], s["password_program"]),
                         ("http", "127.0.0.1", [], "password-window"))
        self.assertIn("no credential helper is configured", d["text"])
        self.assertIn("commits are safe locally", d["text"])
        self.assertTrue([o for o in d["options"] if "`ask`" in o["run"]], d["options"])

    def test_ask_lets_the_window_appear(self):
        code, d = self.run_cli("push", "--since", "root", "--ask", env={"SSH_ASKPASS": str(self.window)})
        self.assertEqual((code, d["status"]), (1, "auth"))
        self.assertIn("Username for 'http://127.0.0.1", self.asked.read_text())
        self.assertFalse([o for o in d["options"] if "`ask`" in o["run"]], "not offered twice")

    def test_a_password_program_set_up_for_git_is_left_alone(self):
        code, d = self.run_cli("push", "--since", "root", env={"GIT_ASKPASS": str(self.window)})
        self.assertEqual(d["status"], "auth")
        self.assertTrue(self.asked.exists(), "GIT_ASKPASS is the user's own setup and is used")
        self.assertIsNone(d["sign_in"]["password_program"])
        self.asked.unlink()
        self.git("config", "core.askPass", str(self.window))
        self.run_cli("push", "--since", "root", env={"SSH_ASKPASS": "/nonexistent"})
        self.assertTrue(self.asked.exists(), "so is core.askPass")

    def test_a_configured_helper_is_named_when_it_has_nothing(self):
        self.git("config", "credential.helper", "cache")
        code, d = self.run_cli("push", "--since", "root")
        self.assertEqual((d["status"], d["sign_in"]["credential_helpers"]), ("auth", ["cache"]))
        self.assertIn("credential helper (cache) had nothing", d["text"])


class RunTest(Base):
    """`run`: one call scans, lets the provider's small model plan, commits, pushes and reports."""

    def setUp(self):
        super().setUp()
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        for name in ("claude", "codex", "agy", "kiro-cli"):
            launcher = bin_dir / name
            launcher.write_text("#!%s\nimport os, runpy\nos.environ['FAKE_NAME'] = %r\n"
                                "runpy.run_path(%r, run_name='__main__')\n" % (sys.executable, name, str(FAKE)))
            launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC)
        self.env["PATH"] = "%s%s%s" % (bin_dir, os.pathsep, self.env["PATH"])
        self.env["FAKE_LOG"] = str(self.tmp / "fake.log")
        self.origin = self.remote()
        self.git("remote", "add", "origin", str(self.origin))
        self.git("push", "-q", "-u", "origin", "main")

    def calls(self):
        path = Path(self.env["FAKE_LOG"])
        return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []

    def answers(self, *plans):
        path = self.tmp / "answers.txt"
        path.write_text("\n---\n".join(p if isinstance(p, str) else json.dumps(p) for p in plans), encoding="utf-8")
        return {"FAKE_ANSWERS": str(path)}

    def test_one_call_scans_plans_commits_and_pushes(self):
        self.write("src/cart.py", "total = 1\n")
        self.write("seed0.txt", "seed 0\nmore\n")
        code, text = self.run_cli("run", "--host", "claude", raw=True)
        self.assertEqual(code, 0, text)
        lines = text.strip().splitlines()
        self.assertEqual(lines[0], "Pushed 1 commit to origin/main")
        self.assertRegex(lines[1], r"^[0-9a-f]{7} feat: update the project$")
        self.assertEqual(len(lines), 2, "the report is the whole output")
        call = self.calls()[0]
        self.assertEqual((call["cli"], call["model"]), ("claude", "haiku"))
        self.assertIn("--tools", call["argv"])
        self.assertNotEqual(Path(call["cwd"]).resolve(), self.repo.resolve(), "the model works in an empty folder")
        for part in ("RULES", "HISTORY", "chore: start the project", "src/cart.py  (new)", "seed0.txt  (changed)", "+total = 1"):
            self.assertIn(part, call["prompt"])
        self.assertEqual(self.log("%an <%ae>|%b")[0], "%s <%s>|" % (NAME, EMAIL))
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(self.git("log", "--format=%s", "main", cwd=self.origin).splitlines()[0], "feat: update the project")

    def test_the_plan_decides_the_commits(self):
        self.write("src/cart.py")
        self.write("src/cart_test.py")
        self.write("docs/setup.md")
        plan = {"commits": [{"subject": "feat(cart): add the cart", "body": [], "paths": ["src"]},
                            {"subject": "docs: explain setup", "body": [], "paths": ["docs/setup.md"]}]}
        code, text = self.run_cli("run", "--host", "codex", "--no-push", raw=True, env=self.answers(plan))
        self.assertEqual(code, 0, text)
        self.assertEqual(text.splitlines()[0], "Committed 2 commits (not pushed)")
        self.assertEqual(self.log()[:2], ["docs: explain setup", "feat(cart): add the cart"])
        self.assertEqual(sorted(self.git("show", "--name-only", "--format=", "HEAD~1").splitlines()),
                         ["src/cart.py", "src/cart_test.py"])

    def test_the_small_current_model_of_each_provider(self):
        pick = helper.pick_model
        ids = lambda *names: [{"id": n} for n in names]  # noqa: E731
        self.assertEqual(pick("claude", []), "haiku")
        self.assertEqual(pick("codex", ids("gpt-5.6-luna", "gpt-5.6-terra", "gpt-6-luna", "gpt-6-astra")), "gpt-6-luna")
        self.assertEqual(pick("codex", ids("gpt-6-luna", "gpt-6.1-luna", "gpt-6.1-sol")), "gpt-6.1-luna")
        self.assertIsNone(pick("codex", []), "no listing: the CLI's own default")
        self.assertEqual(pick("agy", ids("gemini-4-argon-high", "gemini-3.8-flash-low", "gemini-3.5-flash-lite")),
                         "gemini-3.5-flash-lite")
        self.assertEqual(pick("agy", ids("gemini-4-argon-low", "gemini-3.8-flash-high", "gemini-3.8-flash-low",
                                         "gemini-3.8-flash-medium")), "gemini-3.8-flash-low")
        kiro = [{"id": "auto", "rate": 1.0}, {"id": "claude-opus-5.5", "rate": 2.0}, {"id": "claude-haiku-4.5", "rate": 0.4},
                {"id": "claude-haiku-5.5", "rate": 0.06}, {"id": "qwen3-coder-next", "rate": 0.05, "preview": True}]
        self.assertEqual(pick("kiro", kiro), "claude-haiku-5.5")
        self.assertEqual(pick("kiro", [{"id": "auto", "rate": 1.0}, {"id": "big-one", "rate": 2.0}]), "auto")
        self.assertEqual(pick("kiro", []), "auto")

    def test_every_provider_cli_is_driven_the_right_way(self):
        expect = {"claude": "haiku", "codex": "gpt-6-luna", "agy": "gemini-3.8-flash-low", "kiro": "claude-haiku-5.5"}
        for host, model in expect.items():
            self.write("%s.txt" % host)
            # --in is the documented name; --host is the older spelling and must keep working
            code, text = self.run_cli("run", "--in" if host != "codex" else "--host", host, "--no-push", raw=True)
            self.assertEqual((code, text.splitlines()[0]), (0, "Committed 1 commit (not pushed)"), host)
            call = [c for c in self.calls() if "prompt" in c][-1]
            self.assertEqual((call["cli"].replace("-cli", ""), call["model"]), (host, model))
        code, text = self.run_cli("run", "--host", "codex", "--model", "my-own-model", "--dry-run", raw=True)
        self.write("x.txt")
        code, text = self.run_cli("run", "--host", "codex", "--model", "my-own-model", "--dry-run", raw=True)
        self.assertEqual(self.calls()[-1]["model"], "my-own-model")

    def test_a_cli_that_does_not_know_the_newer_flags_still_works(self):
        for host in ("claude", "codex", "agy", "kiro"):
            self.write("%s.txt" % host)
            code, text = self.run_cli("run", "--host", host, "--no-push", raw=True, env={"FAKE_OLD": "1"})
            self.assertEqual(code, 0, "%s: %s" % (host, text))

    def test_an_answer_that_misses_a_path_is_sent_back_once(self):
        self.write("a.txt")
        self.write("b.txt")
        bad = {"commits": [{"subject": "feat: add a", "body": [], "paths": ["a.txt"]}]}
        good = {"commits": [{"subject": "feat: add a and b", "body": [], "paths": ["a.txt", "b.txt"]}]}
        code, text = self.run_cli("run", "--host", "claude", "--no-push", raw=True, env=self.answers(bad, good))
        self.assertEqual((code, self.log()[0]), (0, "feat: add a and b"))
        prompts = [c["prompt"] for c in self.calls()]
        self.assertEqual(len(prompts), 2)
        self.assertIn("these paths are in no commit: b.txt", prompts[1])

    def test_a_message_that_breaks_the_rules_never_becomes_a_commit(self):
        self.write("a.txt")
        bad = {"commits": [{"subject": "feat: add a", "body": ["Co-Authored-By: Claude <noreply@anthropic.com>"], "paths": ["a.txt"]}]}
        before = self.head()
        code, text = self.run_cli("run", "--host", "claude", raw=True, env=self.answers(bad))
        self.assertEqual(code, 3, text)
        self.assertIn("NEED-PLAN", text)
        self.assertIn("Co-authored-by", text)
        self.assertEqual(self.head(), before)

    def test_when_the_model_fails_the_caller_writes_the_plan(self):
        self.write("a.txt")
        self.write(".env", "DB=1\n")
        before = self.head()
        code, text = self.run_cli("run", "--host", "kiro", raw=True, env={"FAKE_KIRO": "fail"})
        self.assertEqual(code, 3)
        self.assertTrue(text.startswith("NEED-PLAN: kiro:claude-haiku-5.5 gave no answer"), text)
        self.assertEqual(self.head(), before)
        brief = Path(re.search(r"Read (\S+)", text).group(1))
        self.addCleanup(lambda: brief.exists() and brief.unlink())
        self.assertIn("a.txt  (new)", brief.read_text(encoding="utf-8"))
        plan = self.tmp / "plan.json"
        plan.write_text(json.dumps({"commits": [{"subject": "feat: add a", "body": [], "paths": ["a.txt"]}]}))
        code, text = self.run_cli("apply", "--plan", plan, raw=True)
        self.assertEqual(code, 0, text)
        self.assertEqual(text.strip().splitlines()[0], "Pushed 1 commit to origin/main")
        self.assertEqual(text.strip().splitlines()[-1], "Left out: .env (credentials file)")
        code, text = self.run_cli("run", raw=True, env={"PATH": "/usr/bin:/bin"})
        self.assertIn("Nothing to commit", text)

    def test_no_provider_named_and_none_detected(self):
        self.write("a.txt")
        code, text = self.run_cli("run", raw=True)
        self.assertEqual(code, 3)
        self.assertIn("no provider was named", text)

    def test_what_is_flagged_never_reaches_the_model(self):
        self.write("config.py", "TOKEN = '%s'\n" % GH_TOKEN)
        self.write(".env", "PASSWORD=hunter2hunter2\n")
        self.write("app/main.py", "print(1)\n")
        self.write("app/id_rsa", "PRIVATE-STUFF\n")
        self.write("node_modules/x/index.js", "junk()\n")
        code, text = self.run_cli("run", "--host", "claude", "--no-push", raw=True)
        self.assertEqual(code, 0, text)
        prompt = self.calls()[0]["prompt"]
        for secret in (GH_TOKEN, "hunter2", "PRIVATE-STUFF", "junk()", "config.py", ".env", "id_rsa", "node_modules"):
            self.assertNotIn(secret, prompt)
        self.assertIn("app/main.py  (new)", prompt)
        self.assertEqual(self.git("show", "--name-only", "--format=", "HEAD"), "app/main.py")
        left = text.strip().splitlines()[-1]
        self.assertTrue(left.startswith("Left out: "), text)
        for part in (".env (credentials file)", "config.py (looks like it holds a GitHub token)", "node_modules/ (belongs in .gitignore)"):
            self.assertIn(part, left)
        self.assertNotIn(GH_TOKEN, text)

    def test_include_takes_a_flagged_path_in(self):
        self.write(".env.test", "MODE=test\n")
        code, text = self.run_cli("run", "--host", "claude", "--no-push", "--include", ".env.test", raw=True)
        self.assertEqual(code, 0, text)
        self.assertEqual(self.git("show", "--name-only", "--format=", "HEAD"), ".env.test")
        self.assertNotIn("Left out", text)

    def test_a_rename_is_one_unit_and_the_index_is_left_alone(self):
        (self.repo / "seed0.txt").rename(self.repo / "renamed.txt")
        self.write("staged-by-hand.txt")
        self.git("add", "staged-by-hand.txt")
        code, text = self.run_cli("run", "--host", "claude", "--dry-run", raw=True)
        self.assertEqual(code, 0, text)
        self.assertIn("renamed.txt  (renamed from seed0.txt)", self.calls()[0]["prompt"])
        self.assertEqual(text.splitlines()[0], "Plan: 1 commit")
        self.assertEqual(self.git("status", "--porcelain").splitlines(),
                         ["D seed0.txt", "A  staged-by-hand.txt", "?? renamed.txt"], "a dry run changes nothing")
        code, text = self.run_cli("run", "--host", "claude", "--no-push", raw=True)
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertIn("seed0.txt", self.git("show", "--name-status", "--format=", "--no-renames", "HEAD"))

    def test_single_staged_and_hint(self):
        self.write("a.txt")
        self.write("b.txt")
        self.git("add", "a.txt")
        two = {"commits": [{"subject": "feat: add a", "body": [], "paths": ["a.txt"]},
                           {"subject": "feat: add b", "body": [], "paths": ["b.txt"]}]}
        code, text = self.run_cli("run", "--host", "claude", "--no-push", "--single", raw=True, env=self.answers(two, two))
        self.assertEqual(code, 3, "two commits where one was asked for is not accepted")
        code, text = self.run_cli("run", "--host", "claude", "--no-push", "--staged", "--hint", "the a file", "--lang",
                                  "Turkish", raw=True)
        self.assertEqual(code, 0, text)
        prompt = self.calls()[-1]["prompt"]
        self.assertIn("a.txt  (new)", prompt)
        self.assertNotIn("b.txt", prompt)
        for part in ("Exactly one commit", "The user says about this work: the a file", "Write in Turkish."):
            self.assertIn(part, prompt)
        self.assertEqual(self.git("status", "--porcelain"), "?? b.txt")

    def test_the_history_sets_format_and_language_for_the_model(self):
        for i, subject in enumerate(("feat(sepet): kupon desteği ekle", "fix(sepet): yuvarlamayı düzelt", "docs: kurulumu açıkla")):
            self.write("h%d.txt" % i)
            self.git("add", "-A")
            self.git("commit", "-qm", subject)
        self.write("odeme.py")
        code, text = self.run_cli("run", "--host", "agy", "--no-push", raw=True,
                                  env={"FAKE_SUBJECT": "feat(ödeme): taksit seçeneği ekle"})
        self.assertEqual((code, self.log()[0]), (0, "feat(ödeme): taksit seçeneği ekle"))
        prompt = [c for c in self.calls() if "prompt" in c][-1]["prompt"]
        for part in ("Scopes in use: sepet", "language of the HISTORY subjects", "docs: kurulumu açıkla  [h2.txt]"):
            self.assertIn(part, prompt)

    def test_a_folder_without_git_and_blockers(self):
        folder = self.tmp / "fresh"
        folder.mkdir()
        self.write("main.py", "print(1)\n", repo=folder)
        code, text = self.run_cli("run", "--host", "claude", cwd=folder, raw=True)
        self.assertEqual(code, 2)
        self.assertIn("Blocked: git does not know who you are", text)
        self.git("config", "--global", "user.name", NAME, cwd=folder)
        self.git("config", "--global", "user.email", EMAIL, cwd=folder)
        code, text = self.run_cli("run", "--host", "claude", cwd=folder, raw=True)
        self.assertEqual(code, 0, text)
        self.assertEqual(text.splitlines()[0], "Committed 1 commit locally (no remote)")
        self.assertTrue(text.splitlines()[-1].startswith("To publish: git remote add origin"))

    def test_nothing_to_commit_still_pushes_what_is_waiting(self):
        self.write("a.txt")
        self.git("add", "-A")
        self.git("commit", "-qm", "feat: made by hand earlier")
        code, text = self.run_cli("run", "--host", "claude", raw=True)
        self.assertEqual((code, text.strip()), (0, "Pushed 1 commit to origin/main"))
        self.assertEqual(self.calls(), [], "no model is asked when there is nothing to name")
        code, text = self.run_cli("run", "--host", "claude", raw=True)
        self.assertEqual(text.strip(), "Nothing to commit, nothing to push")

    def test_a_failing_hook_stops_the_run_and_is_reported(self):
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\necho 'lint: 2 errors' >&2\nexit 1\n")
        hook.chmod(hook.stat().st_mode | stat.S_IEXEC)
        self.write("a.txt")
        code, text = self.run_cli("run", "--host", "claude", raw=True)
        self.assertEqual(code, 2, text)
        self.assertIn("Committed 0 commits, then stopped", text)
        self.assertIn("lint: 2 errors", text)

    def test_json_output_names_the_model(self):
        self.write("a.txt")
        code, d = self.run_cli("run", "--host", "kiro", "--no-push", "--json")
        self.assertEqual((code, d["status"], d["model"], len(d["commits"])), (0, "committed", "kiro:claude-haiku-5.5", 1))


if __name__ == "__main__":
    unittest.main()
