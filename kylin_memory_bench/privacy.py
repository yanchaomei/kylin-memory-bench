"""Remove provider credentials from shareable diagnostics, not test canaries."""
import re


def secret_values(value) -> set[str]:
    result = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in {'key', 'apikey', 'api_key', 'access', 'refresh', 'token', 'password', 'secret', 'access_token', 'refresh_token'}:
                if isinstance(item, str) and len(item) >= 8:
                    result.add(item)
            elif isinstance(item, (dict, list)):
                result.update(secret_values(item))
    elif isinstance(value, list):
        for item in value:
            result.update(secret_values(item))
    return result


def redact(text: str, secrets: set[str]) -> str:
    for value in sorted(secrets, key=len, reverse=True):
        text = text.replace(value, '[provider-secret-redacted]')
    return re.sub(r'(?im)(Token prefix:\s*)[^\r\n]+', r'\1[redacted]', text)


def redact_object(value, secrets: set[str]):
    if isinstance(value, str):
        return redact(value, secrets)
    if isinstance(value, list):
        return [redact_object(v, secrets) for v in value]
    if isinstance(value, dict):
        return {k: redact_object(v, secrets) for k, v in value.items()}
    return value
