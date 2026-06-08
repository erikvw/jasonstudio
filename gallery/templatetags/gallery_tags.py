from django import template

register = template.Library()


@register.filter
def dict_get(d: dict, key: str) -> str:
    if isinstance(d, dict):
        return d.get(str(key), "")
    return ""
