"""
Локальный STT-сервис (Speech-to-Text) на базе faster-whisper.
Запускается на Mac, принимает аудиофайлы от Telegram-ботов и возвращает текст.

Порт:  8766 (или STT_PORT в окружении)
Токен: STT_TOKEN в окружении (секрет, тот же что в Railway Variables)
Модель: STT_MODEL в окружении (по умолчанию "small")
"""
import asyncio
import os
import tempfile
import traceback
from pathlib import Path

import uvicorn
from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from faster_whisper import WhisperModel

# ── Конфигурация ───────────────────────────────────────────────────────────────
STT_TOKEN  = os.environ.get("STT_TOKEN", "")
STT_MODEL  = os.environ.get("STT_MODEL", "small")
STT_PORT   = int(os.environ.get("STT_PORT", "8766"))
MAX_DURATION_SEC = 180  # аудио длиннее этого не принимаем

# ── Модель грузится один раз при старте ────────────────────────────────────────
print(f"[stt] Загружаю модель '{STT_MODEL}' (может занять минуту при первом запуске)…")
model = WhisperModel(STT_MODEL, compute_type="int8", device="cpu")
print(f"[stt] Модель '{STT_MODEL}' загружена, сервис готов к работе.")

# ── Lock: обрабатываем по одному запросу за раз ────────────────────────────────
_lock = asyncio.Lock()

app = FastAPI(title="Juma STT Service")


def _check_token(x_token: str):
    if not STT_TOKEN:
        return  # токен не задан — пропускаем всех (только для локальной отладки)
    if x_token != STT_TOKEN:
        raise HTTPException(status_code=401, detail="Неверный токен")


@app.get("/health")
async def health():
    return {"ok": True, "model": STT_MODEL}


@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    x_token: str = Header(default=""),
):
    _check_token(x_token)

    audio_bytes = await file.read()

    # Ограничение по размеру: ~1 МБ/мин для OGG Opus → 180 сек ≈ 3 МБ
    if len(audio_bytes) > MAX_DURATION_SEC * 16_000:
        raise HTTPException(status_code=413, detail=f"Аудио слишком длинное (лимит {MAX_DURATION_SEC} сек)")

    async with _lock:
        tmp = None
        try:
            # Сохраняем во временный файл (ffmpeg читает по пути, не из буфера)
            suffix = Path(file.filename or "audio.ogg").suffix or ".ogg"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
                f.write(audio_bytes)
                tmp = f.name

            segments, info = model.transcribe(
                tmp,
                language="ru",
                beam_size=5,
                vad_filter=True,          # фильтр тишины — быстрее и точнее
                vad_parameters={"min_silence_duration_ms": 500},
            )
            text = " ".join(s.text.strip() for s in segments).strip()
            print(f"[stt] распознано ({info.duration:.1f}s): {text[:120]!r}")
            return {"ok": True, "text": text}

        except Exception as e:
            traceback.print_exc()
            return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})
        finally:
            if tmp:
                Path(tmp).unlink(missing_ok=True)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=STT_PORT)
