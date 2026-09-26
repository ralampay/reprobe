"""Legacy import compatibility and dependency-free package import checks."""
import importlib
import subprocess
import sys

import pytest


MOVED_MODULES = {
    "model_types": "models.types",
    "model_settings": "models.settings",
    "gguf_metadata": "models.gguf_metadata",
    "model": "models.llama_cpp",
    "repository": "repositories.local",
    "source_sampling": "repositories.sampling",
    "review_types": "review.types",
    "review_commands": "review.commands",
    "context_commands": "review.context",
    "source_context": "review.source_context",
    "review_prompt": "review.prompt",
    "review_contract": "review.contract",
    "chat_types": "chat.types",
    "commands": "chat.commands",
    "terminal": "chat.terminal",
    "presentation": "output.json_report",
}


@pytest.mark.parametrize("old,new", MOVED_MODULES.items())
def test_legacy_exports_are_the_canonical_objects(old, new):
    legacy = importlib.import_module(f"reprobe.{old}")
    canonical = importlib.import_module(f"reprobe.{new}")
    assert legacy.__all__
    for name in legacy.__all__:
        assert getattr(legacy, name) is getattr(canonical, name), name


def test_all_modules_import_without_loading_inference_dependencies():
    result = subprocess.run([sys.executable, "-c", '''
import importlib
import importlib.abc
import pkgutil
import sys

class BlockModelDependencies(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"llama_cpp", "gguf"}:
            raise AssertionError(f"Import attempted model dependency: {fullname}")
        return None

sys.meta_path.insert(0, BlockModelDependencies())
import reprobe
for module in pkgutil.walk_packages(reprobe.__path__, "reprobe."):
    importlib.import_module(module.name)
assert "llama_cpp" not in sys.modules
assert "gguf" not in sys.modules
'''], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
