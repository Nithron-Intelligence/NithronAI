"""Granite R2 is registered with fastembed as a custom ONNX model (CLS pooling, no prefix) before loading."""

from __future__ import annotations

from typing import Any, ClassVar

from app.services.embeddings import CUSTOM_FASTEMBED_MODELS, register_custom_fastembed_model


class FakeTextEmbedding:
    registered: ClassVar[list[dict[str, Any]]] = []

    @classmethod
    def add_custom_model(cls, **kwargs: Any) -> None:
        if any(r["model"] == kwargs["model"] for r in cls.registered):
            raise ValueError("already registered")
        cls.registered.append(kwargs)


def test_granite_is_registered_with_cls_pooling_and_its_dimension() -> None:
    FakeTextEmbedding.registered = []
    model = "ibm-granite/granite-embedding-97m-multilingual-r2"
    assert register_custom_fastembed_model(FakeTextEmbedding, model) is True
    assert register_custom_fastembed_model(FakeTextEmbedding, model) is True  # second time: no error
    (spec,) = FakeTextEmbedding.registered
    assert spec["pooling"].name == "CLS" and spec["dim"] == 384 and spec["normalization"] is True
    assert spec["model_file"] == "onnx/model.onnx"


def test_built_in_models_are_left_to_fastembed() -> None:
    FakeTextEmbedding.registered = []
    assert (
        register_custom_fastembed_model(
            FakeTextEmbedding, "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
        is False
    )
    assert FakeTextEmbedding.registered == []
    assert CUSTOM_FASTEMBED_MODELS["ibm-granite/granite-embedding-311m-multilingual-r2"]["dim"] == 768
