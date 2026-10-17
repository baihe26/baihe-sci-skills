"""Local native PowerPoint research harness. No cloud/model API calls."""
from __future__ import annotations
import asyncio, json, os, sys, time, hashlib, uuid, statistics
from pathlib import Path
from datetime import datetime, timezone
from contextlib import contextmanager
PROJECT=Path(__file__).resolve().parents[2]
BASE=PROJECT.parent.parent
WORK=PROJECT/"本机运行"
(WORK/"tmp").mkdir(parents=True,exist_ok=True)
os.environ["TEMP"]=os.environ["TMP"]=str(WORK/"tmp")
os.environ["PYTHONUTF8"]="1"
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

def decode_result(result):
    raw=result.model_dump(mode="json") if hasattr(result,"model_dump") else result
    texts=[x.get("text","") for x in raw.get("content",[]) if x.get("type")=="text"]
    data=[]
    for text in texts:
        try:data.append(json.loads(text))
        except ValueError:data.append({"text":text})
    payload=data[0] if len(data)==1 else {"items":data}
    if isinstance(payload,str):
        try:payload=json.loads(payload)
        except ValueError:payload={"text":payload}
    failed=bool(raw.get("isError",raw.get("is_error",False)))
    if isinstance(payload,dict):
        failed=failed or payload.get("success") is False or bool(payload.get("error")) or bool(payload.get("errorMessage"))
    return not failed,payload,raw

# Historical registry guard omitted from personal transfer copy.

class Backend:
    def __init__(self,name,session,log,mode="FAST",delay=.15):
        self.name=name;self.session=session;self.log=Path(log);self.mode=mode;self.delay=delay
        self.sid=None;self.path=None;self.names={};self.count=0;self.failures=0;self.samples=[]
        self.slide=0;self.semantic_id=None;self.repair_parent=None
    async def call(self,tool,params,allow_failure=False,bind=True):
        args=dict(params)
        if self.name=="ykuwai":
            args={"params":args}
            if bind and self.path:args["presentation"]=str(self.path)
        elif bind and self.sid and tool!="presentation":args["session_id"]=self.sid
        start=time.perf_counter(); raw={}
        try:
            result=await self.session.call_tool(tool,args)
            ok,data,raw=decode_result(result)
        except Exception as e:ok=False;data={"error":repr(e)}
        duration=time.perf_counter()-start
        event={"timestamp":datetime.now(timezone.utc).isoformat(),"session":self.sid or str(self.path),"slide":self.slide,
          "semantic_object_id":self.semantic_id,"operation":tool,"parameters":args,"backend":self.name,
          "mode":self.mode,"success":ok,"duration":duration,"error":None if ok else data,
          "repair_parent":self.repair_parent,"result":data,"transport_is_error":raw.get("isError",raw.get("is_error"))}
        with self.log.open("a",encoding="utf-8") as f:f.write(json.dumps(event,ensure_ascii=False)+"\n")
        self.count+=1;self.samples.append(duration)
        if not ok:
            self.failures+=1
            if not allow_failure:raise RuntimeError(f"{self.name} {tool}: {data}")
        return data
    async def domain(self,tool,action,**kw):
        return await self.call(tool,dict(action=action,**kw))
    async def create(self,path,resume=False):
        self.path=Path(path)
        if self.path.exists():
            if not resume:raise FileExistsError(self.path)
            if self.name == "sbroenne":
                import shutil
                cps=sorted((self.path.parent/"checkpoints").glob(self.path.stem+"-s*.pptx"))
                if not cps:raise FileExistsError(self.path)
                partial=self.path.with_name(self.path.stem+"-failed-partial.pptx")
                if not partial.exists():shutil.copy2(self.path,partial)
                shutil.copy2(cps[-1],self.path)
                r=await self.call("presentation",{"action":"open","filePath":str(self.path)},bind=False)
                self.sid=r["sessionId"];self.slide=int(cps[-1].stem[-2:])
                print("RESUMED",r,flush=True)
                return
            import win32com.client, pythoncom
            pythoncom.CoInitialize()
            app=win32com.client.GetActiveObject("PowerPoint.Application")
            for i in range(app.Presentations.Count,0,-1):
                pres=app.Presentations(i)
                if str(pres.FullName).lower()==str(self.path).lower():
                    partial=self.path.with_name(self.path.stem+"-failed-partial.pptx")
                    if not partial.exists():pres.SaveCopyAs(str(partial),24)
                    pres.Saved=True
                    pres.Close()
            r=await self.call("ppt_open_presentation",{"file_path":str(self.path)},bind=False)
            self.slide=int(r.get("slides_count",r.get("slide_count",0)))
            print("RESUMED",r,flush=True)
            return
        if self.name=="sbroenne":
            r=await self.call("presentation",{"action":"create","filePath":str(self.path)},bind=False)
            self.sid=r.get("sessionId") or r.get("session_id")
            if not self.sid:raise RuntimeError(r)
            await self.domain("pagesetup","set-size",width=960,height=540)
        else:
            self.path=None
            r=await self.call("ppt_create_presentation",{"preset":"16:9"},bind=False)
            self.path=Path(path)
            await self.call("ppt_save_presentation_as",{"file_path":str(path)},bind=False)
        print("CREATED",self.name,r,flush=True)
    async def add_slide(self):
        self.slide+=1;self.semantic_id=None;self.names={}
        if self.name=="sbroenne":await self.domain("slide","add-blank")
        else:await self.call("ppt_add_slide",{"layout":12})
    async def checkpoint(self):
        cp=self.path.parent/"checkpoints";cp.mkdir(exist_ok=True)
        target=cp/(self.path.stem+f"-s{self.slide:02d}.pptx")
        if self.name=="sbroenne":
            await self.call("presentation",{"action":"save-copy-as","sessionId":self.sid,"targetPath":str(target)},bind=False)
        else:
            await self.call("ppt_save_presentation",{})
            # Saved checkpoint copy is a byte-for-byte copy of the now persisted file.
            import shutil;shutil.copy2(self.path,target)
    async def render(self,folder):
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        if self.name=="sbroenne":
            await self.domain("export","export-slide-to-image",slide_index=self.slide,output_path=str(folder/f"slide-{self.slide:02d}.png"),format="PNG",width=1600,height=900)
        else:
            await self.call("ppt_export_images",{"output_dir":str(folder),"slide_index":self.slide,"file_name":f"slide-{self.slide:02d}.png","width":1600,"height":900})
    async def finish(self):
        if self.name=="sbroenne":
            await self.call("presentation",{"action":"close","sessionId":self.sid,"save":True},bind=False)
        else:
            await self.call("ppt_save_presentation",{})
            await self.call("ppt_close_presentation",{"save":True})
    async def object(self,o):
        self.semantic_id=o["id"]; kind=o["type"]; si=self.slide
        box=dict(zip(["left","top","width","height"],o.get("bbox",[0,0,100,40])))
        a=self.name=="sbroenne";r={}
        if kind in ["text","shape"]:
            if a:
                r=await self.domain("shape","add-text-box" if kind=="text" else "add-auto-shape",slide_index=si,**box,**({"text":o["text"]} if kind=="text" else {"shape_type":o.get("shape","msoShapeRectangle")}))
                idx=r.get("shapeIndex",r.get("shape_index"))
                if idx is None:raise RuntimeError(r)
                await self.domain("shape","set-name",slide_index=si,shape_index=idx,name=o["id"])
                if kind=="shape" and o.get("text"):await self.domain("textframe","set-text",slide_index=si,shape_index=idx,text=o["text"])
                if o.get("text"):
                    await self.domain("textframe","set-font-name",slide_index=si,shape_index=idx,font_name="Microsoft YaHei")
                    await self.domain("textframe","set-font-size",slide_index=si,shape_index=idx,font_size=o.get("size",20))
                    await self.domain("textframe","set-font-color",slide_index=si,shape_index=idx,**rgb(o.get("color","203E3A")))
                    if o.get("bold"):await self.domain("textframe","set-bold",slide_index=si,shape_index=idx,bold=True)
                if kind=="shape":
                    await self.domain("shape","set-fill",slide_index=si,shape_index=idx,**rgb(o.get("fill","EAF3EF")))
                    await self.domain("shape","set-line",slide_index=si,shape_index=idx,visible=False)
                self.names[o["id"]]={"index":idx,"name":o["id"]}
            else:
                p=dict(slide_index=si,**box,text=o.get("text",""),font_name="Microsoft YaHei",font_size=o.get("size",20),font_color="#"+o.get("color","203E3A"),bold=o.get("bold",False))
                if kind=="shape":p.update(shape_type=o.get("shape_b","rectangle"),fill_color="#"+o.get("fill","EAF3EF"),line_visible=False)
                r=await self.call("ppt_add_textbox" if kind=="text" else "ppt_add_shape",p)
                self.names[o["id"]]={"index":r.get("shape_index"),"name":r.get("shape_name")}
        elif kind=="picture":
            r=await self.domain("image","add-picture",slide_index=si,image_path=o["path"],**box) if a else await self.call("ppt_add_picture",dict(slide_index=si,file_path=o["path"],**box))
            self.names[o["id"]]={"index":r.get("shapeIndex",r.get("shape_index")),"name":r.get("shape_name")}
        elif kind=="chart":
            if a:r=await self.domain("chart","add-chart",slide_index=si,chart_type="bar",categories=o["categories"],values=o["values"],series_name=o["series"],**box)
            else:
                r=await self.call("ppt_add_chart",dict(slide_index=si,chart_type="column",**box))
                await self.call("ppt_set_chart_data",{"slide_index":si,"shape_name_or_index":r["shape_name"],"categories":o["categories"],"series":[{"name":o["series"],"values":o["values"]}]})
            idx=r.get("shapeIndex",r.get("shape_index"));name=r.get("shape_name")
            self.names[o["id"]]={"index":idx,"name":name}
            if a:await self.domain("chart","set-legend-visibility",slide_index=si,shape_index=idx,visible=False)
            else:await self.call("ppt_format_chart",{"slide_index":si,"shape_name_or_index":name,"has_legend":False})
        elif kind=="table":
            data=o["data"]
            if a:
                r=await self.domain("table","add-table",slide_index=si,rows=len(data),columns=len(data[0]),**box)
                idx=r.get("shapeIndex",r.get("shape_index"))
                for row,vals in enumerate(data,1):
                    for col,txt in enumerate(vals,1):await self.domain("table","set-cell-text",slide_index=si,shape_index=idx,row=row,column=col,text=str(txt))
            else:
                r=await self.call("ppt_add_table",dict(slide_index=si,rows=len(data),cols=len(data[0]),**box))
                await self.call("ppt_set_table_data",{"slide_index":si,"shape_name_or_index":r["shape_name"],"data":data,"bold_first_row":True})
            self.names[o["id"]]={"index":r.get("shapeIndex",r.get("shape_index")),"name":r.get("shape_name")}
        elif kind=="connector":
            begin=self.names[o["begin"]];end=self.names[o["end"]]
            if a:r=await self.domain("shape","add-attached-connector",slide_index=si,connector_type={"straight":"msoConnectorStraight","elbow":"msoConnectorElbow","curve":"msoConnectorCurve"}[o.get("curve","straight")],begin_shape_index=begin["index"],begin_connection_site=o.get("begin_site",4),end_shape_index=end["index"],end_connection_site=o.get("end_site",2))
            else:r=await self.call("ppt_add_connector",{"slide_index":si,"connector_type":o.get("curve","straight"),"begin_shape":begin["name"],"begin_site":o.get("begin_site",4),"end_shape":end["name"],"end_site":o.get("end_site",2)})
        elif kind=="group":
            members=[self.names[x] for x in o["members"]]
            if a:r=await self.domain("shape","group",slide_index=si,shape_indexes=[x["index"] for x in members])
            else:r=await self.call("ppt_group_shapes",{"slide_index":si,"shape_names":[x["name"] for x in members]})
        else:raise ValueError(kind)
        if self.mode=="LIVE":await asyncio.sleep(self.delay)
        return r

def rgb(hex):
    return dict(zip(["red","green","blue"],[int(hex[i:i+2],16) for i in (0,2,4)]))

async def with_backend(name,func,log,mode="FAST"):
    command=str(WORK/"envs/sbroenne-MCP-Server/powerpoint-mcp.exe") if name=="sbroenne" else sys.executable
    if name=="sbroenne":command=os.environ.get("SBROENNE_MCP_EXE",str(next((WORK/"envs/sbroenne-MCP-Server").glob("*.exe"))))
    args=[] if name=="sbroenne" else ["-m","src.server"]
    with Path(log).with_suffix(".stderr.txt").open("w",encoding="utf-8") as err:
      async with stdio_client(StdioServerParameters(command=command,args=args,env=os.environ.copy()),errlog=err) as streams:
        async with ClientSession(*streams) as session:
          await session.initialize(); b=Backend(name,session,log,mode)
          await func(b)
          return {"backend":name,"tool_actions":b.count,"failures":b.failures,"latency_median":statistics.median(b.samples),"latency_p95":sorted(b.samples)[int(.95*(len(b.samples)-1))]}

def clean_task_smoke():
    import win32com.client,pythoncom
    pythoncom.CoInitialize()
    try:a=win32com.client.GetActiveObject("PowerPoint.Application")
    except Exception:return
    for i in range(a.Presentations.Count,0,-1):
        p=a.Presentations(i)
        if str(p.FullName).startswith(str(PROJECT)) and p.Name=="environment-smoke.pptx":p.Close()
    if a.Presentations.Count==0:a.Quit()

