# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('web', 'web'), ('db', 'db'), ('scraper', 'scraper'), ('scheduler', 'scheduler'), ('config_paths.py', '.'), ('vendor_ffmpeg', 'ffmpeg')],
    hiddenimports=['webview', 'webview.platforms.edgechromium', 'clr', 'pythonnet', 'fastapi', 'uvicorn', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto', 'sqlalchemy', 'yt_dlp', 'tubescrape', 'nicovideo_api_client', 'config_paths', 'version', 'web.update', 'scraper.runner', 'scraper.youtube', 'scraper.niconico', 'scraper.scorer', 'scraper.dedup', 'scraper.channels'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

# We ship ffmpeg/ffprobe + their shared DLLs once under datas as ffmpeg/.
# PyInstaller's binary analysis of those exes ALSO pulls the av*/sw* DLLs into
# the dist *root* — drop only those root-level duplicates (~165MB), keeping the
# copies under ffmpeg/ that our app actually points at.
import os as _os
_FF_PREFIXES = ('avcodec', 'avdevice', 'avfilter', 'avformat', 'avutil',
                'swresample', 'swscale', 'postproc')
a.binaries = [b for b in a.binaries
              if not (_os.path.dirname(b[0]) == ''
                      and _os.path.basename(b[0]).lower().startswith(_FF_PREFIXES))]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='HeatMapAsia',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='HeatMapAsia',
)
