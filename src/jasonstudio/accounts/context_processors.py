from django.http import HttpRequest


def user_role(request: HttpRequest) -> dict:
    user = getattr(request, "user", None)
    if user and user.is_authenticated:
        try:
            is_photographer = bool(user.photographer_profile)
        except Exception:
            is_photographer = False
        try:
            is_customer = bool(user.customer_profile)
        except Exception:
            is_customer = False
        return {"is_photographer": is_photographer, "is_customer": is_customer}
    return {"is_photographer": False, "is_customer": False}
