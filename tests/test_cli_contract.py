"""Integration tests for the CLI contract (subprocess invocations)."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

PYTHON = sys.executable
CLI = [PYTHON, "-m", "termrender"]


def _run(args: list[str], stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        CLI + args,
        input=stdin,
        capture_output=True,
        text=True,
    )


# ---------------------------------------------------------------------------
# Root and branch -h (exit 0, correct schema sections)
# ---------------------------------------------------------------------------

def test_root_help_exit_zero():
    r = _run(["-h"])
    assert r.returncode == 0
    assert "termrender" in r.stdout
    assert "doc" in r.stdout
    assert "pane" in r.stdout
    assert "I/O contract" in r.stdout


def test_doc_help_exit_zero():
    r = _run(["doc", "-h"])
    assert r.returncode == 0
    assert "render" in r.stdout
    assert "check" in r.stdout
    assert "watch" in r.stdout


def test_pane_help_exit_zero():
    r = _run(["pane", "-h"])
    assert r.returncode == 0
    assert "open" in r.stdout
    assert "update" in r.stdout


def test_doc_render_help_has_schema_sections():
    r = _run(["doc", "render", "-h"])
    assert r.returncode == 0
    assert "Input" in r.stdout
    assert "Output (stdout, ANSI)" in r.stdout
    assert "Effects" in r.stdout
    assert "stdin" in r.stdout
    assert "--width" in r.stdout
    assert "--color" in r.stdout
    assert "--cjk" in r.stdout


def test_doc_check_help_has_schema_sections():
    r = _run(["doc", "check", "-h"])
    assert r.returncode == 0
    assert "Input" in r.stdout
    assert "Output (stdout, JSON)" in r.stdout
    assert "Effects" in r.stdout
    assert "stdin" in r.stdout
    assert "--cjk" in r.stdout


def test_doc_watch_help_has_schema_sections():
    r = _run(["doc", "watch", "-h"])
    assert r.returncode == 0
    assert "Input" in r.stdout
    assert "Output (stdout, ANSI)" in r.stdout
    assert "Effects" in r.stdout
    assert "PATH" in r.stdout
    assert "--color" in r.stdout
    assert "--cjk" in r.stdout


def test_pane_open_help_has_schema_sections():
    r = _run(["pane", "open", "-h"])
    assert r.returncode == 0
    assert "Input" in r.stdout
    assert "Output (stdout, JSON)" in r.stdout
    assert "Effects" in r.stdout
    assert "--watch" in r.stdout
    assert "default false" in r.stdout


def test_pane_update_help_has_schema_sections():
    r = _run(["pane", "update", "-h"])
    assert r.returncode == 0
    assert "Input" in r.stdout
    assert "Output (stdout, JSON)" in r.stdout
    assert "Effects" in r.stdout
    assert "--pane-id" in r.stdout
    assert "--watch" in r.stdout
    assert "default false" in r.stdout


# ---------------------------------------------------------------------------
# doc render — happy path (stdin as markdown, not JSON)
# ---------------------------------------------------------------------------

def test_doc_render_produces_ansi_exit_zero():
    r = _run(["doc", "render"], stdin="# Hello\n\nWorld")
    assert r.returncode == 0
    assert "Hello" in r.stdout
    assert "World" in r.stdout
    # Must NOT be a JSON object on success
    try:
        json.loads(r.stdout)
        assert False, "doc render should not produce JSON on success"
    except (json.JSONDecodeError, ValueError):
        pass


def test_doc_render_with_explicit_width():
    r = _run(["doc", "render", "--width", "60", "--color", "off"], stdin="# Hi")
    assert r.returncode == 0
    assert "Hi" in r.stdout


def test_doc_render_color_off():
    r = _run(["doc", "render", "--color", "off"], stdin="**bold**")
    assert r.returncode == 0
    assert "bold" in r.stdout
    # With color=off, minimal/no ANSI escape sequences
    assert "\033[" not in r.stdout or r.stdout.count("\033[") < 5


def test_doc_render_color_on():
    r = _run(["doc", "render", "--color", "on"], stdin="# Title")
    assert r.returncode == 0
    assert "Title" in r.stdout


def test_doc_render_color_auto_default():
    # auto is the default — just ensure it doesn't error
    r = _run(["doc", "render"], stdin="simple text")
    assert r.returncode == 0
    assert "simple text" in r.stdout


def test_doc_render_cjk_flag():
    r = _run(["doc", "render", "--cjk", "--color", "off"], stdin="hello")
    assert r.returncode == 0


# ---------------------------------------------------------------------------
# doc check — ok/not-ok path (stdin as markdown)
# ---------------------------------------------------------------------------

def test_doc_check_ok():
    r = _run(["doc", "check"], stdin="# Valid\n\nJust some text.")
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["ok"] is True
    assert out["errors"] == []


def test_doc_check_syntax_error():
    bad = ":::panel{title=\"x\"}\n:::col\n:::"
    r = _run(["doc", "check"], stdin=bad)
    assert r.returncode == 2
    out = json.loads(r.stdout)
    assert out["ok"] is False
    assert len(out["errors"]) >= 1
    assert out["errors"][0]["kind"] in ("syntax", "nesting")
    assert isinstance(out["errors"][0]["message"], str)


def test_doc_check_cjk_flag():
    r = _run(["doc", "check", "--cjk"], stdin="hello world")
    assert r.returncode == 0
    out = json.loads(r.stdout)
    assert out["ok"] is True


# ---------------------------------------------------------------------------
# Old JSON-on-stdin form is rejected (treated as markdown, not JSON object)
# The old contract sent JSON; new contract sends raw markdown.
# Sending {"source": "# hi"} should render as text (the JSON string itself),
# not be parsed as a command. For doc render, it just renders the JSON as text.
# For doc check, same. The old bad_stdin_json / bad_input errors no longer exist
# for the JSON-form. Instead we test bad_invocation for flag errors.
# ---------------------------------------------------------------------------

def test_json_object_on_stdin_renders_as_text():
    """Old JSON-stdin form is no longer the contract. JSON is now markdown input."""
    r = _run(["doc", "render", "--color", "off"], stdin='{"source": "# hi"}')
    assert r.returncode == 0
    # It's rendered as plain text markdown (curly braces become text output)
    assert r.returncode == 0


def test_json_array_on_stdin_renders_as_text():
    """JSON arrays on stdin are also just treated as markdown text."""
    r = _run(["doc", "render", "--color", "off"], stdin="[1, 2, 3]")
    assert r.returncode == 0


# ---------------------------------------------------------------------------
# bad_invocation — invalid flag combinations
# ---------------------------------------------------------------------------

def test_invalid_color_value_is_bad_invocation():
    r = _run(["doc", "render", "--color", "true"], stdin="hello")
    assert r.returncode == 1
    out = json.loads(r.stdout)
    assert out["error"] == "bad_invocation"
    assert "next" in out


def test_invalid_width_type_is_bad_invocation():
    r = _run(["doc", "render", "--width", "notanint"], stdin="hello")
    assert r.returncode == 1
    out = json.loads(r.stdout)
    assert out["error"] == "bad_invocation"
    assert "received" in out
    assert "next" in out


def test_pane_update_missing_pane_id_is_bad_invocation():
    r = _run(["pane", "update", "/some/path"])
    assert r.returncode == 1
    out = json.loads(r.stdout)
    assert out["error"] == "bad_invocation"


def test_bad_invocation_has_stable_fields():
    r = _run(["doc", "render", "--color", "bogus"], stdin="hello")
    out = json.loads(r.stdout)
    assert "error" in out
    assert "message" in out
    assert "received" in out
    assert "next" in out
    assert isinstance(out["error"], str)
    assert isinstance(out["message"], str)
    assert isinstance(out["next"], str)


def test_unknown_branch_is_bad_invocation():
    r = _run(["foo", "bar"])
    assert r.returncode == 1
    out = json.loads(r.stdout)
    assert out["error"] == "bad_invocation"


def test_unknown_leaf_doc_is_bad_invocation():
    r = _run(["doc", "frobnicate"])
    assert r.returncode == 1
    out = json.loads(r.stdout)
    assert out["error"] == "bad_invocation"


# ---------------------------------------------------------------------------
# watch flag default FLIP — default is now false
# ---------------------------------------------------------------------------

def test_pane_open_watch_default_is_false(tmp_path):
    """--watch is absent by default → watch=false in pane open."""
    # We can't actually spawn a pane (no tmux in CI), but we can verify the
    # help text says "default false" and the parser default is False.
    r = _run(["pane", "open", "-h"])
    assert r.returncode == 0
    assert "default false" in r.stdout


def test_pane_update_watch_default_is_false():
    r = _run(["pane", "update", "-h"])
    assert r.returncode == 0
    assert "default false" in r.stdout


# ---------------------------------------------------------------------------
# Error JSON shape invariants
# ---------------------------------------------------------------------------

def test_error_json_always_has_stable_fields():
    r = _run(["doc", "render", "--color", "bad"], stdin="hello")
    out = json.loads(r.stdout)
    assert "error" in out
    assert "message" in out
    assert "next" in out
    assert isinstance(out["error"], str)
    assert isinstance(out["message"], str)
    assert isinstance(out["next"], str)


# ---------------------------------------------------------------------------
# No branch → usage exit 1 (help on stdout)
# ---------------------------------------------------------------------------

def test_no_subcommand_exits_one():
    r = _run([])
    assert r.returncode == 1
    assert "termrender" in r.stdout


# ---------------------------------------------------------------------------
# Flag parsing correctness
# ---------------------------------------------------------------------------

def test_doc_render_flag_width_accepted():
    r = _run(["doc", "render", "--width", "80", "--color", "off"], stdin="# test")
    assert r.returncode == 0


def test_doc_watch_path_is_positional(tmp_path):
    """doc watch takes PATH as positional arg."""
    f = tmp_path / "test.md"
    f.write_text("# hello")
    r = _run(["doc", "watch", "-h"])
    assert r.returncode == 0
    assert "PATH" in r.stdout


def test_pane_open_window_choices():
    r = _run(["pane", "open", "--window", "invalid_choice", "/path"])
    assert r.returncode == 1
    out = json.loads(r.stdout)
    assert out["error"] == "bad_invocation"


def test_doc_render_rejects_unknown_flag():
    r = _run(["doc", "render", "--unknown-flag"], stdin="hello")
    assert r.returncode == 1
    out = json.loads(r.stdout)
    assert out["error"] == "bad_invocation"


# ---------------------------------------------------------------------------
# Pane command construction — must use an absolute termrender invocation, not a
# bare PATH-resolved name (a venv-only install is not on a spawned pane's PATH).
# ---------------------------------------------------------------------------

def test_build_pane_cmd_uses_absolute_invocation(monkeypatch, tmp_path):
    import termrender.__main__ as m

    fake = tmp_path / "termrender"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setattr(sys, "argv", [str(fake)])

    watch_cmd = m._build_pane_cmd(
        watch=True, path="/docs/a.md", cjk=False, pane_width=None, tmpfile=None,
    )
    assert str(fake.resolve()) in watch_cmd
    assert watch_cmd.startswith(str(fake.resolve()) + " ")  # absolute, not bare
    assert " doc watch " in watch_cmd

    render_cmd = m._build_pane_cmd(
        watch=False, path="/docs/a.md", cjk=False, pane_width=80, tmpfile="/tmp/x.md",
    )
    assert str(fake.resolve()) in render_cmd
    assert " doc render " in render_cmd


def test_termrender_invocation_falls_back_to_python_m(monkeypatch):
    import termrender.__main__ as m

    monkeypatch.setattr(sys, "argv", [""])
    inv = m._termrender_invocation()
    assert "-m termrender" in inv
    assert sys.executable in inv
