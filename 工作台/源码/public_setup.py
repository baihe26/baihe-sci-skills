"""Configure published engines without touching existing local settings."""
from pathlib import Path
import importlib, json, os, struct, subprocess, sys


def configuration():
    return dict(plot_root='配套程序/科研绘图工位', designer_root='配套程序/科学图设计',
                designer_contract_root='配套程序/设计合同', vector_root='配套程序/矢量桥接',
                illustrator_helpers='配套程序/矢量桥接/illustrator_helpers.py',
                studio_root='配套程序/PPT工作室', ppt_backend_root='配套程序/PPT后端',
                python='运行环境/Python/python.exe', plot_python='运行环境/Python/python.exe',
                origin_python='运行环境/Python/python.exe', portable_python='运行环境/Python/python.exe',
                desktop_locks=[])


def write_configuration(root):
    """Relative paths survive moving the project; custom configs are not overwritten."""
    path=Path(root)/'baihe-sci.public.local.json'; expected=configuration()
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8-sig')) != expected:
            raise RuntimeError('已有公开路线配置包含人工修改，保留原文件；请核对后再配置。')
    else:
        with path.open('x',encoding='utf-8') as f: json.dump(expected,f,ensure_ascii=False,indent=2)
    return path


def configure(root):
    root=Path(root).resolve()
    if os.name!='nt' or struct.calcsize('P')!=8 or root.drive.upper()!='D:':
        raise RuntimeError('自动配置支持Windows x64，请完整解压到D盘新目录。')
    if sys.version_info[:3] != (3,12,10):
        raise RuntimeError('当前原生路线要求独立Python 3.12.10；不升级已有环境以绕过门禁。')
    if Path(sys.prefix).resolve() != root/'运行环境/Python':
        raise RuntimeError('请使用安装入口创建的独立运行时，不修改其他Python环境。')
    path=write_configuration(root)
    env=dict(os.environ,BAIHE_SCI_CONFIG=str(path),BAIHE_SCI_HOME=str(root),PYTHONUTF8='1',
             PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
    for key in ('PYTHONPATH','PYTHONHOME'): env.pop(key,None)
    temp=root/'运行环境/临时文件';temp.mkdir(parents=True,exist_ok=True)
    for key in ('TEMP','TMP','TMPDIR','MPLCONFIGDIR','PIP_CACHE_DIR'): env[key]=str(temp)
    result=subprocess.run([sys.executable,str(root/'工作台/源码/workbench.py'),'--doctor'],
                          env=env,capture_output=True,text=True,encoding='utf-8')
    if result.returncode: raise RuntimeError(result.stdout+result.stderr)
    doctor=json.loads(result.stdout)
    if any(row['missing'] for row in doctor['routes']) or doctor['portable']['missing']:
        raise RuntimeError('配套或Python依赖缺失：'+result.stdout)
    for name in ('numpy','pandas','matplotlib','pymupdf','win32com.client','originpro','mcp','pptx'):
        importlib.import_module(name)
    import winreg
    apps={}
    for name,progid,url in (
        ('Origin','Origin.ApplicationSI','https://www.originlab.com/demodownload.aspx'),
        ('Illustrator','Illustrator.Application','https://www.adobe.com/products/illustrator/free-trial-download.html'),
        ('PowerPoint','PowerPoint.Application','https://www.microsoft.com/microsoft-365/powerpoint')):
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,progid): pass
            state='REGISTERED_NATIVE_ACCEPTANCE_PENDING'
        except FileNotFoundError: state='NOT_REGISTERED_INSTALL_OR_REPAIR_FROM_OFFICIAL_SOURCE'
        apps[name]=dict(status=state,official_download=url)
    report=dict(version='0.5.0',status='ENVIRONMENT_READY_NATIVE_ACCEPTANCE_PENDING',doctor=doctor,
                applications=apps,configuration=path.name,
                origin_compatibility='OriginPro 2026 SR0 x64 build 180; strict gate retained',
                native_software_started=False,global_configuration_changed=False,
                ready_without_commercial_apps=['scientific design compile','supported simple editable PPTX generation'],
                scientific_or_author_acceptance='NOT_PERFORMED')
    (root/'运行环境/安装检查.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report


if __name__=='__main__':
    try:
        print(json.dumps(configure(Path(__file__).resolve().parents[2]),ensure_ascii=False,indent=2))
    except Exception as error:
        print('配置停止：'+str(error));sys.exit(2)
