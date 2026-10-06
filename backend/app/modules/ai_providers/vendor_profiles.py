"""Only explicitly supported vendor options can become HTTP headers."""


def vendor_headers(profile, options):
    if profile != "OPENROUTER":
        return {}
    return {
        header: options[key]
        for key, header in (("app_url", "HTTP-Referer"), ("app_name", "X-OpenRouter-Title"))
        if options.get(key)
    }


def embedding_batch_limit(profile, options):
    defaults = {"SILICONFLOW": 32, "NVIDIA_NIM": 32, "VOYAGE": 128}
    vendor_limit = defaults.get(profile, 64)
    return max(1, min(int(options.get("embedding_batch_limit", vendor_limit)), vendor_limit))
