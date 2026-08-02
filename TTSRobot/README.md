# TTS Robot (Windows)

Discord **robot voice** engine packaged like Nova’s Windows app:

- `TTSRobot.exe` — launcher
- Bundled embeddable Python + `discord.py` / `edge-tts` / `PyNaCl`
- Bundled `ffmpeg` for robot voice FX
- Browser control panel (`tts_app.py`) to paste a token, start/stop, preview voices

Ready zip: [`../releases/TTSRobot-Windows.zip`](../releases/TTSRobot-Windows.zip)

## Rebuild

```bash
./TTSRobot/desktop/build_windows.sh
```

Needs `x86_64-w64-mingw32-gcc`, `wget`, `unzip`, `zip`, and network access.

## Source

| File | Role |
|------|------|
| [`desktop/tts_app.py`](desktop/tts_app.py) | Windows control panel |
| [`desktop/launcher.c`](desktop/launcher.c) | `TTSRobot.exe` |
| [`../bot_tts.py`](../bot_tts.py) | Discord TTS engine (also runnable alone) |
