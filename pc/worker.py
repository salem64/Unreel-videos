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
NEG_DEFAULT = ("blurry, low quality, distorted, deformed, watermark, text, subtitles, logo, jpeg artifacts, "
               "static frame, ugly, extra fingers, bad hands, people, faces")
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
    r = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)
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


def render_clip(clip, negative, seed):
    pid = http("/prompt", {"prompt": workflow(clip, negative, seed), "client_id": str(uuid.uuid4())})["prompt_id"]
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


def assemble(clips, out, hook):
    import imageio_ffmpeg
    ff = imageio_ffmpeg.get_ffmpeg_exe()
    args = [ff, "-y", "-loglevel", "error"]
    for c in clips:
        args += ["-i", str(c)]
    n = len(clips)
    parts = "".join(f"[{i}:v]scale=1080:-2,crop=1080:1920,setsar=1,fps=30[v{i}];[{i}:a]aresample=44100[a{i}];" for i in range(n))
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
    subprocess.run(args, check=True)
    if hook:
        out.with_suffix(".hook.png").unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    a = ap.parse_args()
    global ROOT, REPO, COMFY, LOGFILE
    ROOT = Path(a.root)
    REPO = ROOT / "Unreel-videos"
    COMFY = ROOT / "ComfyUI_windows_portable" / "ComfyUI"
    LOGFILE = ROOT / "worker.log"
    py = ROOT / "ComfyUI_windows_portable" / "python_embeded" / "python.exe"

    log("=== Unreel Batch ===")
    git("pull", "--rebase")
    jobs = sorted((REPO / "jobs").glob("*.json"))
    if not jobs:
        log("Keine Auftraege in jobs/ - nichts zu tun.")
        return
    log(f"{len(jobs)} Auftrag/Auftraege gefunden.")

    proc = None
    if not comfy_up():
        log("Starte ComfyUI ...")
        proc = subprocess.Popen([str(py), "-s", str(COMFY / "main.py"), "--windows-standalone-build", "--disable-auto-launch"],
                                cwd=str(COMFY.parent), stdout=open(ROOT / "comfyui.log", "a"), stderr=subprocess.STDOUT)
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
    log(f"Fertig: {done}/{len(jobs)} Videos im Vorrat.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
