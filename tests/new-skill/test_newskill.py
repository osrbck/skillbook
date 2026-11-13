"""Tests for the new-skill helper.  Run:  python3 -m unittest discover -s tests/new-skill -v"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "skills" / "new-skill"
SCRIPT = SKILL / "scripts" / "newskill.py"
DESC = "Counts the lines of a project by language. Use when the user runs /loc or asks how big a project is."
# Built at run time so that no scanner sees a token in this file.
TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0" * 2


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="newskill-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.home = self.tmp / "home"
        for d in (".claude", ".kiro"):
            (self.home / d).mkdir(parents=True)
        self.env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(self.home),
                    "XDG_STATE_HOME": str(self.home / ".local" / "state")}
        self.drafts = self.home / ".local" / "state" / "new-skill" / "drafts"

    def run_cli(self, *args, ok=True):
        p = subprocess.run([sys.executable, str(SCRIPT)] + [str(a) for a in args], env=self.env,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        if ok:
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return p

    def draft(self, name="loc", fill=True, **kw):
        args = ["draft", "--name", name, "--description", kw.get("description", DESC)]
        if kw.get("invoke"):
            args += ["--invoke", kw["invoke"]]
        self.run_cli(*args)
        folder = self.drafts / name
        if fill:
            text = (folder / "SKILL.md").read_text()
            head = text[: text.index("\n---", 4) + 5]
            (folder / "SKILL.md").write_text(head + "\n# %s\n\nCount the lines and print a table.\n" % name)
        return folder


class Draft(Base):
    def test_draft_has_frontmatter_and_is_command_only(self):
        folder = self.draft(fill=False)
        text = (folder / "SKILL.md").read_text()
        self.assertTrue(text.startswith("---\nname: loc\ndescription: "))
        self.assertIn("disable-model-invocation: true", text)

    def test_auto_invoke_leaves_the_line_out(self):
        folder = self.draft(fill=False, invoke="auto")
        self.assertNotIn("disable-model-invocation", (folder / "SKILL.md").read_text())

    def test_description_with_a_colon_is_quoted_and_read_back(self):
        folder = self.draft(description="Does one thing: counts. Use when the user runs /loc or asks for a count.")
        self.assertIn('description: "Does one thing: counts.', (folder / "SKILL.md").read_text())
        self.run_cli("check", "loc")

    def test_bad_names_are_refused(self):
        for name in ("Loc", "a_b", "-a", "a--b", "../x", "a" * 65):
            p = self.run_cli("draft", "--name=" + name, "--description", DESC, ok=False)
            self.assertEqual(p.returncode, 2, name)
            self.assertIn("Blocked:", p.stderr)
        self.assertFalse(self.drafts.exists())

    def test_existing_draft_is_kept_unless_replace(self):
        folder = self.draft()
        p = self.run_cli("draft", "--name", "loc", "--description", DESC, ok=False)
        self.assertEqual(p.returncode, 2)
        self.assertIn("Count the lines", (folder / "SKILL.md").read_text())
        self.run_cli("draft", "--name", "loc", "--description", DESC, "--replace")
        self.assertNotIn("Count the lines", (folder / "SKILL.md").read_text())

    def test_drafts_and_drop(self):
        self.draft()
        self.assertIn("loc", self.run_cli("drafts").stdout)
        self.run_cli("drop", "loc")
        self.assertIn("no drafts", self.run_cli("drafts").stdout)


class Check(Base):
    def test_unfilled_draft_fails(self):
        self.draft(fill=False)
        p = self.run_cli("check", "loc", ok=False)
        self.assertEqual(p.returncode, 1)
        self.assertIn("to fill in", p.stdout)

    def test_filled_draft_passes(self):
        self.draft()
        self.assertIn("ok:", self.run_cli("check", "loc").stdout)

    def test_missing_named_file(self):
        folder = self.draft()
        with (folder / "SKILL.md").open("a") as f:
            f.write("\nRun `scripts/loc.py` and read references/langs.md.\n")
        p = self.run_cli("check", "loc", ok=False)
        self.assertIn("scripts/loc.py", p.stdout)
        self.assertIn("references/langs.md", p.stdout)
        (folder / "scripts").mkdir()
        (folder / "scripts" / "loc.py").write_text("print('ok')\n")
        (folder / "references").mkdir()
        (folder / "references" / "langs.md").write_text("# Languages\n")
        self.run_cli("check", "loc")

    def test_script_that_does_not_compile(self):
        folder = self.draft()
        (folder / "scripts").mkdir()
        (folder / "scripts" / "loc.py").write_text("def broken(:\n")
        p = self.run_cli("check", "loc", ok=False)
        self.assertIn("does not compile", p.stdout)

    def test_token_is_an_error_and_is_not_printed(self):
        folder = self.draft()
        (folder / "notes.md").write_text("token = %s\n" % TOKEN)
        p = self.run_cli("check", "loc", ok=False)
        self.assertIn("looks like an API key", p.stdout)
        self.assertNotIn(TOKEN, p.stdout + p.stderr)

    def test_home_path_is_a_warning(self):
        folder = self.draft()
        with (folder / "SKILL.md").open("a") as f:
            f.write("\nRead /home/" + "ada/notes.txt first.\n")
        p = self.run_cli("check", "loc")
        self.assertIn("warning:", p.stdout)

    def test_name_must_match_folder_and_block_scalars_fail(self):
        folder = self.draft()
        text = (folder / "SKILL.md").read_text()
        (folder / "SKILL.md").write_text(text.replace("name: loc", "name: other"))
        self.assertIn("does not match", self.run_cli("check", "loc", ok=False).stdout)
        (folder / "SKILL.md").write_text("---\nname: loc\ndescription: >\n  folded text\n---\n\n# loc\n\nBody.\n")
        self.assertIn("one line", self.run_cli("check", "loc", ok=False).stdout)

    def test_too_long_description(self):
        folder = self.draft()
        (folder / "SKILL.md").write_text("---\nname: loc\ndescription: %s\n---\n\n# loc\n\nBody.\n" % ("use " * 300))
        self.assertIn("max 1024", self.run_cli("check", "loc", ok=False).stdout)

    def test_shipped_skill_passes_its_own_check(self):
        p = self.run_cli("check", SKILL)
        self.assertNotIn("error:", p.stdout)


class Install(Base):
    def test_install_in_one_provider_removes_the_draft(self):
        folder = self.draft()
        (folder / "scripts").mkdir()
        (folder / "scripts" / "loc.py").write_text("print('ok')\n")
        (folder / "scripts" / "__pycache__").mkdir()
        (folder / "scripts" / "__pycache__" / "x.pyc").write_text("")
        out = self.run_cli("install", "loc", "--in", "claude").stdout
        dest = self.home / ".claude" / "skills" / "loc"
        self.assertIn(str(dest), out)
        self.assertTrue((dest / "SKILL.md").is_file())
        self.assertTrue(os.access(dest / "scripts" / "loc.py", os.X_OK))
        self.assertFalse((dest / "scripts" / "__pycache__").exists())
        self.assertFalse(folder.exists())
        self.assertFalse((self.home / ".codex").exists())

    def test_all_installs_only_where_a_provider_was_found(self):
        self.draft()
        self.run_cli("install", "loc", "--all")
        self.assertTrue((self.home / ".claude" / "skills" / "loc" / "SKILL.md").is_file())
        self.assertTrue((self.home / ".kiro" / "skills" / "loc" / "SKILL.md").is_file())
        self.assertFalse((self.home / ".codex").exists())
        self.assertFalse((self.home / ".gemini").exists())

    def test_also_and_dest(self):
        self.draft()
        repo = self.tmp / "repo" / "skills"
        self.run_cli("install", "loc", "--in", "kiro", "--also", "codex", "--dest", repo)
        for base in (self.home / ".kiro" / "skills", self.home / ".codex" / "skills", repo):
            self.assertTrue((base / "loc" / "SKILL.md").is_file(), base)

    def test_existing_skill_needs_replace_and_is_backed_up(self):
        old = self.home / ".claude" / "skills" / "loc"
        old.mkdir(parents=True)
        (old / "SKILL.md").write_text("old one\n")
        self.draft()
        p = self.run_cli("install", "loc", "--in", "claude", "--also", "kiro", ok=False)
        self.assertEqual(p.returncode, 2)
        self.assertEqual((old / "SKILL.md").read_text(), "old one\n")
        self.assertFalse((self.home / ".kiro" / "skills").exists())
        self.assertTrue((self.drafts / "loc").exists())
        out = self.run_cli("install", "loc", "--in", "claude", "--replace").stdout
        self.assertIn("backup:", out)
        self.assertIn("Count the lines", (old / "SKILL.md").read_text())
        backups = list((self.home / ".local" / "state" / "new-skill" / "backups").iterdir())
        self.assertEqual((backups[0] / "SKILL.md").read_text(), "old one\n")

    def test_skill_with_errors_is_not_installed(self):
        self.draft(fill=False)
        p = self.run_cli("install", "loc", "--in", "claude", ok=False)
        self.assertEqual(p.returncode, 2)
        self.assertFalse((self.home / ".claude" / "skills").exists())

    def test_install_needs_a_target_and_a_known_provider(self):
        self.draft()
        self.assertEqual(self.run_cli("install", "loc", ok=False).returncode, 2)
        self.assertEqual(self.run_cli("install", "loc", "--also", "cursor", ok=False).returncode, 2)

    def test_where_reports_providers_and_names(self):
        self.draft()
        self.run_cli("install", "loc", "--in", "claude", "--keep-draft")
        d = json.loads(self.run_cli("where", "--name", "loc").stdout)
        self.assertTrue(d["providers"]["claude"]["found"])
        self.assertFalse(d["providers"]["codex"]["found"])
        self.assertEqual(d["providers"]["claude"]["skills"], ["loc"])
        self.assertEqual(d["name"]["installed_in"], ["claude"])
        self.assertTrue(d["name"]["draft_exists"])
        self.assertFalse(json.loads(self.run_cli("where", "--name", "Bad Name").stdout)["name"]["valid"])


if __name__ == "__main__":
    unittest.main()
