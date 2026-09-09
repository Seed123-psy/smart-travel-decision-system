from app.core.config import Settings


def configuration_status(settings: Settings) -> dict:
    """Presence checks only; never interpret configured credentials as verified access."""
    providers = []
    definitions = (
        ("llm", "模型服务", ("llm_api_key", "llm_base_url", "llm_model")),
        ("amap", "地图与天气", ("amap_web_service_key",)),
    )
    for name, label, fields in definitions:
        missing = [field.upper() for field in fields if not getattr(settings, field).strip()]
        providers.append({
            "name": name,
            "label": label,
            "configured": not missing,
            "status": "not_configured" if missing else "not_verified",
            "missing_fields": missing,
        })
    return {"live_checked": False, "providers": providers}
