"""Native Office structure, reopen and render verification. Run separately from builds."""
from pathlib import Path
import json,time,hashlib,zipfile,xml.etree.ElementTree as E
from collections import Counter
from native_finish import connect,children
from live_studio import PROJECT

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def openxml(path):
 ns={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','c':'http://schemas.openxmlformats.org/drawingml/2006/chart','asvg':'http://schemas.microsoft.com/office/drawing/2016/SVG/main'}
 with zipfile.ZipFile(path) as z:
  files=z.namelist();slides=sorted([f for f in files if f.startswith('ppt/slides/slide') and f.endswith('.xml')],key=lambda x:int(x.split('slide')[-1][:-4]))
  counts=Counter(slides=len(slides));fonts=set()
  for file in slides:
   root=E.fromstring(z.read(file));counts['textboxes']+=len(root.findall('.//p:cNvSpPr[@txBox="1"]',ns));counts['autoshapes']+=len(root.findall('.//p:sp',ns))-len(root.findall('.//p:cNvSpPr[@txBox="1"]',ns));counts['groups']+=len(root.findall('.//p:grpSp',ns));counts['connectors']+=len(root.findall('.//p:cxnSp',ns));counts['charts']+=len(root.findall('.//c:chart',ns));counts['tables']+=len(root.findall('.//a:tbl',ns));counts['pictures_including_svg']+=len(root.findall('.//p:pic',ns));counts['svgs']+=len(root.findall('.//asvg:svgBlip',ns));counts['animations_effect_nodes']+=len(root.findall('.//p:cTn[@presetClass]',ns));counts['transitions']+=len(root.findall('./p:transition',ns))
   for node in root.iter():
    if node.tag.split('}')[-1] in ['latin','ea'] and node.get('typeface'):fonts.add(node.get('typeface'))
  counts['smartart_parts']=len([f for f in files if f.startswith('ppt/diagrams/data') and f.endswith('.xml')]);counts['embedded_workbooks']=len([f for f in files if f.startswith('ppt/embeddings/') and f.endswith('.xlsx')])
 return {'counts':dict(counts),'fonts':sorted(fonts),'no_whole_slide_bitmap':counts['textboxes']>0 and counts['pictures_including_svg']<counts['textboxes']}

def shape_state(s):
 d={'name':s.Name,'type':s.Type,'bbox':[round(float(v),2) for v in [s.Left,s.Top,s.Width,s.Height]],'rotation':round(s.Rotation,2)}
 if s.HasTextFrame and s.TextFrame.HasText:
  tr=s.TextFrame.TextRange;d.update(text=tr.Text.replace('\r','\n'),font=tr.Font.Name,font_size=round(tr.Font.Size,2),color=int(tr.Font.Color.RGB))
 if s.Connector:
  cf=s.ConnectorFormat;d['connector']={'begin':cf.BeginConnectedShape.Name if cf.BeginConnected else None,'end':cf.EndConnectedShape.Name if cf.EndConnected else None,'begin_site':cf.BeginConnectionSite if cf.BeginConnected else None,'end_site':cf.EndConnectionSite if cf.EndConnected else None,'end_arrow':s.Line.EndArrowheadStyle,'kind':cf.Type}
 if s.HasTable:
  t=s.Table;d['table']=[[t.Cell(r,c).Shape.TextFrame.TextRange.Text for c in range(1,t.Columns.Count+1)] for r in range(1,t.Rows.Count+1)]
 if s.HasChart:
  c=s.Chart;d['chart']={'type':c.ChartType,'series':[{'name':se.Name,'categories':list(se.XValues),'values':list(se.Values)} for se in c.SeriesCollection()]}
 if s.Type==6:d['children']=[shape_state(g) for g in s.GroupItems]
 return d

def snapshot(p):
 return {'canvas':[p.PageSetup.SlideWidth,p.PageSetup.SlideHeight],'slides':[{'index':s.SlideIndex,'layout':s.Layout,'objects':[shape_state(x) for x in s.Shapes],'animations':s.TimeLine.MainSequence.Count} for s in p.Slides]}

def verify(path,label):
 path=Path(path);dest=PROJECT/'06_QA/native-audit'/label;dest.mkdir(parents=True,exist_ok=True);a=connect();t=time.perf_counter();p=a.Presentations.Open(str(path),True,False,True)
 first=snapshot(p);render1=dest/'first';render1.mkdir(exist_ok=True)
 for s in p.Slides:s.Export(str(render1/f'slide-{s.SlideIndex:02}.png'),'PNG',1600,900)
 p.Close();p=a.Presentations.Open(str(path),True,False,True);second=snapshot(p);render2=dest/'reopened';render2.mkdir(exist_ok=True)
 pixels=[];flags=[]
 for s in p.Slides:
  target=render2/f'slide-{s.SlideIndex:02}.png';s.Export(str(target),'PNG',1600,900)
  pixels.append({'slide':s.SlideIndex,'identical':sha(target)==sha(render1/target.name),'sha256':sha(target)})
  for obj in children(s.Shapes):
   if obj.HasTextFrame and obj.TextFrame.HasText and obj.TextFrame.TextRange.BoundHeight>obj.Height+3:flags.append({'slide':s.SlideIndex,'object':obj.Name,'issue':'text_height'})
   if min(obj.Left,obj.Top)<-2 or obj.Left+obj.Width>p.PageSetup.SlideWidth+2 or obj.Top+obj.Height>p.PageSetup.SlideHeight+2:flags.append({'slide':s.SlideIndex,'object':obj.Name,'issue':'offslide'})
 p.Close();evidence={'file':str(path),'sha256':sha(path),'label':label,'native_snapshot_equal_after_reopen':first==second,'pixel_equal_after_reopen':all(v['identical'] for v in pixels),'renders':pixels,'structure':openxml(path),'flags':flags,'elapsed_seconds':time.perf_counter()-t,'office_read_only':True}
 (dest/'snapshot.json').write_text(json.dumps(second,ensure_ascii=False,indent=2),encoding='utf8');(dest/'report.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(evidence,ensure_ascii=False),flush=True);return evidence
if __name__=='__main__':
 paths=[('poc','03_POC/live-demo.pptx'),('academic','07_LONG_DECK/final.pptx'),('fast','06_QA/fast-equivalence/final.pptx'),('business','04_DESIGN/samples/business/business.pptx'),('teaching','04_DESIGN/samples/teaching/teaching.pptx'),('sbroenne','02_BENCHMARK/sbroenne-five-slides.pptx'),('ykuwai','02_BENCHMARK/ykuwai-five-slides.pptx')]
 out=[verify(PROJECT/p,label) for label,p in paths]
 (PROJECT/'06_QA/native-audit-summary.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
 a=json.loads((PROJECT/'06_QA/native-audit/academic/snapshot.json').read_text(encoding='utf8'));b=json.loads((PROJECT/'06_QA/native-audit/fast/snapshot.json').read_text(encoding='utf8'))
 result={'structural_equivalence':a==b,'render_equivalence':all(sha(PROJECT/'07_LONG_DECK/renders'/f'slide-{i:02}.png')==sha(PROJECT/'06_QA/fast-equivalence/renders'/f'slide-{i:02}.png') for i in range(1,11)),'scope':'final repaired LIVE artifact vs FAST build from final manifest; shape ids/creation timestamps excluded'}
 (PROJECT/'06_QA/live-fast-equivalence.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(result)
