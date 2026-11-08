"""One leased heavy subprocess, with persistent jobs, cancellation and recovery."""
import json
import os
import subprocess
import sys
import threading
from uuid import uuid4
from .config import PROJECT_ROOT
from .workflow import Workflow


def terminate(process):
    if process.poll() is not None:return
    if os.name=='nt':
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    else:
        import signal
        os.killpg(process.pid,signal.SIGTERM)
    try:process.wait(timeout=10)
    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)


class WorkflowManager:
    def __init__(self,settings):
        self.settings=settings;self.store=Workflow(settings);self.owner=uuid4().hex
        self.stop_event=threading.Event();self.thread=None

    def start(self):
        self.thread=threading.Thread(target=self.run,name='ai-dj-workflow',daemon=True);self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=15)
        with self.store.db.connection() as c:
            c.execute("DELETE FROM workflow_leases WHERE name='heavy-worker' AND owner=?",(self.owner,))

    def run(self):
        while not self.stop_event.is_set():
            try:
                job=self.store.claim(self.owner)
                if job:self.execute(job)
            except Exception as exc:
                print('Workflow manager: '+str(exc),flush=True)
            self.stop_event.wait(.5)

    def execute(self,job):
        identity=job['id'];work=self.store.storage.root/'tmp'/('workflow-'+identity);work.mkdir(exist_ok=True)
        env=dict(os.environ,AI_DJ_DATA_ROOT=str(self.settings.data_root),AI_DJ_FFMPEG=self.settings.ffmpeg,
                 AI_DJ_FFPROBE=self.settings.ffprobe,NUMBA_CACHE_DIR=str(self.settings.data_root/'cache/numba'),
                 JOBLIB_TEMP_FOLDER=str(self.settings.data_root/'tmp'))
        process=None
        try:
            with (work/'job.log').open('w',encoding='utf-8') as log:
                process=subprocess.Popen([sys.executable,'-m','scripts.workflow_job',identity,self.owner],
                    cwd=PROJECT_ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,
                    start_new_session=os.name!='nt',creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                while process.poll() is None:
                    self.store.heartbeat(identity,self.owner)
                    current=self.store.job(identity,internal=True)
                    if self.stop_event.is_set() or current['cancel_requested']:
                        status='interrupted' if self.stop_event.is_set() else 'cancelled'
                        self.store.finish(identity,self.owner,status,error='Server stopped; retry the job' if status=='interrupted' else 'Cancelled by owner')
                        terminate(process);return
                    self.stop_event.wait(.5)
            result_path=work/'result.json'
            result=json.loads(result_path.read_text(encoding='utf-8')) if result_path.exists() else {}
            if process.returncode or 'error' in result:
                self.store.finish(identity,self.owner,'failed',error=result.get('error','Job stopped unexpectedly. Retry or inspect its log.'))
            else:self.store.finish(identity,self.owner,'succeeded',result=result)
        except Exception as exc:
            if process:terminate(process)
            self.store.finish(identity,self.owner,'failed',error=str(exc))
