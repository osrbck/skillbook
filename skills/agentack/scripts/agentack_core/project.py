"""Project profile: what this repository is built with and how it is put together.

`init` scans the repository once and writes the result to `.agentack.json` (key `project`),
next to an optional `project_override` that always wins. Workers get only the part of the
profile that their role needs, so the scan is the context; nobody asks the user about it.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import config

SKIP_DIRS = {
    ".git", "node_modules", "vendor", "dist", "build", "out", "target", ".next", ".nuxt", ".svelte-kit",
    ".output", "bin", "obj", ".venv", "venv", "env", "__pycache__", ".agentack", "coverage", ".turbo",
    "Pods", ".gradle", ".idea", ".vscode", "tmp", "storage", "public", "static", "assets", "deps",
    "_build", ".dart_tool", "android", "ios", ".expo", "docs", "testdata", "fixtures", "examples",
    "e2e", "cypress", "playwright-report", "test-results", ".angular", ".cache",
}
MAX_DEPTH = 4
KINDS = ("modular-monolith", "microservices", "fullstack-app", "monolith", "serverless", "frontend-only")
LAYERS = ("backend", "frontend", "fullstack")

# JavaScript / TypeScript frameworks, checked in this order: (dependency, framework, layer).
JS_FRAMEWORKS = [
    ("next", "next", "web"), ("nuxt", "nuxt", "web"), ("@sveltejs/kit", "sveltekit", "web"),
    ("@remix-run/react", "remix", "web"), ("@react-router/dev", "react-router", "web"),
    ("@tanstack/react-start", "tanstack-start", "web"), ("@solidjs/start", "solid-start", "web"),
    ("astro", "astro", "frontend"),
    ("@angular/core", "angular", "frontend"), ("expo", "react-native", "frontend"),
    ("react-native", "react-native", "frontend"), ("vue", "vue", "frontend"),
    ("svelte", "svelte", "frontend"), ("solid-js", "solid", "frontend"), ("react", "react", "frontend"),
    ("@nestjs/core", "nest", "backend"), ("fastify", "fastify", "backend"), ("hono", "hono", "backend"),
    ("express", "express", "backend"), ("koa", "koa", "backend"), ("@hapi/hapi", "hapi", "backend"),
    ("@adonisjs/core", "adonis", "backend"), ("elysia", "elysia", "backend"),
]
JS_DATA = ("prisma", "@prisma/client", "drizzle-orm", "kysely", "typeorm", "mongoose", "sequelize",
           "@trpc/server", "next-auth", "@auth/core", "better-auth", "pg", "mysql2", "@supabase/supabase-js")
JS_SERVER_DIRS = ("app/api", "src/app/api", "pages/api", "src/pages/api", "server", "src/server",
                  "src/routes/api", "app/routes", "src/lib/server", "server/api")
PY_FRAMEWORKS = [("django", "django"), ("fastapi", "fastapi"), ("flask", "flask"), ("litestar", "litestar"),
                 ("starlette", "starlette"), ("sanic", "sanic"), ("aiohttp", "aiohttp")]
RUST_WEB = ("axum", "actix-web", "rocket", "warp", "poem", "salvo", "tide", "loco-rs")
RUST_UI = ("leptos", "yew", "dioxus")
JVM_WEB = (("spring-boot", "spring"), ("quarkus", "quarkus"), ("micronaut", "micronaut"),
           ("io.ktor", "ktor"), ("ktor-server", "ktor"), ("vertx", "vertx"), ("dropwizard", "dropwizard"))

BOUNDARY_TOOLS = {
    "eslint-plugin-boundaries": "eslint-plugin-boundaries", "dependency-cruiser": "dependency-cruiser",
    "@nx/enforce-module-boundaries": "nx module boundaries", "spring-modulith": "Spring Modulith",
    "archunit": "ArchUnit", "netarchtest": "NetArchTest", "packwerk": "packwerk", "deptrac": "deptrac",
    "import-linter": "import-linter",
}
MODULE_DIRS = ("internal/modules", "src/modules", "modules", "Modules", "src/Modules", "app/Modules",
               "src/main/java/modules", "lib/modules", "packages/modules", "src/contexts", "contexts",
               "src/bounded-contexts", "src/domains", "domains")
CONTRACT_DIRS = ("contracts", "contract", "api", "apis", "openapi", "spec", "specs", "schemas", "proto",
                 "protos", "schema", "graphql")


# -- small file helpers ----------------------------------------------------------------------

def _read(path: Path, limit: int = 200_000) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return ""


def _json(path: Path) -> dict:
    try:
        data = json.loads(_read(path))
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


def _rel(root: Path, path: Path) -> str:
    r = path.relative_to(root).as_posix()
    return r or "."


def _walk(root: Path, depth: int = MAX_DEPTH):
    """Yield (dir, filenames) breadth first, skipping build output and dependencies."""
    stack = [(root, 0)]
    while stack:
        d, lvl = stack.pop(0)
        try:
            entries = sorted(d.iterdir(), key=lambda p: p.name)
        except OSError:
            continue
        files = [e.name for e in entries if e.is_file()]
        yield d, files, lvl
        if lvl >= depth:
            continue
        for e in entries:
            if e.is_dir() and not e.is_symlink() and e.name not in SKIP_DIRS and not e.name.startswith("."):
                stack.append((e, lvl + 1))


# -- units -----------------------------------------------------------------------------------

def _pm(unit: Path, root: Path) -> str:
    for d in (unit, root):
        if (d / "pnpm-lock.yaml").is_file():
            return "pnpm"
        if (d / "yarn.lock").is_file():
            return "yarn"
        if (d / "bun.lockb").is_file() or (d / "bun.lock").is_file():
            return "bun"
    return "npm"


def _js_unit(d: Path, root: Path, pkg: dict) -> Optional[dict]:
    deps = {}
    for k in ("dependencies", "devDependencies", "peerDependencies"):
        deps.update(pkg.get(k) or {})
    fw, kind = None, None
    for dep, name, layer in JS_FRAMEWORKS:
        if dep in deps:
            fw, kind = name, layer
            break
    if not fw:
        return None
    if kind == "web":
        server = any((d / s).is_dir() for s in JS_SERVER_DIRS) or any(x in deps for x in JS_DATA)
        layer = "fullstack" if server else "frontend"
    else:
        layer = kind
    ts = (d / "tsconfig.json").is_file() or "typescript" in deps
    pm = _pm(d, root)
    run = {"npm": "npm run", "pnpm": "pnpm run", "yarn": "yarn", "bun": "bun run"}[pm]
    scripts = pkg.get("scripts") or {}
    cmds = {}
    for key, names in (("test", ("test", "test:unit")), ("lint", ("lint",)),
                       ("typecheck", ("typecheck", "type-check", "check-types", "tsc", "check")),
                       ("build", ("build",)), ("e2e", ("e2e", "test:e2e")), ("format", ("format:check", "format"))):
        hit = next((n for n in names if n in scripts), None)
        if hit and not (key == "test" and "no test specified" in str(scripts[hit])):
            cmds[key] = "%s %s" % (run, hit)
    if ts and "typecheck" not in cmds:
        cmds["typecheck"] = ("%s tsc --noEmit" % {"npm": "npx", "pnpm": "pnpm exec", "yarn": "yarn",
                                                     "bun": "bunx"}[pm])
    lang = "typescript" if ts else "javascript"
    return {"language": lang, "framework": fw, "layer": layer, "commands": cmds,
            "stack": fw if layer != "backend" else "node", "deps": deps}


def _go_unit(d: Path, root: Path) -> dict:
    mod = _read(d / "go.mod")
    fw = next((n for k, n in (("gin-gonic/gin", "gin"), ("go-chi/chi", "chi"), ("labstack/echo", "echo"),
                              ("gofiber/fiber", "fiber"), ("connectrpc", "connect"), ("grpc", "grpc"))
               if k in mod), None)
    lint = "golangci-lint run" if any((d / n).is_file() or (root / n).is_file()
                                      for n in (".golangci.yml", ".golangci.yaml", ".golangci.toml")) else "go vet ./..."
    return {"language": "go", "framework": fw, "layer": "backend", "stack": "go",
            "commands": {"test": "go test ./...", "lint": lint, "build": "go build ./...",
                         "format": "gofmt -l ."}}


def _dotnet_unit(d: Path, files: List[str]) -> Optional[dict]:
    projs = [f for f in files if f.endswith(".csproj") or f.endswith(".fsproj")]
    if not projs:
        return None
    text = _read(d / projs[0])
    name = projs[0].rsplit(".", 1)[0]
    if re.search(r"xunit|nunit|mstest", text, re.I) or name.lower().endswith(("tests", ".test")):
        return None
    if "Microsoft.NET.Sdk.BlazorWebAssembly" in text:
        layer, fw = "frontend", "blazor"
    elif "Microsoft.NET.Sdk.Web" in text:
        layer, fw = "backend", "aspnetcore"
    else:
        return None                                             # class library: part of a host
    lang = "fsharp" if projs[0].endswith(".fsproj") else "csharp"
    return {"language": lang, "framework": fw, "layer": layer, "stack": "blazor" if fw == "blazor" else lang,
            "commands": {"test": "dotnet test", "build": "dotnet build",
                         "format": "dotnet format --verify-no-changes"}}


def _jvm_unit(d: Path, files: List[str]) -> Optional[dict]:
    text = ""
    for f in ("pom.xml", "build.gradle", "build.gradle.kts"):
        if f in files:
            text += _read(d / f)
    if not text:
        return None
    if "<packaging>pom</packaging>" in text:
        return None                                             # aggregator
    if "com.android.application" in text:
        return {"language": "kotlin", "framework": "android", "layer": "frontend", "stack": "android",
                "commands": {"test": "./gradlew test", "build": "./gradlew assembleDebug"}}
    fw = next((n for k, n in JVM_WEB if k in text), None)
    if not fw:
        return None
    kotlin = "build.gradle.kts" in files or "kotlin" in text
    lang = "kotlin" if kotlin and "src/main/java" not in text and not (d / "src/main/java").is_dir() else "java"
    if "pom.xml" in files:
        mvn = "./mvnw" if (d / "mvnw").is_file() else "mvn"
        cmds = {"test": mvn + " test", "build": mvn + " -q -DskipTests package"}
    else:
        gw = "./gradlew" if (d / "gradlew").is_file() else "gradle"
        cmds = {"test": gw + " test", "build": gw + " build -x test"}
    return {"language": lang, "framework": fw, "layer": "backend", "stack": lang, "commands": cmds,
            "modulith": "spring-modulith" in text, "archunit": "archunit" in text.lower()}


def _py_unit(d: Path, files: List[str]) -> Optional[dict]:
    text = "".join(_read(d / f) for f in ("pyproject.toml", "requirements.txt", "Pipfile", "setup.cfg") if f in files).lower()
    fw = next((n for k, n in PY_FRAMEWORKS if re.search(r"(^|[\s\"'\[=])%s([\s\"'<>=~\[,]|$)" % k, text, re.M)), None)
    if not fw:
        return None
    layer = "backend"
    if fw == "django" and "djangorestframework" not in text and "django-ninja" not in text:
        layer = "fullstack" if any(p.name == "templates" for p in d.glob("*/templates")) or (d / "templates").is_dir() else "backend"
    run = "uv run " if (d / "uv.lock").is_file() else "poetry run " if (d / "poetry.lock").is_file() else ""
    cmds = {"test": run + ("pytest" if "pytest" in text or (d / "pytest.ini").is_file() or (d / "tests").is_dir()
                           else "python manage.py test" if fw == "django" else "pytest")}
    if "ruff" in text:
        cmds["lint"] = run + "ruff check ."
        cmds["format"] = run + "ruff format --check ."
    if "mypy" in text:
        cmds["typecheck"] = run + "mypy ."
    elif "pyright" in text:
        cmds["typecheck"] = run + "pyright"
    return {"language": "python", "framework": fw, "layer": layer, "stack": "python", "commands": cmds}


def _other_unit(d: Path, files: List[str]) -> Optional[dict]:
    if "Gemfile" in files and "rails" in _read(d / "Gemfile"):
        api = "api_only = true" in _read(d / "config" / "application.rb")
        cmds = {"test": "bundle exec rspec" if (d / "spec").is_dir() else "bin/rails test"}
        if (d / ".rubocop.yml").is_file():
            cmds["lint"] = "bundle exec rubocop"
        return {"language": "ruby", "framework": "rails", "layer": "backend" if api else "fullstack",
                "stack": "ruby", "commands": cmds}
    if "composer.json" in files:
        req = _json(d / "composer.json").get("require") or {}
        fw = "laravel" if "laravel/framework" in req else "symfony" if any(k.startswith("symfony/framework") for k in req) else None
        if fw:
            views = (d / "resources" / "views").is_dir() or (d / "templates").is_dir()
            cmds = {"test": "php artisan test" if fw == "laravel" else "vendor/bin/phpunit"}
            if (d / "phpstan.neon").is_file() or (d / "phpstan.neon.dist").is_file():
                cmds["typecheck"] = "vendor/bin/phpstan analyse"
            if (d / "vendor" / "bin" / "pint").exists() or "laravel/pint" in json.dumps(_json(d / "composer.json")):
                cmds["format"] = "vendor/bin/pint --test"
            return {"language": "php", "framework": fw, "layer": "fullstack" if views else "backend",
                    "stack": "php", "commands": cmds}
    if "mix.exs" in files:
        text = _read(d / "mix.exs")
        if ":phoenix" in text:
            cmds = {"test": "mix test", "format": "mix format --check-formatted"}
            if ":credo" in text:
                cmds["lint"] = "mix credo"
            return {"language": "elixir", "framework": "phoenix",
                    "layer": "fullstack" if "phoenix_live_view" in text else "backend",
                    "stack": "elixir", "commands": cmds}
    if "Cargo.toml" in files:
        text = _read(d / "Cargo.toml")
        if "[workspace]" in text and "[package]" not in text:
            return None
        cmds = {"test": "cargo test", "lint": "cargo clippy -- -D warnings", "format": "cargo fmt --check",
                "build": "cargo build"}
        if any(re.search(r"^\s*%s\s*=" % re.escape(k), text, re.M) for k in RUST_WEB):
            return {"language": "rust", "framework": next(k for k in RUST_WEB if re.search(r"^\s*%s\s*=" % re.escape(k), text, re.M)),
                    "layer": "backend", "stack": "rust", "commands": cmds}
        if any(re.search(r"^\s*%s\s*=" % k, text, re.M) for k in RUST_UI):
            return {"language": "rust", "framework": next(k for k in RUST_UI if re.search(r"^\s*%s\s*=" % k, text, re.M)),
                    "layer": "frontend", "stack": "rust-ui", "commands": cmds}
    if "pubspec.yaml" in files and "flutter" in _read(d / "pubspec.yaml"):
        return {"language": "dart", "framework": "flutter", "layer": "frontend", "stack": "flutter",
                "commands": {"test": "flutter test", "lint": "flutter analyze"}}
    return None


def _units_at(d: Path, files: List[str], root: Path) -> List[dict]:
    """Every unit rooted in this directory. One folder can hold two: a Go or Java backend with
    the frontend's package.json next to it is common, and both must be found."""
    out: List[dict] = []
    if "package.json" in files:
        u = _js_unit(d, root, _json(d / "package.json"))
        if u:
            out.append(u)
    if "go.mod" in files:
        out.append(_go_unit(d, root))
    for fn in (_dotnet_unit, _jvm_unit, _py_unit, _other_unit):
        u = fn(d, files) if fn is not _jvm_unit or {"pom.xml", "build.gradle", "build.gradle.kts"} & set(files) else None
        if u:
            out.append(u)
    seen, uniq = set(), []
    for u in out:
        if u["language"] not in seen:
            seen.add(u["language"])
            uniq.append(u)
    return uniq


def _agent(layer: str, stack: str) -> List[str]:
    """The builder name this unit gets: be-go, fe-angular, or fs-next for a unit that is both."""
    return [{"backend": "be-", "frontend": "fe-"}.get(layer, "fs-") + stack]


def _units(root: Path) -> List[dict]:
    found: List[dict] = []
    for d, files, _ in _walk(root):
        path = _rel(root, d)
        for u in _units_at(d, files, root):
            # a unit inside another unit of the same language is one of its parts (a Java/Go submodule)
            if any(path != "." and (o["path"] == "." or path.startswith(o["path"] + "/"))
                   and o["language"] == u["language"] and o["layer"] != "frontend" and u["layer"] == o["layer"]
                   for o in found):
                continue
            u["path"] = path
            found.append(u)
    shared = {u["path"] for u in found if sum(o["path"] == u["path"] for o in found) > 1}
    names: Dict[str, int] = {}
    for u in found:
        base = Path(u["path"]).name if u["path"] != "." else root.name
        if u["path"] in shared:
            # with a backend in the same folder, the JS side is only the frontend
            if u["layer"] == "fullstack" and u["language"] in ("typescript", "javascript"):
                u["layer"] = "frontend"
            base = "%s-%s" % (base, u["stack"])
        base = re.sub(r"[^a-zA-Z0-9_-]+", "-", base).strip("-").lower() or "app"
        names[base] = names.get(base, 0) + 1
        u["name"] = base if names[base] == 1 else "%s-%d" % (base, names[base])
        u["agents"] = _agent(u["layer"], u["stack"])
        u["modules"] = _modules(root / u["path"]) if u["layer"] != "frontend" else []
        u.pop("deps", None)
    return found


def _modules(unit: Path) -> List[str]:
    for rel in MODULE_DIRS:
        d = unit / rel
        if d.is_dir():
            mods = sorted(p.name for p in d.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))
                          and p.name not in ("shared", "common", "core", "platform", "kernel"))
            if len(mods) >= 2:
                return [rel + "/"] + mods[:30]
    return []


SOURCE_EXT = {".go": "go", ".java": "java", ".kt": "kotlin", ".cs": "csharp", ".py": "python", ".rb": "ruby",
              ".php": "php", ".rs": "rust", ".ex": "elixir"}


def _unclaimed(root: Path, units: List[dict]) -> List[dict]:
    """Source code in a backend language that no unit accounts for: the scan missed an app."""
    have = {u["language"] for u in units}
    counts: Dict[str, Dict[str, int]] = {}
    for d, files, lvl in _walk(root, 6):
        top = _rel(root, d).split("/")[0]
        if top in ("scripts", "tools", "tests", "test", "hack", "ci", ".github"):
            continue
        for f in files:
            lang = SOURCE_EXT.get(os.path.splitext(f)[1])
            if lang and lang not in have:
                counts.setdefault(lang, {}).setdefault(top, 0)
                counts[lang][top] += 1
    out = []
    for lang, tops in counts.items():
        total = sum(tops.values())
        if total >= 8:
            where = max(tops, key=tops.get)
            out.append({"language": lang, "files": total, "mostly_in": where + "/" if where != "." else "./"})
    return sorted(out, key=lambda x: -x["files"])


# -- contracts, data, tooling ------------------------------------------------------------------

def _contracts(root: Path, units: List[dict]) -> dict:
    kinds: Dict[str, List[str]] = {}
    for d, files, lvl in _walk(root, 5):
        rel_dir = _rel(root, d)
        in_contract_dir = any(part in CONTRACT_DIRS for part in Path(rel_dir).parts)
        for f in files:
            low = f.lower()
            path = (rel_dir + "/" + f) if rel_dir != "." else f
            if low.endswith(".proto"):
                kinds.setdefault("protobuf", []).append(path)
            elif low.endswith((".graphql", ".graphqls", ".gql")):
                kinds.setdefault("graphql", []).append(path)
            elif low.endswith((".yaml", ".yml", ".json")) and (in_contract_dir or re.search(r"openapi|swagger|asyncapi|api\.", low)):
                if low in ("package.json", "tsconfig.json", "composer.json", "package-lock.json"):
                    continue
                head = _read(d / f, 600)
                if re.search(r"^\s*[\"']?openapi[\"']?\s*:", head, re.M) or re.search(r"^\s*[\"']?swagger[\"']?\s*:", head, re.M):
                    kinds.setdefault("openapi", []).append(path)
                elif re.search(r"^\s*[\"']?asyncapi[\"']?\s*:", head, re.M):
                    kinds.setdefault("asyncapi", []).append(path)
                elif low.endswith(".schema.json") and in_contract_dir:
                    kinds.setdefault("json-schema", []).append(path)
    deps = set()
    for u in units:
        p = root / u["path"] / "package.json"
        if p.is_file():
            pkg = _json(p)
            for k in ("dependencies", "devDependencies"):
                deps.update((pkg.get(k) or {}).keys())
    rootpkg = _json(root / "package.json")
    for k in ("dependencies", "devDependencies"):
        deps.update((rootpkg.get(k) or {}).keys())
    if "@trpc/server" in deps or "@ts-rest/core" in deps or "@orpc/server" in deps:
        kinds.setdefault("typed", [])
    files = [f for k, v in kinds.items() if k != "typed" for f in v]
    roots = sorted({f.split("/")[0] for f in files if "/" in f})
    per_module = False
    for r in roots:
        subs = {f.split("/")[1] for f in files if f.startswith(r + "/") and f.count("/") >= 2}
        if len(subs) >= 2 and r in CONTRACT_DIRS:
            per_module = True
    tools = []
    for marker, tool in (("redocly.yaml", "redocly"), (".redocly.yaml", "redocly"), (".spectral.yaml", "spectral"),
                         (".spectral.yml", "spectral"), ("buf.yaml", "buf"), ("buf.gen.yaml", "buf"),
                         ("orval.config.ts", "orval"), ("orval.config.js", "orval"), ("codegen.ts", "graphql-codegen"),
                         ("codegen.yml", "graphql-codegen"), ("nswag.json", "nswag"), ("openapitools.json", "openapi-generator")):
        if any((root / r / marker).is_file() for r in ["."] + roots + [u["path"] for u in units]):
            tools.append(tool)
    for dep, tool in (("@redocly/cli", "redocly"), ("@stoplight/spectral-cli", "spectral"), ("orval", "orval"),
                      ("openapi-typescript", "openapi-typescript"), ("@graphql-codegen/cli", "graphql-codegen"),
                      ("@asyncapi/cli", "asyncapi-cli"), ("@hey-api/openapi-ts", "hey-api")):
        if dep in deps:
            tools.append(tool)
    order = ["openapi", "asyncapi", "protobuf", "graphql", "json-schema", "typed"]
    return {"kinds": [k for k in order if k in kinds],
            "root": roots[0] + "/" if len(roots) == 1 else None,
            "roots": [r + "/" for r in roots],
            "per_module": per_module,
            "files": sum(len(v) for k, v in kinds.items() if k != "typed"),
            "tools": sorted(set(tools)),
            "check": None}


def _scripts(root: Path, root_is_unit: bool = False) -> Dict[str, str]:
    """Project-wide commands: Makefile / justfile / Taskfile targets and root package scripts."""
    out: Dict[str, str] = {}
    wanted = ("check", "verify", "ci", "test", "lint", "build", "generate", "codegen", "contracts",
              "contract", "contracts-check", "api-check", "openapi", "proto", "typecheck", "e2e")
    mk = _read(root / "Makefile") or _read(root / "makefile")
    for t in re.findall(r"^([a-zA-Z0-9_.:-]+):(?!=)", mk, re.M):
        if t in wanted:
            out[t] = "make " + t
    jf = _read(root / "justfile") or _read(root / "Justfile")
    for t in re.findall(r"^([a-zA-Z0-9_-]+)(?:\s[^:\n]*)?:(?!=)", jf, re.M):
        if t in wanted and t not in out:
            out[t] = "just " + t
    tf = _read(root / "Taskfile.yml") or _read(root / "Taskfile.yaml")
    for t in re.findall(r"^  ([a-zA-Z0-9_:-]+):\s*$", tf, re.M):
        if t in wanted and t not in out:
            out[t] = "task " + t
    pkg = {} if root_is_unit else _json(root / "package.json")
    run = {"npm": "npm run", "pnpm": "pnpm run", "yarn": "yarn", "bun": "bun run"}[_pm(root, root)]
    for t in (pkg.get("scripts") or {}):
        key = t.replace(":", "-")
        if (key in wanted or any(w in t for w in ("contract", "openapi", "codegen", "generate"))) and key not in out:
            out[key] = "%s %s" % (run, t)
    return out


def _contract_check(scripts: Dict[str, str], contracts: dict) -> Optional[str]:
    for name in ("contracts-check", "contracts", "contract", "api-check", "openapi", "proto", "codegen", "generate"):
        for k, v in scripts.items():
            if k == name or (name in k and "watch" not in k):
                return v
    if "protobuf" in contracts["kinds"] and "buf" in contracts["tools"]:
        return "buf lint && buf breaking --against '.git#branch=main'"
    return None


def _data(root: Path, units: List[dict]) -> dict:
    hits = []
    pats = ("migrations", "migration", "db/migrate", "prisma/migrations", "drizzle", "Migrations",
            "src/main/resources/db/migration", "src/main/resources/db/changelog", "priv/repo/migrations",
            "database/migrations", "alembic")
    for u in units:
        base = root / u["path"]
        for p in pats:
            for cand in [base / p] + list(base.glob("*/" + p)) + list(base.glob("internal/*/" + p)):
                if cand.is_dir():
                    hits.append(_rel(root, cand) + "/")
    for p in pats:
        if (root / p).is_dir():
            hits.append(p + "/")
    return {"migrations": sorted(set(hits))[:10]}


def _infra(root: Path) -> dict:
    compose_builds = 0
    for name in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        text = _read(root / name)
        compose_builds = max(compose_builds, len(re.findall(r"^\s+build\s*:", text, re.M)))
    k8s = any((root / d).is_dir() for d in ("k8s", "kubernetes", "helm", "charts", "deploy/k8s", "manifests"))
    serverless = [n for n in ("serverless.yml", "serverless.yaml", "sst.config.ts", "template.yaml", "samconfig.toml",
                              "netlify.toml", "firebase.json", "wrangler.toml", "wrangler.jsonc")
                  if (root / n).is_file()]
    services_dir = next((d for d in ("services", "microservices", "svc") if (root / d).is_dir()), None)
    return {"compose_builds": compose_builds, "kubernetes": k8s, "serverless": serverless, "services_dir": services_dir}


def _boundaries(root: Path, units: List[dict]) -> List[str]:
    blob = ""
    for p in [root / "package.json", root / ".eslintrc.json", root / "eslint.config.js", root / "eslint.config.mjs",
              root / "nx.json", root / ".dependency-cruiser.js", root / ".dependency-cruiser.cjs",
              root / "pyproject.toml", root / ".importlinter", root / "deptrac.yaml", root / "packwerk.yml",
              root / ".go-arch-lint.yml"] + [root / u["path"] / n for u in units
                                             for n in ("package.json", "pom.xml", "build.gradle", "build.gradle.kts",
                                                       "pyproject.toml", ".go-arch-lint.yml", "eslint.config.js",
                                                       ".eslintrc.json", "Directory.Packages.props")]:
        if p.is_file():
            blob += p.name + "\n" + _read(p, 60_000).lower()
    found = [label for key, label in BOUNDARY_TOOLS.items() if key in blob]
    if ".go-arch-lint.yml" in blob:
        found.append("go-arch-lint")
    if "depguard" in blob:
        found.append("depguard")
    return sorted(set(found))


# -- architecture ------------------------------------------------------------------------------

def _architecture(units: List[dict], contracts: dict, infra: dict, boundaries: List[str]) -> Tuple[str, str, List[str]]:
    back = [u for u in units if u["layer"] in ("backend", "fullstack")]
    front = [u for u in units if u["layer"] == "frontend"]
    modular = [u for u in back if u.get("modules")]
    why: List[str] = []
    svc_units = [u for u in back if infra["services_dir"] and u["path"].startswith(infra["services_dir"] + "/")]
    if len(back) >= 2 and (len(svc_units) >= 2 or infra["kubernetes"] or infra["compose_builds"] >= 2):
        why.append("%d deployable backends" % len(back))
        if len(svc_units) >= 2:
            why.append("%s/ holds %d services" % (infra["services_dir"], len(svc_units)))
        if infra["kubernetes"]:
            why.append("Kubernetes manifests")
        if infra["compose_builds"] >= 2:
            why.append("compose builds %d images" % infra["compose_builds"])
        return "microservices", "high" if len(why) >= 3 else "medium", why
    if modular or any(u.get("modulith") for u in back) or (contracts["per_module"] and back):
        if modular:
            why.append("%s has modules in %s (%s)" % (modular[0]["name"], modular[0]["modules"][0],
                                                     ", ".join(modular[0]["modules"][1:6])))
        if contracts["per_module"]:
            why.append("one contract folder per module")
        if boundaries:
            why.append("boundary checks: " + ", ".join(boundaries))
        if any(u.get("modulith") for u in back):
            why.append("Spring Modulith")
        return "modular-monolith", "high" if len(why) >= 2 else "medium", why
    if infra["serverless"] and not back:
        return "serverless", "high", ["deployment config: " + ", ".join(infra["serverless"])]
    if infra["serverless"]:
        why.append("deployment config: " + ", ".join(infra["serverless"]))
    if len(back) == 1 and back[0]["layer"] == "fullstack" and not [u for u in back if u["layer"] == "backend"]:
        why.append("%s (%s) serves pages and data" % (back[0]["name"], back[0]["framework"]))
        return "fullstack-app", "high", why
    if back:
        why.append("%d backend%s, no module structure found" % (len(back), "s" if len(back) > 1 else ""))
        if len(back) >= 2:
            why.append("several backends without deployment config: could also be services")
        return "monolith", "medium" if len(back) == 1 else "low", why
    if front:
        return "frontend-only", "high", ["%d frontend app%s, no backend in this repository" % (len(front), "s" if len(front) > 1 else "")]
    return "monolith", "low", ["no application manifest recognised"]


# -- public API -------------------------------------------------------------------------------

def scan(root: Path) -> dict:
    root = Path(root).resolve()
    units = _units(root)
    contracts = _contracts(root, units)
    scripts = _scripts(root, any(u["path"] == "." for u in units))
    contracts["check"] = _contract_check(scripts, contracts)
    infra = _infra(root)
    boundaries = _boundaries(root, units)
    kind, confidence, why = _architecture(units, contracts, infra, boundaries)
    monorepo = next((n for f, n in (("nx.json", "nx"), ("turbo.json", "turbo"), ("pnpm-workspace.yaml", "pnpm"),
                                    ("lerna.json", "lerna"), ("go.work", "go-work"), ("rush.json", "rush"))
                     if (root / f).is_file()), None)
    e2e = next((n for n in ("playwright.config.ts", "playwright.config.js", "cypress.config.ts", "cypress.config.js")
                if (root / n).is_file() or any((root / u["path"] / n).is_file() for u in units)), None)
    guide = [n for n in ("CLAUDE.md", "AGENTS.md", "GEMINI.md", ".cursorrules") if (root / n).is_file()]
    return {
        "agentack": "2.1",
        "architecture": {"kind": kind, "confidence": confidence, "why": why},
        "units": units,
        "unclaimed": _unclaimed(root, units),
        "contracts": contracts,
        "commands": scripts,
        "data": _data(root, units),
        "boundaries": boundaries,
        "monorepo": monorepo,
        "e2e": e2e.split(".")[0] if e2e else None,
        "guide": guide,
    }


def _merge_units(units: List[dict], over: dict) -> List[dict]:
    out = []
    for u in units:
        o = over.get(u["name"]) or {}
        out.append(config._merge(u, o) if o else dict(u))
    for name, o in over.items():
        if not any(u["name"] == name for u in units) and o.get("path") and o.get("layer") in LAYERS:
            out.append(dict({"name": name, "language": o.get("stack"), "framework": None, "commands": {},
                             "modules": [], "stack": o.get("stack") or "app"}, **o))
    for u in out:
        u["agents"] = _agent(u["layer"], u.get("stack") or u.get("language") or "app")
    return out


def effective(cfg: dict) -> Optional[dict]:
    """The saved profile with the project's own overrides applied, or None when never initialised."""
    prof = cfg.get("project")
    if not isinstance(prof, dict) or "units" not in prof:
        return None
    over = cfg.get("project_override") or {}
    units = _merge_units(prof["units"], over.get("units") or {})
    merged = config._merge(prof, {k: v for k, v in over.items() if k != "units"})
    merged["units"] = units
    if isinstance(over.get("architecture"), str):
        merged["architecture"] = dict(prof["architecture"], kind=over["architecture"], confidence="set by hand")
    return merged


def project_file(root: Path) -> Path:
    return Path(root) / ".agentack.json"


def save(root: Path, profile: dict) -> Tuple[bool, Path]:
    """Write the scan into .agentack.json, keeping everything else in that file. Returns (changed, path)."""
    path = project_file(root)
    data = config.read_json(path) or {}
    if data.get("project") == profile:
        return False, path
    data["project"] = profile
    config.write_json(path, data)
    return True, path


def set_override(root: Path, assignments: List[str]) -> dict:
    """`architecture=microservices`, `contracts.check=make contracts`, `units.api.commands.test=make test`."""
    path = project_file(root)
    data = config.read_json(path) or {}
    over = data.get("project_override") or {}
    for item in assignments:
        if "=" not in item:
            raise ValueError("expected key=value, got %r" % item)
        key, value = item.split("=", 1)
        parts = key.strip().split(".")
        if parts[0] == "architecture" and len(parts) == 1 and value not in KINDS:
            raise ValueError("architecture must be one of: " + ", ".join(KINDS))
        if parts[-1] == "layer" and value not in LAYERS:
            raise ValueError("layer must be one of: " + ", ".join(LAYERS))
        node = over
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        if value == "":
            node.pop(parts[-1], None)
        else:
            node[parts[-1]] = value
    data["project_override"] = over
    config.write_json(path, data)
    return over


def changes(old: Optional[dict], new: dict) -> List[str]:
    """What a re-scan found that differs from the saved profile, in words."""
    if not old:
        return []
    out = []
    a = {u["name"]: u for u in old.get("units") or []}
    b = {u["name"]: u for u in new.get("units") or []}
    for n in sorted(set(b) - set(a)):
        out.append("new unit %s (%s)" % (n, ", ".join(b[n]["agents"])))
    for n in sorted(set(a) - set(b)):
        out.append("unit %s is gone" % n)
    for n in sorted(set(a) & set(b)):
        if (a[n].get("framework"), a[n].get("layer")) != (b[n].get("framework"), b[n].get("layer")):
            out.append("%s is now %s %s" % (n, b[n].get("framework"), b[n]["layer"]))
    if old.get("architecture", {}).get("kind") != new["architecture"]["kind"]:
        out.append("architecture looks like %s now (was %s)" % (new["architecture"]["kind"], old["architecture"]["kind"]))
    if old.get("contracts", {}).get("kinds") != new["contracts"]["kinds"]:
        out.append("contracts: %s" % (", ".join(new["contracts"]["kinds"]) or "none"))
    return out


# -- what a role gets -------------------------------------------------------------------------

def pick_unit(profile: dict, layer: str, unit: Optional[str] = None, stack: Optional[str] = None) -> dict:
    """The unit a builder works in. Raises ValueError with the choices when it is ambiguous."""
    units = profile.get("units") or []
    if unit:
        hit = [u for u in units if u["name"] == unit or u["path"] == unit.rstrip("/")]
        if not hit:
            raise ValueError("no unit named %s (units: %s)" % (unit, ", ".join(u["name"] for u in units) or "none"))
        return hit[0]
    fit = [u for u in units if u["layer"] == layer or u["layer"] == "fullstack"]
    if stack:
        fit = [u for u in fit if stack in (u.get("stack"), u.get("language"), u.get("framework"))] or fit
    if len(fit) == 1:
        return fit[0]
    if not fit:
        raise ValueError("this project has no %s unit (units: %s)" % (layer, ", ".join(
            "%s=%s" % (u["name"], u["layer"]) for u in units) or "none"))
    raise ValueError("several %s units: %s; pass --unit" % (layer, ", ".join(
        "%s (%s)" % (u["name"], "/".join(u["agents"])) for u in fit)))


def label(role: str, unit: Optional[dict]) -> str:
    """be-go / fe-angular / fs-next for builders; the role itself for everyone else."""
    if not unit or role not in ("backend", "frontend"):
        return role
    stack = unit.get("stack") or unit.get("language") or "app"
    return ("fs-" if unit["layer"] == "fullstack" else "be-" if role == "backend" else "fe-") + stack


def _commands_line(u: dict) -> str:
    cmds = u.get("commands") or {}
    return " · ".join("%s: `%s`" % (k, v) for k, v in cmds.items()) or "none detected: find them in the unit's README or CI"


def describe_unit(u: dict) -> str:
    bits = [u.get("language"), u.get("framework")]
    lines = ["- Unit: `%s/` · %s · %s" % (u["path"].rstrip("/") if u["path"] != "." else ".",
                                           " / ".join(b for b in bits if b), u["layer"])]
    lines.append("- Commands (run inside the unit): " + _commands_line(u))
    if u.get("modules"):
        lines.append("- Modules in `%s`: %s" % (u["modules"][0], ", ".join(u["modules"][1:])))
    return "\n".join(lines)


def describe(profile: dict, short: bool = False) -> str:
    a = profile["architecture"]
    out = ["- Architecture: %s (%s)" % (a["kind"], a.get("confidence"))]
    for u in profile.get("units") or []:
        out.append("- %s `%s/` %s · %s%s" % ("/".join(u["agents"]), u["path"], u.get("framework") or u.get("language"),
                                          u["layer"], "" if short or not u.get("modules") else
                                          " · modules: " + ", ".join(u["modules"][1:8])))
    c = profile.get("contracts") or {}
    if c.get("kinds"):
        where = c.get("root") or ", ".join(c.get("roots") or []) or "the code (tRPC / ts-rest types)"
        out.append("- Contracts: %s in %s%s" % (", ".join(c["kinds"]), where,
                                                 "" if not c.get("check") else " · check: `%s`" % c["check"]))
    else:
        out.append("- Contracts: none found; the interface between units is the code itself")
    if not short:
        if profile.get("commands"):
            out.append("- Project commands: " + " · ".join("`%s`" % v for v in profile["commands"].values()))
        if (profile.get("data") or {}).get("migrations"):
            out.append("- Migrations: " + ", ".join(profile["data"]["migrations"]))
        if profile.get("boundaries"):
            out.append("- Boundary checks: " + ", ".join(profile["boundaries"]))
        if profile.get("e2e"):
            out.append("- E2E: " + profile["e2e"])
    return "\n".join(out)


def section(path: Path, heading: str) -> str:
    """One `## heading` section of a reference file, without the heading."""
    text = _read(path)
    m = re.search(r"^## %s\s*\n(.*?)(?=^## |\Z)" % re.escape(heading), text, re.M | re.S)
    return m.group(1).strip() if m else ""


def load(root: Path, cfg: dict) -> Tuple[dict, bool]:
    """(profile, saved): the saved profile, or a fresh scan held in memory when init never ran."""
    prof = effective(cfg)
    if prof:
        return prof, True
    return scan(root), False
