"""Shared optional native finish layer, kept separate from upstream backend measurements."""
from pathlib import Path
import json,time,shutil
from datetime import datetime,timezone
import pythoncom,win32com.client,win32gui
from PIL import ImageGrab
from live_studio import PROJECT
PROFILES={
 'Academic Clean':dict(bg='FFFFFF',ink='203E3A',accent='287B65',muted='566961',surface='E7F0EC',line='BCCFC7'),
 'Modern Professional':dict(bg='FAFBFD',ink='18263C',accent='315FC3',muted='586579',surface='EAF0FB',line='C3CFDF'),
 'Dark Technical':dict(bg='132330',ink='F0F5F7',accent='54D2C2',muted='B3C6CD',surface='203A48',line='46626D')}
def color(h):return int(h[:2],16)+256*int(h[2:4],16)+65536*int(h[4:6],16)
def connect():
 pythoncom.CoInitialize()
 try:a=win32com.client.GetActiveObject('PowerPoint.Application')
 except Exception:a=win32com.client.Dispatch('PowerPoint.Application')
 a.Visible=True
 return a

def get_presentation(app,path):
 matches=[p for p in app.Presentations if str(p.FullName).lower()==str(Path(path)).lower()]
 if len(matches)>1:raise RuntimeError('Ambiguous duplicate full path; reconcile windows before writing')
 if matches:
  if matches[0].ReadOnly:raise RuntimeError('Target presentation is read-only')
  return matches[0]
 return app.Presentations.Open(str(Path(path)),False,False,True)

def children(shapes):
 for s in shapes:
  yield s
  if s.Type==6:
   yield from children(s.GroupItems)

def find(slide,name):
 for s in children(slide.Shapes):
  if s.Name==name:return s
 raise KeyError(name)

def bind_manifest(slide,objects):
 available=list(children(slide.Shapes));used=set();out={}
 for o in objects:
  if o['type'] in ['connector','group']:continue
  if 'bbox' not in o:continue
  match=None
  for s in available:
   if s.Id in used or s.Type==6 or s.Connector:continue
   try:
    if o['type']=='chart' and not s.HasChart:continue
    if o['type']=='table' and not s.HasTable:continue
    if o['type'] in ['text','shape'] and not s.HasTextFrame:continue
    if o['type']=='picture' and s.Type not in [13,28]:continue
    err=sum(abs(float(x)-y) for x,y in zip((s.Left,s.Top,s.Width,s.Height),o['bbox']))
    if match is None or err<match[0]:match=(err,s)
   except Exception:continue
  if not match or match[0]>100:raise ValueError(('cannot bind',o['id'],None if not match else match[0]))
  s=match[1];s.Name=o['id'];s.Tags.Add('STUDIO_ID',o['id']);used.add(s.Id);out[o['id']]=s
  if o['type']=='text':s.TextFrame.AutoSize=0;s.Left,s.Top,s.Width,s.Height=o['bbox']
 for o in objects:
  if o['type']!='connector':continue
  for s in available:
   if not s.Connector or s.Id in used:continue
   cf=s.ConnectorFormat
   if cf.BeginConnected and cf.EndConnected and cf.BeginConnectedShape.Name==o['begin'] and cf.EndConnectedShape.Name==o['end']:
    s.Name=o['id'];s.Tags.Add('STUDIO_ID',o['id']);used.add(s.Id);out[o['id']]=s;break
 return out

def style_chart(s,t):
 c=s.Chart;c.HasLegend=False;c.HasTitle=False
 c.ChartArea.Font.Name='Microsoft YaHei';c.ChartArea.Font.Size=15;c.ChartArea.Font.Color=color(t['ink'])
 c.ChartArea.Format.Fill.Visible=0;c.ChartArea.Format.Line.Visible=0
 c.PlotArea.Format.Fill.Visible=0;c.PlotArea.Format.Line.Visible=0
 for k in (1,2):
  ax=c.Axes(k,1);ax.TickLabels.Font.Name='Microsoft YaHei';ax.TickLabels.Font.Size=15;ax.TickLabels.Font.Color=color(t['muted'])
  ax.Format.Line.ForeColor.RGB=color(t['line']);ax.Format.Line.Weight=.75
  if k==2:
   ax.MinimumScale=0;ax.HasMajorGridlines=True;ax.MajorGridlines.Format.Line.ForeColor.RGB=color(t['line']);ax.MajorGridlines.Format.Line.Weight=.5
 for se in c.SeriesCollection():
  se.Format.Fill.Solid();se.Format.Fill.ForeColor.RGB=color(t['accent']);se.Format.Line.Visible=0
 try:c.ChartGroups(1).GapWidth=75
 except Exception:pass

def style_table(s,t):
 table=s.Table
 for r in range(1,table.Rows.Count+1):
  for col in range(1,table.Columns.Count+1):
   cell=table.Cell(r,col).Shape;cell.Fill.Solid();cell.Fill.ForeColor.RGB=color(t['ink'] if r==1 else t['surface'] if r%2==0 else t['bg'])
   tf=cell.TextFrame;tf.MarginLeft=8;tf.MarginRight=6;tf.MarginTop=4;tf.MarginBottom=4;tf.VerticalAnchor=3
   tr=tf.TextRange;tr.Font.Name='Microsoft YaHei';tr.Font.NameFarEast='Microsoft YaHei';tr.Font.Size=18
   tr.Font.Bold=-1 if r==1 else 0;tr.Font.Color.RGB=color(t['bg'] if r==1 else t['ink'])
   for border in range(1,5):
    line=table.Cell(r,col).Borders(border);line.ForeColor.RGB=color(t['bg']);line.Weight=1

def polish_slide(slide,profile='Academic Clean',objects=None):
 t=PROFILES[profile];slide.FollowMasterBackground=False;slide.Background.Fill.Solid();slide.Background.Fill.ForeColor.RGB=color(t['bg'])
 if objects:bind_manifest(slide,objects)
 for s in children(slide.Shapes):
  if s.Connector:
   s.Line.ForeColor.RGB=color(t['accent']);s.Line.Weight=2;s.Line.EndArrowheadStyle=3
   if 'feedback' in s.Name:s.Line.DashStyle=4
  if s.HasChart:style_chart(s,t)
  if s.HasTable:style_table(s,t)
  if s.HasTextFrame and s.TextFrame.HasText:
   s.TextFrame.TextRange.Font.Name='Microsoft YaHei';s.TextFrame.TextRange.Font.NameFarEast='Microsoft YaHei'
   s.TextFrame.MarginLeft=4;s.TextFrame.MarginRight=4;s.TextFrame.MarginTop=3;s.TextFrame.MarginBottom=3
   s.TextFrame.WordWrap=True;s.TextFrame.AutoSize=0
   if s.Type==1:s.TextFrame.VerticalAnchor=3
  if s.Name=='branchlabel':s.Left=500;s.Top=260;s.Width=170;s.Height=45
 return t

def screenshot(app,pres,path,topmost=True):
 pres.Windows(1).Activate();app.WindowState=3
 h=win32gui.FindWindow('PPTFrameClass',None)
 if not h:raise RuntimeError('No PowerPoint frame')
 title=win32gui.GetWindowText(h)
 if pres.Name not in title:raise RuntimeError(('wrong frame',title))
 win32gui.ShowWindow(h,9)
 win32gui.ShowWindow(h,3)
 if topmost:win32gui.SetWindowPos(h,-1,0,0,0,0,3|64)
 if win32gui.GetClientRect(h)[2]<400:raise RuntimeError('PowerPoint window is not capture-ready')
 time.sleep(.4)
 ImageGrab.grab(bbox=win32gui.GetWindowRect(h)).save(str(path))
 if topmost:win32gui.SetWindowPos(h,-2,0,0,0,0,3)
 return {'title':title,'hwnd':h,'rect':win32gui.GetWindowRect(h)}

def polish_file(source,target,renderdir,manifest,resume=False):
 source,target,renderdir=Path(source),Path(target),Path(renderdir)
 if target.exists() and not resume:raise FileExistsError(target)
 if not target.exists():shutil.copy2(source,target)
 a=connect();p=get_presentation(a,target);renderdir.mkdir(parents=True,exist_ok=True)
 log=PROJECT/'03_POC/logs/visual-repairs.jsonl'
 for i,s in enumerate(p.Slides,1):
  start=time.perf_counter();polish_slide(s,objects=manifest['slides'][i-1]['objects'])
  # Group the complete diagram; native child shapes/connectors remain editable.
  if i in [2,5]:
   names=[x.Name for x in s.Shapes if x.Type==1 or x.Connector]
   if len(names)>1:s.Shapes.Range(tuple(names)).Group().Name='workflow_group' if i==2 else 'mechanism_group'
  p.Save();s.Export(str(renderdir/f'slide-{i:02}.png'),'PNG',1600,900)
  with log.open('a',encoding='utf-8') as f:f.write(json.dumps(dict(timestamp=datetime.now(timezone.utc).isoformat(),session=str(target),slide=i,semantic_object_id='slide',operation='native_style_repair',parameters={'profile':'Academic Clean'},backend='studio-native-polish',success=True,duration=time.perf_counter()-start,error=None,repair_parent='visual-review-001'),ensure_ascii=False)+'\n')
 screenshot(a,p,renderdir/'powerpoint-window.png');p.Close()
 return str(target)
if __name__=='__main__':
 m=json.loads((PROJECT/'05_AGENT/benchmark-manifest.json').read_text(encoding='utf-8'))
 print(polish_file(PROJECT/'02_BENCHMARK/ykuwai-five-slides.pptx',PROJECT/'03_POC/live-demo.pptx',PROJECT/'06_QA/repaired-renders',m,resume=True))
