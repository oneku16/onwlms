"""Explicit SQLAlchemy model registry for migrations and composition."""

from importlib import import_module

_MODEL_MODULES = (
    "academics.infrastructure.models",
    "admissions.infrastructure.models",
    "audit.infrastructure.models",
    "entitlements.infrastructure.models",
    "grading.infrastructure.models",
    "identity.infrastructure.models",
    "integrations.infrastructure.models",
    "notifications.infrastructure.models",
    "organizations.infrastructure.models",
    "outbox.infrastructure.models",
    "people.infrastructure.models",
    "provisioning.infrastructure.models",
    "scheduling.infrastructure.models",
)


def load_all_models() -> None:
    """Import every owning module's persistence models without wildcard discovery."""

    for module_name in _MODEL_MODULES:
        import_module(module_name)


__all__ = ["load_all_models"]
