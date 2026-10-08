"""Unreel PC worker: renders jobs/*.json with ComfyUI (Wan 2.2 5B + MMAudio) into queue/.

Run with ComfyUI's embedded Python (the desktop .bat does this):
    python_embeded\\python.exe -s Unreel-videos\\pc\\worker.py --root C:\\Unreel

Job file (jobs/<id>.json):
{
  "id": "2026-10-12-glass-kiwi",
  "clips": [{"prompt": "...", "audio_prompt": "...", "seed": 123}],
  "negative": "optional negative prompt",
  "hook": "optional text shown in the first 2.5 s",
  "meta": {"topic": "...", "caption": "...", "first_comment": "...", "youtube_title": "...", "tiktok_title": "..."}
}
"""
import argparse, json, os, random, subprocess, sys, time, traceback, urllib.request, uuid
from pathlib import Path

HOST = "http://127.0.0.1:8188"
NOWIN = {"creationflags": 0x08000000} if os.name == "nt" else {}  # CREATE_NO_WINDOW
NEG_DEFAULT = ("static, still image, frozen frame, no motion, photo, slideshow, long exposure, star trails, timelapse streaks, "
               "blurry, low quality, distorted, deformed, watermark, text, subtitles, logo, jpeg artifacts, "
               "ugly, extra fingers, bad hands, faces")
W, H, LENGTH, FPS = 704, 1280, 121, 24  # Wan 2.2 5B native vertical, ~5 s per clip


def log(msg):
    line = time.strftime("%H:%M:%S ") + msg
    print(line, flush=True)
    with open(LOGFILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def http(path, data=None, timeout=30):
    req = urllib.request.Request(HOST + path, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def comfy_up():
    try:
        http("/system_stats", timeout=3)
        return True
    except Exception:
        return False


def git(*args, check=True):
    r = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True, **NOWIN)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def workflow(clip, negative, seed):
    dur = round(LENGTH / FPS, 2)
    return {
        "37": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_ti2v_5B_fp16.safetensors", "weight_dtype": "default"}},
        "38": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}},
        "39": {"class_type": "VAELoader", "inputs": {"vae_name": "wan2.2_vae.safetensors"}},
        "48": {"class_type": "ModelSamplingSD3", "inputs": {"shift": 8, "model": ["37", 0]}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": clip["prompt"], "clip": ["38", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["38", 0]}},
        "55": {"class_type": "Wan22ImageToVideoLatent", "inputs": {"vae": ["39", 0], "width": W, "height": H, "length": LENGTH, "batch_size": 1}},
        "3": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": 20, "cfg": 5, "sampler_name": "uni_pc", "scheduler": "simple",
                                                    "denoise": 1, "model": ["48", 0], "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["55", 0]}},
        "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["39", 0]}},
        "60": {"class_type": "MMAudioModelLoader", "inputs": {"mmaudio_model": "mmaudio_large_44k_v2_fp16.safetensors", "base_precision": "fp16"}},
        "61": {"class_type": "MMAudioFeatureUtilsLoader", "inputs": {"vae_model": "mmaudio_vae_44k_fp16.safetensors",
                                                                     "synchformer_model": "mmaudio_synchformer_fp16.safetensors",
                                                                     "clip_model": "apple_DFN5B-CLIP-ViT-H-14-384_fp16.safetensors",
                                                                     "mode": "44k", "precision": "fp16"}},
        "62": {"class_type": "MMAudioSampler", "inputs": {"mmaudio_model": ["60", 0], "feature_utils": ["61", 0], "duration": dur, "steps": 25,
                                                          "cfg": 4.5, "seed": seed, "prompt": clip.get("audio_prompt", ""),
                                                          "negative_prompt": "music, speech, voice, talking, noise, hum",
                                                          "mask_away_clip": False, "force_offload": True, "images": ["8", 0]}},
        "57": {"class_type": "CreateVideo", "inputs": {"images": ["8", 0], "fps": FPS, "audio": ["62", 0]}},
        "58": {"class_type": "SaveVideo", "inputs": {"video": ["57", 0], "filename_prefix": "unreel/clip", "format": "auto", "codec": "auto"}},
    }


# ---------------------------------------------------------------- pipeline v2 (best quality)
# Z-Image Turbo start frame -> Wan 2.2 14B I2V (fp8, lightx2v 4-step LoRAs) -> RIFE x2 -> MMAudio
V2_FILES = [
    "models/diffusion_models/z_image_turbo_bf16.safetensors",
    "models/text_encoders/qwen_3_4b.safetensors",
    "models/vae/ae.safetensors",
    "models/diffusion_models/wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors",
    "models/diffusion_models/wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors",
    "models/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors",
    "models/loras/wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors",
    "models/vae/wan_2.1_vae.safetensors",
    "custom_nodes/ComfyUI-Frame-Interpolation",
]
V2_W, V2_H, V2_LEN, V2_FPS = 576, 1024, 81, 16   # ~5 s, interpolated to 32 fps
V2_MODE = os.environ.get("UNREEL_V2_MODE", "max")  # "max": full 20 steps, best motion (slow) | "fast": lightx2v 4-step LoRAs


def v2_available():
    return all((COMFY / f).exists() for f in V2_FILES)


def workflow_v2(clip, negative, seed):
    # MMAudio reads the frame batch as if it were 25 fps and cuts the audio to len(frames)/25 s,
    # so give it the RIFE output (32 fps, 161 frames) -> full-length audio.
    dur = round((2 * V2_LEN - 1) / (2 * V2_FPS), 2)
    fast = V2_MODE == "fast"
    steps, split, cfg = (4, 2, 1) if fast else (20, 10, 3.5)
    wf = {
        # start image (Z-Image Turbo)
        "z1": {"class_type": "UNETLoader", "inputs": {"unet_name": "z_image_turbo_bf16.safetensors", "weight_dtype": "default"}},
        "z2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen_3_4b.safetensors", "type": "lumina2", "device": "default"}},
        "z3": {"class_type": "VAELoader", "inputs": {"vae_name": "ae.safetensors"}},
        "z4": {"class_type": "ModelSamplingAuraFlow", "inputs": {"shift": 3, "model": ["z1", 0]}},
        "z5": {"class_type": "CLIPTextEncode", "inputs": {"text": clip["image_prompt"], "clip": ["z2", 0]}},
        "z6": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["z5", 0]}},
        "z7": {"class_type": "EmptySD3LatentImage", "inputs": {"width": 768, "height": 1344, "batch_size": 1}},
        "z8": {"class_type": "KSampler", "inputs": {"seed": seed, "steps": 8, "cfg": 1, "sampler_name": "res_multistep", "scheduler": "simple",
                                                     "denoise": 1, "model": ["z4", 0], "positive": ["z5", 0], "negative": ["z6", 0], "latent_image": ["z7", 0]}},
        "z9": {"class_type": "VAEDecode", "inputs": {"samples": ["z8", 0], "vae": ["z3", 0]}},
        "z10": {"class_type": "SaveImage", "inputs": {"images": ["z9", 0], "filename_prefix": "unreel/start"}},
        # video (Wan 2.2 14B I2V, two experts, 4-step LoRAs)
        "w1": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors", "weight_dtype": "default"}},
        "w2": {"class_type": "UNETLoader", "inputs": {"unet_name": "wan2.2_i2v_low_noise_14B_fp8_scaled.safetensors", "weight_dtype": "default"}},
        "w3": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["w1", 0], "lora_name": "wan2.2_i2v_lightx2v_4steps_lora_v1_high_noise.safetensors", "strength_model": 1.0}},
        "w4": {"class_type": "LoraLoaderModelOnly", "inputs": {"model": ["w2", 0], "lora_name": "wan2.2_i2v_lightx2v_4steps_lora_v1_low_noise.safetensors", "strength_model": 1.0}},
        "w5": {"class_type": "ModelSamplingSD3", "inputs": {"shift": 5, "model": ["w3", 0]}},
        "w6": {"class_type": "ModelSamplingSD3", "inputs": {"shift": 5, "model": ["w4", 0]}},
        "w7": {"class_type": "CLIPLoader", "inputs": {"clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan", "device": "default"}},
        "w8": {"class_type": "VAELoader", "inputs": {"vae_name": "wan_2.1_vae.safetensors"}},
        "w9": {"class_type": "CLIPTextEncode", "inputs": {"text": clip["prompt"], "clip": ["w7", 0]}},
        "w10": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["w7", 0]}},
        "w11": {"class_type": "WanImageToVideo", "inputs": {"positive": ["w9", 0], "negative": ["w10", 0], "vae": ["w8", 0], "start_image": ["z9", 0],
                                                             "width": V2_W, "height": V2_H, "length": V2_LEN, "batch_size": 1}},
        "w12": {"class_type": "KSamplerAdvanced", "inputs": {"model": ["w5", 0], "add_noise": "enable", "noise_seed": seed, "steps": steps, "cfg": cfg,
                                                              "sampler_name": "euler", "scheduler": "simple", "positive": ["w11", 0], "negative": ["w11", 1],
                                                              "latent_image": ["w11", 2], "start_at_step": 0, "end_at_step": split, "return_with_leftover_noise": "enable"}},
        "w13": {"class_type": "KSamplerAdvanced", "inputs": {"model": ["w6", 0], "add_noise": "disable", "noise_seed": 0, "steps": steps, "cfg": cfg,
                                                              "sampler_name": "euler", "scheduler": "simple", "positive": ["w11", 0], "negative": ["w11", 1],
                                                              "latent_image": ["w12", 0], "start_at_step": split, "end_at_step": 10000, "return_with_leftover_noise": "disable"}},
        "w14": {"class_type": "VAEDecode", "inputs": {"samples": ["w13", 0], "vae": ["w8", 0]}},
        # smoother motion
        "r1": {"class_type": "RIFE VFI", "inputs": {"ckpt_name": "rife49.pth", "frames": ["w14", 0], "clear_cache_after_n_frames": 10, "multiplier": 2,
                                                     "fast_mode": True, "ensemble": True, "scale_factor": 1.0,
                                                     "dtype": "float32", "torch_compile": False, "batch_size": 1}},
        # sound
        "60": {"class_type": "MMAudioModelLoader", "inputs": {"mmaudio_model": "mmaudio_large_44k_v2_fp16.safetensors", "base_precision": "fp16"}},
        "61": {"class_type": "MMAudioFeatureUtilsLoader", "inputs": {"vae_model": "mmaudio_vae_44k_fp16.safetensors",
                                                                     "synchformer_model": "mmaudio_synchformer_fp16.safetensors",
                                                                     "clip_model": "apple_DFN5B-CLIP-ViT-H-14-384_fp16.safetensors",
                                                                     "mode": "44k", "precision": "fp16"}},
        "62": {"class_type": "MMAudioSampler", "inputs": {"mmaudio_model": ["60", 0], "feature_utils": ["61", 0], "duration": dur, "steps": 25,
                                                          "cfg": 4.5, "seed": seed, "prompt": clip.get("audio_prompt", ""),
                                                          "negative_prompt": "music, speech, voice, talking, noise, hum",
                                                          "mask_away_clip": False, "force_offload": True, "images": ["r1", 0]}},
        "57": {"class_type": "CreateVideo", "inputs": {"images": ["r1", 0], "fps": V2_FPS * 2, "audio": ["62", 0]}},
        "58": {"class_type": "SaveVideo", "inputs": {"video": ["57", 0], "filename_prefix": "unreel/clip", "format": "auto", "codec": "auto"}},
    }
    if not fast:  # drop the speed LoRAs: base models directly into ModelSamplingSD3
        del wf["w3"], wf["w4"]
        wf["w5"]["inputs"]["model"] = ["w1", 0]
        wf["w6"]["inputs"]["model"] = ["w2", 0]
    return wf


def run_prompt(wf, exts, timeout=3600):
    """Queue a graph, wait, return list of output file paths with the given extensions."""
    pid = http("/prompt", {"prompt": wf, "client_id": str(uuid.uuid4())})["prompt_id"]
    t0 = time.time()
    while True:
        time.sleep(2)
        hist = http(f"/history/{pid}")
        if pid in hist:
            h = hist[pid]
            st = h.get("status", {})
            if st.get("status_str") == "error":
                msgs = [m for m in st.get("messages", []) if m[0] == "execution_error"]
                raise RuntimeError(f"ComfyUI error: {json.dumps(msgs)[:800]}")
            files = []
            for out in h.get("outputs", {}).values():
                for lst in out.values():
                    if isinstance(lst, list):
                        for it in lst:
                            if isinstance(it, dict) and str(it.get("filename", "")).lower().endswith(exts) and it.get("type", "output") == "output":
                                files.append(COMFY / "output" / it.get("subfolder", "") / it["filename"])
            if not files:
                raise RuntimeError(f"no {exts} in outputs: {json.dumps(h.get('outputs'))[:500]}")
            return files, int(time.time() - t0)
        if time.time() - t0 > timeout:
            raise RuntimeError("timeout")


ZIMG_FILES = ["models/diffusion_models/z_image_turbo_bf16.safetensors", "models/text_encoders/qwen_3_4b.safetensors", "models/vae/ae.safetensors"]


def workflow_still(image_prompt, seed):
    """Start-frame only (Z-Image Turbo), ~15 s."""
    wf = workflow_v2({"image_prompt": image_prompt, "prompt": ""}, NEG_DEFAULT, seed)
    return {k: v for k, v in wf.items() if k.startswith("z")}


def render_stills(job):
    """Stills mode: for each variant x seed render only the start image; save small JPEGs to queue/stills/<id>/."""
    from PIL import Image
    jid = job["id"]
    outdir = REPO / "queue" / "stills" / jid
    outdir.mkdir(parents=True, exist_ok=True)
    index = []
    for vi, var in enumerate(job["variants"]):
        seeds = var.get("seeds") or [random.randint(1, 2**31) for _ in range(int(var.get("count", 3)))]
        for seed in seeds:
            files, secs = run_prompt(workflow_still(var["image_prompt"], int(seed)), (".png",), timeout=900)
            name = f"{var.get('name', 'v' + str(vi + 1))}-{seed}.jpg"
            im = Image.open(files[0]).convert("RGB")
            im.thumbnail((720, 1280))
            im.save(outdir / name, quality=88)
            index.append({"file": name, "variant": var.get("name", f"v{vi + 1}"), "seed": int(seed),
                          "image_prompt": var["image_prompt"], "topic": var.get("topic", job.get("topic", ""))})
            log(f"  Startbild {name} in {secs} s")
    (outdir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(index)


def stage_start_image(rel_path):
    """Copy an approved still from the repo into ComfyUI/input and return its file name for LoadImage."""
    import shutil
    src = REPO / rel_path
    dst_name = "unreel_" + src.name
    shutil.copyfile(src, COMFY / "input" / dst_name)
    return dst_name


def render_clip(clip, negative, seed):
    use_v2 = bool(clip.get("image_prompt")) and v2_available()
    if not use_v2 and clip.get("image_prompt"):
        clip = dict(clip, prompt=clip["image_prompt"] + " " + clip["prompt"])  # v1 fallback: scene + motion in one prompt
    wf = workflow_v2(clip, negative, seed) if use_v2 else workflow(clip, negative, seed)
    if use_v2 and clip.get("start_image"):  # use the approved still exactly
        wf = {k: v for k, v in wf.items() if not k.startswith("z")}
        wf["z9"] = {"class_type": "LoadImage", "inputs": {"image": stage_start_image(clip["start_image"])}}
    log(f"  Pipeline {'v2 (Z-Image + Wan 14B + RIFE)' if use_v2 else 'v1 (Wan 5B)'}")
    pid = http("/prompt", {"prompt": wf, "client_id": str(uuid.uuid4())})["prompt_id"]
    t0 = time.time()
    while True:
        time.sleep(5)
        hist = http(f"/history/{pid}")
        if pid in hist:
            h = hist[pid]
            st = h.get("status", {})
            if st.get("status_str") == "error":
                msgs = [m for m in st.get("messages", []) if m[0] == "execution_error"]
                raise RuntimeError(f"ComfyUI error: {json.dumps(msgs)[:800]}")
            for out in h.get("outputs", {}).values():
                for lst in out.values():
                    if isinstance(lst, list):
                        for it in lst:
                            if isinstance(it, dict) and str(it.get("filename", "")).endswith(".mp4"):
                                p = COMFY / "output" / it.get("subfolder", "") / it["filename"]
                                log(f"  clip fertig in {int(time.time() - t0)} s: {p.name}")
                                return p
            raise RuntimeError(f"no mp4 in outputs: {json.dumps(h.get('outputs'))[:500]}")
        if time.time() - t0 > 3600:
            raise RuntimeError("timeout")


def hook_png(text, path):
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGBA", (1080, 1920), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font = None
    for f in ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"]:
        if os.path.exists(f):
            font = ImageFont.truetype(f, 84)
            break
    font = font or ImageFont.load_default()
    words, lines, cur = text.upper().split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=font) <= 900 or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    lines.append(cur)
    y = 260
    for l in lines:
        tw = d.textlength(l, font=font)
        d.text(((1080 - tw) / 2, y), l, font=font, fill=(255, 255, 255, 255), stroke_width=8, stroke_fill=(0, 0, 0, 255))
        y += 100
    img.save(path)


def video_duration(ff, path):
    """Duration of the video stream in seconds (parsed from ffmpeg's stream info)."""
    import re
    r = subprocess.run([ff, "-i", str(path)], capture_output=True, text=True, **NOWIN)
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", r.stderr)
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 5.0


def assemble(clips, out, hook):
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    args = [ff, "-y", "-loglevel", "error"]
    for c in clips:
        args += ["-i", str(c)]
    n = len(clips)
    durs = [video_duration(ff, c) for c in clips]
    parts = "".join(f"[{i}:v]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,unsharp=5:5:0.5,setsar=1,fps=30[v{i}];"
                    f"[{i}:a]aresample=44100,apad=whole_dur={durs[i]:.3f},atrim=0:{durs[i]:.3f},asetpts=PTS-STARTPTS[a{i}];" for i in range(n))
    concat = "".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vc][ac]"
    fc = parts + concat
    vout = "[vc]"
    if hook:
        png = out.with_suffix(".hook.png")
        hook_png(hook, png)
        args += ["-i", str(png)]
        fc += f";[vc][{n}:v]overlay=0:0:enable='lt(t,2.5)'[vo]"
        vout = "[vo]"
    args += ["-filter_complex", fc, "-map", vout, "-map", "[ac]", "-c:v", "libx264", "-preset", "medium", "-crf", "19",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)]
    subprocess.run(args, check=True, **NOWIN)
    if hook:
        out.with_suffix(".hook.png").unlink(missing_ok=True)


def gpu_busy(threshold=35, samples=5):
    """True if the GPU is in use (e.g. gaming) - average utilization over a few seconds."""
    vals = []
    for _ in range(samples):
        try:
            out = subprocess.run(["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, **NOWIN).stdout.strip().splitlines()
            vals.append(max(int(v) for v in out if v.strip().isdigit()))
        except Exception:
            return False
        time.sleep(1)
    return sum(vals) / len(vals) >= threshold


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--auto", action="store_true", help="scheduled mode: quiet exit if nothing to do or GPU busy")
    a = ap.parse_args()
    global ROOT, REPO, COMFY, LOGFILE
    ROOT = Path(a.root)
    REPO = ROOT / "Unreel-videos"
    COMFY = ROOT / "ComfyUI_windows_portable" / "ComfyUI"
    LOGFILE = ROOT / "worker.log"
    py = ROOT / "ComfyUI_windows_portable" / "python_embeded" / "python.exe"

    lock = ROOT / "worker.lock"
    if lock.exists() and time.time() - lock.stat().st_mtime < 6 * 3600:
        if not a.auto:
            print("Es laeuft bereits ein Batch (worker.lock). Abbruch.")
        return
    try:
        git("pull", "--rebase")
    except Exception as e:
        if not a.auto:
            raise
        return
    jobs = sorted((REPO / "jobs").glob("*.json"),
                  key=lambda p: (0 if '"stills"' in p.read_text(encoding="utf-8") else 1, p.name))
    if not jobs:
        if not a.auto:
            log("Keine Auftraege in jobs/ - nichts zu tun.")
        return
    if a.auto and gpu_busy():
        log(f"{len(jobs)} Auftraege warten, aber die Grafikkarte ist gerade beschaeftigt - spaeter erneut.")
        return
    lock.write_text(str(os.getpid()))
    global LOCK
    LOCK = lock
    log("=== Unreel Batch ===")
    log(f"{len(jobs)} Auftrag/Auftraege gefunden.")

    proc = None
    if not comfy_up():
        log("Starte ComfyUI ...")
        proc = subprocess.Popen([str(py), "-s", str(COMFY / "main.py"), "--windows-standalone-build", "--disable-auto-launch"],
                                cwd=str(COMFY.parent), stdout=open(ROOT / "comfyui.log", "a"), stderr=subprocess.STDOUT, **NOWIN)
        for _ in range(120):
            if comfy_up():
                break
            time.sleep(3)
        else:
            raise RuntimeError("ComfyUI startet nicht - siehe comfyui.log")
    (REPO / "queue").mkdir(exist_ok=True)
    done = 0
    try:
        for jf in jobs:
            job = json.loads(jf.read_text(encoding="utf-8"))
            jid = job.get("id", jf.stem)
            if job.get("mode") == "stills":
                if not all((COMFY / f).exists() for f in ZIMG_FILES):
                    log(f"Auftrag {jid} (Startbilder) braucht Z-Image (install_v2.ps1) - uebersprungen.")
                    continue
                try:
                    n = render_stills(job)
                    jf.unlink()
                    git("add", "-A")
                    git("commit", "-m", f"PC stills: {jid} ({n} images)")
                    git("pull", "--rebase")
                    git("push")
                    done += 1
                    log(f"  -> queue/stills/{jid}/ ({n} Startbilder) hochgeladen")
                except Exception:
                    log(f"  Startbilder {jid} fehlgeschlagen:\n{traceback.format_exc()}")
                continue
            if job.get("require_v2") and not v2_available():
                log(f"Auftrag {jid} braucht Pipeline v2 (install_v2.ps1) - uebersprungen.")
                continue
            log(f"Auftrag {jid}: {len(job['clips'])} Clips")
            try:
                clips = []
                for c in job["clips"]:
                    seed = int(c.get("seed", random.randint(1, 2**31)))
                    try:
                        clips.append(render_clip(c, job.get("negative", NEG_DEFAULT), seed))
                    except Exception as e:
                        log(f"  Fehler, zweiter Versuch: {e}")
                        clips.append(render_clip(c, job.get("negative", NEG_DEFAULT), seed + 1))
                out = REPO / "queue" / f"{jid}.mp4"
                assemble(clips, out, job.get("hook"))
                meta = dict(job.get("meta", {}))
                meta.update({"id": jid, "ai_label": True, "file": out.name})
                (REPO / "queue" / f"{jid}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
                jf.unlink()
                git("add", "-A")
                git("commit", "-m", f"PC render: {jid}")
                git("pull", "--rebase")
                git("push")
                done += 1
                log(f"  -> queue/{out.name} hochgeladen")
            except Exception:
                log(f"  Auftrag {jid} fehlgeschlagen:\n{traceback.format_exc()}")
    finally:
        if proc:
            proc.terminate()
        lock.unlink(missing_ok=True)
    log(f"Fertig: {done}/{len(jobs)} Videos im Vorrat.")


LOCK = None

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        try:
            log("FEHLER:\n" + traceback.format_exc())
        except Exception:
            pass
        sys.exit(1)
    finally:
        if LOCK is not None:
            LOCK.unlink(missing_ok=True)
