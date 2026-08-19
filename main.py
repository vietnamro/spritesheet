from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
import imageio
from PIL import Image
import requests
import os

app = FastAPI()

@app.get("/")
def home():
    return {"status": "Render Roblox API Aktif!"}

@app.get("/convert")
def convert_video(video_url: str):
    video_path = "input.mp4"
    output_image = "spritesheet.jpg"
    
    if os.path.exists(video_path): os.remove(video_path)
    if os.path.exists(output_image): os.remove(output_image)
    
    try:
        response = requests.get(video_url, stream=True, timeout=10)
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Video indirilemedi.")
            
        with open(video_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk: f.write(chunk)
        
        reader = imageio.get_reader(video_path, 'ffmpeg')
        frames = []
        for i, frame in enumerate(reader):
            if i >= 64: break 
            img = Image.fromarray(frame).resize((128, 128))
            frames.append(img)
        reader.close()
        
        if not frames:
            raise HTTPException(status_code=400, detail="Kare bulunamadı.")
            
        spritesheet = Image.new("RGB", (1024, 1024), (0, 0, 0))
        for index, frame in enumerate(frames):
            x = (index % 8) * 128
            y = (index // 8) * 128
            spritesheet.paste(frame, (x, y))
            
        spritesheet.save(output_image, "JPEG", quality=85)
        return FileResponse(output_image, media_type="image/jpeg")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
