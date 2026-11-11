"""End-to-end tests against fake agent CLIs.  Run:  python3 -m unittest discover -s tests/agentack -v"""

import json
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "skills" / "agentack" / "scripts" / "agentack.py"
FAKE = Path(__file__).resolve().parent / "fakecli.py"
CLIS = ("claude", "codex", "agy", "cursor-agent", "kiro-cli")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="agentack-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        for name in CLIS:           # one tiny launcher per CLI name, all running the same fake
            launcher = self.bin / name
            launcher.write_text("#!%s\nimport os, runpy\nos.environ['FAKE_NAME'] = %r\n"
                                "runpy.run_path(%r, run_name='__main__')\n" % (sys.executable, name, str(FAKE)))
            launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC)
        self.project = self.tmp / "proj"
        self.project.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "T")
        (self.project / "a.txt").write_text("one\n")
        self.git("add", ".")
        self.git("commit", "-qm", "init")
        self.brief = self.project / ".brief.md"
        self.brief.write_text("Do the thing.\n")
        self.env = {
            "PATH": "%s:/usr/bin:/bin" % self.bin, "HOME": str(self.tmp / "home"),
            "XDG_CONFIG_HOME": str(self.tmp / "cfg"), "XDG_STATE_HOME": str(self.tmp / "state"),
            "CLAUDE_CONFIG_DIR": str(self.tmp / "home" / ".claude"),
            "FAKE_LOG": str(self.tmp / "fake.log"),
        }
        (self.tmp / "home").mkdir()

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.project), *args], check=True, capture_output=True)

    def run_cli(self, *args, env=None, stdin=None, raw=False):
        p = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True,
                           cwd=str(self.project), env={**self.env, **(env or {})}, input=stdin)
        if raw:
            return p.returncode, p.stdout
        try:
            return p.returncode, json.loads(p.stdout)
        except json.JSONDecodeError:
            self.fail("not JSON (exit %s): %s\n%s" % (p.returncode, p.stdout, p.stderr))

    def setup_providers(self, providers, *extra):
        code, data = self.run_cli("setup", "--providers", providers, *extra)
        self.assertEqual(code, 0, data)
        return data

    def go(self, role, *extra, env=None, host="codex"):
        """dispatch + wait; returns the finished run row."""
        code, d = self.run_cli("dispatch", "--role", role, "--brief", self.brief, "--host", host, *extra, env=env)
        self.assertEqual(code, 0, d)
        code, w = self.run_cli("wait", d["run_id"], "--timeout", 30, env=env)
        self.assertTrue(w["all_finished"], w)
        return w["runs"][0]

    def fake_log(self):
        path = Path(self.env["FAKE_LOG"])
        return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []

    def primary(self, data, role):
        return next(r for r in data["roster"] if r["role"] == role)["primary"]


class SetupTest(Base):
    def test_detect_finds_all(self):
        code, d = self.run_cli("detect")
        self.assertEqual({p["name"] for p in d["providers"] if p["installed"]},
                         {"claude", "codex", "agy", "cursor", "kiro"})
        self.assertFalse(d["configured"])

    def test_auth_is_a_hint_and_ping_is_the_test(self):
        auth = lambda env=None: {p["name"]: p.get("auth") for p in self.run_cli("detect", env=env)[1]["providers"]}  # noqa: E731
        self.assertEqual(auth()["kiro"], "ok", "a logged-in kiro session counts without KIRO_API_KEY")
        self.assertEqual(auth({"FAKE_KIRO_LOGIN": "no"})["kiro"], "not signed in")
        self.assertEqual(auth()["agy"], "ok")
        self.setup_providers("kiro,agy")
        code, d = self.run_cli("doctor", "--ping")
        self.assertEqual({p["name"]: p["ping"]["ok"] for p in d["providers"]}, {"kiro": True, "agy": True})
        code, d = self.run_cli("doctor", "--ping", env={"FAKE_AGY": "error"})
        agy = next(p for p in d["providers"] if p["name"] == "agy")
        self.assertFalse(agy["ping"]["ok"])
        self.assertIn("boom", agy["ping"]["error"])

    def test_unconfigured_dispatch_asks_for_setup(self):
        code, d = self.run_cli("dispatch", "--role", "scout", "--brief", self.brief)
        self.assertEqual(code, 3)
        self.assertIn("not set up", d["error"])

    def test_single_provider_covers_every_role(self):
        d = self.setup_providers("codex")
        self.assertTrue(d["single_provider"])
        self.assertEqual(d["notes"], [])
        self.assertEqual(self.primary(d, "decider"), "codex:gpt-6-astra@high")
        self.assertEqual(self.primary(d, "reviewer"), "codex:gpt-6.1-sol@high")
        self.assertEqual(self.primary(d, "be-go"), "codex:gpt-6.1-sol@medium")
        self.assertEqual(self.primary(d, "scout"), "codex:gpt-6-luna@low")
        self.assertFalse(d["second_opinion"])

    def test_two_providers_reviewer_on_other_vendor(self):
        d = self.setup_providers("claude,codex")
        self.assertEqual(self.primary(d, "fe-next"), "claude:sonnet")
        self.assertEqual(self.primary(d, "reviewer"), "codex:gpt-6.1-sol@high")
        self.assertEqual(self.primary(d, "architect"), "claude:opus")
        self.assertTrue(d["second_opinion"])

    def test_agy_models_come_from_listing(self):
        d = self.setup_providers("agy")
        self.assertEqual(self.primary(d, "decider"), "agy:gemini-4-argon-high")
        self.assertEqual(self.primary(d, "reviewer"), "agy:gemini-4-argon-high", "Argon is the code model")
        self.assertEqual(self.primary(d, "qa"), "agy:gemini-3.1-pro-high", "build runs on Pro, not Flash")
        self.assertEqual(self.primary(d, "scout"), "agy:gemini-3.8-flash-medium", "mechanical runs on Flash")
        self.assertFalse(any("lite" in (r["primary"] or "") for r in d["roster"]), "Flash-Lite is never used")

    KARBON = "gemini-4-karbon-high,gemini-4-argon-high,gemini-3.1-pro-high,gemini-3.8-flash-medium,gemini-3.5-flash-lite"

    def test_agy_prefers_karbon_and_falls_back_to_argon_when_it_is_locked(self):
        env = {"FAKE_AGY_MODELS": self.KARBON}
        code, d = self.run_cli("setup", "--providers", "agy", env=env)
        self.assertEqual(self.primary(d, "decider"), "agy:gemini-4-karbon-high")
        self.assertEqual(self.primary(d, "architect"), "agy:gemini-4-argon-high")
        code, d = self.run_cli("verify", env={**env, "FAKE_AGY_NO_MODELS": "gemini-4-karbon-high"})
        self.assertEqual(d["removed"], ["agy:gemini-4-karbon-high (S4)"])
        row = next(r for r in d["roster"] if r["role"] == "decider")
        self.assertEqual((row["primary"], row["substituted"]), ("agy:gemini-4-argon-high", False))

    def test_auto_only_provider_still_runs_and_says_so(self):
        d = self.setup_providers("kiro")
        row = next(r for r in d["roster"] if r["role"] == "reviewer")
        self.assertEqual(row["primary"], "kiro:auto")
        self.assertIn("Auto model", row["note"])
        self.assertEqual(self.go("reviewer")["status"], "done")
        d = self.setup_providers("kiro", "--model", "kiro:S3=claude-opus-5.5")
        self.assertEqual(self.primary(d, "reviewer"), "kiro:claude-opus-5.5")
        self.assertEqual(self.primary(d, "decider"), "kiro:claude-opus-5.5")   # no S4: S3 stands in

    def test_check_conductor(self):
        self.setup_providers("claude,codex")
        ok = lambda h, m: self.run_cli("check-conductor", "--host", h, "--model", m)[1]["ok"]  # noqa: E731
        self.assertTrue(ok("claude", "claude-opus-5-5"))
        self.assertFalse(ok("claude", "claude-sonnet-5-5"))
        self.assertTrue(ok("codex", "gpt-6.1-sol"))
        self.assertFalse(ok("codex", "gpt-6-luna"))
        self.setup_providers("agy")
        self.assertTrue(ok("agy", "Gemini 4 Argon"))
        self.assertTrue(ok("agy", "Gemini 3.1 Pro"))
        self.assertTrue(ok("agy", "gemini-4-argon-high"))
        self.assertFalse(ok("agy", "Gemini 3.8 Flash"))

    def test_antigravity_can_conduct_with_cli_workers(self):
        self.setup_providers("agy,claude")
        code, d = self.run_cli("dispatch", "--role", "architect", "--brief", self.brief, "--host", "agy")
        self.assertEqual((d["via"], d["provider"]), ("cli", "agy"))
        code, d = self.run_cli("detect")
        self.assertTrue(next(p for p in d["providers"] if p["name"] == "agy")["can_conduct"])

    def test_roster_markdown(self):
        self.setup_providers("claude")
        code, text = self.run_cli("roster", "--md", raw=True)
        self.assertIn("| reviewer | S3 plan & review | claude:opus | 5/5 review | goal |", text)


class GuidanceTest(Base):
    """Setup is tailored to the machine: detect describes it, next_steps says what to fix."""

    def test_detect_describes_the_machine(self):
        code, d = self.run_cli("detect")
        env = d["environment"]
        self.assertEqual((env["git_repo"], env["project_guide"]), (True, None))
        kiro = next(p for p in d["providers"] if p["name"] == "kiro")
        self.assertEqual(kiro["sign_in"], "kiro-cli login")

    def test_broken_provider_gets_an_exact_fix(self):
        self.setup_providers("claude,codex")
        code, d = self.run_cli("verify", env={"FAKE_CODEX": "error"})
        step = next(s for s in d["next_steps"] if s.get("provider") == "codex")
        self.assertEqual((step["level"], step["kind"], step["then"]), ("action", "unknown", "/agentack verify"))
        self.assertIn("run `codex` once by hand", step["fix"], "an unexplained failure is not blamed on sign-in")
        code, text = self.run_cli("roster", "--md", raw=True)
        self.assertIn("→ Codex is set aside", text)
        self.assertIn("Fix: run `codex` once by hand", text)

    def test_signed_out_provider_is_told_to_sign_in(self):
        self.setup_providers("claude,kiro")
        code, d = self.run_cli("verify", env={"FAKE_KIRO_LOGIN": "no", "FAKE_KIRO": "error"})
        step = next(s for s in d["next_steps"] if s.get("provider") == "kiro")
        self.assertEqual((step["kind"], step["fix"]), ("sign-in", "kiro-cli login"))
        self.assertEqual(d["summary"]["set_aside"], ["kiro"])

    def test_summary_states_who_does_what(self):
        code, d = self.run_cli("setup", "--providers", "claude,codex", "--fallback", "on", "--brief")
        self.assertNotIn("roster", d)
        code, d = self.run_cli("verify", env={"FAKE_CODEX_NO_MODELS": "gpt-6-astra"})
        s = d["summary"]
        self.assertEqual((s["builds"], s["reviews"], s["review_is_independent"]),
                         ("claude:sonnet", "codex:gpt-6.1-sol@high", True))
        self.assertEqual((s["decides"], s["second_opinion"]), ("claude:fable", None))
        self.assertEqual((s["limit_fallback"], s["usage_measured_for"]), ("on, switch at 85%", ["codex"]))

    def test_missing_project_guide_and_single_provider_are_pointed_out(self):
        self.setup_providers("claude")
        code, d = self.run_cli("verify")
        texts = [s["text"] for s in d["next_steps"]]
        self.assertTrue(any("no CLAUDE.md / AGENTS.md" in t for t in texts))
        self.assertTrue(any("one provider in use" in t for t in texts))
        (self.project / "AGENTS.md").write_text("# guide\n")
        code, d = self.run_cli("roster")
        self.assertFalse(any(s["level"] == "action" for s in d["next_steps"]))

    def test_fallback_measurement_gaps_are_explained(self):
        self.setup_providers("claude,cursor", "--fallback", "on")
        code, d = self.run_cli("roster")
        texts = " ".join(s["text"] for s in d["next_steps"])
        self.assertIn("Claude usage is not measured", texts)
        self.assertIn("Cursor usage cannot be measured", texts)
        self.run_cli("hook", "install")
        code, d = self.run_cli("roster")
        self.assertNotIn("Claude usage is not measured", " ".join(s["text"] for s in d["next_steps"]))


class DispatchTest(Base):
    def test_each_provider_runs_and_returns_text(self):
        for prov, cli, model in (("codex", "codex", "gpt-6.1-sol"), ("agy", "agy", "gemini-3.1-pro-high"),
                                 ("cursor", "cursor-agent", "cursor-composer-2-5"), ("kiro", "kiro-cli", "auto"),
                                 ("claude", "claude", "sonnet")):
            self.setup_providers(prov, "--reset")
            row = self.go("be-go")
            self.assertEqual(row["status"], "done", row)
            code, text = self.run_cli("result", row["id"], raw=True)
            self.assertIn("%s:%s finished the task" % (cli, model), text)
        calls = {c["cli"]: c for c in self.fake_log()}
        self.assertIn("workspace-write", calls["codex"]["argv"])
        self.assertIn('model_reasoning_effort="medium"', calls["codex"]["argv"])
        self.assertIn("--force", calls["cursor-agent"]["argv"])
        self.assertIn("acceptEdits", calls["claude"]["argv"])
        self.assertTrue(all(c["prompt_has_brief"] for c in calls.values()))

    def test_read_only_roles(self):
        self.setup_providers("codex")
        self.go("reviewer")
        call = self.fake_log()[-1]
        self.assertIn("read-only", call["argv"])
        self.assertTrue(call["prompt_read_only"])

    def test_native_subagent_on_claude_host(self):
        self.setup_providers("claude,codex")
        code, d = self.run_cli("dispatch", "--role", "be-node", "--brief", self.brief, "--host", "claude")
        self.assertEqual((d["via"], d["model"]), ("native", "sonnet"))
        self.assertTrue(d["role_file"].endswith("roles/be-node.md"))
        code, d = self.run_cli("dispatch", "--role", "reviewer", "--brief", self.brief, "--host", "claude")
        self.assertEqual((d["via"], d["provider"]), ("cli", "codex"))

    def test_read_only_violation_is_reported(self):
        self.setup_providers("agy")
        row = self.go("reviewer", env={"FAKE_AGY": "edit"})
        self.assertEqual(row["status"], "done")
        self.assertIn("touched-by-agy.txt", " ".join(row["violation"]["files"]))

    def test_plain_error_is_not_a_limit(self):
        self.setup_providers("claude,codex", "--fallback", "on")
        row = self.go("be-go", env={"FAKE_CLAUDE": "error"})
        self.assertEqual(row["status"], "error")
        self.assertIn("boom", row["error"])

    def test_timeout(self):
        self.setup_providers("codex")
        row = self.go("scout", "--timeout", "0.02", env={"FAKE_CODEX": "slow"})
        self.assertEqual(row["status"], "timeout")

    def test_project_allowlist(self):
        self.setup_providers("claude,codex")
        (self.project / ".agentack.json").write_text(json.dumps({"allowed_providers": ["codex"]}))
        self.assertEqual(self.go("fe-next")["provider"], "codex")

    def test_report(self):
        self.setup_providers("codex")
        self.go("scout")
        code, d = self.run_cli("report")
        self.assertEqual(d["runs"], {"scout -> codex:gpt-6-luna": 1})
        self.assertEqual((d["switches"], d["problems"]), ([], []))

    def test_new_brief_numbers_files(self):
        self.setup_providers("codex")
        code, a = self.run_cli("new-brief", "architect")
        code, b = self.run_cli("new-brief", "be-go")
        self.assertTrue(a["path"].endswith(".agentack/briefs/01-architect.md"))
        self.assertTrue(b["path"].endswith(".agentack/briefs/02-be-go.md"))
        self.assertIn("# Brief · be-go", Path(b["path"]).read_text())
        self.assertEqual((self.project / ".agentack" / ".gitignore").read_text(), "*\n")


class MissingModelTest(Base):
    """A model the account does not have is skipped silently; nobody is asked anything."""
    NO_ARGON = {"FAKE_AGY_MODELS": "gemini-3.8-flash-medium,gemini-3.8-flash-high,gemini-3.5-flash-lite"}

    def chain(self, data, role):
        row = next(r for r in data["roster"] if r["role"] == role)
        return [row["primary"]] + row["fallbacks"]

    def test_listing_without_the_model_uses_other_providers(self):
        code, d = self.run_cli("setup", "--providers", "claude,codex,agy", env=self.NO_ARGON)
        self.assertEqual(self.chain(d, "decider"), ["claude:fable", "codex:gpt-6-astra@high"])
        self.assertEqual(self.chain(d, "architect"), ["claude:opus", "codex:gpt-6.1-sol@high"])
        self.assertEqual(self.chain(d, "be-go")[-1], "agy:gemini-3.8-flash-high", "build falls to Flash, last")
        self.assertTrue(any("gemini-4-argon (S4) is not available" in n for n in d["notes"]))

    def test_verify_heals_a_roster_saved_with_a_model_the_listing_lacks(self):
        self.setup_providers("claude,agy")                      # saved while Argon was listed
        code, d = self.run_cli("verify", env=self.NO_ARGON)     # the account no longer lists it
        self.assertIn("agy:gemini-4-argon-high (S4)", d["removed"])
        self.assertEqual(self.chain(d, "decider"), ["claude:fable"])

    def test_tier_missing_everywhere_drops_to_the_next_one(self):
        code, d = self.run_cli("setup", "--providers", "agy", env=self.NO_ARGON)
        row = next(r for r in d["roster"] if r["role"] == "decider")
        self.assertEqual((row["primary"], row["runs_on"], row["substituted"]),
                         ("agy:gemini-3.8-flash-high", "S2", True))
        self.assertEqual(self.go("decider", env=self.NO_ARGON)["status"], "done")

    def test_verify_prunes_models_the_account_lacks(self):
        self.setup_providers("claude,codex")
        code, d = self.run_cli("verify", env={"FAKE_CLAUDE_NO_MODELS": "fable"})
        self.assertEqual(d["removed"], ["claude:fable (S4)"])
        self.assertEqual(self.chain(d, "decider"), ["codex:gpt-6-astra@high"], "same tier, other provider")
        self.assertEqual(self.chain(d, "architect")[0], "claude:opus")
        # with nobody offering S4, the decider runs one tier down
        code, d = self.run_cli("verify", env={"FAKE_CLAUDE_NO_MODELS": "fable", "FAKE_CODEX_NO_MODELS": "gpt-6-astra"})
        row = next(r for r in d["roster"] if r["role"] == "decider")
        self.assertEqual((row["primary"], row["runs_on"]), ("claude:opus", "S3"))

    def test_sign_in_failure_is_not_treated_as_missing_model(self):
        self.setup_providers("claude,codex")
        code, d = self.run_cli("verify", env={"FAKE_CODEX": "error"})
        self.assertEqual(d["removed"], [])
        self.assertEqual(len([c for c in d["checked"] if c["provider"] == "codex"]), 1, "stops after one ping")
        self.assertEqual(self.chain(d, "reviewer"), ["claude:opus"], "the failing provider is set aside")
        self.assertTrue(any("codex is set aside" in n for n in d["notes"]))
        code, d = self.run_cli("verify")
        self.assertEqual(self.chain(d, "reviewer")[0], "codex:gpt-6.1-sol@high", "and comes back when it works")

    def test_refused_at_run_time_moves_on_without_fallback_setting(self):
        self.setup_providers("claude,codex", "--fallback", "off")
        env = {"FAKE_CLAUDE_NO_MODELS": "fable"}
        row = self.go("decider", env=env)
        self.assertEqual((row["status"], row["provider"], row["model"]), ("done", "codex", "gpt-6-astra"))
        self.assertEqual(row["attempts"][0]["outcome"], "model unavailable")
        code, d = self.run_cli("resolve", "--role", "decider", env=env)
        self.assertEqual(d["provider"], "codex", "remembered: no second try on the missing model")
        code, d = self.run_cli("resolve", "--role", "architect", env=env)
        self.assertEqual(d["model"], "opus", "other Claude models are unaffected")

    def test_codex_model_refused_for_chatgpt_accounts(self):
        self.setup_providers("codex,claude")
        code, d = self.run_cli("verify", env={"FAKE_CODEX_NO_MODELS": "gpt-6-astra"})
        self.assertEqual(d["removed"], ["codex:gpt-6-astra (S4)"])
        refused = next(c for c in d["checked"] if c["model"] == "gpt-6-astra")
        self.assertIn("not supported when using Codex with a ChatGPT account", refused["error"])
        self.assertEqual(self.chain(d, "decider"), ["claude:fable"])
        self.assertEqual(self.chain(d, "be-go")[0], "codex:gpt-6.1-sol@medium", "the rest of Codex stays")
        self.assertTrue(d["verified"])

    def test_codex_listing_drops_models_before_any_ping(self):
        code, d = self.run_cli("setup", "--providers", "codex,claude", env={"FAKE_CODEX_MODELS": "gpt-6.1-sol,gpt-6-luna"})
        self.assertEqual(self.chain(d, "decider"), ["claude:fable"])
        self.assertFalse(d["verified"])
        # an older Sol stands in when the default one is not listed
        code, d = self.run_cli("setup", "--providers", "codex", "--reset", env={"FAKE_CODEX_MODELS": "gpt-5.6-sol,gpt-6-luna"})
        self.assertEqual(self.chain(d, "reviewer"), ["codex:gpt-5.6-sol@high"])

    def test_log_noise_about_other_models_is_not_a_refusal(self):
        self.setup_providers("codex,claude")
        row = self.go("be-go", env={"FAKE_CODEX": "error_noise"})
        self.assertEqual((row["status"], row["provider"]), ("error", "codex"))
        code, d = self.run_cli("roster")
        self.assertEqual(self.chain(d, "be-go")[0], "codex:gpt-6.1-sol@medium")

    def test_available_model_is_never_downgraded(self):
        self.setup_providers("claude")
        code, d = self.run_cli("resolve", "--role", "decider")
        self.assertEqual((d["model"], d.get("substituted")), ("fable", None))


class StrengthsTest(Base):
    """Providers do what they are good at: weak fits go last, specialties go to the best."""

    def chain(self, data, role):
        row = next(r for r in data["roster"] if r["role"] == role)
        return [row["primary"]] + row["fallbacks"]

    def test_gemini_reviews_and_plans_but_writes_code_only_as_a_last_resort(self):
        d = self.setup_providers("agy,claude,codex")            # the user even put Gemini first
        self.assertEqual(self.chain(d, "architect")[0], "agy:gemini-4-argon-high")
        self.assertEqual(self.chain(d, "decider")[0], "agy:gemini-4-argon-high")
        for role in ("be-go", "fe-next", "qa", "scout"):
            chain = self.chain(d, role)
            self.assertTrue(chain[0].startswith("claude:"), role)
            self.assertTrue(chain[-1].startswith("agy:"), role + ": weak fit is the last resort")
        self.assertTrue(self.chain(d, "reviewer")[0].startswith("agy:"), "review off the builders' vendor")

    def test_single_weak_provider_still_works_and_says_so(self):
        d = self.setup_providers("agy")
        row = next(r for r in d["roster"] if r["role"] == "be-go")
        self.assertEqual((row["fit"], row["skill"]), (2, "backend"))
        self.assertIn("weak at this kind of work", row["note"])
        self.assertTrue(any("rated weak" in s["text"] for s in d["next_steps"]) if "next_steps" in d else True)
        self.assertEqual(self.go("be-go")["weak_fit"], True)

    def test_visual_specialty_goes_to_the_best_rated(self):
        self.setup_providers("claude,codex,agy")
        code, d = self.run_cli("resolve", "--role", "reviewer", "--skill", "visual")
        self.assertEqual((d["provider"], d["fit"]), ("agy", 5))
        code, d = self.run_cli("resolve", "--role", "reviewer")
        self.assertEqual(d["provider"], "codex")

    def test_user_can_rerate_a_provider(self):
        self.setup_providers("agy,claude")
        code, d = self.run_cli("setup", "--rate", "agy:backend=4")
        self.assertTrue(self.chain(d, "be-go")[0].startswith("agy:"))
        code, e = self.run_cli("setup", "--rate", "agy:backend=9")
        self.assertEqual(code, 2)

    def test_scorecard_and_suggested_order(self):
        code, d = self.run_cli("detect")
        self.assertEqual(d["suggested_order"][:2], ["claude", "codex"])
        self.setup_providers("claude,agy")
        code, text = self.run_cli("strengths", "--md", raw=True)
        self.assertIn("| agy | 4 | 4 | 4 | 5 | 2 | 2 | 2 | 2 |", text)
        self.assertIn("Ratings reviewed:", text)


class BriefStyleTest(Base):
    """Each model is briefed the way it works best; the strongest one gets a question and evidence."""

    def style(self, data, role):
        return next(r for r in data["roster"] if r["role"] == role)["style"]

    def test_styles_follow_the_model(self):
        d = self.setup_providers("claude")
        self.assertEqual([self.style(d, r) for r in ("decider", "architect", "be-go", "scout")],
                         ["peer", "goal", "structured", "rules"])
        d = self.setup_providers("codex")
        self.assertEqual([self.style(d, r) for r in ("decider", "reviewer", "be-go", "scout")],
                         ["peer", "explicit", "explicit", "rules"])
        d = self.setup_providers("kiro")
        self.assertEqual(self.style(d, "be-go"), "explicit", "an Auto router is briefed with nothing implicit")

    def test_style_can_be_overridden_per_tier(self):
        self.setup_providers("codex")
        code, d = self.run_cli("setup", "--style", "codex:S2=structured")
        self.assertEqual(self.style(d, "be-go"), "structured")
        code, e = self.run_cli("setup", "--style", "codex:S9=goal")
        self.assertEqual(code, 2)

    def test_new_brief_uses_the_template_for_that_model(self):
        self.setup_providers("claude,codex")
        for role, style, marker in (("be-go", "structured", "## Steps"), ("architect", "goal", "## Done looks like"),
                                    ("reviewer", "explicit", "## Steps (do them in order"),
                                    ("scout", "rules", "## Examples"), ("decider", "peer", "## Evidence")):
            code, b = self.run_cli("new-brief", role)
            self.assertEqual(b["style"], style, role)
            self.assertIn(marker, Path(b["path"]).read_text(), role)
            self.assertTrue(b["put_in"])

    def test_decider_brief_stays_a_peer_brief_when_no_s4_exists(self):
        self.setup_providers("claude")
        code, d = self.run_cli("verify", env={"FAKE_CLAUDE_NO_MODELS": "fable"})
        code, b = self.run_cli("new-brief", "decider")
        self.assertEqual((b["style"], b["model"]), ("peer", "claude:opus"))

    def test_worker_is_told_how_to_work_and_expands_a_looser_brief_after_a_switch(self):
        self.setup_providers("claude,codex", "--fallback", "on")
        code, b = self.run_cli("new-brief", "architect")                 # written for Opus: goal style
        Path(b["path"]).write_text(Path(b["path"]).read_text() + "\nDesign the invoice list.\n")
        code, d = self.run_cli("dispatch", "--role", "architect", "--brief", b["path"], "--host", "codex",
                               env={"FAKE_CLAUDE": "limit"})
        self.run_cli("wait", d["run_id"], "--timeout", 30, env={"FAKE_CLAUDE": "limit"})
        first, second = self.fake_log()[-2:]
        self.assertIn("You have latitude", first["how"])
        self.assertFalse(first["expand"])
        self.assertEqual(second["cli"], "codex")
        self.assertIn("step by step", second["how"])
        self.assertTrue(second["expand"], "Sol gets a goal-style brief: it must spell the steps out first")


class LimitTest(Base):
    def test_fallback_on_switches_and_remembers(self):
        self.setup_providers("claude,codex", "--fallback", "on")
        row = self.go("be-go", env={"FAKE_CLAUDE": "limit"})
        self.assertEqual((row["status"], row["provider"]), ("done", "codex"))
        self.assertTrue(row["switched"])
        self.assertEqual([a["outcome"] for a in row["attempts"]], ["limit", "done"])
        self.assertTrue(self.fake_log()[-1]["prompt_has_previous"])
        code, rep = self.run_cli("report")
        self.assertEqual(rep["runs"], {"be-go -> codex:gpt-6.1-sol": 1}, "credited to who finished it")
        self.assertEqual([(x["role"], x["instead_of"]) for x in rep["switches"]], [("be-go", ["claude"])])
        code, lim = self.run_cli("limits")
        claude = next(p for p in lim["providers"] if p["provider"] == "claude")
        self.assertFalse(claude["available"])
        # the next task goes straight to the other provider, without asking anyone
        code, d = self.run_cli("resolve", "--role", "architect")
        self.assertEqual((d["provider"], d["switched"]), ("codex", True))
        self.assertIn("limit reached", d["skipped"][0]["reason"])

    def test_fallback_off_never_switches(self):
        self.setup_providers("claude,codex", "--fallback", "off")
        row = self.go("be-go", env={"FAKE_CLAUDE": "limit"})
        self.assertEqual(row["status"], "limit")
        self.assertEqual(len(self.fake_log()), 1)
        code, d = self.run_cli("resolve", "--role", "be-go")
        self.assertEqual(d["provider"], "claude", "recorded limits are ignored while the feature is off")

    def test_gate_roles_are_never_downgraded(self):
        self.setup_providers("claude", "--fallback", "on")
        row = self.go("be-go", env={"FAKE_CLAUDE": "limit"})
        self.assertEqual(row["status"], "limit")
        code, e = self.run_cli("resolve", "--role", "reviewer")
        self.assertEqual(code, 3)
        self.assertIn("never downgraded", e["error"])

    def test_builder_may_drop_one_tier(self):
        self.setup_providers("claude,kiro", "--fallback", "on")
        cfg_path = Path(self.env["XDG_CONFIG_HOME"]) / "agentack" / "config.json"
        cfg = json.loads(cfg_path.read_text())
        cfg["providers"]["kiro"]["tiers"]["S2"] = None        # kiro only has an S1 model here
        cfg_path.write_text(json.dumps(cfg))
        self.go("scout", env={"FAKE_CLAUDE": "limit"})        # records the Claude limit
        code, d = self.run_cli("resolve", "--role", "be-go")
        self.assertEqual((d["provider"], d["tier"], d["dropped"]), ("kiro", "S1", True))
        self.run_cli("setup", "--drop-tier", "off")
        code, e = self.run_cli("resolve", "--role", "be-go")
        self.assertEqual(code, 3)

    def test_measured_usage_triggers_switch(self):
        self.setup_providers("claude,codex", "--fallback", "on", "--threshold", "80")
        payload = {"model": {"display_name": "Opus"},
                   "rate_limits": {"five_hour": {"used_percentage": 91}, "seven_day": {"used_percentage": 12}}}
        code, line = self.run_cli("statusline", stdin=json.dumps(payload), raw=True)
        self.assertIn("5h 91%", line)
        code, d = self.run_cli("resolve", "--role", "be-go")
        self.assertEqual(d["provider"], "codex")
        self.assertIn("5h usage 91% >= 80%", d["skipped"][0]["reason"])
        # Codex is measured through its app-server
        code, lim = self.run_cli("limits", "--refresh", env={"FAKE_CODEX_USED": "97"})
        codex = next(p for p in lim["providers"] if p["provider"] == "codex")
        self.assertEqual((codex["available"], codex["source"]), (False, "probe"))

    def test_kiro_usage_is_measured(self):
        self.setup_providers("claude,kiro", "--fallback", "on")
        code, lim = self.run_cli("limits", "--refresh", env={"FAKE_KIRO_SPENT": "48"})
        kiro = next(p for p in lim["providers"] if p["provider"] == "kiro")
        self.assertEqual((kiro["available"], kiro["source"]), (False, "probe"))
        self.assertEqual(kiro["usage"]["month"]["used"], 96.0)
        self.assertIn("month usage 96% >= 85%", kiro["reason"])

    def test_antigravity_quota_parser_and_probe_failure_is_harmless(self):
        sys.path.insert(0, str(SCRIPT.parent))
        from agentack_core.providers import parse_quota_summary
        data = {"groups": [
            {"displayName": "Gemini (Flash and Pro)", "buckets": [
                {"bucketId": "five_hour", "displayName": "Five-hour limit", "remaining": {"remainingFraction": 0.25}},
                {"bucketId": "weekly", "displayName": "Weekly limit", "remaining": {"remainingFraction": 0.9}}]},
            {"displayName": "Claude and GPT", "buckets": [
                {"bucketId": "weekly", "displayName": "Weekly limit", "remaining": {"remainingFraction": 0.0}}]}]}
        w = parse_quota_summary(data)
        self.assertEqual((w["5h"]["used"], w["7d"]["used"]), (75.0, 10.0), "only the Gemini group counts")
        self.setup_providers("agy,claude", "--fallback", "on")
        code, lim = self.run_cli("limits", "--refresh")        # the fake agy has no quota server
        agy = next(p for p in lim["providers"] if p["provider"] == "agy")
        self.assertTrue(agy["available"])

    def test_reviewer_independence(self):
        self.setup_providers("claude,codex")
        code, d = self.run_cli("resolve", "--role", "reviewer", "--avoid", "codex")
        self.assertEqual((d["provider"], d["independent"]), ("claude", True))
        code, d = self.run_cli("resolve", "--role", "reviewer", "--avoid", "claude,codex")
        self.assertFalse(d["independent"])
        self.assertIn("no other vendor", d["independence_note"])

    def test_statusline_hook_keeps_existing_command(self):
        self.setup_providers("claude")
        settings = Path(self.env["CLAUDE_CONFIG_DIR"]) / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"statusLine": {"type": "command", "command": "echo mine"}, "x": 1}))
        self.run_cli("hook", "install")
        self.assertIn("agentack.py statusline", json.loads(settings.read_text())["statusLine"]["command"])
        code, line = self.run_cli("statusline", stdin="{}", raw=True)
        self.assertEqual(line.strip(), "mine")
        self.run_cli("hook", "remove")
        data = json.loads(settings.read_text())
        self.assertEqual((data["statusLine"]["command"], data["x"]), ("echo mine", 1))


class WorktreeTest(Base):
    def test_add_apply_remove_without_commits(self):
        code, d = self.run_cli("worktree", "add", "fe")
        self.assertTrue(d["ok"], d)
        wt = Path(d["path"])
        (wt / "a.txt").write_text("one\ntwo\n")
        (wt / "new.txt").write_text("hello\n")
        (self.project / "staged.txt").write_text("user work\n")
        self.git("add", "staged.txt")
        code, d = self.run_cli("worktree", "apply", "fe", "--remove")
        self.assertTrue(d["ok"] and d["changed"], d)
        self.assertEqual(sorted(d["files"]), ["a.txt", "new.txt"])
        self.assertEqual((self.project / "a.txt").read_text(), "one\ntwo\n")
        self.assertFalse(wt.exists())
        log = subprocess.run(["git", "-C", str(self.project), "log", "--oneline"], capture_output=True, text=True)
        self.assertEqual(len(log.stdout.splitlines()), 1, "no commits were created")
        staged = subprocess.run(["git", "-C", str(self.project), "diff", "--cached", "--name-only"],
                                capture_output=True, text=True).stdout.split()
        self.assertEqual(staged, ["staged.txt"], "the user's staged work is untouched")


if __name__ == "__main__":
    unittest.main()
