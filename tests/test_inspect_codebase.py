from pathlib import Path
from unittest.mock import patch

import pytest

from reprobe.repositories.local import LocalRepository, RepositoryError
from reprobe.review.commands import InspectCodebase
from reprobe.review.types import SourceCandidate

def inspect(path):
    return InspectCodebase(path, LocalRepository()).execute()

@pytest.mark.parametrize("name,language", [
    ("main.go", "go"), ("main.js", "javascript"), ("main.jsx", "javascript"),
    ("main.mjs", "javascript"), ("main.cjs", "javascript"),
    ("main.ts", "typescript"), ("main.tsx", "typescript"),
    ("main.mts", "typescript"), ("main.cts", "typescript"),
    ("main.py", "python"), ("window.pyw", "python"),
    ("main.cpp", "cpp"), ("main.cc", "cpp"), ("main.cxx", "cpp"),
    ("api.h", "cpp"), ("api.hpp", "cpp"), ("api.hh", "cpp"),
    ("api.hxx", "cpp"), ("MAIN.CPP", "cpp"),
    ("main.rb", "ruby"), ("tasks.rake", "ruby"),
    ("Rakefile", "ruby"), ("Gemfile", "ruby"), ("config.ru", "ruby"),
])
def test_recognizes_supported_names_without_git(tmp_path, name, language):
    source = tmp_path / "src" / name
    source.parent.mkdir()
    source.write_text("example", encoding="utf-8")
    result = inspect(tmp_path)

    assert result.is_codebase
    assert result.root == tmp_path.resolve()
    assert result.candidates == (SourceCandidate(f"src/{name}", language),)
    assert result.languages == (language,)
    assert result.reason == "recognized_source"

def test_no_recognized_source_is_a_result_not_an_error(tmp_path):
    for name in ("README.md", "pyproject.toml", "main.c"):
        (tmp_path / name).write_text("example", encoding="utf-8")

    result = inspect(tmp_path)
    assert not result.is_codebase
    assert result.candidates == ()
    assert result.languages == ()
    assert result.reason == "no_supported_source"

def test_excluded_directories_and_sorted_results(tmp_path):
    for name in (".git", ".venv", "venv", "__pycache__", "build", "dist", "vendor", ".bundle"):
        directory = tmp_path / "nested" / name
        directory.mkdir(parents=True)
        (directory / "hidden.py").write_text("pass", encoding="utf-8")

    for name in ("z.rb", "a.cpp", "m.py"):
        (tmp_path / name).write_text("example", encoding="utf-8")

    result = inspect(tmp_path)
    
    assert [c.path for c in result.candidates] == ["a.cpp", "m.py", "z.rb"]
    assert result.languages == ("cpp", "python", "ruby")

def test_nested_symlinks_are_not_followed(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    (external / "secret.py").write_text("secret", encoding="utf-8")
    
    try:
        (root / "linked").symlink_to(external, target_is_directory=True)
        (root / "linked.py").symlink_to(external / "secret.py")
        (root / "loop").symlink_to(root, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("This environment cannot create symlinks")

    assert inspect(root).candidates == ()

def test_invalid_root_is_actionable(tmp_path):
    file = tmp_path / "main.py"
    file.write_text("pass", encoding="utf-8")
    for path in (tmp_path / "missing", file):
        with pytest.raises(RepositoryError, match="Repository"):
            inspect(path)

def test_filesystem_error_keeps_its_cause(tmp_path):
    failure = PermissionError("access denied")
    with patch("reprobe.repositories.local.os.walk", side_effect=failure):
        with pytest.raises(RepositoryError, match="Cannot inspect") as raised:
            inspect(tmp_path)

    assert raised.value.__cause__ is failure

def test_command_accepts_a_repository_fake(tmp_path):
    class FakeRepository:
        def resolve_root(self, path):
            assert path == Path("input")
            return tmp_path

        def discover(self, root):
            assert root == tmp_path
            return (SourceCandidate("main.go", "go"), ("main.js", "javascript"), ("main.jsx", "javascript"),
    ("main.mjs", "javascript"), ("main.cjs", "javascript"),
    ("main.ts", "typescript"), ("main.tsx", "typescript"),
    ("main.mts", "typescript"), ("main.cts", "typescript"),
    ("main.py", "python"),)

    result = InspectCodebase(Path("input"), FakeRepository()).execute()
    assert result.is_codebase
    assert result.root == tmp_path
