from pathlib import Path
from unittest.mock import patch

import pytest

from reprobe.repositories.local import LocalRepository, RepositoryError
from reprobe.repositories.sampling import SourceSampler
from reprobe.review.commands import InspectCodebase


def write(root, name, text="pass"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def paths(root):
    return [item.path for item in LocalRepository().discover(root)]


@pytest.mark.parametrize("directory", [
    "ENV", ".env", ".tox", ".nox", "node_modules", "site-packages",
    "dist-packages", "third_party", "third-party", "thirdparty", ".yarn",
    ".pnpm-store", "app.egg-info", ".eggs", "cmake-build-debug",
])
def test_dependencies_never_reach_sampling(tmp_path, directory):
    write(tmp_path, f"nested/{directory}/dependency.py")
    write(tmp_path, "src/app.py")
    repository = LocalRepository()
    inspection = InspectCodebase(tmp_path, repository).execute()
    with patch.object(repository, "read_excerpt", wraps=repository.read_excerpt) as read:
        SourceSampler(repository).sample(inspection)
    assert [c.path for c in inspection.candidates] == ["src/app.py"]
    assert [call.args[1].path for call in read.call_args_list] == ["src/app.py"]


@pytest.mark.parametrize("marker", ["pyvenv.cfg", "conda-meta/history"])
def test_renamed_environment_is_pruned_even_when_explicit_root(tmp_path, marker):
    write(tmp_path, f"custom-runtime/{marker}", "")
    write(tmp_path, "custom-runtime/lib/dependency.py")
    write(tmp_path, "lib/app.py")
    assert paths(tmp_path) == ["lib/app.py"]
    assert paths(tmp_path / "custom-runtime") == []


def test_ignore_scopes_negation_and_custom_overrides(tmp_path):
    write(tmp_path, ".gitignore", "/generated/\n*.generated.py\n*.skip.py\n")
    write(tmp_path, "src/.gitignore", "!keep.skip.py\n/local.py\n")
    write(tmp_path, ".reprobeignore", "custom-deps/\nsrc/keep.skip.py\n!allowed.skip.py\n!env/\n")
    excluded = ["generated/code.py", "src/a.generated.py", "src/no.skip.py",
                "src/local.py", "src/keep.skip.py", "custom-deps/lib.py", "env/lib.py"]
    included = ["lib/app.py", "src/generated/app.py", "src/nested/local.py",
                "tests/test_app.py", "examples/demo.py", "allowed.skip.py"]
    for name in excluded + included:
        write(tmp_path, name)
    assert paths(tmp_path) == sorted(included)


def test_nested_negation_and_ignored_parent_pruning(tmp_path):
    write(tmp_path, ".gitignore", "*.py\n!src/keep.py\nignored/\n!ignored/keep.py\n")
    write(tmp_path, "src/.gitignore", "!other.py\n")
    for name in ["src/keep.py", "src/other.py", "src/drop.py", "ignored/keep.py"]:
        write(tmp_path, name)
    # If an excluded directory is entered, reading this invalid file would fail.
    (tmp_path / "ignored/.gitignore").write_bytes(b"\xff")
    assert paths(tmp_path) == ["src/keep.py", "src/other.py"]


def test_invalid_ignore_encoding_is_actionable(tmp_path):
    (tmp_path / ".gitignore").write_bytes(b"\xff")
    with pytest.raises(RepositoryError, match="Cannot read ignore rules") as error:
        paths(tmp_path)
    assert error.value.__cause__ is not None


def test_linked_ignore_file_is_not_read(tmp_path):
    write(tmp_path, "outside", "*.py")
    root = tmp_path / "repo"
    write(root, "app.py")
    (root / ".gitignore").symlink_to(tmp_path / "outside")
    assert paths(root) == ["app.py"]
