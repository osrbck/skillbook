"""End-to-end tests with fake provider CLIs.  Run:  python3 -m unittest discover -s tests/deepsearch -v"""

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
SCRIPT = ROOT / "skills" / "deepsearch" / "scripts" / "deepsearch.py"
FAKE = Path(__file__).resolve().parent / "fakecli.py"
sys.path.insert(0, str(SCRIPT.parent))
import deepsearch as helper  # noqa: E402

ALL = ("claude", "codex", "agy", "kiro-cli")


class Base(unittest.TestCase):
    clis = ALL

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="deepsearch-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.work = self.tmp / "work"
        bin_dir = self.tmp / "bin"
        for d in (self.work, bin_dir, self.tmp / "home"):
            d.mkdir()
        for name in self.clis:
            launcher = bin_dir / name
            launcher.write_text("#!%s\nimport os, runpy\nos.environ['FAKE_NAME'] = %r\n"
                                "runpy.run_path(%r, run_name='__main__')\n" % (sys.executable, name, str(FAKE)))
            launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC)
        # a PATH with python and the fakes only: no real agent CLI of this machine can leak in
        system = os.pathsep.join(d for d in ("/usr/bin", "/bin") if os.path.isdir(d))
        self.env = {"PATH": "%s%s%s" % (bin_dir, os.pathsep, system), "HOME": str(self.tmp / "home"),
                    "XDG_CONFIG_HOME": str(self.tmp / "home" / ".config"), "FAKE_LOG": str(self.tmp / "fake.log"),
                    "DEEPSEARCH_OFFLINE": "1"}                 # no test opens a real link

    def run_cli(self, *args, env=None, raw=False):
        p = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], cwd=str(self.work),
                           env={**self.env, **(env or {})}, capture_output=True, text=True, encoding="utf-8")
        if raw:
            return p.returncode, p.stdout
        try:
            return p.returncode, json.loads(p.stdout)
        except json.JSONDecodeError:
            self.fail("not JSON (exit %s): %s\n%s" % (p.returncode, p.stdout, p.stderr))

    def calls(self, **match):
        path = Path(self.env["FAKE_LOG"])
        rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
        return [r for r in rows if all(r.get(k) == v for k, v in match.items())]

    def start(self, degree="low", topic="Solid-state batteries", *extra, env=None):
        code, d = self.run_cli("start", "--degree", degree, "--topic", topic, *extra, env=env)
        self.assertEqual(code, 0, d)
        return Path(d["run"]), d

    def fill(self, run):
        plan = run / "plan.md"
        plan.write_text(re.sub(r"\[\[.*?\]\]", "filled in", plan.read_text(encoding="utf-8")), encoding="utf-8")

    def drive(self, run, env=None, limit=12):
        """advance and wait until the helper asks for the final document; returns every advance answer."""
        answers = []
        for _ in range(limit):
            code, d = self.run_cli("advance", "--run", run, env=env)
            self.assertEqual(code, 0, d)
            answers.append(d)
            if d["stage"] in ("reflect", "done") or "write" in d or d.get("yours"):
                return answers
            code, w = self.run_cli("wait", "--run", run, "--timeout", 60, env=env)
            self.assertTrue(w["finished"], w)
        self.fail("the run did not finish: %s" % answers[-1])


class Roster(Base):
    def test_default_teams_grow_with_the_degree_and_reviewers_stay_on_top(self):
        code, d = self.run_cli("roster")
        self.assertEqual(code, 0)
        self.assertEqual([d["degrees"][x]["agents"] for x in ("low", "medium", "hard")], [3, 5, 6])
        self.assertEqual([d["degrees"][x]["cycles"] for x in ("low", "medium", "hard")], [1, 2, 3])
        for degree, tier in (("low", "fast"), ("medium", "deep"), ("hard", "top")):
            team = d["degrees"][degree]["team"]
            self.assertEqual({t["tier"] for t in team if t["agent"].startswith("researcher")}, {tier}, degree)
            self.assertEqual({t["tier"] for t in team if t["agent"].startswith(("reviewer", "panel"))}, {"top"}, degree)
        hard = d["degrees"]["hard"]["team"]
        self.assertEqual([t["provider"] for t in hard[:3]], ["claude", "codex", "agy"], "researchers are spread")
        writers = {x: [t["tier"] for t in d["degrees"][x]["team"] if t["agent"] == "writer-1"] for x in ("low", "medium", "hard")}
        self.assertEqual(writers, {"low": [], "medium": ["deep"], "hard": ["top"]}, "at low the caller writes")
        self.assertIn("No setup was saved", " ".join(d["notes"]))

    def test_models_come_from_each_cli_listing(self):
        code, d = self.run_cli("detect")
        tiers = {p["name"]: p["tiers"] for p in d["providers"]}
        self.assertEqual(tiers["claude"]["top"], {"model": "fable", "effort": "high"})
        self.assertEqual(tiers["codex"]["deep"], {"model": "gpt-6-astra", "effort": "medium"})
        self.assertEqual(tiers["agy"]["top"], {"model": "gemini-4-argon-high"}, "the slug carries the effort")
        self.assertEqual(tiers["agy"]["deep"], {"model": "gemini-4-argon-medium"})
        self.assertEqual(tiers["agy"]["fast"], {"model": "gemini-3.8-flash-high"}, "never a lite model")
        self.assertEqual(tiers["kiro"]["top"]["model"], "claude-opus-5.5", "newest version, not a preview")
        self.assertEqual(tiers["kiro"]["fast"]["model"], "claude-sonnet-5.5")

    def test_a_missing_model_is_dropped_and_a_smaller_one_stands_in_with_full_effort(self):
        code, d = self.run_cli("detect", env={"FAKE_CODEX_MODELS": "gpt-6.1-sol,gpt-6-luna"})
        codex = next(p for p in d["providers"] if p["name"] == "codex")
        self.assertIsNone(codex["tiers"]["top"])
        self.assertEqual(codex["unavailable"], {"top": "gpt-6-astra"})
        self.assertEqual(codex["tiers"]["deep"], {"model": "gpt-6.1-sol", "effort": "high"})

    def test_reviewer_is_the_first_providers_top_model_and_the_panel_another_vendor(self):
        cfg = helper._merge(helper.DEFAULTS, {"order": ["claude", "codex"], "providers": {
            "claude": {"tiers": dict(helper.PROVIDERS["claude"]["tiers"])},
            "codex": {"tiers": dict(helper.PROVIDERS["codex"]["tiers"])}}})
        cfg["providers"]["kiro"] = {"tiers": {"top": {"model": "claude-opus-5.5"}}}
        cfg["order"] = ["claude", "kiro", "codex"]
        cfg["degrees"]["hard"].update(researchers=1, panel=2)
        team = helper.team(cfg, "hard")
        self.assertEqual([(a["agent"], a["chain"][0]["provider"]) for a in team],
                         [("researcher-1", "claude"), ("reviewer-1", "claude"), ("panel-1", "codex"), ("panel-2", "kiro"),
                          ("writer-1", "claude")],
                         "Kiro's Opus is the same vendor as Claude's, so Codex sits on the panel first")
        self.assertEqual(helper.vendor("kiro", "claude-opus-5.5"), "anthropic", "a reseller's model keeps its vendor")

    def test_setup_saves_and_changes_models_roles_and_degrees(self):
        code, d = self.run_cli("setup", "--providers", "codex,claude", "--model", "codex:top=my-model@xhigh",
                               "--role", "reviewer=claude", "--degree", "hard:researchers=5,panel=2", "--timeout", "top=60")
        self.assertEqual(code, 0, d)
        self.assertEqual(d["degrees"]["hard"]["agents"], 9)
        self.assertEqual({t["provider"] for t in d["degrees"]["low"]["team"] if t["agent"] == "reviewer-1"}, {"claude"})
        saved = json.loads((self.tmp / "home" / ".config" / "deepsearch" / "config.json").read_text())
        self.assertEqual(saved["order"], ["codex", "claude"])
        self.assertEqual(saved["providers"]["codex"]["tiers"]["top"], {"model": "my-model", "effort": "xhigh"})
        self.assertEqual(saved["timeouts"]["top"], 60)
        code, d = self.run_cli("setup", "--degree", "low:researchers=3")          # a later call keeps the rest
        self.assertEqual((d["degrees"]["low"]["agents"], d["degrees"]["hard"]["agents"]), (4, 9))
        self.assertEqual(d["providers"][0]["tiers"]["top"]["model"], "my-model")
        code, d = self.run_cli("roster", "--md", raw=True)
        self.assertIn("| hard | 9 |", d)
        self.assertIn("ask in plain words", d)

    def test_setup_refuses_what_it_does_not_understand(self):
        for bad in (["--providers", "cursor"], ["--model", "codex:huge=x"], ["--role", "editor=claude"],
                    ["--degree", "hard:researchers=99"], ["--degree", "hard:tier=mega"], ["--timeout", "top=0"]):
            code, d = self.run_cli("setup", *bad)
            self.assertEqual((code, d["ok"]), (2, False), bad)
        self.assertFalse((self.tmp / "home" / ".config" / "deepsearch" / "config.json").exists())


class Run(Base):
    def test_start_needs_a_degree_and_opens_a_run_with_a_plan(self):
        code, d = self.run_cli("start", "--topic", "x")
        self.assertEqual((code, d["error"]), (2, "no-degree"))
        self.assertEqual(sorted(d["degrees"]), ["hard", "low", "medium"])
        run, d = self.start("medium", "Türkiye'de güneş enerjisi yatırımı")
        self.assertRegex(run.name, r"^\d{4}-\d\d-\d\d-turkiye-de-gunes-enerjisi-yatirimi$")
        self.assertEqual(run.parent, self.work / "research")
        plan = (run / "plan.md").read_text(encoding="utf-8")
        for agent in ("researcher-1", "researcher-2", "researcher-3", "reviewer-1"):
            self.assertIn("## %s\nPersona: [[" % agent, plan)
        self.assertNotIn("panel-1", plan)
        code, again = self.run_cli("start", "--degree", "medium", "--topic", "Türkiye'de güneş enerjisi yatırımı")
        self.assertTrue(again["run"].endswith("-2"), "a second run on the same day gets its own folder")

    def test_advance_refuses_a_plan_that_is_not_filled_in(self):
        run, _ = self.start()
        code, d = self.run_cli("advance", "--run", run)
        self.assertEqual((code, d["error"]), (2, "plan-not-ready"))
        self.assertEqual(self.calls(), [])

    def test_low_run_researches_reviews_and_revises_only_what_was_sent_back(self):
        run, started = self.start("low")
        self.fill(run)
        answers = self.drive(run)
        last = answers[-1]
        self.assertEqual(last["stage"], "write")
        self.assertEqual(last["write"], str(run / "report.md"))
        self.assertEqual(sorted(Path(p).name for p in last["read"]), ["researcher-1.md", "researcher-2.md", "reviewer-1.md"])
        self.assertIn("REVISED", (run / "findings" / "researcher-1.md").read_text())
        self.assertNotIn("REVISED", (run / "findings" / "researcher-2.md").read_text())
        self.assertNotIn("REVISED", (run / ".work" / "history" / "researcher-1.before-revise.md").read_text())
        self.assertEqual(last["last_verdicts"], {"researcher-1": "revise", "researcher-2": "accept"})
        stages = sorted(c["stage"] for c in self.calls() if c["agent"])
        self.assertEqual(stages, ["research", "research", "review", "revise"])
        review = self.calls(stage="review")[0]
        self.assertEqual(review["model"], started["team"][-1]["model"].split("@")[0], "the reviewer runs on its top model")
        self.assertEqual({r["status"] for r in last["team"]}, {"done"})
        log = (run / "log.md").read_text()
        self.assertIn("review finished: 1 done · verdicts: researcher-1 revise, researcher-2 accept", log)
        self.assertIn("Hypothesis: filled in", (run / ".work" / "plan.cycle-1.md").read_text(), "the plan as it was run")

    def test_agents_get_web_tools_and_nothing_else(self):
        run, _ = self.start("hard", "Solid-state batteries", "--researchers", 4)
        self.fill(run)
        self.drive(run)
        seen = {c["cli"] for c in self.calls() if c["agent"]}
        self.assertEqual(seen, set(ALL))
        for c in self.calls():
            argv = " ".join(c["argv"])
            self.assertNotIn("dangerously", argv)
            self.assertNotIn("--trust-all-tools", argv)
            self.assertNotIn("bypass", argv)
            if not c["agent"]:
                continue
            if c["cli"] == "claude":
                self.assertIn("--tools WebSearch,WebFetch", argv)
            if c["cli"] == "codex":
                self.assertIn("--search exec", argv)
                self.assertIn("--sandbox read-only", argv)
            if c["cli"] == "kiro-cli":
                self.assertIn("--trust-tools=*web*", argv)
            self.assertNotEqual(Path(c["cwd"]).resolve(), self.work.resolve(), "agents run in an empty folder")

    def test_hard_run_adds_a_second_panel_that_sees_the_first_review(self):
        run, started = self.start("hard")
        self.assertEqual(started["agents"], 6)
        self.fill(run)
        answers = self.drive(run, env={"FAKE_PANEL_REVISE": "researcher-3"})
        stages = sorted(c["stage"] for c in self.calls() if c["agent"])
        self.assertEqual(stages, ["panel", "research", "research", "research", "review", "revise", "revise"])
        prompt = (run / ".work" / "runs" / "panel-1.panel" / "prompt.md").read_text()
        self.assertIn("# Second panel", prompt)
        self.assertIn("===== reviewer-1 =====", prompt)
        self.assertIn("REVISED", prompt, "the panel judges the research as revised")
        again = (run / ".work" / "runs" / "researcher-3.revise2" / "prompt.md").read_text()
        self.assertIn("===== panel-1 =====", again)
        self.assertNotIn("===== reviewer-1 =====", again.split("THE REVIEW YOU ANSWER")[1])
        self.assertEqual(answers[-1]["last_verdicts"]["researcher-3"], "revise")
        self.assertEqual((answers[-1]["stage"], answers[-1]["cycles_left"]), ("reflect", 2))
        first, second = (next(c for c in self.calls(stage=s))["cli"] for s in ("review", "panel"))
        self.assertNotEqual(first, second, "the panel is another provider than the first reviewer")

    def test_reflection_concludes_or_opens_another_cycle_that_builds_on_the_notes(self):
        run, _ = self.start("medium")
        self.fill(run)
        first = self.drive(run, env={"FAKE_REVISE": ""})[-1]
        self.assertEqual((first["stage"], first["cycles_left"]), ("reflect", 1))
        code, d = self.run_cli("reflect", "--run", run, "--direction", "deepen", "--reason", "cost data is thin")
        self.assertEqual((code, d["error"]), (2, "no-notes"))
        (run / "notes.md").write_text("# Notes\n\n## Established\n" + "The cells last 6000 cycles [3]. " * 12)
        code, d = self.run_cli("reflect", "--run", run, "--direction", "sideways", "--reason", "x")
        self.assertEqual(code, 2)
        code, d = self.run_cli("reflect", "--run", run, "--direction", "deepen", "--reason", "cost data is thin")
        self.assertEqual(code, 0, d)
        self.assertEqual([a["agent"] for a in d["added"]], ["researcher-4", "researcher-5", "reviewer-2"])
        self.assertEqual(d["added"][-1]["tier"], "top")
        code, refused = self.run_cli("advance", "--run", run)
        self.assertEqual(refused["error"], "plan-not-ready")
        self.assertIn("researcher-4", refused["text"] + (run / "plan.md").read_text())
        self.fill(run)
        before = len(self.calls())
        second = self.drive(run, env={"FAKE_REVISE": ""})[-1]
        new = [c for c in self.calls()[before:] if c["agent"]]
        self.assertEqual(sorted(c["agent"] for c in new), ["researcher-4", "researcher-5", "reviewer-2", "writer-1"])
        prompt = (run / ".work" / "runs" / "researcher-4.research" / "prompt.md").read_text()
        self.assertIn("WHAT THE TEAM HAS ESTABLISHED SO FAR", prompt)
        self.assertIn("The cells last 6000 cycles", prompt)
        review = (run / ".work" / "runs" / "reviewer-2.review" / "prompt.md").read_text()
        self.assertIn("===== researcher-4 =====", review)
        self.assertNotIn("===== researcher-1 =====", review, "a later reviewer judges its own cycle")
        self.assertEqual(second["stage"], "done", "the degree's cycles are used: the writer follows without a reflection")
        self.assertTrue(second["check"]["ok"], second["check"])
        writer = (run / ".work" / "runs" / "writer-1.write" / "prompt.md").read_text()
        for needle in ("===== researcher-1 =====", "===== researcher-5 =====", "===== reviewer-2 =====", "The cells last 6000 cycles",
                       "reflect: deepen — cost data is thin"):
            self.assertIn(needle, writer)
        self.assertEqual(len(second["last_verdicts"]), 5)
        code, d = self.run_cli("reflect", "--run", run, "--direction", "broaden", "--reason", "more")
        self.assertEqual((code, d["error"]), (2, "no-cycle-left"))
        log = (run / "log.md").read_text()
        self.assertIn("cycle 1 · reflect: deepen — cost data is thin", log)
        self.assertIn("cycle 2 · research started: researcher-4", log)

    def test_concluding_early_leads_to_the_final_document(self):
        run, _ = self.start("medium")
        self.fill(run)
        self.drive(run, env={"FAKE_REVISE": ""})
        code, d = self.run_cli("reflect", "--run", run, "--direction", "conclude", "--reason", "x")
        self.assertEqual(d["error"], "no-notes")
        (run / "notes.md").write_text("# Notes\n" + "Established and reviewed. " * 20)
        code, d = self.run_cli("reflect", "--run", run, "--direction", "conclude", "--reason", "the question is answered")
        self.assertEqual((code, d["stage"], d["writes"]), (0, "write", "writer-1"))
        last = self.drive(run)[-1]
        self.assertEqual((last["stage"], last["document"]), ("done", str(run / "report.md")))
        self.assertIn("([Example](https://example.org))", (run / "report.md").read_text())
        self.assertEqual(self.calls(stage="write")[0]["model"], "opus", "medium: the writer runs on the deep model")
        code, d = self.run_cli("advance", "--run", run)
        self.assertEqual(d["stage"], "done", "a finished run stays finished")
        self.assertIn("final document written and checked", (run / "log.md").read_text())

    def test_the_reflection_reads_a_digest_not_the_full_documents(self):
        run, _ = self.start("medium")
        self.fill(run)
        last = self.drive(run)[-1]
        self.assertEqual(last["read"], [str(run / "digest.md")])
        self.assertEqual(len(last["full"]), 4)
        digest = (run / "digest.md").read_text()
        for kept in ("TAKEAWAY-OF-researcher-2", "GAP-OF-researcher-3", "## Hypothesis", "## Overall", "VERDICT researcher-1: revise"):
            self.assertIn(kept, digest)
        for cut in ("CITED-FINDING", "INFERENCE", "[must]"):
            self.assertNotIn(cut, digest)
        full = sum(len(Path(f).read_text()) for f in last["full"])
        self.assertLess(len(digest), full * 0.75)

    def test_the_question_decides_how_many_researchers_and_budgets_bound_them(self):
        run, d = self.start("medium", "One narrow question", "--researchers", 1)
        self.assertEqual([t["agent"] for t in d["team"]], ["researcher-1", "reviewer-1", "writer-1"])
        code, bad = self.run_cli("start", "--degree", "low", "--topic", "x", "--researchers", 0)
        self.assertEqual(code, 2)
        self.fill(run)
        self.run_cli("advance", "--run", run)
        prompt = (run / ".work" / "runs" / "researcher-1.research" / "prompt.md").read_text()
        self.assertIn("About 12 searches and page reads in all", prompt)
        self.assertIn("Not yours: filled in", prompt)
        self.assertIn("Sources: filled in", prompt)
        self.run_cli("wait", "--run", run, "--timeout", 60)

    def test_a_follow_up_run_builds_on_an_earlier_document(self):
        old, _ = self.start("low", "Sodium-ion cost")
        (old / "report.md").write_text("# Earlier\n\nEARLIER-FINDING: cells cost 60 USD/kWh.\n" + "More. " * 40)
        run, _ = self.start("low", "Sodium-ion cost in 2027", "--builds-on", old)
        self.fill(run)
        self.run_cli("advance", "--run", run)
        prompt = (run / ".work" / "runs" / "researcher-1.research" / "prompt.md").read_text()
        self.assertIn("EARLIER RESEARCH ON THIS TOPIC", prompt)
        self.assertIn("EARLIER-FINDING", prompt)
        self.run_cli("wait", "--run", run, "--timeout", 60)
        code, d = self.run_cli("start", "--degree", "low", "--topic", "x", "--builds-on", self.tmp / "nowhere")
        self.assertEqual((code, d["error"]), (2, "no-run"))

    def test_check_finds_sources_nobody_on_the_team_cited(self):
        run, _ = self.start("low")
        self.fill(run)
        self.drive(run)
        code, d = self.run_cli("check", "--run", run)
        self.assertEqual((code, d["error"]), (2, "no-document"))
        (run / "report.md").write_text("# Answer\nA claim [1].\n\n[1] Example. https://example.org.\n")
        code, d = self.run_cli("check", "--run", run)
        self.assertEqual((code, d["ok"], d["sources"]), (0, True, 1))
        (run / "report.md").write_text("# Answer\n[1] https://example.org\n[2] https://invented.example.com/paper\n")
        code, d = self.run_cli("check", "--run", run)
        self.assertEqual((code, d["unknown_sources"]), (1, ["https://invented.example.com/paper"]))

    def test_nothing_to_revise_skips_the_revision(self):
        run, _ = self.start("low")
        self.fill(run)
        answers = self.drive(run, env={"FAKE_REVISE": ""})
        self.assertEqual(self.calls(stage="revise"), [])
        self.assertIn({"stage": "revise", "skipped": "nothing was sent back for revision"}, answers[-1]["passed"])

    def test_a_failing_provider_is_replaced_by_the_next_one(self):
        run, _ = self.start("low")
        self.fill(run)
        answers = self.drive(run, env={"FAKE_CLAUDE": "limit", "FAKE_REVISE": ""})
        rows = {r["agent"]: r for r in answers[-1]["team"] if r["stage"] == "research"}
        self.assertEqual(rows["researcher-1"]["status"], "done")
        self.assertEqual(rows["researcher-1"]["provider"], "codex")
        self.assertEqual(rows["researcher-1"]["attempts"][0], {"provider": "claude", "model": "sonnet", "outcome": "limit"})

    def test_old_clis_are_asked_again_without_the_newer_flags(self):
        run, _ = self.start("low")
        self.fill(run)
        answers = self.drive(run, env={"FAKE_OLD": "1", "FAKE_REVISE": ""})
        self.assertEqual({r["status"] for r in answers[-1]["team"]}, {"done"})
        self.assertTrue(any("--disallowedTools" in " ".join(c["argv"]) for c in self.calls(cli="claude")))

    def test_too_short_an_answer_is_not_research(self):
        run, _ = self.start("low")
        self.fill(run)
        answers = self.drive(run, env={"FAKE_SHORT": "1"})
        self.assertEqual(answers[-1]["stage"], "research")
        self.assertEqual(len(answers[-1]["yours"]), 2, "nobody answered: the caller takes the seats")
        self.assertIn("only 10 characters", answers[-1]["failed"][0]["error"])

    def test_long_prompts_reach_antigravity_as_a_file(self):
        self.run_cli("setup", "--providers", "agy")
        run, _ = self.start("low")
        self.fill(run)
        plan = run / "plan.md"
        plan.write_text(plan.read_text() + "\n" + "x" * 40000 + "\n", encoding="utf-8")   # lands in the last section
        self.drive(run, env={"FAKE_REVISE": ""})
        review = self.calls(stage="review")[0]
        self.assertTrue(review["from_file"])
        self.assertGreater(review["chars"], 40000)
        self.assertFalse(self.calls(stage="research")[0]["from_file"])

    def test_project_file_shapes_the_prompts_but_cannot_touch_the_machine(self):
        code, d = self.run_cli("init", "--set", "focus=A grid storage startup", "--set", "prefer_sources=peer-reviewed,IEA",
                               "--set", "language=Turkish", "--set", "output=docs/research")
        self.assertEqual(code, 0, d)
        self.assertEqual(d["settings"]["prefer_sources"], ["peer-reviewed", "IEA"])
        run, _ = self.start("low")
        self.assertEqual(run.parent, self.work / "docs" / "research")
        self.assertIn("Language: Turkish", (run / "plan.md").read_text())
        self.fill(run)
        self.run_cli("advance", "--run", run)
        prompt = (run / ".work" / "runs" / "researcher-1.research" / "prompt.md").read_text()
        self.assertIn("A grid storage startup", prompt)
        self.assertIn("Prefer these sources: peer-reviewed, IEA", prompt)
        self.assertIn("Write in Turkish", prompt)
        self.run_cli("wait", "--run", run, "--timeout", 60)
        (self.work / ".deepsearch.json").write_text(json.dumps({
            "output": "../outside", "providers": {"claude": {"bin": "/tmp/evil"}}, "degrees": {}, "focus": "ok"}))
        code, d = self.run_cli("roster")
        self.assertEqual(d["project"], {"focus": "ok"})
        self.assertEqual(d["output"], str(self.work / "research"))
        self.assertIn("Ignored keys in .deepsearch.json", " ".join(d["notes"]))
        code, d = self.run_cli("init", "--set", "bin=/tmp/evil")
        self.assertEqual(code, 2)

    def test_status_and_runs(self):
        run, _ = self.start("low")
        self.fill(run)
        self.drive(run)
        code, d = self.run_cli("status")
        self.assertEqual((d["run"], d["stage"], d["document"]), (str(run), "write", None))
        (run / "report.md").write_text("# done\n")
        code, d = self.run_cli("runs")
        self.assertEqual(d["runs"], [{"run": str(run), "topic": "Solid-state batteries", "degree": "low", "written": True}])


class Links(Base):
    def setUp(self):
        super().setUp()

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200 if self.path == "/paper" else 404)
                self.end_headers()
            do_HEAD = do_GET

            def log_message(self, *a):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.shutdown)
        self.base = "http://127.0.0.1:%d" % self.server.server_port
        self.online = {"DEEPSEARCH_OFFLINE": "", "DEEPSEARCH_ALLOW_LOCAL": "1"}

    def test_links_that_do_not_open_reach_the_reviewer_without_a_model(self):
        self.run_cli("setup", "--providers", "claude", "--model", "claude:fast=sonnet")
        run, _ = self.start("low")
        self.fill(run)
        plan = run / "plan.md"
        env = {**self.online, "FAKE_DEAD_LINK": self.base + "/gone"}
        answers = self.drive(run, env=env)
        self.assertEqual(json.loads((run / ".work" / "links.json").read_text())[self.base + "/gone"], "dead")
        review = (run / ".work" / "runs" / "reviewer-1.review" / "prompt.md").read_text()
        self.assertIn("LINK CHECK (automatic", review)
        self.assertIn("- researcher-1: %s/gone" % self.base, review)
        revise = (run / ".work" / "runs" / "researcher-1.revise" / "prompt.md").read_text()
        self.assertIn("these links of yours did not open", revise)
        self.assertIn("cited link(s) do not open", (run / "log.md").read_text())
        (run / "report.md").write_text("# A\nFine ([P](%s/paper)).\n" % self.base)
        code, d = self.run_cli("check", "--run", run, env=self.online)
        self.assertEqual((code, d["unknown_sources"]), (1, [self.base + "/paper"]), "nobody on the team cited it")
        (run / "report.md").write_text("# A\nBad ([G](%s/gone)).\n" % self.base)
        code, d = self.run_cli("check", "--run", run, env=self.online)
        self.assertEqual((code, d["dead_links"], d["unknown_sources"]), (1, [self.base + "/gone"], []))

    def test_a_link_check_never_reaches_into_the_local_network(self):
        self.assertEqual(helper.link_status(self.base + "/paper"), "unverified", "loopback is not checked")
        os.environ["DEEPSEARCH_ALLOW_LOCAL"] = "1"
        self.addCleanup(os.environ.pop, "DEEPSEARCH_ALLOW_LOCAL", None)
        self.assertEqual(helper.link_status(self.base + "/paper"), "ok")
        self.assertEqual(helper.link_status(self.base + "/gone"), "dead")

    def test_a_writer_that_invents_a_source_is_caught(self):
        run, _ = self.start("medium", "Solid-state batteries", "--researchers", 1)
        self.fill(run)
        self.drive(run, env={"FAKE_REVISE": ""})
        (run / "notes.md").write_text("# Notes\n" + "Established and reviewed. " * 20)
        self.run_cli("reflect", "--run", run, "--direction", "conclude", "--reason", "answered")
        last = self.drive(run, env={"FAKE_WRITER_INVENTS": "1"})[-1]
        self.assertEqual(last["stage"], "done")
        self.assertEqual(last["check"]["unknown_sources"], ["https://invented.example.com/x"])
        self.assertIn("Fix what `check` reports", last["next"])


class Verify(Base):
    def test_verify_drops_refused_models_checks_the_web_and_saves(self):
        code, d = self.run_cli("verify", env={"FAKE_NOMODEL": "fable", "FAKE_AGY_WEB": "no"})
        self.assertEqual(code, 0, d)
        by = {v["provider"]: v for v in d["verified"]}
        self.assertEqual(by["claude"]["dropped"], ["top: fable"])
        self.assertEqual(by["agy"]["web"], "no web search")
        self.assertEqual(by["codex"]["web"], "ok")
        self.assertTrue(d["saved"])
        hard = d["degrees"]["hard"]["team"]
        self.assertNotIn("claude", [t["provider"] for t in hard if t["tier"] == "top"])
        self.assertEqual([t["provider"] for t in d["degrees"]["low"]["team"][:2]], ["claude", "codex"], "agy cannot search: used last")
        self.assertIn("could not search the web", " ".join(d["notes"]))
        code, d = self.run_cli("verify", "--no-web")                # the account has the model now
        self.assertEqual({v["provider"]: v["restored"] for v in d["verified"]}["claude"], ["top: fable"])
        self.assertEqual(d["providers"][0]["tiers"]["top"], {"model": "fable", "effort": "high"})


class NoCli(Base):
    clis = ()

    def test_without_any_cli_the_caller_plays_every_role(self):
        code, d = self.run_cli("roster")
        self.assertIn("No provider CLI was found", " ".join(d["notes"]))
        run, started = self.start("low")
        self.assertEqual({t["runs"][:3] for t in started["team"]}, {"you"})
        self.fill(run)
        code, d = self.run_cli("advance", "--run", run)
        self.assertEqual([y["agent"] for y in d["started"]], ["researcher-1", "researcher-2"])
        self.assertTrue(Path(d["started"][0]["prompt_file"]).is_file())
        code, d = self.run_cli("advance", "--run", run)
        self.assertEqual(len(d["yours"]), 2, "still waiting for the caller's documents")
        for y in d["yours"]:
            Path(y["save_to"]).write_text("# Findings\n" + "A finding with its source [1]. " * 20)
        code, d = self.run_cli("advance", "--run", run)
        self.assertEqual((d["stage"], d["started"][0]["agent"]), ("review", "reviewer-1"))
        Path(d["started"][0]["save_to"]).write_text("# Review\n" + "Fine. " * 60 + "\nVERDICT researcher-1: accept\nVERDICT researcher-2: accept\n")
        code, d = self.run_cli("advance", "--run", run)
        self.assertEqual(d["stage"], "write")
        code, d = self.run_cli("setup")
        self.assertEqual((code, d["error"]), (2, "no-provider"))


if __name__ == "__main__":
    unittest.main()
