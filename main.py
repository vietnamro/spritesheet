import io
import os
import time
import json
import uuid
import math
import random
import hashlib
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

VIDEO_KEYS = [
    os.environ.get("DEAPI_VIDEO_KEY", "16784|XHKP9SURzRg4Vjr3S5RxRiSmkGNreoNwyKv2Ja4gd2fc14b4"),
    os.environ.get("DEAPI_VIDEO_KEY_2", "16780|9zdlANbmyo2V9F7R8XF5Eiau9rtdvtIQT3Yi1tcE4382c265"),
    os.environ.get("DEAPI_VIDEO_KEY_3", "13714|e1j05Nl7OuZAnBY59lCcRHO4jbN21OE12YGxi6Jze5f610c7"),
    os.environ.get("DEAPI_VIDEO_KEY_4", "13713|1zj50CKnjvZOHKk09UJWpsihXUie1qlanRQtrqrId828d27c"),
]
KEY_CURSOR = [0]
KEYS_LOCK = threading.Lock()

ROBLOX_API_KEY = "0yHiwJwAAUKKcwqk4y3AowUCo6XmiSHr6uSGyie+N1G1lSzbZXlKaGJHY2lPaUpTVXpJMU5pSXNJbXRwWkNJNkluTnBaeTB5TURJeExUQTNMVEV6VkRFNE9qVXhPalE1V2lJc0luUjVjQ0k2SWtwWFZDSjkuZXlKaGRXUWlPaUpTYjJKc2IzaEpiblJsY201aGJDSXNJbWx6Y3lJNklrTnNiM1ZrUVhWMGFHVnVkR2xqWVhScGIyNVRaWEoyYVdObElpd2lZbUZ6WlVGd2FVdGxlU0k2SWpCNVNHbDNTbmRCUVZWTFMyTjNjV3MwZVROQmIzZFZRMjgyV0cxcFUwaHlOblZUUjNscFpTdE9NVWN4YkZONllpSXNJbTkzYm1WeVNXUWlPaUl4TURReE56QTJOVEl4TXlJc0ltVjRjQ0k2TVRjNE56RTFNakl4TUN3aWFXRjBJam94TnpnM01UUTROakV3TENKdVltWWlPakUzT0RjeE5EZzJNVEI5Lm5CSmlJNWhDSUc1RDJpZzVheUFkQzR5NFdHR3l1a1hfOVV0dDJQamc0Sl8xQmF5ODdObjJvZjRLWTgyY3hFX1dURi1HSllKZThaSFI4M2ZYVl9GLXQ0QmtxdXU1T09LZmlJaUVVOEV6NWUwSUlRc1V0amtQUm15LVdLTE5yYlozMnliNzlEQ3NCZ0l3MWdDSTBrQTJleERjbHFUaEx6aTd4STNHcWd0aERIajdydWlISm5jS0pTaDBCUVQ4RVZmWlV2ZmRiTzhNWUpBOFdQOVRUVXhUY29aQkFNSGRsZFVkajBsc1VMbXVGOTFBOVpCRkhaRjhQSjQ3NjhZREJidEZBRS14dnBuZkdmSUtuMjh2Ykp4ZExkT3hXRExMa1N1RkdxWXhEa3QxeU5YYXptRGRJY3lEOEx2ZWVZUjVyMmNQSzRCYm1ZQWxjV0N3MjY0QzV5M0JBQQ=="
ROBLOX_OWNER_ID = "10417065213"
ROBLOX_ASSETS_URL = "https://apis.roblox.com/assets/v1/assets"
ROBLOX_OPERATIONS_URL = "https://apis.roblox.com/assets/v1/operations"

MODEL = "Ltxv_13B_0_9_8_Distilled_FP8"
FRAMES = 70
FPS = 30
WIDTH = 768
HEIGHT = 512

GRID_COLS = 4
GRID_ROWS = 5
CELL_W = 240
CELL_H = 160
PER_SHEET = GRID_COLS * GRID_ROWS
SHEET_COUNT = int(math.ceil(FRAMES / PER_SHEET))

SHEET_CACHE = {}
SHEET_CACHE_LOCK = threading.Lock()

JOBS = {}
JOBS_LOCK = threading.Lock()
QUEUE = []
QUEUE_LOCK = threading.Lock()
WORKER_ALIVE = True
INTER_JOB_DELAY = 3


def cleanup_jobs():
    now = time.time()
    with JOBS_LOCK:
        for key in list(JOBS.keys()):
            st = JOBS[key]
            if st.get("status") in ("done", "error") and now - st.get("_ts", 0) > 1800:
                del JOBS[key]


@app.get("/")
def home():
    return {"status": "Render Roblox Video API Aktif!"}


def _rate_limited(resp):
    if resp is None:
        return False
    if resp.status_code == 429:
        return True
    try:
        text = (resp.text or "").lower()
    except Exception:
        return False
    return ("too many" in text) or ("rate limit" in text) or ("attempt" in text)


def _key_error_kind(resp):
    if resp is None:
        return "none"
    if resp.status_code == 429:
        return "rate"
    if resp.status_code in (401, 403):
        return "auth"
    try:
        t = (resp.text or "").lower()
    except Exception:
        return "none"
    if "balance" in t or "credit" in t or "insufficient" in t:
        return "balance"
    if "too many" in t or "rate limit" in t or "attempt" in t:
        return "rate"
    if "invalid" in t or "unauthorized" in t or "forbidden" in t:
        return "auth"
    return "none"


def _next_key_index():
    with KEYS_LOCK:
        idx = KEY_CURSOR[0] % len(VIDEO_KEYS)
        KEY_CURSOR[0] = (idx + 1) % len(VIDEO_KEYS)
        return idx


def deapi_generate_video(prompt):
    n = len(VIDEO_KEYS)
    start = _next_key_index()
    request_id = None
    used_key = None
    last_error = "deapi request failed"
    for attempt in range(n * 3):
        idx = (start + attempt) % n
        key = VIDEO_KEYS[idx]
        if not key:
            continue
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
        try:
            r = requests.post(
                DEAPI_GENERATE_URL,
                headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                json=body,
                timeout=60,
            )
        except Exception as exc:
            last_error = "deapi request failed: " + str(exc)[:120]
            time.sleep(3)
            continue
        if r.status_code in (200, 201):
            data = r.json().get("data", r.json())
            request_id = data.get("request_id") or data.get("requestId") or data.get("id")
            if request_id:
                used_key = key
                break
            raise Exception("deapi returned no request id")
        last_error = "deapi request failed: " + r.text[:200]
        kind = _key_error_kind(r)
        if kind in ("balance", "auth"):
            time.sleep(1)
        elif kind == "rate":
            time.sleep(5 + attempt * 2)
        else:
            time.sleep(3)
    if not request_id or not used_key:
        raise Exception(last_error)
    rate_waits = 0
    for _ in range(120):
        time.sleep(3)
        p = requests.get(
            DEAPI_JOB_URL + "/" + request_id,
            headers={"Authorization": "Bearer " + used_key},
            timeout=30,
        )
        if p.status_code != 200:
            kind = _key_error_kind(p)
            if kind == "rate":
                rate_waits += 1
                if rate_waits > 24:
                    raise Exception("deapi rate limited while polling")
                time.sleep(15)
            elif kind in ("auth", "balance"):
                raise Exception("deapi key invalidated during polling")
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
    pil_frame.save(buf, format="JPEG", quality=97)
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
    for _ in range(40):
        time.sleep(0.5)
        rr = requests.get(
            ROBLOX_OPERATIONS_URL + "/" + op_id,
            headers={"x-api-key": ROBLOX_API_KEY},
            timeout=20,
        )
        if rr.status_code == 200:
            j = rr.json()
            if j.get("done"):
                asset_id = (j.get("response") or {}).get("assetId")
                if asset_id:
                    return str(asset_id)
                raise Exception("upload done without assetId")
            if j.get("error"):
                raise Exception("upload error: " + str(j.get("error"))[:120])
        elif rr.status_code in (401, 403):
            raise Exception("roblox key rejected (HTTP %d)" % rr.status_code)
    raise Exception("upload timeout")


def refresh_positions():
    with QUEUE_LOCK:
        order = list(QUEUE)
    with JOBS_LOCK:
        for i, jid in enumerate(order):
            job = JOBS.get(jid)
            if job:
                job["position"] = i


def worker():
    while WORKER_ALIVE:
        jid = None
        with QUEUE_LOCK:
            if QUEUE:
                jid = QUEUE.pop(0)
        if not jid:
            time.sleep(1)
            continue
        with JOBS_LOCK:
            job = JOBS.get(jid)
            if not job:
                refresh_positions()
                continue
            job["status"] = "processing"
            job["position"] = 0
        refresh_positions()
        try:
            mp4 = deapi_generate_video(job["prompt"])
            ent = get_video_cache(mp4)
            total = len(ent["indices"])
            sheets = int(math.ceil(total / PER_SHEET)) if PER_SHEET else 1
            with JOBS_LOCK:
                job.update({
                    "status": "done",
                    "mp4": mp4,
                    "frames": total,
                    "sheets": sheets,
                    "cols": GRID_COLS,
                    "rows": GRID_ROWS,
                    "cellW": CELL_W,
                    "cellH": CELL_H,
                    "_ts": time.time(),
                })
        except Exception as exc:
            with JOBS_LOCK:
                job["status"] = "error"
                job["error"] = str(exc)[:400]
                job["_ts"] = time.time()
        refresh_positions()
        time.sleep(INTER_JOB_DELAY)


def sample_indices(total, frames):
    if total <= frames:
        return list(range(total))
    out = []
    for i in range(frames):
        out.append(int(i * (total - 1) / max(frames - 1, 1)))
    return out


def get_video_cache(video_url):
    key = hashlib.md5(video_url.encode()).hexdigest()
    with SHEET_CACHE_LOCK:
        ent = SHEET_CACHE.get(key)
        if ent and os.path.exists(ent["path"]) and time.time() - ent["ts"] < 900:
            return ent
    r = requests.get(video_url, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    tmp_path = "/tmp/" + key + ".mp4"
    with open(tmp_path, "wb") as f:
        f.write(r.content)
    reader = imageio.get_reader(tmp_path)
    try:
        total = reader.count_frames()
    finally:
        try:
            reader.close()
        except Exception:
            pass
    indices = sample_indices(total, FRAMES)
    ent = {"path": tmp_path, "indices": indices, "ts": time.time()}
    with SHEET_CACHE_LOCK:
        SHEET_CACHE[key] = ent
    return ent


def split_video_to_grid(video_url, sheet=1):
    ent = get_video_cache(video_url)
    reader = imageio.get_reader(ent["path"])
    sheet_img = Image.new("RGB", (GRID_COLS * CELL_W, GRID_ROWS * CELL_H), (0, 0, 0))
    start = (sheet - 1) * PER_SHEET
    for k in range(PER_SHEET):
        idx = start + k
        if idx >= len(ent["indices"]):
            break
        frame = reader.get_data(ent["indices"][idx])
        im = Image.fromarray(frame).convert("RGB").resize((CELL_W, CELL_H), Image.Resampling.LANCZOS)
        r_, c_ = divmod(k, GRID_COLS)
        sheet_img.paste(im, (c_ * CELL_W, r_ * CELL_H))
    try:
        reader.close()
    except Exception:
        pass
    buf = io.BytesIO()
    sheet_img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


@app.get("/convert")
def convert(video_url: str = "", sheet: int = 1):
    if not video_url:
        return JSONResponse({"error": "video_url required"}, status_code=400)
    if sheet < 1:
        sheet = 1
    try:
        ent = get_video_cache(video_url)
        data = split_video_to_grid(video_url, sheet)
    except Exception as exc:
        return JSONResponse({"error": str(exc)[:200]}, status_code=400)
    from fastapi.responses import Response

    total = len(ent["indices"])
    sheets = int(math.ceil(total / PER_SHEET)) if PER_SHEET else 1
    return Response(content=data, media_type="image/jpeg", headers={
        "X-Cols": str(GRID_COLS),
        "X-Rows": str(GRID_ROWS),
        "X-CellW": str(CELL_W),
        "X-CellH": str(CELL_H),
        "X-Frames": str(total),
        "X-Sheets": str(sheets),
        "X-Sheet": str(sheet),
    })


@app.get("/generate")
def generate(prompt: str = ""):
    cleanup_jobs()
    if not prompt or not prompt.strip():
        return JSONResponse({"error": "prompt required"}, status_code=400)
    job = uuid.uuid4().hex
    with JOBS_LOCK:
        JOBS[job] = {"status": "queued", "prompt": prompt, "position": 0, "_ts": time.time()}
    with QUEUE_LOCK:
        QUEUE.append(job)
        position = len(QUEUE) - 1
    refresh_positions()
    return {"job": job, "position": position}


@app.get("/job")
def job_status(job: str = ""):
    cleanup_jobs()
    if not job:
        return JSONResponse({"error": "job required"}, status_code=400)
    st = JOBS.get(job)
    if not st:
        return JSONResponse({"error": "not found"}, status_code=404)
    status = st.get("status")
    if status == "done":
        fr = st.get("frames")
        if isinstance(fr, list) and fr:
            return {"status": "done", "frames": fr}
        return {
            "status": "done",
            "mp4": st.get("mp4"),
            "frames": [],
            "sheets": st.get("sheets", 0),
            "cols": st.get("cols", GRID_COLS),
            "rows": st.get("rows", GRID_ROWS),
            "cellW": st.get("cellW", CELL_W),
            "cellH": st.get("cellH", CELL_H),
        }
    if status == "error":
        return {"status": "error", "error": st.get("error", "failed")}
    if status == "queued":
        return {"status": "queued", "position": st.get("position", 0)}
    return {"status": "processing", "done": st.get("done", 0), "total": st.get("total", FRAMES)}


threading.Thread(target=worker, daemon=True).start()


def run_render_job(job, video_url):
    start = time.time()
    try:
        with JOBS_LOCK:
            JOBS[job] = {"status": "processing", "done": 0, "total": FRAMES, "_ts": time.time()}
        r = requests.get(video_url, timeout=120, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        if time.time() - start > 400:
            raise Exception("download too slow")
        tmp_path = "/tmp/" + job + ".mp4"
        with open(tmp_path, "wb") as f:
            f.write(r.content)
        reader = imageio.get_reader(tmp_path)
        try:
            total = reader.count_frames()
        finally:
            pass
        indices = sample_indices(total, FRAMES)
        frames = []
        for k, idx in enumerate(indices):
            if time.time() - start > 420:
                raise Exception("render job timeout")
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


@app.get("/render")
def render_video(video_url: str = ""):
    cleanup_jobs()
    if not video_url:
        return JSONResponse({"error": "video_url required"}, status_code=400)
    job = uuid.uuid4().hex
    threading.Thread(target=run_render_job, args=(job, video_url), daemon=True).start()
    return {"job": job}


