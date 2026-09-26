"""Compatibility exports; implementation lives in :mod:`reprobe.models.gguf_metadata`."""
from reprobe.models.gguf_metadata import (
    GgufMetadataReader as GgufMetadataReader,
    MetadataError as MetadataError,
    ModelMetadata as ModelMetadata,
)

__all__ = ['GgufMetadataReader', 'MetadataError', 'ModelMetadata']
