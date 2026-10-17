"""Configure an unpacked personal support pack; never edits global settings."""
from pathlib import Path
import sys, os, json, hashlib, struct, subprocess, argparse


def check_location(root):
    if os.name != 'nt' or struct.calcsize('P') != 8:
        raise RuntimeError('当前配套包只适用于Windows x64。')
    if root.drive.upper() != 'D:':
        raise RuntimeError('请将整包解压到D盘目录后运行，不能在ZIP中直接启动。')


def verify(root):
    record=json.loads((root/'配套文件清单.json').read_text(encoding='utf-8'))
    for item in record['files']:
        relative=Path(item['path'])
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('非法清单路径')
        p=root/relative
        if not p.resolve().is_relative_to(root.resolve()) or not p.is_file():raise RuntimeError('配套文件缺失或路径越界：'+str(relative))
        with p.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
        if actual!=item['sha256']:
            raise RuntimeError('配套文件缺失或变化：'+str(relative))
    return len(record['files'])


def configure(root):
    root=Path(root).resolve();check_location(root);count=verify(root)
    python=root/'Python/python.exe'
    if not python.is_file():raise RuntimeError('缺少包内Python，整包必须完整解压。')
    repo=root/'工具';support=root/'配套程序'
    config=dict(plot_root=str(support/'科研绘图工位'),designer_root=str(support/'科学图设计'),
                designer_contract_root=str(support/'设计合同'),vector_root=str(support/'矢量桥接'),
                illustrator_helpers=str(support/'矢量桥接/illustrator_helpers.py'),
                studio_root=str(support/'PPT工作室'),ppt_backend_root=str(support/'PPT后端'),
                python=str(python),plot_python=str(python),origin_python=str(python),portable_python=str(python),desktop_locks=[])
    path=root/'baihe-sci.migration.local.json'
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8-sig'))!=config:
            raise RuntimeError('已有配置与当前目录不同，保留原文件；请让本机Codex核对，不自动覆盖。')
    else:
        with path.open('x',encoding='utf-8') as f:json.dump(config,f,ensure_ascii=False,indent=2)
    env=dict(os.environ,BAIHE_SCI_CONFIG=str(path),BAIHE_SCI_HOME=str(repo),PYTHONUTF8='1',PYTHONDONTWRITEBYTECODE='1',PYTHONNOUSERSITE='1')
    for key in ('PYTHONPATH','PYTHONHOME'):env.pop(key,None)
    temp=root/'本机运行/临时文件';temp.mkdir(parents=True,exist_ok=True)
    for key in ('TEMP','TMP','TMPDIR','MPLCONFIGDIR','PIP_CACHE_DIR'):env[key]=str(temp)
    result=subprocess.run([str(python),str(repo/'工作台/源码/workbench.py'),'--doctor'],env=env,capture_output=True,text=True,encoding='utf-8')
    if result.returncode:raise RuntimeError(result.stdout+result.stderr)
    doctor=json.loads(result.stdout)
    if any(row['missing'] for row in doctor['routes']) or doctor['portable']['missing']:
        raise RuntimeError('配套文件或Python依赖不完整：'+result.stdout)
    import winreg
    registered={}
    for name,progid in [('Origin','Origin.ApplicationSI'),('Illustrator','Illustrator.Application'),('PowerPoint','PowerPoint.Application')]:
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT,progid):pass
            registered[name]='REGISTERED_NOT_ACTIVATED'
        except FileNotFoundError:registered[name]='PROGID_NOT_FOUND_NEEDS_LOCAL_CHECK'
    report=dict(status='SUPPORT_PACK_CONFIGURED_NATIVE_ACCEPTANCE_PENDING',files_verified=count,doctor=doctor,
                config=str(path),applications=registered,global_settings_changed=False,commercial_software_installed=False,
                native_apps_started=False,source_research_materials_bundled=False,
                origin_compatibility='Existing worker gate retained: Python 3.12.10, OriginPro 2026 SR0 x64 build 180. Other versions need separate compatibility work.',
                next_step='Read 从这里开始.md; run each native route on self-authored synthetic inputs in new output folders, one app writer at a time.')
    (root/'本机运行/配置检查.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    try:print(json.dumps(configure(Path(__file__).resolve().parent),ensure_ascii=False,indent=2))
    except Exception as error:print('安全停止：'+str(error));sys.exit(2)
