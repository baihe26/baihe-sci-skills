"""Isolated output adapter. Reuse unmodified workstation renderer and owned session/queue."""
from paths import *
sys.path[:0]=[str(PLOT/'src'),str(PLOT/'vendor/editaplot/runtime/src'),str(PLOT/'scripts'),str(PLOT)]
from origin_sciplot.origin_backend.execution_context import require_interactive_origin_context
from origin_sciplot.origin_backend.job_queue import origin_job_slot
from origin_sciplot.origin_backend.session import OriginSession
from figure_system.common import write_new
from workstation_support import origin_environment
from phase2c.native import render,reopen
def main():
    action,out=sys.argv[1],Path(sys.argv[2]).resolve()
    from core import writable
    writable(out)
    require_interactive_origin_context()
    with origin_job_slot(job_kind='integrated-workbench',on_wait=lambda n:print('WAITING_ORIGIN_QUEUE',n,flush=True)):
        with OriginSession(keep_open=False) as session:
            env=origin_environment(session);save(out/'环境.json',env)
            if not env['environment_gate']['pass']:raise RuntimeError('ORIGIN_ENVIRONMENT_GATE')
            if action=='render':render(session.op,out)
            elif action=='reopen':reopen(session.op,out)
            else:raise ValueError(action)
if __name__=='__main__':main()
