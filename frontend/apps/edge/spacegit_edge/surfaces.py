"""Local surface jobs and artifact delivery. Open3D runs outside the camera edge."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from threading import Lock, Thread, Timer
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import Field

from .models import Id, Strict
from .rig import SLOTS, archive_root, cloud_name


ROOT = Path(__file__).resolve().parents[4]
LIMIT = 192*1024*1024
ACTIVE = {'queued', 'running'}
ARTIFACTS = {'cleaned': 'cleaned_pointcloud.ply', 'mesh': 'reconstructed_mesh.ply', 'report': 'reconstruction_report.json'}


class SurfaceSettings(Strict):
    outliers: bool = True
    outlier_strength: float = Field(2.5, ge=1.5, le=6)
    voxel: float = Field(0, ge=0, le=12)
    depth: int = Field(9, ge=5, le=11)
    density_percent: float = Field(2, ge=0, le=10)
    support: float = Field(4, ge=1.5, le=8)
    smoothing: int = Field(3, ge=0, le=15)
    smoothing_intensity: float = Field(.45, ge=.1, le=.5)


class SurfaceRequest(Strict):
    source: Id
    action: Literal['analyse', 'reconstruct', 'smooth']
    settings: SurfaceSettings = Field(default_factory=SurfaceSettings)
    base: Id | None = None


def work_root(runtime):
    return (runtime.store.path.parent/(runtime.store.path.stem+'-surfaces')).resolve()


def sources(runtime, ident):
    upload = work_root(runtime)/'inputs'/ident/'original.ply'
    if upload.is_file():
        return {1: upload}, False
    folder = archive_root(runtime.store)/ident
    files = {slot: (folder/cloud_name(slot)).resolve() for slot in SLOTS}
    if (folder/'manifest.json').is_file() and all(path.is_file() for path in files.values()):
        return files, True
    raise HTTPException(404, 'Load a PLY or select a saved PointDiT version first.')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def save_state(folder, state):
    path = folder/'state.tmp'
    path.write_text(json.dumps(state, allow_nan=False), encoding='utf-8')
    path.replace(folder/'state.json')


class SurfaceJobs:
    def __init__(self):
        self.lock = Lock()
        self.folder = None
        self.process = None
        self.thread = None
        self.cancelled = False

    def read(self, folder):
        with self.lock:
            try:
                state = read_json(folder/'state.json')
            except FileNotFoundError as error:
                raise HTTPException(404, 'Surface job not found.') from error
            if state['status'] in ACTIVE and self.folder!=folder:
                # The workstation edge restarted before this job could publish artifacts.
                state.update(status='failed', error='Processing was interrupted by an edge restart.')
        if state['status']=='complete':
            state['reports'] = read_json(folder/'results'/'report.json')
        return state

    def start(self, job_root, request, inputs, is_rig, base):
        env = ROOT/'frontend'/'.cache'/'surface-env'
        default = env/'Scripts'/'python.exe' if os.name=='nt' else env/'bin'/'python'
        executable = Path(os.environ.get('SPACEGIT_SURFACE_PYTHON', default))
        if not executable.is_file():
            raise HTTPException(503, 'Install Open3D in the surface-worker environment first. See the setup guide.')
        with self.lock:
            if self.folder is not None:
                raise HTTPException(409, 'A surface job is already running. Wait for it or cancel it.')
            ident = uuid4().hex
            folder = job_root/ident
            output = folder/'staging'
            output.mkdir(parents=True)
            state = dict(id=ident, source=request.source, model=is_rig, action=request.action, status='queued',
                         slots=list(inputs), stage='Starting the Open3D worker', completed=0,
                         settings=request.settings.model_dump(), base=base.name if base else None)
            config = dict(sources={slot:str(path) for slot,path in inputs.items()}, output=str(output),
                          settings=state['settings'], camera_origin=is_rig, analysis_only=request.action=='analyse',
                          base=str(base/'results') if base else None)
            settings = folder/'job.json'
            settings.write_text(json.dumps(config), encoding='utf-8')
            save_state(folder, state)
            self.folder = folder
            self.cancelled = False
            self.thread = Thread(target=self.run, args=(executable, settings, state.copy()), daemon=True)
            self.thread.start()
            return state

    def cancel(self, folder):
        with self.lock:
            if self.folder!=folder:
                return
            self.cancelled = True
            if self.process and self.process.poll() is None:
                self.process.kill()

    def shutdown(self):
        folder = self.folder
        if folder:
            self.cancel(folder)
        if self.thread:
            self.thread.join(timeout=5)

    def run(self, executable, settings, state):
        folder = settings.parent
        output = folder/'staging'
        timer = None
        try:
            with self.lock:
                if self.cancelled:
                    raise RuntimeError('Processing cancelled.')
                env = {**os.environ, 'OMP_NUM_THREADS':'4', 'OPENBLAS_NUM_THREADS':'4', 'PYTHONUTF8':'1'}
                with (folder/'worker.log').open('w', encoding='utf-8') as log:
                    self.process = worker = subprocess.Popen(
                        [str(executable), str(ROOT/'reconstruction'/'surface_cli.py'), '--job', str(settings)],
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=log, text=True,
                        encoding='utf-8', errors='replace', env=env,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            timer = Timer(900, worker.kill)
            timer.daemon = True
            timer.start()
            with worker.stdout as stream:
                for line in stream:
                    try:
                        progress = json.loads(line)
                    except json.JSONDecodeError:
                        continue  # Open3D can also emit native diagnostics to stdout.
                    state.update(progress, status='running')
                    with self.lock:
                        save_state(folder, state)
            exit_status = worker.wait()
            with self.lock:
                if self.cancelled:
                    raise RuntimeError('Processing cancelled.')
                if exit_status:
                    with (folder/'worker.log').open('rb') as log:
                        log.seek(max(0, (folder/'worker.log').stat().st_size-8192))
                        lines = log.read().decode('utf-8', errors='replace').splitlines()
                    last = lines[-1] if lines else ''
                    if last.startswith('{"error":'):
                        raise RuntimeError(json.loads(last)['error'])
                    raise RuntimeError('The Open3D worker stopped. Check the worker log, or try a lower Poisson depth.')
                if not (output/'report.json').is_file():
                    raise RuntimeError('The Open3D worker returned no results.')
                output.rename(folder/'results')
                state.update(status='complete', completed=len(state['slots']), stage='Complete')
                save_state(folder, state)
        except (OSError, RuntimeError, ValueError) as error:
            state.update(status='cancelled' if self.cancelled else 'failed', error=str(error)[:450])
        finally:
            if timer:
                timer.cancel()
            with self.lock:
                if self.process and self.process.poll() is None:
                    self.process.kill()
                    self.process.wait()
                self.process = None
                try:
                    if state['status']!='complete':
                        shutil.rmtree(output, ignore_errors=True)
                        save_state(folder, state)
                finally:
                    self.folder = None


def routes(authorize, jobs):
    router = APIRouter(prefix='/api/v1/surfaces')

    @router.post('/inputs', status_code=201)
    async def upload(request: Request, runtime=Depends(authorize)):
        declared = request.headers.get('content-length', '0')
        if declared.isdecimal() and int(declared)>LIMIT:
            raise HTTPException(413, 'The input PLY exceeds 192 MiB.')
        if request.headers.get('content-type')!='application/octet-stream':
            raise HTTPException(415, 'Send the original PLY bytes.')
        ident = 'input-'+uuid4().hex
        folder = work_root(runtime)/'inputs'/ident
        folder.mkdir(parents=True)
        pending = folder/'upload.tmp'
        total = 0
        try:
            with pending.open('wb') as stream:
                async for chunk in request.stream():
                    total += len(chunk)
                    if total>LIMIT:
                        raise HTTPException(413, 'The input PLY exceeds 192 MiB.')
                    stream.write(chunk)
            with pending.open('rb') as stream:
                if stream.readline(6).rstrip(b'\r\n')!=b'ply':
                    raise HTTPException(422, 'Select a point-cloud PLY file.')
            pending.rename(folder/'original.ply')
        finally:
            if pending.exists():
                pending.unlink()
                folder.rmdir()
        return {'source': ident}

    @router.post('/jobs', status_code=202)
    def start(request: SurfaceRequest, runtime=Depends(authorize)):
        inputs, is_rig = sources(runtime, request.source)
        root = work_root(runtime)/'jobs'
        base = None
        if request.action=='smooth':
            if not request.base:
                raise HTTPException(422, 'Select a successful surface job for smoothing.')
            prior = jobs.read(root/request.base)
            if prior['status']!='complete' or prior['action']=='analyse' or prior['source']!=request.source:
                raise HTTPException(409, 'The selected result has no compatible surface.')
            base = root/(prior['base'] or prior['id'])
            settings = SurfaceSettings.model_validate(prior['settings']).model_copy(update={
                'smoothing':request.settings.smoothing, 'smoothing_intensity':request.settings.smoothing_intensity})
            request = request.model_copy(update={'settings':settings})
        return jobs.start(root, request, inputs, is_rig, base)

    @router.get('/sources/{source}/latest')
    def latest(source: Id, runtime=Depends(authorize)):
        root = work_root(runtime)/'jobs'
        match = None
        with jobs.lock:
            candidates = sorted(root.glob('*/state.json'), key=lambda path:path.stat().st_mtime, reverse=True)
            for path in candidates:
                state = read_json(path)
                if (state['source']==source and state['action']!='analyse' and state['status']=='complete'
                        and (state['action']!='smooth' or state.get('applied'))):
                    match = path.parent
                    break
        return jobs.read(match) if match else None

    @router.get('/jobs/{ident}')
    def status(ident: Id, runtime=Depends(authorize)):
        return jobs.read(work_root(runtime)/'jobs'/ident)

    @router.delete('/jobs/{ident}')
    def cancel(ident: Id, runtime=Depends(authorize)):
        folder = work_root(runtime)/'jobs'/ident
        jobs.read(folder)
        jobs.cancel(folder)
        return {'ok': True}

    @router.post('/jobs/{ident}/apply')
    def apply(ident: Id, runtime=Depends(authorize)):
        folder = work_root(runtime)/'jobs'/ident
        state = jobs.read(folder)
        if state['status']!='complete' or state['action']!='smooth':
            raise HTTPException(409, 'Only a finished smoothing preview can be applied.')
        with jobs.lock:
            record = read_json(folder/'state.json')
            record['applied'] = True
            save_state(folder, record)
        return {**state, 'applied': True}

    @router.get('/jobs/{ident}/views/{slot}/{artifact}')
    def artifact(ident: Id, slot: int, artifact: Literal['original', 'cleaned', 'mesh', 'report'], runtime=Depends(authorize)):
        root = work_root(runtime)/'jobs'
        folder = root/ident
        state = jobs.read(folder)
        if slot not in state['slots'] or state['status']!='complete' or state['action']=='analyse':
            raise HTTPException(404, 'This reconstruction artifact is unavailable.')
        if artifact=='original':
            path = sources(runtime, state['source'])[0][slot]
        else:
            if artifact=='cleaned' and state['base']:
                folder = root/state['base']
            path = folder/'results'/str(slot)/ARTIFACTS[artifact]
        if not path.is_file():
            raise HTTPException(404, 'This reconstruction artifact is missing.')
        return FileResponse(path, media_type='application/json' if artifact=='report' else 'application/octet-stream')

    return router
