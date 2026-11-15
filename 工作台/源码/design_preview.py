"""Render generated local SVG with a compatible local renderer; never fake effects.

Only self-contained generated SVG is accepted. An isolated browser profile stays
in the work drive; it does not use the user's browser session or remote service.
"""
from pathlib import Path
import os
import re
import subprocess
import tempfile
from core import GateError


def browser_executable():
    roots=[Path(os.environ.get('PROGRAMFILES','C:/Program Files')),Path(os.environ.get('PROGRAMFILES(X86)','C:/Program Files (x86)'))]
    for root in roots:
        for suffix in ('Microsoft/Edge/Application/msedge.exe','Google/Chrome/Application/chrome.exe'):
            candidate=root/suffix
            if candidate.is_file():return candidate
    return None


def raster_svg(svg_text,png,width,height):
    png=Path(png).resolve()
    # No client data or external URLs enter a renderer. Generated geometry carries
    # only local definitions and embedded pixel assets.
    for value in re.findall(r'(?:href|xlink:href)\s*=\s*[\"\']([^\"\']+)',svg_text):
        if not (value.startswith('#') or value.startswith('data:image/')):raise GateError('PREVIEW_EXTERNAL_REFERENCE_FORBIDDEN')
    if re.search(r'<(?:script|foreignObject|iframe)\b|\bon\w+\s*=|@import|url\([\"\']?(?:https?:|file:)',svg_text,re.I):
        raise GateError('PREVIEW_ACTIVE_CONTENT_FORBIDDEN')
    renderer=browser_executable()
    if renderer:
        with tempfile.TemporaryDirectory(prefix='图面预览_',dir=png.parent,ignore_cleanup_errors=True) as directory:
            base=Path(directory);page=base/'预览.html'
            # CSS dimensions make the requested pixel canvas independent of the
            # SVG's correct publication-sized pt dimensions.
            page.write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'"><style>html,body{margin:0;background:white;overflow:hidden}svg{display:block;width:'+str(width)+'px;height:'+str(height)+'px}</style>'+svg_text,encoding='utf-8')
            cmd=[str(renderer),'--headless=new','--disable-gpu','--no-first-run','--disable-background-networking','--disable-extensions','--disable-sync','--metrics-recording-only','--hide-scrollbars','--force-device-scale-factor=1',
                 '--user-data-dir='+str(base/'隔离浏览器'),f'--window-size={int(width)},{int(height)}','--screenshot='+str(png),page.as_uri()]
            result=subprocess.run(cmd,capture_output=True,timeout=40,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            if result.returncode!=0 or not png.is_file():raise GateError('LOCAL_SVG_PREVIEW_RENDER_FAILED')
            return dict(status='RENDERED',renderer=renderer.name,gradient_support=True,source='CURRENT_GENERATED_SVG',visual_review='PENDING')
    if '<linearGradient' in svg_text or '<radialGradient' in svg_text or 'stroke-dasharray' in svg_text:
        return dict(status='COMPATIBLE_RENDERER_REQUIRED',renderer=None,gradient_support=False,source='CURRENT_GENERATED_SVG',
                    message='保留可编辑SVG。当前轻量预览器不支持所需渐变或虚线，未生成可能失真的PNG；请用现有浏览器或原生软件导出核验。')
    try:
        import fitz
    except ImportError:
        return dict(status='COMPATIBLE_RENDERER_REQUIRED',renderer=None,source='CURRENT_GENERATED_SVG')
    with fitz.open(stream=svg_text.encode(),filetype='svg') as doc:pdf=doc.convert_to_pdf()
    with fitz.open(stream=pdf,filetype='pdf') as doc:
        pix=doc[0].get_pixmap(matrix=fitz.Matrix(width/doc[0].rect.width,height/doc[0].rect.height),alpha=False);pix.save(png)
    return dict(status='RENDERED',renderer='PyMuPDF_SIMPLE_ONLY',gradient_support=False,source='CURRENT_GENERATED_SVG',visual_review='PENDING')
