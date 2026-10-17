#!/usr/bin/env python
"""Small, local-only bridge for Adobe Illustrator on Windows.

The bridge deliberately supports a narrow safe surface: detect, inspect, and
create a brand-new demonstration document under the configured D: workspace.
It never opens, overwrites, or changes an existing .ai file by default.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pythoncom
import win32com.client


WORKSPACE = Path(__file__).resolve().parents[1]
OUTPUT_DIR = WORKSPACE / "outputs"


def emit(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def illustrator():
    pythoncom.CoInitialize()
    try:
        return win32com.client.Dispatch("Illustrator.Application")
    except Exception as exc:
        raise RuntimeError(f"无法连接 Adobe Illustrator COM：{exc}") from exc


def detect() -> dict:
    app = illustrator()
    return {
        "connected": True,
        "version": str(app.Version),
        "path": str(app.Path),
        "automation": "Windows COM",
        "write_action": False,
    }


def inspect() -> dict:
    app = illustrator()
    if app.Documents.Count == 0:
        return {"connected": True, "open_documents": 0, "active_document": None}
    doc = app.ActiveDocument
    return {
        "connected": True,
        "open_documents": int(app.Documents.Count),
        "active_document": {
            "name": str(doc.Name),
            "layers": int(doc.Layers.Count),
            "artboards": int(doc.Artboards.Count),
            "text_frames": int(doc.TextFrames.Count),
            "path_items": int(doc.PathItems.Count),
        },
        "write_action": False,
    }


def _js_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace('"', '\\"')


def create_demo(name: str, pause_ms: int) -> dict:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ai_path = OUTPUT_DIR / f"{name}.ai"
    svg_path = OUTPUT_DIR / f"{name}.svg"
    png_path = OUTPUT_DIR / f"{name}.png"
    existing = [str(p) for p in (ai_path, svg_path, png_path) if p.exists()]
    if existing:
        raise FileExistsError(
            "为避免覆盖，以下输出已存在：" + "；".join(existing) + "。请换一个名称。"
        )

    app = illustrator()
    pause_seconds = max(pause_ms, 0) / 1000
    script = f'''#target illustrator
var doc = app.documents.add(DocumentColorSpace.RGB, 1600, 900);
doc.name = "{name}";
doc.artboards[0].artboardRect = [0, 900, 1600, 0];

function rgb(r,g,b) {{ var c=new RGBColor(); c.red=r; c.green=g; c.blue=b; return c; }}
function rect(layer,x,y,w,h,fill,stroke,weight,radius) {{
  var item = radius ? layer.pathItems.roundedRectangle(900-y, x, w, h, radius, radius) : layer.pathItems.rectangle(900-y, x, w, h);
  item.filled=true; item.fillColor=fill; item.stroked=true; item.strokeColor=stroke; item.strokeWidth=weight; return item;
}}
function label(layer,content,x,y,size,color) {{
  var t=layer.textFrames.add(); t.contents=content; t.left=x; t.top=900-y;
  t.textRange.characterAttributes.size=size; t.textRange.characterAttributes.fillColor=color;
  t.textRange.characterAttributes.textFont=app.textFonts.getByName("ArialMT"); return t;
}}
function line(layer,x1,y1,x2,y2,color,weight) {{
  var p=layer.pathItems.add(); p.setEntirePath([[x1,900-y1],[x2,900-y2]]); p.stroked=true; p.strokeColor=color; p.strokeWidth=weight; p.filled=false; return p;
}}

var dark=rgb(31,45,61), teal=rgb(38,128,126), mint=rgb(215,241,232), blue=rgb(69,127,191), light=rgb(247,250,252), white=rgb(255,255,255);
var background=doc.layers.add(); background.name="01 Background";
rect(background,0,0,1600,900,white,white,0,0);
var structure=doc.layers.add(); structure.name="02 Structure";
rect(structure,85,115,1430,650,light,dark,2,28);
app.redraw();
var process=doc.layers.add(); process.name="03 Process";
rect(process,150,315,285,180,mint,teal,3,22);
rect(process,655,315,285,180,mint,teal,3,22);
rect(process,1160,315,285,180,mint,teal,3,22);
line(process,435,405,655,405,dark,4); line(process,940,405,1160,405,dark,4);
var a1=process.pathItems.polygon(655,495,18,3); a1.rotate(90); a1.fillColor=dark; a1.stroked=false;
var a2=process.pathItems.polygon(1160,495,18,3); a2.rotate(90); a2.fillColor=dark; a2.stroked=false;
app.redraw();
var icons=doc.layers.add(); icons.name="04 Icons";
var c1=icons.pathItems.ellipse(450,210,92,92); c1.fillColor=blue; c1.filled=true; c1.stroked=false;
var c2=icons.pathItems.ellipse(955,210,92,92); c2.fillColor=teal; c2.filled=true; c2.stroked=false;
var c3=icons.pathItems.ellipse(1460,210,92,92); c3.fillColor=dark; c3.filled=true; c3.stroked=false;
app.redraw();
var text=doc.layers.add(); text.name="05 Labels";
label(text,"Codex × Illustrator",150,205,42,dark);
label(text,"Input",255,395,30,dark); label(text,"Vector build",720,395,30,dark); label(text,"Export",1250,395,30,dark);
label(text,"reference / data",205,445,20,dark); label(text,"native AI objects",690,445,20,dark); label(text,"AI · SVG · PNG",1220,445,20,dark);
label(text,"Sequential native-object drawing test",150,685,26,teal);
app.redraw();
var aiFile=new File("{_js_path(ai_path)}"); var aiOptions=new IllustratorSaveOptions(); doc.saveAs(aiFile,aiOptions);
var svgFile=new File("{_js_path(svg_path)}"); var svgOptions=new ExportOptionsSVG(); doc.exportFile(svgFile,ExportType.SVG,svgOptions);
var pngFile=new File("{_js_path(png_path)}"); var pngOptions=new ExportOptionsPNG24(); pngOptions.artBoardClipping=true; pngOptions.transparency=false; pngOptions.horizontalScale=100; pngOptions.verticalScale=100; doc.exportFile(pngFile,ExportType.PNG24,pngOptions);
'''
    app.DoJavaScript(script)
    if pause_seconds:
        time.sleep(pause_seconds)
    return {
        "created": True,
        "document": str(ai_path),
        "svg": str(svg_path),
        "png": str(png_path),
        "write_action": True,
        "overwrite": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Adobe Illustrator COM bridge")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("detect")
    sub.add_parser("inspect")
    demo = sub.add_parser("create-demo")
    demo.add_argument("--name", default="codex_illustrator_demo")
    demo.add_argument("--pause-ms", type=int, default=0)
    args = parser.parse_args()
    try:
        if args.command == "detect":
            emit(detect())
        elif args.command == "inspect":
            emit(inspect())
        else:
            emit(create_demo(args.name, args.pause_ms))
        return 0
    except Exception as exc:
        emit({"ok": False, "error": str(exc), "command": args.command})
        return 1
    finally:
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    sys.exit(main())
