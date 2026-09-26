from pathlib import Path
from unittest.mock import Mock

import pytest

from reprobe.models.gguf_metadata import GgufMetadataReader, MetadataError, ModelMetadata
from reprobe.models.settings import ResolveModelSettings


def resolve(context=32768, **overrides):
    reader = Mock()
    reader.read.return_value = ModelMetadata("llama", context)
    return ResolveModelSettings(Path("model.gguf"), reader, **overrides).execute()


@pytest.mark.parametrize("model_context,context,output", [
    (2048, 2048, 512), (4096, 4096, 1024), (32768, 8192, 2048), (None, 4096, 1024),
])
def test_metadata_policy(model_context, context, output):
    result = resolve(model_context)
    assert (result.config.n_ctx, result.config.max_tokens) == (context, output)
    assert bool(result.diagnostics) == (model_context is None)


def test_independent_explicit_overrides():
    result = resolve(n_ctx=16384)
    assert (result.config.n_ctx, result.config.max_tokens) == (16384, 2048)
    assert result.context_source == "explicit"
    result = resolve(max_tokens=3000)
    assert (result.config.n_ctx, result.config.max_tokens) == (8192, 3000)
    assert result.output_source == "explicit"
    result = resolve(4096, n_ctx=8192, max_tokens=5000)
    assert result.config.max_tokens == 5000
    assert "exceeds" in result.diagnostics[0]


@pytest.mark.parametrize("options", [{"n_ctx": 0}, {"max_tokens": 0},
                                      {"n_ctx": 2048, "max_tokens": 2048},
                                      {"max_tokens": 8192}, {"n_ctx": "4096"}, {"n_ctx": True},
                                      {"max_tokens": 1.5}])
def test_invalid_limits_are_not_silently_adjusted(options):
    with pytest.raises(ValueError):
        resolve(**options)


def test_reader_translates_corrupt_file(tmp_path):
    path = tmp_path / "broken.gguf"
    path.write_bytes(b"not a GGUF file")
    with pytest.raises(MetadataError) as exc:
        GgufMetadataReader().read(path)
    assert exc.value.__cause__ is not None


def test_real_metadata_only_gguf(tmp_path):
    gguf = pytest.importorskip("gguf")
    path = tmp_path / "metadata.gguf"
    writer = gguf.GGUFWriter(str(path), "llama")
    writer.add_context_length(32768)
    writer.write_header_to_file()
    writer.write_kv_data_to_file()
    writer.write_tensors_to_file()
    writer.close()
    assert GgufMetadataReader().read(path) == ModelMetadata("llama", 32768)
