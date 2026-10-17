"""Handoff environment checks only. Scientific checks remain in the existing pipeline."""
from pathlib import Path
import sys,os,json,hashlib,platform,struct,importlib.metadata as md,ctypes,tempfile
ROOT=Path(__file__).resolve().parents[1]
def dump(path,data):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('x',encoding='utf-8') as f:json.dump(data,f,indent=2,ensure_ascii=False)
def verify_payload():
 m=json.loads((ROOT/'HANDOFF_FILES.json').read_text(encoding='utf-8'))
 for n,h in m['sha256'].items():
  p=ROOT/n
  with p.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
  if actual!=h:raise RuntimeError('Handoff integrity mismatch: '+n)
 return len(m['sha256'])
def check_python():
 if sys.platform!='win32' or struct.calcsize('P')!=8 or platform.machine().lower() not in ('amd64','x86_64'):raise RuntimeError('Windows x64 required')
 if sys.version_info[:3]!=(3,12,10):raise RuntimeError('Python 3.12.10 required; observed '+platform.python_version())
 return {'version':platform.python_version(),'executable':sys.executable,'bits':64}
def check_packages(kind):
 versions={}
 for line in (ROOT/'environment'/('requirements-'+kind+'.lock')).read_text(encoding='utf-8-sig').splitlines():
  if not line.strip() or line.startswith('#'):continue
  n,v=line.split('==');got=md.version(n);versions[n]=got
  if got!=v:raise RuntimeError('Package mismatch: '+n+' expected '+v+' got '+got)
 return versions
def executable_build(exe):
 class FIXED(ctypes.Structure):_fields_=[(x,ctypes.c_uint32) for x in ('signature','structVersion','fileMS','fileLS','productMS','productLS','flagsMask','flags','OS','type','subtype','dateMS','dateLS')]
 api=ctypes.WinDLL('version',use_last_error=True)
 api.GetFileVersionInfoSizeW.argtypes=[ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_uint32)];api.GetFileVersionInfoSizeW.restype=ctypes.c_uint32
 api.GetFileVersionInfoW.argtypes=[ctypes.c_wchar_p,ctypes.c_uint32,ctypes.c_uint32,ctypes.c_void_p];api.GetFileVersionInfoW.restype=ctypes.c_int
 api.VerQueryValueW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.POINTER(ctypes.c_void_p),ctypes.POINTER(ctypes.c_uint32)];api.VerQueryValueW.restype=ctypes.c_int
 size=api.GetFileVersionInfoSizeW(str(exe),None)
 if not size:raise RuntimeError('Cannot read executable version resource')
 buf=ctypes.create_string_buffer(size)
 if not api.GetFileVersionInfoW(str(exe),0,size,buf):raise RuntimeError('Cannot read executable version resource')
 ptr=ctypes.c_void_p();length=ctypes.c_uint32()
 if not api.VerQueryValueW(buf,'\\',ctypes.byref(ptr),ctypes.byref(length)):raise RuntimeError('Missing fixed version resource')
 v=ctypes.cast(ptr,ctypes.POINTER(FIXED)).contents
 return {'file_version':[v.fileMS>>16,v.fileMS&65535,v.fileLS>>16,v.fileLS&65535],'product_version':[v.productMS>>16,v.productMS&65535,v.productLS>>16,v.productLS&65535]}
def origin_environment(session):
 check_python();packages=check_packages('origin')
 op=session.op;program=Path(op.path('e')).resolve();exe=program/'Origin64.exe';uff=Path(op.path('u')).resolve()
 report={'product':'OriginPro' if op.lt_int('@VLP')==1 else 'Origin','version_at_V':op.lt_float('@V'),'Origin_bits':op.lt_int('@VB'),'program_executable':str(exe),'actual_UFF':str(uff),'resource_language':op.lt_int('@VRL'),'python':platform.python_version(),'originpro':packages['originpro'],'OriginExt':packages['OriginExt'],'license_mode':'software_started_license_details_not_read','credentials_collected':False,'worker_pid':os.getpid(),'ownership':'NEW_ISOLATED_OWNED_SESSION','session_environment':session.environment.to_dict()}
 if exe.is_file():report.update(executable_version=executable_build(exe))
 problems=[]
 if report['product']!='OriginPro':problems.append('OriginPro required')
 if abs(report['version_at_V']-10.300180)>1e-7:problems.append('Expected Origin 2026 SR0 @V 10.300180')
 if report['Origin_bits']!=64:problems.append('Origin x64 required')
 if not exe.is_file() or report.get('executable_version',{}).get('file_version',[None]*4)[3]!=180:problems.append('Executable build 180 required')
 if not uff.is_dir():problems.append('Actual UFF missing')
 else:
  try:
   # Only our unique temporary probe is removed. No UFF configuration is changed.
   with tempfile.NamedTemporaryFile(prefix='workstation_write_probe_',suffix='.tmp',dir=uff):pass
   report['UFF_writable']=True
  except OSError:report['UFF_writable']=False;problems.append('Actual UFF not writable')
 report['environment_gate']={'pass':not problems,'failures':problems}
 return report
