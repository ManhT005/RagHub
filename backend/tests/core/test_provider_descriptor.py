from dataclasses import FrozenInstanceError

import pytest

from app.core_domain.providers.descriptor import ProviderDescriptor


def test_descriptor_has_no_secret_and_detaches_nested_options():
    options = {"options": {"temperature": 0.2, "stop": ["STOP"]}}
    descriptor = ProviderDescriptor("OLLAMA", "CHAT", "model", options=options)
    options["options"]["stop"].append("MUTATED")
    options["options"]["temperature"] = 0.9
    assert descriptor.options_dict() == {"options": {"temperature": 0.2, "stop": ["STOP"]}}
    with pytest.raises(TypeError):
        descriptor.options["new"] = True
    with pytest.raises(TypeError):
        descriptor.options["options"]["temperature"] = 0.9
    with pytest.raises(FrozenInstanceError):
        descriptor.model = "changed"
    assert not hasattr(descriptor, "secret") and not hasattr(descriptor, "encrypted_secret")


def test_vendor_options_copy_does_not_mutate_descriptor():
    descriptor = ProviderDescriptor("OLLAMA", "CHAT", "model", options={"options": {"stop": ["a"]}})
    payload = descriptor.options_dict()
    payload["options"]["stop"].append("b")
    assert descriptor.options_dict() == {"options": {"stop": ["a"]}}
