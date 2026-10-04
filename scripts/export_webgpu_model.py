"""Repackage the local Phi-3.5 Vision model (onnxruntime-genai layout, AI_MODEL_PATH) for Transformers.js in the browser (WebGPU).

    uv run --with onnx python scripts/export_webgpu_model.py [SRC] [DST]
    SRC default models/gpu/gpu-int4-rtn-block-32 · DST default models/webgpu/phi-3.5-vision

Transformers.js (model_type phi3_v, dtype q4f16) expects onnx/{prepare_inputs_embeds,model,vision_encoder}_q4f16.onnx,
each with its weights in <file>.onnx_data. The genai graphs keep their weights in phi-3.5-v-instruct-*.onnx.data, so:
- the small graph files are rewritten with the new external-data location (weights untouched);
- the weight files are hard-linked (no 2.6 GB copy; copied only when linking fails);
- Transformers.js feeds float32 image features / pixel values, the genai graphs use float16 → Cast nodes at those edges;
- config.json / generation_config.json are written; tokenizer files are copied.
"""
import json
import os
import shutil
import sys
from pathlib import Path

import onnx
from onnx import TensorProto, helper
from onnx.external_data_helper import _get_all_tensors

FILES = {  # genai name → Transformers.js session name
    "phi-3.5-v-instruct-embedding.onnx": "prepare_inputs_embeds",
    "phi-3.5-v-instruct-text.onnx": "model",
    "phi-3.5-v-instruct-vision.onnx": "vision_encoder",
}
SUFFIX = "_q4f16"
F32_INPUTS = {"prepare_inputs_embeds": ["image_features"], "vision_encoder": ["pixel_values"]}
F32_OUTPUTS = {"vision_encoder": ["image_features"]}
TOKENIZER_FILES = ["tokenizer.json", "tokenizer_config.json", "special_tokens_map.json"]


def rename_inputs(graph, old, new):
    """Point every use of `old` at `new`, also inside If/Loop subgraphs (they read outer-scope names)."""
    for node in graph.node:
        node.input[:] = [new if i == old else i for i in node.input]
        for attr in node.attribute:
            for sub in [attr.g] if attr.type == onnx.AttributeProto.GRAPH else list(attr.graphs):
                rename_inputs(sub, old, new)


def cast_inputs_to_f32(graph, names):
    """Input `x` (float16) becomes float32; a Cast feeds the old float16 value to the graph."""
    for inp in graph.input:
        if inp.name not in names:
            continue
        inner = f"{inp.name}_f16"
        rename_inputs(graph, inp.name, inner)
        inp.type.tensor_type.elem_type = TensorProto.FLOAT
        graph.node.insert(0, helper.make_node("Cast", [inp.name], [inner], to=TensorProto.FLOAT16,
                                              name=f"cast_{inp.name}_to_f16"))


def cast_outputs_to_f32(graph, names):
    for out in graph.output:
        if out.name not in names:
            continue
        inner = f"{out.name}_f16"
        for node in graph.node:
            node.output[:] = [inner if o == out.name else o for o in node.output]
        out.type.tensor_type.elem_type = TensorProto.FLOAT
        graph.node.append(helper.make_node("Cast", [inner], [out.name], to=TensorProto.FLOAT,
                                           name=f"cast_{out.name}_to_f32"))


def relocate(model, location):
    """New weights file name for every external tensor (initializers and Constant/subgraph tensors)."""
    for tensor in _get_all_tensors(model):
        for entry in tensor.external_data:
            if entry.key == "location":
                entry.value = location


def link_or_copy(src: Path, dst: Path):
    if dst.exists():
        if dst.stat().st_size == src.stat().st_size:
            return
        dst.unlink()
    try:
        os.link(src, dst)
    except OSError:
        shutil.copyfile(src, dst)


def config(genai: dict) -> dict:
    m = genai["model"]
    d = m["decoder"]
    return {
        "model_type": "phi3_v",
        "architectures": ["Phi3VForCausalLM"],
        "hidden_size": d["hidden_size"],
        "num_attention_heads": d["num_attention_heads"],
        "num_key_value_heads": d["num_key_value_heads"],
        "num_hidden_layers": d["num_hidden_layers"],
        "head_dim": d["head_size"],
        "vocab_size": m["vocab_size"],
        "max_position_embeddings": m["context_length"],
        "bos_token_id": m["bos_token_id"],
        "eos_token_id": [m["eos_token_id"], m["pad_token_id"]],
        "pad_token_id": m["pad_token_id"],
        "transformers.js_config": {"dtype": "q4f16", "use_external_data_format": 1},
    }


def main(src: Path, dst: Path):
    genai = json.loads((src / "genai_config.json").read_text(encoding="utf-8"))
    (dst / "onnx").mkdir(parents=True, exist_ok=True)
    for genai_name, session in FILES.items():
        name = f"{session}{SUFFIX}.onnx"
        model = onnx.load(str(src / genai_name), load_external_data=False)
        relocate(model, f"{name}_data")
        cast_inputs_to_f32(model.graph, F32_INPUTS.get(session, []))
        cast_outputs_to_f32(model.graph, F32_OUTPUTS.get(session, []))
        onnx.save(model, str(dst / "onnx" / name))
        link_or_copy(src / f"{genai_name}.data", dst / "onnx" / f"{name}_data")
        print(f"onnx/{name} (+ _data)")
    cfg = config(genai)
    (dst / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    (dst / "generation_config.json").write_text(json.dumps({
        "bos_token_id": cfg["bos_token_id"], "eos_token_id": cfg["eos_token_id"], "pad_token_id": cfg["pad_token_id"],
        "do_sample": False}, indent=2), encoding="utf-8")
    for f in TOKENIZER_FILES:
        if (src / f).exists():
            shutil.copyfile(src / f, dst / f)
    print(f"done: {dst}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "models/gpu/gpu-int4-rtn-block-32"),
         Path(sys.argv[2] if len(sys.argv) > 2 else "models/webgpu/phi-3.5-vision"))
