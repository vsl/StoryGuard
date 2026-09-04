"""Isolated, bounded coreference inference. JSON files are data, never code.

Run with the separate Python environment from coreference_requirements.txt.
No application imports: its dependencies intentionally differ from the server's.
"""

import argparse
import hashlib
import json
import time
import importlib.metadata
from pathlib import Path
from collections import defaultdict
from typing import Any
from unittest.mock import patch

from langsmith import get_current_run_tree, traceable

MODEL = "sapienzanlp/xcore-litbank"
REVISION = "a77857e473848d85acc01debdaa8353c59440d84"
PIPELINE = "coreference-windows-v1"
ENCODER = "microsoft/deberta-v3-large"
ENCODER_REVISION = "64a8c8eab3e352a784c658aef62be1662607476f"


@traceable(name="coreference_windows", run_type="chain",
           process_inputs=lambda inputs: {"documents": len(inputs["documents"]),
               "text_chars": sum(len(doc["text"]) for doc in inputs["documents"]), "pipeline": PIPELINE},
           process_outputs=lambda output: {key: value for key, value in (output or {}).items() if key != "documents"})
def predict(documents: list[dict], cache_dir: Path, window_tokens: int = 800) -> dict:
    import spacy
    import torch
    from huggingface_hub import hf_hub_download
    from omegaconf import DictConfig
    from omegaconf.base import ContainerMetadata, Metadata
    from omegaconf.nodes import AnyNode
    from xcore import xCoRe
    from xcore.models.model_cross import xCoRe_system
    from transformers import AutoConfig, AutoModel, AutoTokenizer, PreTrainedModel

    if not 64 <= window_tokens <= 1200:
        raise ValueError("Window must contain 64–1200 tokens")
    torch.set_num_threads(4)
    started = time.perf_counter()
    checkpoint = hf_hub_download(MODEL, "weights.ckpt", revision=REVISION, cache_dir=cache_dir)
    # Keep weights-only loading. Decode the legacy AttributeDict as plain dictionary
    # data, not as a custom pickle class. Never accept arbitrary checkpoint paths.
    with torch.serialization.safe_globals([dict, Any, defaultdict,
            (dict, "pytorch_lightning.utilities.parsing.AttributeDict"),
            DictConfig, Metadata, AnyNode, ContainerMetadata]):
        saved = torch.load(checkpoint, map_location="cpu", weights_only=True, mmap=True)
    settings = dict(saved["hyper_parameters"]["model"])
    if settings["huggingface_model_name"] != ENCODER:
        raise ValueError("Unexpected coreference encoder")
    encoder_config = AutoConfig.from_pretrained(ENCODER, revision=ENCODER_REVISION)
    # The upstream constructor downloads/allocates base encoder weights which the
    # full checkpoint immediately replaces. Construct shapes only, then assign the
    # restricted memory-mapped checkpoint. This keeps peak memory within local Docker.
    resize = PreTrainedModel.resize_token_embeddings
    with (torch.device("meta"),
          patch.object(AutoModel, "from_pretrained", side_effect=lambda *a, **k: AutoModel.from_config(encoder_config)),
          patch.object(AutoConfig, "from_pretrained", return_value=encoder_config),
          patch.object(PreTrainedModel, "resize_token_embeddings", lambda self, size: resize(self, size, mean_resizing=False))):
        system = xCoRe_system(**settings)
    system.load_state_dict({key.removeprefix("model."): value for key, value in saved["state_dict"].items()}, strict=True, assign=True)
    # Non-persistent position buffers are not checkpoint weights.
    for module in system.modules():
        for name, value in module.named_buffers(recurse=False):
            if not value.is_meta:
                continue
            if name == "position_ids":
                module.register_buffer(name, torch.arange(value.shape[-1]).expand(value.shape), persistent=False)
            elif name == "token_type_ids":
                module.register_buffer(name, torch.zeros(value.shape, dtype=value.dtype), persistent=False)
            else:
                raise ValueError("Unknown non-persistent model buffer")
    model = xCoRe.__new__(xCoRe)
    model.device = system.device = "cpu"
    model.model = system.eval().float()
    model.tokenizer = AutoTokenizer.from_pretrained(ENCODER, revision=ENCODER_REVISION, use_fast=True, add_prefix_space=True)
    model.tokenizer.add_special_tokens({"additional_special_tokens": ["[SPEAKER_START]", "[SPEAKER_END]"]})
    load_ms = (time.perf_counter() - started) * 1000
    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    output = []
    for document in documents:
        text = document["text"]
        nlp.max_length = max(nlp.max_length, len(text) + 1)
        tokens = [token for token in nlp(text) if not token.is_space]
        windows = []
        # ponytail: local windows only; cross-window/long-distance ambiguity goes to Gemma.
        # Bound input before xCoRe: its preprocessing allocates a quadratic full-input mask.
        for start in range(0, len(tokens), window_tokens):
            part = tokens[start:start + window_tokens]
            sentences, sentence = [], []
            for token in part:
                if token.is_sent_start and sentence:
                    sentences.append(sentence)
                    sentence = []
                sentence.append(token.text)
            if sentence:
                sentences.append(sentence)
            before = time.perf_counter()
            result = model.predict(sentences, mode="short", max_length=10000, singletons=False)
            if result["tokens"] != [token.text for token in part]:
                raise ValueError("Coreference token alignment changed")
            clusters = []
            for cluster in result["clusters_token_offsets"]:
                spans = []
                for left, right in cluster:
                    if not 0 <= left <= right < len(part):
                        raise ValueError("Coreference span outside original tokens")
                    spans.append([part[left].idx, part[right].idx + len(part[right].text)])
                clusters.append(spans)
            windows.append({"clusters": clusters, "latency_ms": (time.perf_counter() - before) * 1000})
        output.append({"id": document["id"], "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "windows": windows})
    run = get_current_run_tree()
    return {"pipeline": PIPELINE, "model": MODEL, "revision": REVISION,
            "trace_id": str(run.id) if run else None,
            "runtime_versions": {name: importlib.metadata.version(name) for name in
                                 ("xcore-coref", "torch", "transformers", "spacy", "pytorch-lightning")},
            "encoder_model": model.model.encoder_hf_model_name,
            "encoder_revision": getattr(model.model.encoder.config, "_commit_hash", None),
            "window_tokens": window_tokens, "load_ms": load_ms,
            "wall_ms": (time.perf_counter() - started) * 1000, "documents": output}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--window-tokens", type=int, default=800)
    args = parser.parse_args()
    result = predict(json.loads(args.input.read_text())["documents"], args.cache_dir, args.window_tokens)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "documents"}))


if __name__ == "__main__":
    main()
