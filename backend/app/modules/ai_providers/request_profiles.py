"""Provider request differences are host adapter policy, not engine behavior."""


def embedding_payload(profile: str, model: str, texts: list[str], input_type: str):
    payload = {"model": model, "input": texts}
    if profile in {"NVIDIA_NIM", "SICT_SPACES"}:
        payload.update(input_type=input_type, encoding_format="float")
    return payload
