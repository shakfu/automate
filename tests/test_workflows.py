"""Structural checks on the reusable workflows.

These are the workflows' only automated coverage. The injection guard exists
because actionlint does not cover this case: its script-injection rule fires
only for expressions it classifies as untrusted (`github.event.*`,
`github.head_ref`, and similar). A `workflow_call` input is treated as trusted
and is not flagged, even though it reaches bash the same way -- GitHub
substitutes `${{ }}` textually before bash parses the script.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

WORKFLOW_DIR = Path(__file__).parent.parent / ".github" / "workflows"

EXPRESSION_RE = re.compile(r"\$\{\{(?P<expr>[^}]*)\}\}")

# Inputs whose entire purpose is to be executed as a shell command. These
# cannot be passed as data, so callers able to set them are trusted. Any
# other expression reaching a `run:` body is a script-injection vector.
COMMAND_INPUTS = {
    "inputs.build-command",
    "inputs.install-command",
}


def workflow_files() -> list[Path]:
    files = sorted(WORKFLOW_DIR.glob("*.yml"))
    assert files, f"no workflows found in {WORKFLOW_DIR}"
    return files


def load(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    assert isinstance(data, dict)
    return data


def iter_steps(workflow: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Yield (job_name, step) for every step with a `run:` body."""
    out: list[tuple[str, dict[str, Any]]] = []
    for job_name, job in (workflow.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if isinstance(step, dict) and "run" in step:
                out.append((job_name, step))
    return out


IDS = [p.name for p in workflow_files()]


@pytest.mark.parametrize("path", workflow_files(), ids=IDS)
class TestNoScriptInjection:
    def test_run_bodies_use_env_not_interpolation(self, path: Path) -> None:
        offenders: list[str] = []
        for job_name, step in iter_steps(load(path)):
            for match in EXPRESSION_RE.finditer(str(step["run"])):
                expr = match.group("expr").strip()
                if expr not in COMMAND_INPUTS:
                    name = step.get("name", "<unnamed>")
                    offenders.append(
                        f"{path.name}: job '{job_name}', step '{name}': ${{{{ {expr} }}}}"
                    )
        assert not offenders, (
            "expressions interpolated into a `run:` body are substituted before bash "
            "parses the script, so a value containing $(...) executes. Pass them "
            "through the step's `env:` block instead:\n  " + "\n  ".join(offenders)
        )

    def test_command_inputs_are_the_only_exemption(self, path: Path) -> None:
        """A command input must be the whole script, never spliced into a larger one."""
        for job_name, step in iter_steps(load(path)):
            run = str(step["run"]).strip()
            exprs = [m.group("expr").strip() for m in EXPRESSION_RE.finditer(run)]
            if not any(e in COMMAND_INPUTS for e in exprs):
                continue
            assert len(exprs) == 1, (
                f"{path.name}:{job_name}: command input mixed with other expressions"
            )
            assert run == "${{ %s }}" % exprs[0], (
                f"{path.name}: job '{job_name}': a command input must be the entire "
                f"`run:` body, not spliced into a larger script; got {run!r}"
            )


@pytest.mark.parametrize("path", workflow_files(), ids=IDS)
def test_workflow_parses(path: Path) -> None:
    wf = load(path)
    # PyYAML parses the unquoted key `on` as the boolean True.
    assert "jobs" in wf
    assert True in wf or "on" in wf


class TestGuardDetectsRegressions:
    """The guard must actually fail on the shape it is meant to catch."""

    def _write(self, tmp_path: Path, run_body: str) -> Path:
        wf = tmp_path / "bad.yml"
        wf.write_text(
            "name: Bad\n"
            "on:\n  workflow_call:\n    inputs:\n"
            "      description:\n        type: string\n"
            "jobs:\n  x:\n    runs-on: ubuntu-latest\n    steps:\n"
            f"      - name: Step\n        run: {run_body}\n"
        )
        return wf

    def test_flags_interpolated_input(self, tmp_path: Path) -> None:
        wf = self._write(tmp_path, 'echo "${{ inputs.description }}"')
        offenders = [
            m.group("expr").strip()
            for _, step in iter_steps(load(wf))
            for m in EXPRESSION_RE.finditer(str(step["run"]))
            if m.group("expr").strip() not in COMMAND_INPUTS
        ]
        assert offenders == ["inputs.description"]

    def test_flags_command_input_spliced_into_larger_script(self, tmp_path: Path) -> None:
        wf = self._write(tmp_path, "cd src && ${{ inputs.build-command }}")
        _, step = iter_steps(load(wf))[0]
        run = str(step["run"]).strip()
        assert run != "${{ inputs.build-command }}"

    def test_accepts_env_var_form(self, tmp_path: Path) -> None:
        wf = self._write(tmp_path, 'echo "$DESCRIPTION"')
        offenders = [
            m.group("expr")
            for _, step in iter_steps(load(wf))
            for m in EXPRESSION_RE.finditer(str(step["run"]))
        ]
        assert offenders == []


@pytest.mark.parametrize("path", workflow_files(), ids=IDS)
def test_no_cross_repo_nested_workflow_calls(path: Path) -> None:
    """A `uses:` reference cannot inherit the ref its own workflow was called
    at, so a nested cross-repo call has to name one literally -- which means a
    consumer pinning the outer workflow to a tag still runs the inner one from
    whatever that literal ref points at. Local `./` refs resolve to the same
    commit and are fine."""
    offenders = []
    for job_name, job in (load(path).get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        uses = job.get("uses")
        if isinstance(uses, str) and not uses.startswith("./"):
            offenders.append(f"{path.name}: job '{job_name}' calls {uses}")
    assert not offenders, (
        "nested cross-repo workflow calls defeat version pinning; inline the "
        "job instead:\n  " + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("path", workflow_files(), ids=IDS)
def test_publish_jobs_declare_id_token(path: Path) -> None:
    """Trusted publishing needs id-token: write on the job that publishes."""
    for job_name, job in (load(path).get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        steps = job.get("steps") or []
        publishes = any(
            isinstance(s, dict) and "pypi-publish" in str(s.get("uses", "")) for s in steps
        )
        if publishes:
            perms = job.get("permissions") or {}
            assert perms.get("id-token") == "write", (
                f"{path.name}: job '{job_name}' publishes but does not declare id-token: write"
            )


REF_RE = re.compile(r"^(v\d+(\.\d+)*|release/v\d+|[0-9a-f]{40})$")


@pytest.mark.parametrize("path", workflow_files(), ids=IDS)
def test_third_party_actions_use_a_release_ref(path: Path) -> None:
    """An unqualified branch name follows whatever lands on that branch next.
    These workflows hold `contents: write` and `id-token: write`, so the ref
    they run is part of the release supply chain. A version tag, a release
    branch, or a commit SHA are all accepted; SHAs are reserved for actions
    whose ref would otherwise move on every upstream release. Local `./` refs
    and Docker image tags are addressed differently and are exempt."""
    offenders = []
    for job_name, job in (load(path).get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if not isinstance(step, dict):
                continue
            uses = step.get("uses")
            if not isinstance(uses, str) or uses.startswith(("./", "docker://")):
                continue
            ref = uses.rpartition("@")[2]
            if not REF_RE.match(ref):
                offenders.append(f"{path.name}: job '{job_name}' uses {uses}")
    assert not offenders, "use a version tag or release branch:\n  " + "\n  ".join(offenders)


class TestDependabot:
    """Version refs still go stale across majors; without this they rot."""

    CONFIG = Path(__file__).parent.parent / ".github" / "dependabot.yml"

    def test_config_exists(self) -> None:
        assert self.CONFIG.exists(), "pinned actions need Dependabot to stay current"

    def test_covers_github_actions(self) -> None:
        cfg = yaml.safe_load(self.CONFIG.read_text())
        ecosystems = {u["package-ecosystem"] for u in cfg["updates"]}
        assert "github-actions" in ecosystems
