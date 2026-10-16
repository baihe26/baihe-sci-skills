"""Optional isolated setup; never upgrades or changes an existing Python environment."""
from pathlib import Path
import sys,os,argparse,subprocess,shutil,json


def main():
    if sys.version_info < (3,11):raise RuntimeError('需要Python 3.11或更新版本；未创建环境。')
    repo=Path(__file__).resolve().parent
    parser=argparse.ArgumentParser(description='在仓库内新建可选PPT后端环境；保留已有软件/配置。')
    parser.add_argument('--dry-run',action='store_true');parser.add_argument('--wheelhouse',type=Path)
    parser.add_argument('--environment',type=Path,default=repo/'工作台/可选环境')
    args=parser.parse_args();destination=args.environment.resolve()
    if os.name=='nt' and (destination.drive.upper()!='D:' or repo.drive.upper()!='D:'):raise ValueError('本机存储约定要求仓库、缓存和新环境位于D盘；未创建环境。')
    if destination.exists():raise FileExistsError('保留已有环境；请用doctor核查或指定新的--environment目录。')
    config=repo/'baihe-sci.portable.local.json'
    if config.exists():raise FileExistsError('保留已有可选配置；未安装或覆盖环境。')
    free=shutil.disk_usage(destination.anchor).free
    if free<256*1024*1024:raise ValueError('目标盘可用空间少于256MiB；停止安装。')
    python=destination/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    pip=[str(python),'-m','pip','install','--require-virtualenv','--disable-pip-version-check','--cache-dir',str(repo/'工作台/临时文件/包缓存'),'-r',str(repo/'requirements-portable.txt')]
    if args.wheelhouse:pip.extend(['--no-index','--find-links',str(args.wheelhouse.resolve())])
    commands=[[sys.executable,'-m','venv',str(destination)],pip]
    if args.dry_run:
        print(json.dumps(dict(status='DRY_RUN',destination=str(destination),commands=commands,existing_environment_modified=False),ensure_ascii=False,indent=2));return
    cache=repo/'工作台/临时文件/安装缓存';cache.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,TEMP=str(cache),TMP=str(cache),TMPDIR=str(cache),PIP_CACHE_DIR=str(repo/'工作台/临时文件/包缓存'),PYTHONDONTWRITEBYTECODE='1')
    for command in commands:subprocess.run(command,check=True,env=env)
    subprocess.run([str(python),'-c','import pptx,PIL; print(pptx.__version__,PIL.__version__)'],check=True,env=env)
    with config.open('x',encoding='utf-8') as f:json.dump(dict(portable_python=str(python)),f,ensure_ascii=False,indent=2)
    print(json.dumps(dict(status='OPTIONAL_BACKEND_READY',python=str(python),configuration=str(config),
                         use='Set BAIHE_SCI_CONFIG for this process, then use --target ppt --backend portable',
                         default_config_changed=False,office_installed=False),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
