"""Compatibility exports; implementation lives in :mod:`reprobe.models.types`."""
from reprobe.models.types import (
    ModelConfig as ModelConfig,
    ModelMetadata as ModelMetadata,
    validate_model_options as validate_model_options,
)

__all__ = ['ModelConfig', 'ModelMetadata', 'validate_model_options']
