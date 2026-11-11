#!/usr/bin/env python3
"""Check that every skill in skills/ is well-formed.

  python3 scripts/validate.py

Checks per skill: SKILL.md exists, has YAML frontmatter with `name` equal to the folder name and
a non-empty `description` (at most 1024 characters), the name is lowercase-hyphenated, and the
skill is listed in both root READMEs. Exits 1 if anything fails.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_DESCRIPTION = 1024


def frontmatter(text):
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---", 4)
    if end == -1:
        return None
    fields = {}
    for line in text[4:end].splitlines():
        m = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if m:
            fields[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return fields


def check(skill_dir, readmes):
    errors = []
    name = skill_dir.name
    skill_md = skill_dir / "SKILL.md"
    if not NAME_RE.match(name):
        errors.append("folder name must be lowercase letters, digits and hyphens")
    if not skill_md.is_file():
        return errors + ["missing SKILL.md"]
    fm = frontmatter(skill_md.read_text(encoding="utf-8"))
    if fm is None:
        return errors + ["SKILL.md has no frontmatter (--- ... ---) at the top"]
    if fm.get("name") != name:
        errors.append("frontmatter name %r does not match folder %r" % (fm.get("name"), name))
    desc = fm.get("description", "")
    if not desc:
        errors.append("frontmatter description is empty")
    elif len(desc) > MAX_DESCRIPTION:
        errors.append("description is %d characters (max %d)" % (len(desc), MAX_DESCRIPTION))
    if not (skill_dir / "README.md").is_file():
        errors.append("missing README.md")
    for readme_name, text in readmes.items():
        if "skills/%s/" % name not in text:
            errors.append("not listed in %s" % readme_name)
    return errors


def main():
    readmes = {p.name: p.read_text(encoding="utf-8") for p in (ROOT / "README.md", ROOT / "README.tr.md") if p.exists()}
    skills = sorted(d for d in (ROOT / "skills").iterdir() if d.is_dir() and not d.name.startswith("."))
    if not skills:
        print("no skills found in skills/")
        return 1
    failed = 0
    for d in skills:
        errors = check(d, readmes)
        if errors:
            failed += 1
            print("FAIL %s" % d.name)
            for e in errors:
                print("     - %s" % e)
        else:
            print("ok   %s" % d.name)
    print("\n%d skill(s), %d failed" % (len(skills), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
