import io
import os
import time
import json
import uuid
import random
import threading

import requests
import imageio.v2 as imageio
from PIL import Image
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()

DEAPI_KEY = "16784|XHKP9SURzRg4Vjr3S5RxRiSmkGNreoNwyKv2Ja4gd2fc14b4"
DEAPI_GENERATE_URL = "https://api.deapi.ai/api/v2/videos/generations"
DEAPI_JOB_URL = "https://api.deapi.ai/api/v2/jobs"

ROBLOX_API_KEY = "0yHiwJwAAUKKcwqk4y3AowUCo6XmiSHr6uSGyie+N1G1lSzbZXlKaGJHY2lPaUpTVXpJMU5pSXNJbXRwWkNJNkluTnBaeTB5TURJeExUQTNMVEV6VkRFNE9qVXhPalE1V2lJc0luUjVjQ0k2SWtwWFZDSjkuZXlKaGRXUWlPaUpTYjJKc2IzaEpiblJsY201aGJDSXNJbWx6Y3lJNklrTnNiM1ZrUVhWMGFHVnVkR2xqWVhScGIyNVRaWEoyYVdObElpd2lZbUZ6WlVGd2FVdGxlU0k2SWpCNVNHbDNTbmRCUVZWTFMyTjNjV3MwZVROQmIzZFZRMjgyV0cxcFUwaHlOblZUUjNscFpTdE9NVWN4YkZONllpSXNJbTkzYm1WeVNXUWlPaUl4TURReE56QTJOVEl4TXlJc0ltVjRjQ0k2TVRjNE56RTFNakl4TUN3aWFXRjBJam94TnpnM01UUTROakV3TENKdVltWWlPakUzT0RjeE5EZzJNVEI5Lm5CSmlJNWhDSUc1RDJpZzVheUFkQzR5NFdHR3l1a1hfOVV0dDJQamc0Sl8xQmF5ODdObjJvZjRLWTgyY3hFX1dURi1HSllKZThaSFI4M2ZYVl9GLXQ0QmtxdXU1T09LZmlJaUVVOEV6NWUwSUlRc1V0amtQUm15LVdLTE5yYlozMnliNzlEQ3NCZ0l3MWdDSTBrQTJleERjbHFUaEx6aTd4STNHcWd0aERIajdydWlISm5jS0pTaDBCUVQ4RVZmWlV2ZmRiTzhNWUpBOFdQOVRUVXhUY29aQkFNSGRsZFVkajBsc1VMbXVGOTFBOVpCRkhaRjhQSjQ3NjhZREJidEZBRS14dnBuZkdmSUtuMjh2Ykp4ZExkT3hXRExMa1N1RkdxWXhEa3QxeU5YYXptRGRJY3lEOEx2ZWVZUjVyMmNQSzRCYm1ZQWxjV0N3MjY0QzV5M0JBQQ=="
ROBLOX_OWNER_ID = "10417065213"
ROBLOX_ASSETS_URL = "https://apis.roblox.com/assets/v1/assets"
ROBLOX_OPERATIONS_URL = "https://apis.roblox.com/assets/v1/operations"

MODEL = "Ltxv_13B_0_9_8_Distilled_FP8"
FRAMES = 120
FPS = 30
WIDTH = 768
HEIGHT = 512

JOBS = {}
JOBS_LOCK = threading.Lock()


def cleanup_jobs():
    now = time.time()
    with JOBS_LOCK:
        for key in list(JOBS.keys()):
            if now - JOBS[key].get("_ts", 0) > 900:
                del JOBS[key]


@app.get("/")
def home():
    return {"status": "Render Roblox Video API Aktif!"}


def deapi_generate_video(prompt):
    body = {
        "model": MODEL,
        "prompt": prompt,
        "width": WIDTH,
        "height": HEIGHT,
        "frames": FRAMES,
        "fps": FPS,
        "guidance": 7.5,
        "steps": 1,
        "seed": random.randint(1, 2147483647),
    }
    r = requests.post(
        DEAPI_GENERATE_URL,
        headers={"Authorization": "Bearer " + DEAPI_KEY, "Content-Type": "application/json"},
        json=body,
        timeout=60,
    )
    if r.status_code not in (200, 201):
        raise Exception("deapi request failed: " + r.text[:200])
    data = r.json().get("data", r.json())
    request_id = data.get("request_id") or data.get("requestId") or data.get("id")
    if not request_id:
        raise Exception("deapi returned no request id")
    for _ in range(60):
        time.sleep(3)
        p = requests.get(
            DEAPI_JOB_URL + "/" + request_id,
            headers={"Authorization": "Bearer " + DEAPI_KEY},
            timeout=30,
        )
        if p.status_code != 200:
            continue
        j = p.json().get("data", p.json())
        status = str(j.get("status", "")).lower()
        if status in ("done", "completed", "success"):
            url = j.get("result_url") or j.get("result")
            if not url:
                raise Exception("deapi done without result url")
            return url
        if status in ("error", "failed"):
            raise Exception("deapi generation failed")
    raise Exception("deapi generation timeout")


def upload_frame_to_roblox(pil_frame, name):
    buf = io.BytesIO()
    pil_frame.save(buf, format="JPEG", quality=95)
    content = buf.getvalue()
    req = {
        "assetType": "Decal",
        "displayName": name,
        "description": "Sydec AI video frame",
        "creationContext": {"creator": {"userId": ROBLOX_OWNER_ID}},
    }
    r = requests.post(
        ROBLOX_ASSETS_URL,
        headers={"x-api-key": ROBLOX_API_KEY},
        data={"request": json.dumps(req)},
        files={"fileContent": (name + ".jpg", content, "image/jpeg")},
        timeout=60,
    )
    if r.status_code not in (200, 201):
        raise Exception("roblox upload failed: " + r.text[:200])
    body = r.json()
    op_id = body.get("operationId") or str(body.get("path", "")).split("/")[-1]
    if not op_id:
        raise Exception("no operation id")
    for _ in range(80):
        time.sleep(0.8)
        rr = requests.get(
            ROBLOX_OPERATIONS_URL + "/" + op_id,
            headers={"x-api-key": ROBLOX_API_KEY},
            timeout=30,
        )
        if rr.status_code == 200:
            j = rr.json()
            if j.get("done"):
                asset_id = (j.get("response") or {}).get("assetId")
                if asset_id:
                    return str(asset_id)
                raise Exception("upload done without assetId")
    raise Exception("upload timeout")


def run_job(job, prompt):
    try:
        with JOBS_LOCK:
            JOBS[job] = {"status": "processing", "done": 0, "total": FRAMES, "_ts": time.time()}
        video_url = deapi_generate_video(prompt)
        with JOBS_LOCK:
            JOBS[job]["done"] = 0
        r = requests.get(video_url, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        tmp_path = "/tmp/" + job + ".mp4"
        with open(tmp_path, "wb") as f:
            f.write(r.content)
        reader = imageio.get_reader(tmp_path)
        total = reader.count_frames()
        indices = []
        if total <= FRAMES:
            indices = list(range(total))
        else:
            for i in range(FRAMES):
                indices.append(int(i * (total - 1) / max(FRAMES - 1, 1)))
        frames = []
        for k, idx in enumerate(indices):
            frame = reader.get_data(idx)
            im = Image.fromarray(frame).convert("RGB")
            asset_id = upload_frame_to_roblox(im, "SydecVideoFrame" + str(k))
            frames.append("rbxassetid://" + asset_id)
            with JOBS_LOCK:
                JOBS[job] = {"status": "processing", "done": k + 1, "total": len(indices), "_ts": time.time()}
        try:
            reader.close()
        except Exception:
            pass
        try:
            os.unlink(tmp_path)
        except Exception:
            pass
        with JOBS_LOCK:
            JOBS[job] = {"status": "done", "frames": frames, "_ts": time.time()}
    except Exception as exc:
        with JOBS_LOCK:
            JOBS[job] = {"status": "error", "error": str(exc)[:400], "_ts": time.time()}


def split_video_to_grid(video_url, frames=120, cols=9, cellW=108, cellH=72):
    r = requests.get(video_url, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    tmp_path = "/tmp/" + uuid.uuid4().hex + ".mp4"
    with open(tmp_path, "wb") as f:
        f.write(r.content)
    reader = imageio.get_reader(tmp_path)
    total = reader.count_frames()
    indices = []
    if total <= frames:
        indices = list(range(total))
    else:
        for i in range(frames):
            indices.append(int(i * (total - 1) / max(frames - 1, 1)))
    rows = (len(indices) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cellW, rows * cellH), (0, 0, 0))
    for k, idx in enumerate(indices):
        frame = reader.get_data(idx)
        im = Image.fromarray(frame).convert("RGB").resize((cellW, cellH), Image.Resampling.LANCZOS)
        r_, c_ = divmod(k, cols)
        sheet.paste(im, (c_ * cellW, r_ * cellH))
    try:
        reader.close()
    except Exception:
        pass
    try:
        os.unlink(tmp_path)
    except Exception:
        pass
    buf = io.BytesIO()
    sheet.save(buf, format="JPEG", quality=95)
    return buf.getvalue(), cols, rows, len(indices), cellW, cellH


@app.get("/convert")
def convert(video_url: str = ""):
    if not video_url:
        return JSONResponse({"error": "video_url required"}, status_code=400)
    try:
        data, cols, rows, count, cellW, cellH = split_video_to_grid(video_url)
    except Exception as exc:
        return JSONResponse({"error": str(exc)[:200]}, status_code=400)
    from fastapi.responses import Response

    return Response(content=data, media_type="image/jpeg", headers={"X-Cols": str(cols), "X-Rows": str(rows), "X-Frames": str(count), "X-CellW": str(cellW), "X-CellH": str(cellH)})


@app.get("/generate")
def generate(prompt: str = ""):
    cleanup_jobs()
    if not prompt or not prompt.strip():
        return JSONResponse({"error": "prompt required"}, status_code=400)
    job = uuid.uuid4().hex
    threading.Thread(target=run_job, args=(job, prompt), daemon=True).start()
    return {"job": job}


@app.get("/job")
def job_status(job: str = ""):
    cleanup_jobs()
    if not job:
        return JSONResponse({"error": "job required"}, status_code=400)
    st = JOBS.get(job)
    if not st:
        return JSONResponse({"error": "not found"}, status_code=404)
    if st.get("status") == "done":
        return {"status": "done", "frames": st.get("frames", [])}
    if st.get("status") == "error":
        return {"status": "error", "error": st.get("error", "failed")}
    return {"status": "processing", "done": st.get("done", 0), "total": st.get("total", FRAMES)}
