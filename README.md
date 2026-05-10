# PCM Player

Player de áudio portátil com suporte a PCM raw e detecção automática de formatos comuns.

## Formatos suportados

**Detecção automática (header):**
- WAV, FLAC, OGG/Vorbis, OPUS, AIFF, AU, MP3 (libsndfile ≥ 1.1)

**PCM raw (parâmetros configuráveis na UI):**
- 8-bit signed/unsigned
- 16-bit signed/unsigned (LE/BE)
- 24-bit signed (LE/BE)
- 32-bit signed (LE/BE)
- 32-bit float (LE/BE)
- 64-bit float (LE)
- 1 a 8 canais
- 8000 Hz a 192000 Hz
- Header skip (offset em bytes) ajustável

Extensões reconhecidas como raw PCM com defaults sensatos: `.pcm`, `.raw`, `.bin`, `.dat`, `.s8`, `.s16/le/be`, `.s24/le/be`, `.s32/le/be`, `.u8`, `.f32/le/be`, `.f64`.

## Atalhos

| Tecla | Ação |
|-------|------|
| **Space** | Play / Pause |
| **Esc** | Stop |
| **← →** | Avançar/voltar 5 s |
| **Shift + ← →** | Avançar/voltar 30 s |
| **Ctrl + ← →** | Faixa anterior / próxima |
| **↑ ↓** | Volume +/− 5 % |
| **Ctrl + O** | Abrir arquivo |

Drag & drop em qualquer lugar da janela adiciona à playlist. Auto-advance entre faixas.

## Build do `.exe` portátil (Windows)

**Pré-requisitos:** Python 3.10 ou superior instalado e disponível no `PATH`. Internet para o `pip install` (uma vez só).

```cmd
cd onde-você-extraiu-o-projeto
build_windows.bat
```

O script:
1. Cria um venv local em `.venv\`
2. Instala `PySide6`, `numpy`, `sounddevice`, `soundfile` e `pyinstaller`
3. Roda o PyInstaller com `--onefile --windowed`, agrupando as DLLs nativas (PortAudio + libsndfile)
4. Limpa pastas intermediárias

**Resultado:** `dist\PCMPlayer.exe` — um único arquivo portátil. Copie pra um pendrive, área de trabalho, ou qualquer lugar — sem instalação, sem dependências externas.

Tamanho esperado: ~80 MB (Qt + libsndfile + PortAudio embutidos).

## Build manual (Linux / macOS / debug)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python pcm_player.py
```

Para executável em Linux/macOS, mesma linha do `pyinstaller`:

```bash
pyinstaller --noconfirm --clean --onefile --windowed \
  --name PCMPlayer \
  --collect-binaries sounddevice \
  --collect-binaries soundfile \
  --collect-data soundfile \
  pcm_player.py
```

## Estrutura

```
pcmplayer/
├── pcm_player.py          # Aplicação principal (single-file)
├── requirements.txt       # Dependências
├── build_windows.bat      # Build script para Windows
└── README.md              # Este arquivo
```

## Notas técnicas

- Engine de áudio usa `sounddevice.OutputStream` com callback (baixa latência, thread separada do GUI).
- Decodificação delegada ao **libsndfile** via `soundfile`. Para PCM raw, o arquivo é lido em buffer e passado ao `sf.read(format='RAW', ...)` com os parâmetros da UI — mesmo motor que o ffmpeg/audacity usam pra esse tipo de payload.
- Decoder manual `_decode_u16` cobre o único caso que o libsndfile não suporta nativamente (PCM unsigned 16-bit).
- Waveform é pré-computada em thread separada após o load (sem travar UI mesmo em arquivos longos).
- Seek é "seamless": fecha o stream, ajusta o cursor, reabre — imperceptível em hardware moderno.
