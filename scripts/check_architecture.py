from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
SCRIPTS = ROOT / "scripts"
FORM_OPTIONS = ROOT / "app" / "src" / "renderer" / "form-options.ts"
SHARED_SCAN_ROOTS = [
    ROOT / "README.md",
    ROOT / "app" / "src",
    ROOT / "config",
    ROOT / "docs",
    ROOT / "scripts",
]


def fail(message: str) -> None:
    print(f"architecture check failed: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_manifest() -> dict[str, Any]:
    path = CONFIG / "workflow_actions.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"cannot load {path}: {error}")
    if not isinstance(payload, dict):
        fail(f"{path} must contain a JSON object")
    return payload


def string_list(payload: dict[str, Any], key: str) -> list[str]:
    value = payload.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        fail(f"workflow_actions.json key {key!r} must be a string array")
    return value


def string_dict(payload: dict[str, Any], key: str) -> dict[str, str]:
    value = payload.get(key)
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        fail(f"workflow_actions.json key {key!r} must be a string map")
    return value


def renderer_workflow_actions() -> list[str]:
    text = FORM_OPTIONS.read_text(encoding="utf-8")
    match = re.search(r"export const WORKFLOW_ACTIONS = \[(.*?)\] as const;", text, re.S)
    if not match:
        fail("cannot find WORKFLOW_ACTIONS in app/src/renderer/form-options.ts")
    return re.findall(r'\[\s*"([^"]+)"\s*,', match.group(1))


def assert_no_duplicates(name: str, values: list[str]) -> None:
    seen: set[str] = set()
    duplicates = sorted({value for value in values if value in seen or seen.add(value)})
    if duplicates:
        fail(f"{name} contains duplicate values: {', '.join(duplicates)}")


def assert_project_boundary() -> None:
    if (SCRIPTS / "build_event_highlight.py").exists():
        fail("project-specific event highlight scripts must stay under the owning project's scripts directory")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    required_rules = [
        "!/projects/*/*.md",
        "!/projects/*/scripts/",
        "!/projects/*/scripts/**",
        "!/projects/*/config/",
        "!/projects/*/config/**",
    ]
    missing = [rule for rule in required_rules if rule not in gitignore]
    if missing:
        fail(f".gitignore is missing project tracking rules: {', '.join(missing)}")


def shared_text_files() -> list[Path]:
    files: list[Path] = []
    for root in SHARED_SCAN_ROOTS:
        if root.is_file():
            files.append(root)
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".json", ".md", ".py", ".ts", ".tsx"}:
                files.append(path)
    return files


def assert_no_project_specific_shared_references() -> None:
    banned_terms = [
        "260526" + "-birthday",
        "new" + "-folder-2",
        "app_" + "interview_output",
        "camera" + " audit",
        "camera5" + " color",
        "birthday" + "_preview",
        "birthday" + "_highlight",
    ]
    violations: list[str] = []
    for path in shared_text_files():
        if path == Path(__file__).resolve():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lowered = text.lower()
        hits = [term for term in banned_terms if term.lower() in lowered]
        if hits:
            relative = path.relative_to(ROOT).as_posix()
            violations.append(f"{relative}: {', '.join(hits)}")
    if violations:
        fail("project-specific references found in shared files: " + "; ".join(violations))


def assert_renderer_boundary() -> None:
    shim = SCRIPTS / "render_app_interview.py"
    implementation = SCRIPTS / "render_multicam.py"
    if not shim.is_file() or not implementation.is_file():
        fail("render_multicam.py and render_app_interview.py must both exist")
    shim_text = shim.read_text(encoding="utf-8")
    implementation_text = implementation.read_text(encoding="utf-8")
    if "from render_multicam import main" not in shim_text or len(shim_text.splitlines()) > 12:
        fail("render_app_interview.py must remain a small compatibility shim around render_multicam.py")
    if "render_app_interview" in implementation_text:
        fail("render_multicam.py must not import or depend on render_app_interview.py")


def main() -> None:
    manifest = load_manifest()
    python_scripts = string_list(manifest, "pythonScripts")
    render_scripts = string_list(manifest, "renderScripts")
    workflow_actions = string_list(manifest, "workflowActions")
    simple_actions = string_dict(manifest, "simplePythonActions")
    render_aliases = string_dict(manifest, "renderScriptAliases")

    for name, values in (
        ("pythonScripts", python_scripts),
        ("renderScripts", render_scripts),
        ("workflowActions", workflow_actions),
        ("simplePythonActions keys", list(simple_actions)),
    ):
        assert_no_duplicates(name, values)

    for script in python_scripts:
        if not (SCRIPTS / script).is_file():
            fail(f"pythonScripts references missing file: scripts/{script}")

    python_script_set = set(python_scripts)
    for action, script in simple_actions.items():
        if action not in workflow_actions:
            fail(f"simplePythonActions contains action not listed in workflowActions: {action}")
        if script not in python_script_set:
            fail(f"simplePythonActions maps {action} to script outside pythonScripts: {script}")

    render_script_set = set(render_scripts)
    for script in render_scripts:
        if script not in python_script_set:
            fail(f"renderScripts entry is not allowlisted in pythonScripts: {script}")
    for source, target in render_aliases.items():
        if source not in render_script_set or target not in render_script_set:
            fail(f"renderScriptAliases must map renderScripts to renderScripts: {source} -> {target}")

    renderer_actions = renderer_workflow_actions()
    assert_no_duplicates("renderer WORKFLOW_ACTIONS", renderer_actions)
    if renderer_actions != workflow_actions:
        missing_in_renderer = [action for action in workflow_actions if action not in renderer_actions]
        missing_in_manifest = [action for action in renderer_actions if action not in workflow_actions]
        details = []
        if missing_in_renderer:
            details.append(f"missing in renderer: {', '.join(missing_in_renderer)}")
        if missing_in_manifest:
            details.append(f"missing in manifest: {', '.join(missing_in_manifest)}")
        fail("workflow action order/list mismatch; " + "; ".join(details))

    assert_project_boundary()
    assert_no_project_specific_shared_references()
    assert_renderer_boundary()
    print("architecture check passed")


if __name__ == "__main__":
    main()
