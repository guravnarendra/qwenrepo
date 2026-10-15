"""
Qwen-Image 2.1 Uncensored (Wan2GP INT8 Edition) - Runner Script
Cross-platform: Windows (RDP) & Linux (Colab / Cloud)
Automatically downloads checkpoints, checks out Wan2GP, loads the engine, and launches Gradio Web UI.
"""

import os
import sys
import time
import shutil
import subprocess
import urllib.request
import threading
import re
import gc
import types
import warnings
import webbrowser
from concurrent.futures import ThreadPoolExecutor

# Environment setup
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
os.environ["HF_XET_CHUNK_CACHE_SIZE_BYTES"] = "0"
os.environ.pop("HF_XET_HIGH_PERFORMANCE", None)
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
os.environ["TOKENIZERS_PARALLELISM"] = "false"
os.environ["USE_FLAX"] = "0"
os.environ["USE_TF"] = "0"

warnings.filterwarnings("ignore", message=".*parameter in the Blocks constructor.*")

ROOT = os.path.dirname(os.path.abspath(__file__))
WAN2GP_DIR = os.path.join(ROOT, "Wan2GP")
CKPT_DIR = os.path.join(ROOT, "qwen21_ckpts")
OUT_DIR = os.path.join(ROOT, "outputs")
WAN2GP_COMMIT = "91301f0eda923b6c4b05159e32f1dfd2a960af9d"

os.makedirs(CKPT_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

IS_WIN = sys.platform == "win32"
CLOUDFLARED_BIN = os.path.join(ROOT, "cloudflared.exe" if IS_WIN else "cloudflared")


# =====================================================================
# STEP 1: GPU CHECK & PREREQUISITES
# =====================================================================
def check_gpu():
    try:
        import torch
        if not torch.cuda.is_available():
            print("⚠️ WARNING: No CUDA GPU detected! PyTorch is running in CPU mode.")
            print("   For fast image generation, an NVIDIA GPU with CUDA support is required.")
            return None
        props = torch.cuda.get_device_properties(0)
        vram_gb = props.total_memory / (1024**3)
        print(f"✅ GPU: {props.name} · {vram_gb:.1f} GB VRAM · SM {props.major}.{props.minor}")
        if (props.major, props.minor) < (7, 5):
            print("⚠️ INT8 tensor-core kernels need a T4 (SM 7.5) or newer; this GPU will use the PyTorch INT8 fallback.")
        return props
    except Exception as e:
        print(f"❌ Error checking GPU: {e}")
        return None


# =====================================================================
# STEP 2: WAN2GP REPO FETCH
# =====================================================================
def fetch_wan2gp():
    print(f"\n📥 Setting up Wan2GP (commit: {WAN2GP_COMMIT[:10]})...")
    def git_run(*args):
        subprocess.run(["git", "-C", WAN2GP_DIR, *args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if not os.path.isdir(os.path.join(WAN2GP_DIR, ".git")):
        shutil.rmtree(WAN2GP_DIR, ignore_errors=True)
        os.makedirs(WAN2GP_DIR, exist_ok=True)
        git_run("init", "-q")
        git_run("remote", "add", "origin", "https://github.com/DeepBeepMeep/Wan2GP.git")

    git_run("fetch", "-q", "--depth", "1", "origin", WAN2GP_COMMIT)
    git_run("checkout", "-q", "-f", "FETCH_HEAD")
    git_run("reset", "-q", "--hard")
    git_run("clean", "-q", "-fd")

    handler_path = os.path.join(WAN2GP_DIR, "models", "qwen21", "qwen21_handler.py")
    if not os.path.exists(handler_path):
        raise RuntimeError("Wan2GP checkout is incomplete or corrupted.")
    print("✅ Wan2GP ready.")


# =====================================================================
# STEP 3: MODEL WEIGHTS & CLOUDFLARED DOWNLOAD
# =====================================================================
UNCENSORED_REPO = "abenzerps/Qwen-Image-2.1-Uncensored-GGUF"
QWEN_REPO = "DeepBeepMeep/Qwen_image_2"
ENCODER_REPO = "DeepBeepMeep/Ideogram4"
VIGGLE_REPO = "Viggle/Qwen-Image-2.1-viggle-turbo"
ALIBABA_REPO = "alibaba-pai/Qwen-Image-2.1-Fun-Acc-LoRAs"
TE = "Qwen3-VL-8B-Instruct"

TE_FILES = [
    "config_legacy.json", "tokenizer_legacy.json", "tokenizer_config_legacy.json", "preprocessor_config.json",
    "chat_template.jinja", "merges.txt", "vocab.json", "added_tokens.json", "special_tokens_map.json",
    "video_preprocessor_config.json"
]

FILES = [
    (UNCENSORED_REPO, "qwen-image-2.1-UC-int8_convrot.safetensors"),     # 7.3 GB
    (ENCODER_REPO, f"{TE}/{TE}_int8_convrot.safetensors"),             # 8.9 GB
    *[(ENCODER_REPO, f"{TE}/{name}") for name in TE_FILES],
    (QWEN_REPO, "qwen_image_21/qwen_image_21_vae.safetensors"),         # 1.4 GB
    (QWEN_REPO, "qwen_image_21/vae_config.json"),
    (QWEN_REPO, "qwen_image_21/scheduler_config.json"),
    (VIGGLE_REPO, "Qwen-Image-2.1-viggle-turbo-v0.2.1-6step-lora-r128.safetensors"),  # 0.7 GB
    (QWEN_REPO, "loras/p_qwen_image_2.1_8step_v0.1.safetensors"),       # 0.3 GB
    (ALIBABA_REPO, "models/Qwen-Image-2.1-Fun-Acc-4Step.safetensors"),  # 0.35 GB
    (ALIBABA_REPO, "models/pdd_config.json"),
]

def download_cloudflared():
    if os.path.exists(CLOUDFLARED_BIN):
        return
    url = (
        "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
        if IS_WIN else
        "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64"
    )
    print(f"🌐 Downloading cloudflared binary from {url}...")
    urllib.request.urlretrieve(url, CLOUDFLARED_BIN)
    if not IS_WIN:
        import stat
        os.chmod(CLOUDFLARED_BIN, os.stat(CLOUDFLARED_BIN).st_mode | stat.S_IEXEC)
    print("✅ Cloudflared binary ready.")

def fetch_file(repo, filename):
    from huggingface_hub import hf_hub_download
    dest_path = os.path.join(CKPT_DIR, filename)
    if os.path.exists(dest_path):
        return filename
    print(f"⬇️ Downloading {filename} from {repo}...")
    hf_hub_download(repo_id=repo, filename=filename, local_dir=CKPT_DIR)
    return filename

def download_all_models():
    print("\n⬇️ Checking / Downloading config files and tokenizer...")
    small_files = [(repo, name) for repo, name in FILES if not name.endswith(".safetensors")]
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(fetch_file, r, f) for r, f in small_files] + [pool.submit(download_cloudflared)]
        for fut in futures:
            fut.result()

    print("\n⬇️ Checking / Downloading model safetensors weights (~19 GB)...")
    large_files = [(repo, name) for repo, name in FILES if name.endswith(".safetensors")]
    for repo, name in large_files:
        t0 = time.time()
        fetch_file(repo, name)
        size_gb = os.path.getsize(os.path.join(CKPT_DIR, name)) / (1024**3)
        print(f"✅ Ready: {name} ({size_gb:.1f} GB, {time.time() - t0:.1f}s)")


# =====================================================================
# STEP 4: LOAD ENGINE & SETUP GRADIO
# =====================================================================
def start_app():
    if WAN2GP_DIR not in sys.path:
        sys.path.insert(0, WAN2GP_DIR)
    os.chdir(WAN2GP_DIR)

    # Stub rembg if missing
    if "rembg" not in sys.modules:
        _rembg = types.ModuleType("rembg")
        def _no_rembg(*args, **kwargs):
            raise RuntimeError("Background removal is not available in this build.")
        _rembg.remove = _rembg.new_session = _no_rembg
        sys.modules["rembg"] = _rembg

    import numpy as np
    import psutil
    import torch
    import gradio as gr
    from PIL import Image
    from mmgp import offload, quant_router
    from optimum.quanto.tensor.weights import qbytes
    from shared.utils import files_locator as fl
    from shared.kernels import int8_backend, quanto_int8_inject
    from types import SimpleNamespace
    import random
    import zipfile
    import traceback

    quant_router.unregister_handler(".fp8_quanto_bridge")
    quant_router.register_handler("shared.qtypes.int8_convrot")
    fl.set_checkpoints_paths([CKPT_DIR])
    from models.qwen21.qwen21_handler import family_handler, ENCODER

    BASE_MODEL_TYPE = "qwen_image_21_7B"
    TRANSFORMER_FILE = os.path.join(CKPT_DIR, "qwen-image-2.1-UC-int8_convrot.safetensors")
    TEXT_ENCODER_FILE = os.path.join(CKPT_DIR, ENCODER, f"{ENCODER}_int8_convrot.safetensors")
    VIGGLE_LORA_FILE = os.path.join(CKPT_DIR, "Qwen-Image-2.1-viggle-turbo-v0.2.1-6step-lora-r128.safetensors")
    PRUNA_LORA_FILE = os.path.join(CKPT_DIR, "loras", "p_qwen_image_2.1_8step_v0.1.safetensors")
    ALIBABA_LORA_FILE = os.path.join(CKPT_DIR, "models", "Qwen-Image-2.1-Fun-Acc-4Step.safetensors")
    ALIBABA_CONFIG_FILE = os.path.join(CKPT_DIR, "models", "pdd_config.json")

    has_cuda = torch.cuda.is_available()
    gpu = torch.cuda.get_device_properties(0) if has_cuda else SimpleNamespace(name="CPU", major=0, minor=0, total_memory=16*(1024**3))
    DTYPE = (torch.bfloat16 if gpu.major >= 8 else torch.float16) if has_cuda else torch.float32

    INT8_LABELS = {"kitchen": "Comfy Kitchen INT8", "triton": "Triton INT8", "pytorch": "PyTorch (exact)"}
    FP16_MAX = 65504.0
    PHASE_TIMES = {}
    ACT_PEAK = {}
    KV_MARGIN_BYTES = int(1.5 * 1024**3)
    VAE_TILE = 1024

    def _gb(n):
        return f"{n / (1024**3):.1f} GB"

    def _dt(dtype):
        return str(dtype).replace("torch.", "").upper()

    class CPUEmbedding(torch.nn.Module):
        def __init__(self, weight):
            super().__init__()
            self._table = [weight]

        def forward(self, input_ids):
            return torch.nn.functional.embedding(input_ids.cpu(), self._table[0]).to(input_ids.device)

    def load_alibaba_pdd(transformer):
        import json
        from safetensors import safe_open
        import models.qwen21.pipeline as qwen_pipeline

        with open(ALIBABA_CONFIG_FILE, encoding="utf-8") as reader:
            config = json.load(reader)
        sigmas = [float(value) for value in config["pdd_sigmas"]]
        if config.get("pdd_block_size") != 1 or len(sigmas) != config["pdd_num_steps"] + 1:
            raise ValueError(f"Unsupported Alibaba PDD export: {config.get('pdd_export_format')}")
        qwen_pipeline.PRUNA_SIGMAS[len(sigmas) - 1] = tuple(sigmas[:-1])
        head = transformer.proj_out.weight
        with safe_open(ALIBABA_LORA_FILE, framework="pt", device="cpu") as reader:
            heads = reader.get_tensor("proj_out.weight").to(head.device, head.dtype)
            norms = []
            for name in config["pdd_full_parameters"]:
                param = transformer.get_parameter(name)
                norms.append((param, param.data.clone(), reader.get_tensor(name).to(param.device, param.dtype)))
        pdd = SimpleNamespace(active=False, heads=heads, base_head=head.data.clone(), norms=norms,
                              steps=len(sigmas) - 1, sigmas=sigmas)

        def select_head(module, args):
            if pdd.active:
                module.weight.data.copy_(pdd.heads[min(getattr(transformer, "_lora_step_no", 0), pdd.steps - 1)])

        transformer.proj_out.register_forward_pre_hook(select_head)
        return pdd

    def set_alibaba_pdd(engine, active):
        pdd = engine.pdd
        if pdd is None or pdd.active == active:
            return
        for param, base, replacement in pdd.norms:
            param.data.copy_(replacement if active else base)
        if not active:
            engine.transformer.proj_out.weight.data.copy_(pdd.base_head)
        pdd.active = active

    def _load_engine():
        for path in (TRANSFORMER_FILE, TEXT_ENCODER_FILE, VIGGLE_LORA_FILE, PRUNA_LORA_FILE, ALIBABA_LORA_FILE, ALIBABA_CONFIG_FILE):
            if not os.path.exists(path):
                raise SystemExit(f"❌ Required model file not found: {path}")

        try:
            int8_backend.configure("auto", 1)
        except Exception as e:
            print(f"⚠️ INT8 kernels unavailable, using PyTorch INT8: {e}")
        int8_backend._SCRATCH_BYTES = 384 * 1024 * 1024

        print(f"📂 Loading Qwen-Image 2.1 Uncensored (INT8 ConvRot) · transformer {_dt(DTYPE)}...")
        _fast_load = offload.fast_load_transformers_model
        def _fast_load_dtype(*args, **kwargs):
            kwargs.setdefault("default_dtype", DTYPE)
            return _fast_load(*args, **kwargs)
        offload.fast_load_transformers_model = _fast_load_dtype
        try:
            model_def = family_handler.query_model_def(BASE_MODEL_TYPE, {})
            pipeline, parts = family_handler.load_model(
                [TRANSFORMER_FILE], BASE_MODEL_TYPE, BASE_MODEL_TYPE, model_def,
                text_encoder_filename=TEXT_ENCODER_FILE
            )
        finally:
            offload.fast_load_transformers_model = _fast_load

        transformer = parts["transformer"]
        text_model = parts["text_encoder"]
        text_model.embed_tokens = CPUEmbedding(text_model.embed_tokens.weight.data)

        offload_obj = offload.profile(
            {"transformer": transformer, "text_encoder": text_model, "vision_encoder": parts["vision_encoder"],
             "vae": parts["vae"]},
            profile_no=4,
            pinnedMemory=False,
            quantizeTransformer=False,
            extraModelsToQuantize=[],
            budgets={"transformer": 0, "vae": 0, "vision_encoder": 0, "text_encoder": 2000},
            coTenantsMap={"transformer": "*", "vae": "*"},
            loras=["transformer"],
            convertWeightsFloatTo=DTYPE,
            asyncTransfers=True,
        )
        offload.shared_state["_attention"] = "sdpa"

        def lora_keys(sd):
            if any(key.endswith(".lora_down") for key in sd):
                sd = {"transformer." + key.rsplit(".", 1)[0] + (".lora_A.weight" if key.endswith(".lora_down") else ".lora_B.weight"): value
                      for key, value in sd.items() if key.endswith((".lora_down", ".lora_up"))}
            return transformer.preprocess_loras(BASE_MODEL_TYPE, sd)

        loaded = offload.load_loras_into_model(
            transformer, [VIGGLE_LORA_FILE, PRUNA_LORA_FILE, ALIBABA_LORA_FILE], [1.0, 1.0, 1.0], activate_all_loras=True,
            pinnedLora=False,
            preprocess_sd=lora_keys,
            split_linear_modules_map=getattr(transformer, "split_linear_modules_map", None),
        )
        adapters = {path: str(no) for no, path in enumerate(loaded)}
        for error in getattr(transformer, "_loras_errors", None) or []:
            print(f"⚠️ LoRA note: {error}")

        if DTYPE == torch.float16:
            def track_peak(module, args, output):
                peak = (output[0] if isinstance(output, tuple) else output).detach().abs().amax().float()
                ACT_PEAK["fp16"] = peak if "fp16" not in ACT_PEAK else torch.maximum(ACT_PEAK["fp16"], peak)
            for block in transformer.transformer_blocks:
                block.register_forward_hook(track_peak)

        encode_fast = pipeline._encode_conditioning
        def _to_dit_dtype(embeds):
            if DTYPE == torch.float16:
                peak = embeds.float().abs().amax(dim=-1, keepdim=True)
                embeds = embeds.float() / (peak / 32768).clamp(min=1)
            return embeds.to(DTYPE)

        def encode_exact(prompts, images, device, batch_size):
            t0 = time.time()
            backend = int8_backend._backend
            fast_forward = qbytes.WeightQBytesLinearFunction.__dict__["forward"]
            int8_backend._backend = "pytorch"
            qbytes.WeightQBytesLinearFunction.forward = staticmethod(quanto_int8_inject._default_quanto_qbytes_linear_forward)
            try:
                contexts = encode_fast(prompts, images, device, batch_size)
            finally:
                int8_backend._backend = backend
                qbytes.WeightQBytesLinearFunction.forward = fast_forward
                if set(offload_obj.active_models_ids) - {"transformer", "vae"}:
                    offload_obj.unload_all(keep=["transformer", "vae"])
                PHASE_TIMES["text"] = time.time() - t0
            return [(_to_dit_dtype(embeds), mask, slots) for embeds, mask, slots in contexts]

        pipeline._encode_conditioning = encode_exact

        decode_fast = pipeline.vae.decode_to_cpu_uint8
        def decode_checked(latent_holder, **kwargs):
            t0 = time.time()
            latents = latent_holder[0]
            if not torch.isfinite(latents).all():
                raise RuntimeError("non-finite latents")
            try:
                return decode_fast(latent_holder, **kwargs)
            except torch.OutOfMemoryError:
                print("⚠️ VAE ran out of VRAM with 1024px tiles - retrying with 512px tiles.")
                gc.collect()
                if has_cuda:
                    torch.cuda.empty_cache()
                pipeline.vae.configure_tiling((True, 512), latents.shape[-1] * 16, latents.shape[-2] * 16)
                return decode_fast([latents], **kwargs)
            finally:
                PHASE_TIMES["vae"] = time.time() - t0

        pipeline.vae.decode_to_cpu_uint8 = decode_checked

        for model_id in ("transformer", "vae"):
            offload_obj.ensure_model_loaded(model_id)

        pdd = load_alibaba_pdd(transformer) if adapters.get(ALIBABA_LORA_FILE) is not None else None
        return SimpleNamespace(pipeline=pipeline, transformer=transformer, offload=offload_obj, dtype=DTYPE, pdd=pdd,
                               adapters={"viggle": adapters.get(VIGGLE_LORA_FILE), "pruna": adapters.get(PRUNA_LORA_FILE),
                                         "alibaba": adapters.get(ALIBABA_LORA_FILE)})

    # Constants & tasks
    TASK_CREATE = "🖼️ Create (text → image)"
    TASK_REFS = "🧩 Edit & Multi-Reference"
    TASK_INPAINT = "🖌️ Inpaint (paint the area to change)"
    TASK_OUTPAINT = "🔲 Outpaint (extend the image)"

    OUTPAINT_RATIOS = {"Custom margins (sliders)": "", "16:9 Landscape": "16:9", "9:16 Portrait": "9:16", "1:1 Square": "1:1",
                       "4:3 Standard": "4:3", "3:4 Portrait": "3:4", "2:3 Poster": "2:3", "21:9 Cinematic": "21:9"}
    OUTPAINT_DEFAULT_PROMPT = "Continue the scene naturally beyond the original borders, matching its style and lighting."

    MODE_VIGGLE = "✨ Turbo HQ · Viggle v0.2.1 · 6 steps (best fast quality)"
    MODE_PRUNA = "⚡ Turbo · Pruna v0.1 · 8 steps"
    MODE_ALIBABA = "🚀 Turbo Fast · Alibaba Fun-Acc · 4 steps (fastest)"
    MODE_QUALITY = "🎨 Quality · base model + CFG (slow, follows prompts best)"

    MODES = {
        MODE_VIGGLE: {"lora": "viggle", "steps": 6, "solver": "viggle_v02"},
        MODE_PRUNA: {"lora": "pruna", "steps": 8, "solver": "pruna"},
        MODE_ALIBABA: {"lora": "alibaba", "steps": 4, "solver": "pruna"},
        MODE_QUALITY: {"lora": None, "steps": None, "solver": "default"}
    }

    MATCH_INPUT = "Match input image"
    ASPECT_RATIOS = {MATCH_INPUT: None, "1:1 Square": (1, 1), "16:9 Landscape": (16, 9), "9:16 Portrait": (9, 16),
                     "4:3 Standard": (4, 3), "3:4 Portrait": (3, 4), "2:3 Poster": (2, 3)}
    RESOLUTIONS = {"768px (fastest)": 768, "1024px (recommended)": 1024, "1536px (high, slow on T4)": 1536}
    MAX_REFS = 10
    BLOCK = 32

    ENGINE_READY = threading.Event()
    LOAD_ERROR = None
    QWEN_ENGINE = None

    def resolve_size(aspect_ratio, resolution, input_image=None):
        base = RESOLUTIONS.get(resolution, 1024)
        ratio = ASPECT_RATIOS.get(aspect_ratio)
        if ratio is None:
            if input_image is None:
                ratio = (1, 1)
            else:
                ratio = input_image.size
                scale = base / max(ratio)
                return (max(256, int(ratio[0] * scale) // BLOCK * BLOCK), max(256, int(ratio[1] * scale) // BLOCK * BLOCK))
        rw, rh = ratio
        if rw >= rh:
            return base, max(256, int(base * rh / rw) // BLOCK * BLOCK)
        return max(256, int(base * rw / rh) // BLOCK * BLOCK), base

    def fit_reference(image, width, height):
        has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
        image = image.convert("RGBA" if has_alpha else "RGB")
        scale = (width * height / (image.width * image.height)) ** 0.5
        size = (max(BLOCK, round(image.width * scale / BLOCK) * BLOCK), max(BLOCK, round(image.height * scale / BLOCK) * BLOCK))
        return image if image.size == size else image.resize(size, Image.Resampling.LANCZOS)

    def gallery_images(value):
        images = []
        for item in value or []:
            image = item[0] if isinstance(item, (list, tuple)) else item
            images.append(image if isinstance(image, Image.Image) else Image.open(image))
        return images

    def editor_image_and_mask(value):
        if not value or value.get("background") is None:
            return None, None
        background = value["background"]
        background = background if isinstance(background, Image.Image) else Image.open(background)
        mask = np.zeros((background.height, background.width), dtype=bool)
        for layer in value.get("layers") or []:
            layer = layer if isinstance(layer, Image.Image) else Image.open(layer)
            alpha = np.array(layer.convert("RGBA").resize(background.size))[..., 3]
            mask |= alpha > 0
        return background.convert("RGB"), Image.fromarray(mask.astype(np.uint8) * 255)

    def outpaint_layout(image, resolution, ratio_label, top, bottom, left, right):
        from shared.utils.utils import get_outpainting_frame_location, get_outpainting_full_area_dimensions, resolve_outpainting_dims
        image = image.convert("RGB")
        dims = resolve_outpainting_dims(image.height, image.width, [top, bottom, left, right], OUTPAINT_RATIOS.get(ratio_label, ""))
        if not any(dims):
            return None, None, None, None
        full_height, full_width = get_outpainting_full_area_dimensions(image.height, image.width, dims)
        scale = RESOLUTIONS.get(resolution, 1024) / max(full_width, full_height)
        width = max(256, round(full_width * scale / BLOCK) * BLOCK)
        height = max(256, round(full_height * scale / BLOCK) * BLOCK)
        source_height, source_width, top_px, left_px = get_outpainting_frame_location(height, width, dims, 1, quantize_margins=BLOCK)
        canvas = Image.new("RGB", (width, height), (255, 0, 0))
        canvas.paste(image.resize((source_width, source_height), Image.Resampling.LANCZOS), (left_px, top_px))
        return canvas, dims, width, height

    def outpaint_preview(image, resolution, ratio_label, top, bottom, left, right):
        if image is None:
            return None
        canvas, _, _, _ = outpaint_layout(image, resolution, ratio_label, top, bottom, left, right)
        return canvas

    def stop_generation():
        if ENGINE_READY.is_set() and QWEN_ENGINE is not None:
            QWEN_ENGINE.pipeline._interrupt = True
        return "⏹️ Stopping after the current step..."

    PROGRESS = {"active": False, "fraction": 0.0, "text": "", "started": 0.0}

    def report_progress(fraction, text):
        PROGRESS.update(active=True, fraction=float(fraction), text=text)

    STYLE_MODIFIERS = {
        "Cinematic": "cinematic lighting, dramatic shadows, film grain, highly detailed, masterpiece",
        "Photographic": "professional photography, 35mm lens, f/2.8, depth of field, natural lighting, photorealistic, highly detailed",
        "Anime": "anime key visual, vibrant color palette, clean line art, highly detailed digital illustration",
        "Cyberpunk": "cyberpunk aesthetic, glowing neon lights, futuristic city, volumetric smoke, high contrast",
        "Fantasy": "mythical fantasy scene, glowing magical particles, ethereal light, digital painting, masterpiece",
    }
    TRANSPARENCY_PREFIX = "This is an RGBA image with transparency."
    TRANSPARENCY_SUFFIX = "The image has an alpha channel and the background is transparent."

    def apply_transparency(prompt):
        text = prompt.lower()
        if "rgba" not in text:
            prompt = f"{TRANSPARENCY_PREFIX} {prompt}"
        if "transparent" not in text or "alpha" not in text:
            prompt = f"{prompt.rstrip().rstrip('.')}. {TRANSPARENCY_SUFFIX}"
        return prompt

    def apply_style(prompt, style_preset):
        modifier = STYLE_MODIFIERS.get(style_preset)
        if not modifier or modifier in prompt:
            return prompt
        return f"{prompt}, {modifier}" if prompt else modifier

    def fp16_report():
        if "fp16" not in ACT_PEAK:
            return ""
        peak = float(ACT_PEAK["fp16"])
        if peak >= FP16_MAX * 0.99:
            return f"⚠️ FP16 overflow (activations hit ±{FP16_MAX:.0f} limit)."
        return f"FP16 headroom OK (peak {peak:.0f} of {FP16_MAX:.0f})"

    def run_generation(prompt, negative_prompt, mode, steps, guidance, width, height, seed, callback=None,
                       ref_images=None, edit_image=None, edit_mask=None, strength=1.0, outpainting_dims=None, rgba=False):
        engine = QWEN_ENGINE
        PHASE_TIMES.clear()
        ACT_PEAK.clear()
        spec = MODES[mode]
        names = [no for no in engine.adapters.values() if no is not None]
        offload.activate_loras(engine.transformer, names,
                               [1.0 if no == engine.adapters.get(spec["lora"]) else 0.0 for no in names])
        set_alibaba_pdd(engine, spec["lora"] == "alibaba")
        turbo = spec["lora"] is not None
        images = list(ref_images or []) + ([edit_image] if edit_image is not None else [])
        text_tokens = max(len(engine.pipeline.tokenizer.encode(text or " ")) for text in (prompt, negative_prompt)) + 64
        prefix_tokens = text_tokens + sum((image.width // 16) * (image.height // 16) for image in images)
        cache_bytes = prefix_tokens * 2 * 4096 * 2 * len(engine.transformer.transformer_blocks) * (1 if turbo else 2)
        if has_cuda:
            free = torch.cuda.mem_get_info()[0] + torch.cuda.memory_reserved() - torch.cuda.memory_allocated()
            use_kv = cache_bytes < free - KV_MARGIN_BYTES
        else:
            use_kv = False
        PHASE_TIMES["kv"] = f"KV cache {cache_bytes / 1024**3:.1f} GB" if use_kv else "KV cache off"

        kwargs = dict(input_prompt=prompt, n_prompt=None if turbo else negative_prompt or None, seed=seed, width=width,
                      height=height, sampling_steps=spec["steps"] or int(steps), sample_solver=spec["solver"],
                      guide_scale=1.0 if turbo else float(guidance), batch_size=1, callback=callback,
                      VAE_tile_size=(True, VAE_TILE), loras_slists=None, input_ref_images=ref_images or None,
                      outpainting_dims=outpainting_dims,
                      custom_settings={"qwen21_kv_cache": "Enabled" if use_kv else "Disabled",
                                       "rgba": "Enabled" if rgba else "Disabled"})
        if edit_image is not None:
            frame = torch.from_numpy(np.array(edit_image.convert("RGB"), copy=True)).permute(2, 0, 1).float()
            mask = torch.from_numpy(np.array(edit_mask.convert("L"), copy=True)).float().div_(255)
            kwargs.update(input_frames=frame.div_(127.5).sub_(1).unsqueeze(1), input_masks=mask[None, None],
                          denoising_strength=float(strength), masking_strength=1.0, model_mode=0)
        try:
            return engine.pipeline.generate(**kwargs)
        except torch.OutOfMemoryError:
            if not use_kv:
                raise
            print("⚠️ Out of VRAM with KV cache - retrying without it.")
            gc.collect()
            if has_cuda:
                torch.cuda.empty_cache()
            kwargs["custom_settings"] = {**kwargs["custom_settings"], "qwen21_kv_cache": "Disabled"}
            PHASE_TIMES["kv"] = "KV cache off (retried)"
            return engine.pipeline.generate(**kwargs)
        except RuntimeError as e:
            if "non-finite" not in str(e) or int8_backend._backend == "pytorch":
                raise
            print("⚠️ INT8 non-finite values - switching to exact INT8 path.")
            int8_backend.configure("disabled", 1)
            return engine.pipeline.generate(**kwargs)

    def generate_image(task, prompt, refs_value, editor_value, strength, outpaint_image, outpaint_ratio, out_top, out_bottom,
                       out_left, out_right, negative_prompt, style_preset, mode, transparent, steps, guidance, aspect_ratio,
                       resolution, seed, num_images, progress=gr.Progress()):
        PROGRESS.update(active=True, fraction=0.0, text="Starting...", started=time.time())
        while not ENGINE_READY.is_set():
            report_progress(0.0, "Model is loading...")
            if LOAD_ERROR:
                PROGRESS["active"] = False
                yield gr.update(), f"❌ Model failed to load: {LOAD_ERROR}", gr.update(visible=False)
                return
            yield gr.update(), "⏳ Model is loading...", gr.update(visible=False)
            time.sleep(2)

        pipeline = QWEN_ENGINE.pipeline
        try:
            pipeline._interrupt = False
            prompt = apply_style((prompt or "").strip(), style_preset)
            if not prompt and task == TASK_OUTPAINT:
                prompt = OUTPAINT_DEFAULT_PROMPT
            if not prompt:
                yield gr.update(), "❌ Please enter a prompt.", gr.update(visible=False)
                return
            if transparent:
                prompt = apply_transparency(prompt)

            refs, edit_image, edit_mask, outpainting_dims = [], None, None, None
            if task == TASK_OUTPAINT:
                if outpaint_image is None:
                    yield gr.update(), "❌ Upload the image to extend.", gr.update(visible=False)
                    return
                canvas, outpainting_dims, width, height = outpaint_layout(outpaint_image, resolution, outpaint_ratio,
                                                                          out_top, out_bottom, out_left, out_right)
                if canvas is None:
                    yield gr.update(), "❌ Nothing to extend.", gr.update(visible=False)
                    return
                refs = [canvas]
            elif task == TASK_REFS:
                refs = gallery_images(refs_value)
                if not refs:
                    yield gr.update(), "❌ Upload at least one image (up to 10).", gr.update(visible=False)
                    return
                if len(refs) > MAX_REFS:
                    yield gr.update(), f"❌ Max {MAX_REFS} reference images allowed.", gr.update(visible=False)
                    return
                width, height = resolve_size(aspect_ratio, resolution, refs[0])
                refs = [fit_reference(img, width, height) for img in refs]
            elif task == TASK_INPAINT:
                source, mask = editor_image_and_mask(editor_value)
                if source is None:
                    yield gr.update(), "❌ Upload an image, then paint over the area to change.", gr.update(visible=False)
                    return
                if not np.array(mask).any():
                    yield gr.update(), "❌ Paint over the area you want to change.", gr.update(visible=False)
                    return
                width, height = resolve_size(MATCH_INPUT, resolution, source)
                edit_image = source.resize((width, height), Image.Resampling.LANCZOS)
                edit_mask = mask.resize((width, height), Image.Resampling.NEAREST)
            else:
                width, height = resolve_size(aspect_ratio, resolution)

            spec = MODES[mode]
            turbo = spec["lora"] is not None
            if turbo and QWEN_ENGINE.adapters.get(spec["lora"]) is None:
                yield gr.update(), "❌ This turbo LoRA did not load. Pick another mode.", gr.update(visible=False)
                return
            negative_prompt = "" if turbo else (negative_prompt or "").strip()
            total_steps = spec["steps"] or int(steps)
            num_images = int(num_images)
            initial_seed = random.randint(0, 2**32 - 1) if seed is None or seed < 0 else int(seed)

            yield gr.update(value=None, selected_index=None), "⏳ Initializing generation...", gr.update(visible=False)

            paths, seeds_used, start_time, headroom = [], [], time.time(), ""
            for idx in range(num_images):
                current_seed = (initial_seed + idx) % (2**32)

                def cb(step_idx, latent=None, is_start=False, override_num_inference_steps=None, progress_title=None, **kwargs):
                    if progress_title:
                        total = override_num_inference_steps or 1
                        done = 0.98 if "VAE" in progress_title else 0.0
                        fraction = min((idx + done) / num_images, 0.99)
                        desc = f"Image {idx+1}/{num_images} - {progress_title} {max(step_idx + 1, 0)}/{total}"
                    elif step_idx >= 0:
                        fraction = min((idx + (step_idx + 1) / total_steps) / num_images, 0.99)
                        desc = f"Image {idx+1}/{num_images} - Step {step_idx+1}/{total_steps}"
                    else:
                        return
                    progress(fraction, desc=desc)
                    report_progress(fraction, desc)

                print(f"Generating image {idx+1}/{num_images}: {width}x{height}, {spec['lora'] or 'quality'}, seed={current_seed}")
                t_img = time.time()
                result = run_generation(prompt, negative_prompt, mode, steps, guidance, width, height, current_seed,
                                        callback=cb, ref_images=refs, edit_image=edit_image, edit_mask=edit_mask,
                                        strength=strength, outpainting_dims=outpainting_dims, rgba=transparent)
                if result is None:
                    if pipeline._interrupt:
                        break
                    raise RuntimeError(f"Generation of image {idx+1} failed.")

                img_path = os.path.join(OUT_DIR, f"qwen21_{time.strftime('%Y%m%d_%H%M%S')}_seed{current_seed}.png")
                Image.fromarray(result[:, 0].permute(1, 2, 0).contiguous().numpy(),
                                mode="RGBA" if result.shape[0] == 4 else "RGB").save(img_path)
                paths.append(img_path)
                seeds_used.append(current_seed)
                took = time.time() - t_img
                print(f"  ✅ Finished image {idx+1} in {took:.1f}s -> {img_path}")
                yield gr.update(value=paths, selected_index=0), f"⏳ Generated {len(paths)}/{num_images} images...", gr.update(visible=False)

            if not paths:
                yield gr.update(value=None, selected_index=None), "⏹️ Generation stopped.", gr.update(visible=False)
                return

            zip_path = None
            if len(paths) > 1:
                zip_path = os.path.join(OUT_DIR, f"qwen21_batch_{time.strftime('%Y%m%d_%H%M%S')}.zip")
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_STORED) as zipf:
                    for path in paths:
                        zipf.write(path, os.path.basename(path))

            elapsed = time.time() - start_time
            status = f"✅ Generated {len(paths)} image(s) in {elapsed:.1f}s | Seeds: {seeds_used} | {width}x{height}"
            yield gr.update(value=paths, selected_index=0), status, gr.update(value=zip_path, visible=zip_path is not None)
        except Exception as e:
            traceback.print_exc()
            yield gr.update(value=None, selected_index=None), f"❌ Error: {str(e)}", gr.update(visible=False)
        finally:
            pipeline._interrupt = False
            PROGRESS.update(active=False, fraction=1.0)
            gc.collect()

    def switch_mode(mode):
        quality = mode == MODE_QUALITY
        return gr.update(interactive=quality), gr.update(interactive=quality), gr.update(interactive=quality)

    TASK_TIPS = {
        TASK_CREATE: "Describe what is visible. Put exact text in \"double quotes\".",
        TASK_REFS: "Describe edits or refer to uploaded images in order.",
        TASK_INPAINT: "Describe what belongs in the painted area.",
        TASK_OUTPAINT: "Describe what the wider view contains (or leave empty to auto-extend).",
    }

    def switch_task(task):
        return (gr.update(visible=task == TASK_REFS), gr.update(visible=task == TASK_INPAINT),
                gr.update(visible=task == TASK_INPAINT), gr.update(visible=task == TASK_OUTPAINT),
                gr.update(info=TASK_TIPS[task]),
                gr.update(value=MATCH_INPUT if task != TASK_CREATE else "1:1 Square",
                          interactive=task not in (TASK_INPAINT, TASK_OUTPAINT)))

    # Cloudflare tunnel helper
    def start_cloudflare_tunnel(port):
        found = {"url": None}
        try:
            if not os.path.exists(CLOUDFLARED_BIN):
                download_cloudflared()
            if IS_WIN:
                subprocess.run(["taskkill", "/F", "/IM", "cloudflared.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.run(["pkill", "-f", "cloudflared tunnel"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            tunnel = subprocess.Popen([CLOUDFLARED_BIN, "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"],
                                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        except Exception as e:
            print(f"⚠️ Cloudflare tunnel unavailable: {e}")
            return found

        def _watch():
            for line in tunnel.stdout:
                match = re.search(r"https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com", line)
                if match and not found["url"]:
                    found["url"] = match.group(0)

        threading.Thread(target=_watch, daemon=True).start()
        return found

    # Gradio Interface
    CSS = """
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
    * { font-family: 'Inter', sans-serif !important; }
    .gradio-container { max-width: 1050px !important; margin: auto !important; }
    .brand-header { text-align: center; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 25px; border-radius: 14px; margin-bottom: 20px; box-shadow: 0 10px 25px rgba(102,126,234,0.3); }
    .brand-title { color: white; font-size: 2em; font-weight: 700; margin: 0 0 6px 0; }
    .brand-subtitle { color: rgba(255,255,255,0.88); font-size: 1em; }
    button.primary { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important; color: white !important; font-weight: 600 !important; border-radius: 10px !important; }
    """

    BRAND_HTML = """
    <div class="brand-header">
      <div class="brand-title">🎨 Qwen-Image 2.1 Uncensored (RDP Edition)</div>
      <div class="brand-subtitle">AIQUEST Academy · Text-to-Image · Inpaint · Multi-Reference · INT8 Tensor Cores</div>
    </div>
    """

    with gr.Blocks(theme=gr.themes.Soft(), css=CSS, title="Qwen-Image 2.1 Uncensored") as demo:
        gr.HTML(BRAND_HTML)

        with gr.Row():
            with gr.Column(scale=1):
                task_in = gr.Radio(label="🧭 Task", choices=[TASK_CREATE, TASK_REFS, TASK_INPAINT, TASK_OUTPAINT], value=TASK_CREATE)
                refs_in = gr.Gallery(label="🧩 Images (up to 10)", type="pil", interactive=True, columns=4, height=220, visible=False)
                editor_in = gr.ImageEditor(label="🖌️ Paint over area to change", type="pil", sources=["upload", "clipboard"], layers=False, visible=False)
                strength_in = gr.Slider(label="💪 Strength (Inpaint)", minimum=0.3, maximum=1.0, step=0.05, value=1.0, visible=False)
                with gr.Group(visible=False) as outpaint_group:
                    with gr.Row():
                        outpaint_in = gr.Image(label="🔲 Image to extend", type="pil", sources=["upload", "clipboard"], height=240)
                        outpaint_preview_out = gr.Image(label="👁️ Preview", interactive=False, height=240)
                    outpaint_ratio_in = gr.Dropdown(label="📐 Ratio", choices=list(OUTPAINT_RATIOS), value="Custom margins (sliders)")
                    with gr.Row():
                        out_left_in = gr.Slider(label="⬅️ Left %", minimum=0, maximum=100, step=5, value=25)
                        out_right_in = gr.Slider(label="➡️ Right %", minimum=0, maximum=100, step=5, value=25)
                    with gr.Row():
                        out_top_in = gr.Slider(label="⬆️ Top %", minimum=0, maximum=100, step=5, value=0)
                        out_bottom_in = gr.Slider(label="⬇️ Bottom %", minimum=0, maximum=100, step=5, value=0)
                prompt_in = gr.Textbox(label="📝 Prompt", lines=3, info=TASK_TIPS[TASK_CREATE], placeholder="Describe what you want to create...")
                mode_in = gr.Radio(label="🚀 Mode", choices=[MODE_VIGGLE, MODE_PRUNA, MODE_ALIBABA, MODE_QUALITY], value=MODE_VIGGLE)
                transparent_in = gr.Checkbox(label="🫥 Transparent background (RGBA PNG)", value=False)
                with gr.Row():
                    style_in = gr.Dropdown(label="🎨 Style Preset", choices=["None"] + list(STYLE_MODIFIERS), value="None")
                    resolution_in = gr.Dropdown(label="🖥️ Base Resolution", choices=list(RESOLUTIONS), value="1024px (recommended)")
                with gr.Row():
                    aspect_in = gr.Dropdown(label="📏 Aspect Ratio", choices=list(ASPECT_RATIOS), value="1:1 Square")
                    num_images_in = gr.Slider(label="🖼️ Number of Images", minimum=1, maximum=4, step=1, value=1)
                with gr.Accordion("⚙️ Advanced Settings", open=False):
                    negative_in = gr.Textbox(label="🚫 Negative Prompt", lines=2, interactive=False)
                    with gr.Row():
                        steps_in = gr.Slider(label="🔁 Steps", minimum=10, maximum=50, step=1, value=40, interactive=False)
                        guidance_in = gr.Slider(label="🧲 Guidance / CFG", minimum=1.0, maximum=8.0, step=0.5, value=4.0, interactive=False)
                    seed_in = gr.Number(label="🎲 Seed (-1 for Random)", value=-1, precision=0)
                with gr.Row():
                    gen_btn = gr.Button("🎨 Generate", variant="primary", size="lg")
                    stop_btn = gr.Button("⏹️ Stop", variant="stop", size="lg")

            with gr.Column(scale=1):
                gallery_out = gr.Gallery(label="🖼️ Generated Images", columns=2, rows=2, object_fit="contain", preview=True)
                zip_out = gr.File(label="📦 Download ZIP", visible=False)
                status_out = gr.Textbox(label="ℹ️ Status", interactive=False)

        task_in.change(switch_task, inputs=task_in, outputs=[refs_in, editor_in, strength_in, outpaint_group, prompt_in, aspect_in], queue=False)
        outpaint_inputs = [outpaint_in, resolution_in, outpaint_ratio_in, out_top_in, out_bottom_in, out_left_in, out_right_in]
        for component in outpaint_inputs:
            component.change(outpaint_preview, inputs=outpaint_inputs, outputs=outpaint_preview_out, queue=False)
        mode_in.change(switch_mode, inputs=mode_in, outputs=[negative_in, steps_in, guidance_in], queue=False)
        gen_btn.click(
            generate_image,
            inputs=[task_in, prompt_in, refs_in, editor_in, strength_in, outpaint_in, outpaint_ratio_in, out_top_in,
                    out_bottom_in, out_left_in, out_right_in, negative_in, style_in, mode_in, transparent_in, steps_in, guidance_in, aspect_in, resolution_in, seed_in, num_images_in],
            outputs=[gallery_out, status_out, zip_out],
            concurrency_limit=1,
        )
        stop_btn.click(stop_generation, outputs=[status_out], queue=False)

    SERVER_PORT = 7860
    cf = start_cloudflare_tunnel(SERVER_PORT)

    print("\n" + "=" * 65)
    print("🎨 Loading Qwen-Image 2.1 Engine...")
    print("=" * 65)
    non_local_engine = _load_engine()
    globals()["QWEN_ENGINE"] = non_local_engine
    ENGINE_READY.set()
    print("✅ Model loaded and ready!")

    demo.queue(max_size=20)
    demo.launch(
        server_name="0.0.0.0",
        server_port=SERVER_PORT,
        share=True,
        inline=False,
        show_error=True,
        prevent_thread_lock=True,
        quiet=False,
        allowed_paths=[OUT_DIR]
    )

    for _ in range(30):
        if cf.get("url"):
            break
        time.sleep(0.5)

    local_url = f"http://127.0.0.1:{SERVER_PORT}"
    print("\n" + "=" * 65)
    print("🚀 Qwen-Image 2.1 Uncensored Web UI is LIVE!")
    print("=" * 65)
    print(f"🏠 Local URL:        {local_url}")
    print(f"🌐 Cloudflare URL:   {cf.get('url') or '(connecting, check trycloudflare console)'}")
    print(f"🔗 Gradio Share URL: {getattr(demo, 'share_url', None) or '(see above)'}")
    print(f"💾 Outputs saved to: {OUT_DIR}")
    print("=" * 65 + "\n")

    try:
        webbrowser.open(local_url)
    except Exception:
        pass

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Generator stopped.")


def main():
    print("=" * 65)
    print("🎨 Qwen-Image 2.1 Uncensored - Auto Setup & Launch")
    print("=" * 65)
    check_gpu()
    fetch_wan2gp()
    download_all_models()
    start_app()

if __name__ == "__main__":
    main()
