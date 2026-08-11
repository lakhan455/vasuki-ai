from __future__ import annotations
import base64, io, json, uuid
from typing import Any
import httpx
from PIL import Image, ImageFilter

def consistency_prompt(prompt: str, *, identity: str="", style: str="", pose: str="", composition: str="", reference_strength: float=0.75)->str:
    controls=[]
    if identity.strip(): controls.append(f"Keep identity/brand features consistent with this locked description: {identity.strip()}")
    if style.strip(): controls.append(f"Style reference: {style.strip()}")
    if pose.strip(): controls.append(f"Pose: {pose.strip()}")
    if composition.strip(): controls.append(f"Composition: {composition.strip()}")
    controls.append(f"Reference strength target: {max(0.0,min(1.0,reference_strength)):.2f}")
    return prompt.strip()+"\n\nCONSISTENCY CONTROLS:\n- "+"\n- ".join(controls)

def apply_mask_composite(original_bytes: bytes, edited_bytes: bytes, mask_bytes: bytes)->bytes:
    original=Image.open(io.BytesIO(original_bytes)).convert("RGBA")
    edited=Image.open(io.BytesIO(edited_bytes)).convert("RGBA").resize(original.size,Image.Resampling.LANCZOS)
    mask=Image.open(io.BytesIO(mask_bytes)).convert("L").resize(original.size,Image.Resampling.LANCZOS)
    mask=mask.filter(ImageFilter.GaussianBlur(radius=1.2))
    out=Image.composite(edited,original,mask)
    buf=io.BytesIO(); out.save(buf,format="PNG",optimize=True)
    return buf.getvalue()

async def generate_video(settings, *, prompt: str, image_url: str|None=None, duration_seconds: int=6, aspect_ratio: str="16:9", camera: str="cinematic")->dict[str,Any]:
    base=str(getattr(settings,"v11_video_api_base_url","") or "").rstrip("/")
    key=str(getattr(settings,"v11_video_api_key","") or "").strip()
    model=str(getattr(settings,"v11_video_model","") or "auto").strip()
    if not base or not key:
        raise RuntimeError("Video provider is not configured. Set V11_VIDEO_API_BASE_URL and V11_VIDEO_API_KEY.")
    payload={"model":model,"prompt":prompt,"duration":max(1,min(60,duration_seconds)),"aspect_ratio":aspect_ratio,"camera":camera}
    if image_url: payload["image_url"]=image_url
    async with httpx.AsyncClient(timeout=180.0) as client:
        r=await client.post(f"{base}/v1/videos/generations",headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json=payload)
    if r.status_code>=400: raise RuntimeError(f"Video provider failed ({r.status_code}): {r.text[:700]}")
    data=r.json()
    return {"provider":"openai-compatible-video","model":model,"result":data}

async def server_tts(settings, *, text: str, voice: str="alloy", model: str|None=None)->bytes:
    base=str(getattr(settings,"v11_tts_api_base_url","") or "").rstrip("/")
    key=str(getattr(settings,"v11_tts_api_key","") or "").strip()
    default_model=str(getattr(settings,"v11_tts_model","") or "tts-1").strip()
    if not base or not key: raise RuntimeError("Server TTS is not configured.")
    async with httpx.AsyncClient(timeout=90.0) as client:
        r=await client.post(f"{base}/v1/audio/speech",headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json={"model":model or default_model,"input":text[:12000],"voice":voice})
    if r.status_code>=400: raise RuntimeError(f"TTS provider failed ({r.status_code}): {r.text[:500]}")
    return r.content

async def server_stt(settings, *, audio: bytes, filename: str="audio.webm", model: str|None=None)->dict[str,Any]:
    base=str(getattr(settings,"v11_stt_api_base_url","") or "").rstrip("/")
    key=str(getattr(settings,"v11_stt_api_key","") or "").strip()
    default_model=str(getattr(settings,"v11_stt_model","") or "whisper-1").strip()
    if not base or not key: raise RuntimeError("Server STT is not configured.")
    async with httpx.AsyncClient(timeout=120.0) as client:
        r=await client.post(f"{base}/v1/audio/transcriptions",headers={"Authorization":f"Bearer {key}"},data={"model":model or default_model},files={"file":(filename,audio,"application/octet-stream")})
    if r.status_code>=400: raise RuntimeError(f"STT provider failed ({r.status_code}): {r.text[:500]}")
    return r.json()

def multimodal_contract()->dict[str,Any]:
    return {"inputs":["text","image","pdf","docx","txt","markdown","audio"],"joint_reasoning":True,"implementation":"V11 request endpoint normalizes text plus extracted file/audio context before one final model call.","max_files":8}
