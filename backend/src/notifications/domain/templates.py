"""Constrained notification template rendering."""

import re

from core.errors import ValidationError

_PLACEHOLDER = re.compile(r"\{\{([a-z][a-z0-9_]*)\}\}")


def render_template(
    template: str,
    variables: dict[str, str],
) -> str:
    """Render declared simple placeholders and reject missing values."""

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = variables.get(key)
        if value is None:
            raise ValidationError(f"Missing notification template value: {key}")
        return value

    rendered = _PLACEHOLDER.sub(replace, template)
    if len(rendered) > 10_000:
        raise ValidationError("Rendered notification is too large")
    return rendered


__all__ = ["render_template"]
