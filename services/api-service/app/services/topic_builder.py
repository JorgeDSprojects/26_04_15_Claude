_NAMESPACE_MAP: dict[str, str] = {
    "informative": "measure",
    "operational": "events",
    "descriptive": "$meta",
    "analytic": "$analytics",
}


def compute_topic(asset_path: str, signal_type_name: str, signal_name: str) -> str:
    """Compute the full MQTT topic for a signal.

    This is the single authoritative implementation. No other service may
    reimplement this function — they must consume the precomputed topic from
    the registry or from $meta messages.
    """
    namespace = _NAMESPACE_MAP[signal_type_name]
    return f"{asset_path}/{namespace}/{signal_name}"
