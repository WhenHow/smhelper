from __future__ import annotations

import pytest

from smhelper.core.ids import IdGenerationError, SequenceIdGenerator, UuidGenerator


def test_sequence_id_generator_returns_ids_in_order() -> None:
    generator = SequenceIdGenerator(["session-1", "dispatch-1"])

    assert generator.new_id("session") == "session-1"
    assert generator.new_id("dispatch") == "dispatch-1"


def test_sequence_id_generator_fails_when_exhausted() -> None:
    generator = SequenceIdGenerator([])

    with pytest.raises(IdGenerationError, match="No IDs left"):
        generator.new_id("session")


def test_uuid_generator_prefixes_generated_id() -> None:
    generated = UuidGenerator().new_id("session")

    assert generated.startswith("session-")
