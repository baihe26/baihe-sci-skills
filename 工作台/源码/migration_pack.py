"""Create an allowlisted personal transfer pack from already configured engines.

Never uploads the private payload. Source engines and research projects stay read-only.
"""
from pathlib import Path
import sys,os,json,ast,hashlib,shutil,subprocess,zipfile,argparse


def hash_file(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def function_subset(path,names,header):
    text=Path(path).read_text(encoding='utf-8-sig');tree=ast.parse(text);found={}
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in names:found[node.name]=ast.get_source_segment(text,node)
    if set(found)!=set(names):raise RuntimeError('兼容辅助函数缺失：'+str(path.name))
    return header+'\n\n'+'\n\n'.join(found[name] for name in names)+'\n'


def build(repo,config,out,include_python=False):
    repo=Path(repo).resolve();config=Path(config).resolve();out=Path(out).resolve()
    if os.name!='nt' or out.drive.upper()!='D:':raise RuntimeError('个人配套迁移包须在Windows的D盘创建。')
    if out.exists():raise FileExistsError('保留已有目录，请选择新的输出目录。')
    if shutil.disk_usage(out.anchor).free<2*1024**3:raise RuntimeError('D盘需至少2GiB可用空间再创建带运行时的迁移包。')
    cfg=json.loads(config.read_text(encoding='utf-8-sig'))
    def root(key):
        p=Path(cfg[key]);return p.resolve() if p.is_absolute() else (config.parent/p).resolve()
    out.mkdir(parents=True);pack=out/'baihe-sci配套包';pack.mkdir();records=[];changes=[]
    def copy(path,destination,component,source_root=None):
        path=Path(path).resolve()
        if source_root and not path.is_relative_to(Path(source_root).resolve()):raise RuntimeError('源路径越界')
        target=pack/destination;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
        records.append(dict(path=Path(destination).as_posix(),sha256=hash_file(target),source_sha256=hash_file(path),component=component))
    def generated(destination,text,component,reason):
        target=pack/destination;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(text,encoding='utf-8',newline='\r\n' if target.suffix=='.cmd' else '\n')
        records.append(dict(path=Path(destination).as_posix(),sha256=hash_file(target),component=component,adaptation=reason));changes.append(dict(path=Path(destination).as_posix(),reason=reason))
    def patch_existing(destination,old,new,reason):
        path=pack/destination;body=path.read_text(encoding='utf-8-sig')
        if body.count(old)!=1:raise RuntimeError('迁移路径补丁与源版本不符：'+str(destination))
        path.write_text(body.replace(old,new),encoding='utf-8',newline='\n')
        row=next(r for r in records if r['path']==Path(destination).as_posix());row.update(sha256=hash_file(path),adaptation=reason)
        changes.append(dict(path=Path(destination).as_posix(),reason=reason))
    # Export only tracked public tools, never local configs, outputs, credentials or Git history.
    tracked=[p for p in subprocess.check_output(['git','-C',str(repo),'ls-files','-z']).decode('utf-8').split('\0') if p]
    for name in tracked:copy(repo/name,Path('工具')/name,'public-workbench',repo)
    plot=root('plot_root');target=Path('配套程序/科研绘图工位')
    for folder in ['src/figure_system','vendor/editaplot/runtime']:
        for p in (plot/folder).rglob('*'):
            if p.is_file() and not {'__pycache__','.pytest_cache'}&set(p.parts) and p.suffix!='.pyc':copy(p,target/p.relative_to(plot),'plot-runtime',plot)
    for folder,names in {
        'phase2c':['__init__.py','native.py','native_identity.py','semantics.py','acceptance.py','legacy.py'],
        'phase2c_1':['__init__.py','contracts.py','native.py','oracle.py','qa.py','color_title_probe.py','colorscale_format.c'],
        'scripts':['workstation_support.py'],
        'blocker_sprint_20261004/scripts':['analyze_outputs_complete.py'],
        'environment':['requirements-origin.lock'],
        'phase2b/CX_STYLE_V0_1_FREEZE_20261007':['FIGURESTATE_STYLE_V0_1.json','ADVISOR_CORPUS.json','REFERENCE_PANEL_REGISTRY.json'],
        'fixtures':['figurestate.schema.json'],
        'fixtures/styles':['style_v0_1_selected.json'],
        'vendor/editaplot':['LICENSE','NOTICE','AUTHORS.md','THIRD_PARTY_NOTICES.md'],
        'vendor/nature_qa':['LICENSE'],
        'vendor/nature_qa/scripts':['audit_figure_collisions.py','audit_pdf_text.py'],
        '.':['REPOSITORY_LICENSE_MANIFEST.md','PLOT_SEMANTICS_CONTRACT.md']
    }.items():
        for name in names:
            p=plot/folder/name
            if p.is_file():copy(p,target/p.relative_to(plot),'plot-support',plot)
            elif folder!='.':raise FileNotFoundError(p)
    patch_existing(target/'src/figure_system/common.py',"ORIGIN_PY=ROOT/'.origin-venv/Scripts/python.exe'", "ORIGIN_PY=Path(__file__).resolve().parents[4]/'Python/python.exe'",'Use private pack Python for legacy source-worker delegation; original source unchanged')
    for name in ['CORE_ARCHETYPE_REGISTRY_V2.json','CORE_ARCHETYPE_REGISTRY_V2.md','PLOT_DECISION_RULES.md','ADVISOR_AWARE_PLOT_PREFERENCE.md','PLOT_SEMANTICS_CONTRACT.md','EXPERIMENTAL_UNIT_CONTRACT.md','NESTED_DATA_RULES.md','NATIVE_COLOR_REFERENCE.json','COLOR_SEMANTICS.md']:
        copy(plot/'phase2c'/name,target/'phase2c'/name,'plot-contract',plot)
    design=root('designer_root')/'corpus_grounded_design_v1';dest=Path('配套程序/科学图设计/corpus_grounded_design_v1')
    for name in ['重放设计.py','handoff_metadata.py']:copy(design/name,dest/name,'frozen-designer',design)
    io_header='from pathlib import Path\nimport json,hashlib\nROOT=Path(__file__).resolve().parent\nREPO=ROOT.parent'
    generated(dest/'整理研究证据.py',function_subset(design/'整理研究证据.py',['read','dump','write','sha'],io_header),'designer-io-adapter','Extract only existing file IO functions; exclude study corpus, reading records and evaluation cases')
    handoff=root('designer_contract_root')
    for p in (handoff/'schemas').glob('*.json'):copy(p,Path('配套程序/设计合同/schemas')/p.name,'design-schema',handoff)
    bridge=root('vector_root')/'bridge/illustrator_bridge.py';body=bridge.read_text(encoding='utf-8-sig');tree=ast.parse(body)
    node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='WORKSPACE' for t in n.targets))
    body=body.replace(ast.get_source_segment(body,node),'WORKSPACE = Path(__file__).resolve().parents[1]')
    generated('配套程序/矢量桥接/bridge/illustrator_bridge.py',body,'vector-bridge','Copy with WORKSPACE resolved relative to the transferred bridge; original unmodified')
    helper=root('illustrator_helpers');tree=ast.parse(helper.read_text(encoding='utf-8-sig'))
    node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='JS_HELPERS' for t in n.targets))
    generated('配套程序/矢量桥接/illustrator_helpers.py','JS_HELPERS = '+repr(ast.literal_eval(node.value))+'\n','vector-helper','Only the existing JS export/audit helpers; exclude project scripts and material')
    studio=root('studio_root')
    for name in ['live_studio.py','manifest_contract.py','native_finish.py','native_audit.py','recovery_journal.py']:
        p=studio/'03_POC/source'/name;body=p.read_text(encoding='utf-8-sig')
        if name=='live_studio.py':
            tree=ast.parse(body);guard=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='designer_guard')
            lines=body.splitlines(keepends=True);start=min([guard.lineno,*[d.lineno for d in guard.decorator_list]])-1
            lines[start:guard.end_lineno]=['# Historical registry guard omitted from personal transfer copy.\n'];body=''.join(lines)
            body=body.replace('import winreg\n','').replace('WORK=BASE/"work"','WORK=PROJECT/"本机运行"\n(WORK/"tmp").mkdir(parents=True,exist_ok=True)')
            generated(Path('配套程序/PPT工作室/03_POC/source')/name,body,'studio','Relative private runtime path; omit unused historical registry guard; rendering backend unchanged')
        else:copy(p,Path('配套程序/PPT工作室/03_POC/source')/name,'studio',studio)
    for name in ['PROFILE_README.md','AUTHOR_STYLE_BASELINE_V03.md','AUTHOR_STYLE_PROFILE_V03.json','HARD_INVARIANTS.md','ADAPTIVE_LAYOUT_POLICY.md','HUMAN_OVERRIDE_POLICY.md']:
        copy(studio/'AUTHOR_STYLE_BASELINE_V03'/name,Path('配套程序/PPT工作室/AUTHOR_STYLE_BASELINE_V03')/name,'author-style',studio)
    backend=root('ppt_backend_root')
    for p in (backend/'src').rglob('*'):
        if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc':copy(p,Path('配套程序/PPT后端')/p.relative_to(backend),'ppt-backend-MIT',backend)
    copy(backend/'pyproject.toml','配套程序/PPT后端/pyproject.toml','ppt-backend-license',backend)
    generated('配套程序/PPT后端/许可来源.md','# 上游许可记录\n\n本地固定版本pyproject.toml声明MIT，作者ykuwai，来源https://github.com/ykuwai/ppt-mcp 。保留原始元数据。上游未提供独立LICENSE文件，本包不补造版权年份。\n','license-record','Preserve the original upstream MIT declaration; no invented license or copyright notice')
    setup=(repo/'工作台/源码/migration_setup.py').read_text(encoding='utf-8')
    generated('配置另一台电脑.py',setup,'setup','Project-local path configuration; no global settings, software install or automatic native mutation')
    python_source=None
    if include_python:
        current=root('python');result=subprocess.check_output([str(current),'-c','import sys,json;print(json.dumps(dict(base=sys.base_prefix,version=list(sys.version_info[:3]))))'],text=True)
        info=json.loads(result)
        if info['version']!=[3,12,10]:raise RuntimeError('当前原生兼容包要求原基准Python 3.12.10，不自动替换版本。')
        python_source=Path(info['base'])
        for p in python_source.iterdir():
            if p.is_file() and (p.suffix in ('.exe','.dll') or p.name.lower().startswith('license')):copy(p,Path('Python')/p.name,'python-PSF',python_source)
        for folder in ['Lib','DLLs','tcl']:
            for p in (python_source/folder).rglob('*'):
                if not p.is_file() or {'site-packages','__pycache__','test','tests','idlelib'}&set(p.relative_to(python_source).parts) or p.suffix=='.pyc' or p.name in ('sitecustomize.py','usercustomize.py'):continue
                copy(p,Path('Python')/p.relative_to(python_source),'python-PSF',python_source)
    generated('配置与检查.cmd','@echo off\nsetlocal\nchcp 65001 >nul\nset PYTHONUTF8=1\nset PYTHONDONTWRITEBYTECODE=1\nset PYTHONNOUSERSITE=1\nset PYTHONPATH=\nset PYTHONHOME=\nif not exist "%~dp0本机运行\\临时文件" mkdir "%~dp0本机运行\\临时文件"\nset "TEMP=%~dp0本机运行\\临时文件"\nset "TMP=%TEMP%"\nset "TMPDIR=%TEMP%"\nset "MPLCONFIGDIR=%TEMP%"\nset "PIP_CACHE_DIR=%TEMP%"\n"%~dp0Python\\python.exe" "%~dp0配置另一台电脑.py"\npause\n','entry','Only local setup and file/registration inspection')
    generated('启动工作台.cmd','@echo off\nsetlocal\nchcp 65001 >nul\nset PYTHONUTF8=1\nset PYTHONDONTWRITEBYTECODE=1\nset PYTHONNOUSERSITE=1\nset PYTHONPATH=\nset PYTHONHOME=\nif not exist "%~dp0本机运行\\临时文件" mkdir "%~dp0本机运行\\临时文件"\nset "TEMP=%~dp0本机运行\\临时文件"\nset "TMP=%TEMP%"\nset "TMPDIR=%TEMP%"\nset "MPLCONFIGDIR=%TEMP%"\nset "PIP_CACHE_DIR=%TEMP%"\nset "BAIHE_SCI_CONFIG=%~dp0baihe-sci.migration.local.json"\nset "BAIHE_SCI_HOME=%~dp0工具"\n"%~dp0Python\\python.exe" "%~dp0工具\\工作台\\源码\\workbench.py" %*\n','entry','Per-process use of the transferred engine paths; no global install')
    manifest=dict(schema_version='personal-support-pack-0.1',date='2026-10-18',private_personal_transfer=True,
                  public_workbench_commit=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD']).decode().strip(),
                  files=records,adaptations=changes,research_data_included=False,commercial_software_included=False,
                  original_engines_modified=False,python_included=include_python,native_target_acceptance='PENDING')
    (pack/'配套文件清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return dict(pack=str(pack),files=len(records),python_source=str(python_source) if python_source else None,archive_created=False)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',required=True);p.add_argument('--out',required=True);p.add_argument('--include-python',action='store_true');a=p.parse_args()
    print(json.dumps(build(Path(__file__).resolve().parents[2],a.config,a.out,a.include_python),ensure_ascii=False,indent=2))
