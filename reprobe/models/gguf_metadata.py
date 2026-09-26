"""Read GGUF metadata without constructing an inference model."""
from pathlib import Path

# Preserve the original public import while keeping policy independent of GGUF.
from reprobe.models.types import ModelMetadata as ModelMetadata


class MetadataError(RuntimeError):
    """The local model could not be inspected."""


class GgufMetadataReader:
    def read(self, path: Path) -> ModelMetadata:
        try:
            from gguf import GGUFReader
            reader = GGUFReader(path, mode="r")
            try:
                field = reader.get_field("general.architecture")
                architecture = field.contents() if field else None
                if architecture is not None and (not isinstance(architecture, str) or not architecture):
                    raise ValueError("invalid general.architecture metadata")
                field = reader.get_field(f"{architecture}.context_length") if architecture else None
                context = field.contents() if field else None
                if context is not None and (type(context) is not int or context <= 0):
                    raise ValueError("model context_length must be a positive integer")
                return ModelMetadata(architecture, context)
            finally:
                # No arrays or tensor views escape this adapter.
                reader.data._mmap.close()
        except Exception as exc:
            raise MetadataError(
                f"Cannot inspect GGUF model {path}: {exc}. Ensure the file is valid "
                "and install dependencies with `python -m pip install -e .`."
            ) from exc
