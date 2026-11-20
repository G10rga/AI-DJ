"""Loopback API using the app's origin policy and existing catalog/upload adapter."""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.concurrency import run_in_threadpool
from .store import Projects


def router(workflow):
    routes = APIRouter(prefix='/api/v1/mix-projects'); store = Projects(workflow)
    async def body(request):
        raw = await request.body()
        if len(raw) > 256*1024: raise HTTPException(413, 'Project edit is too large')
        try:
            value = await request.json()
            if not isinstance(value, dict): raise ValueError()
            return value
        except (ValueError, TypeError): raise HTTPException(422, 'Expected a JSON object')
    async def call(fn, *args):
        try: return await run_in_threadpool(fn, *args)
        except KeyError: raise HTTPException(404, 'Project, song or artifact unavailable')
        except (ValueError, TypeError) as exc:
            raise HTTPException(409 if 'reload' in str(exc) else 422, str(exc))
    @routes.get('')
    async def index():
        return {'projects': store.list(), 'library': workflow.catalog()}
    @routes.post('')
    async def create(request: Request):
        value = await body(request)
        return await call(store.create, value.get('track_ids'), value.get('name', 'Untitled playlist'))
    @routes.get('/{identity}')
    async def read(identity: str): return await call(store.get, identity)
    @routes.patch('/{identity}')
    async def update(identity: str, request: Request):
        value = await body(request)
        return await call(store.mutate, identity, value.get('expected_revision'), 'update', value)
    @routes.post('/{identity}/{action}')
    async def action(identity: str, action: str, request: Request):
        value = await body(request)
        if action in ('auto', 'preview', 'export', 'reorder'):
            return await call(store.enqueue, identity, value.get('expected_revision'), action)
        if action in ('transition', 'reset', 'grid', 'restore'):
            return await call(store.mutate, identity, value.get('expected_revision'), action, value)
        if action == 'cancel':
            return await call(store.cancel, identity, value.get('expected_revision'), value.get('job_id'))
        raise HTTPException(404, 'Unknown project operation')
    @routes.get('/{identity}/jobs/{job_id}/media/{name}')
    async def media(identity: str, job_id: str, name: str, download: bool = False):
        path = await call(store.media, identity, job_id, name)
        return FileResponse(path, filename=path.name, content_disposition_type='attachment' if download else 'inline')
    @routes.get('/{identity}/source/{index}')
    async def original(identity: str, index: int, revision: int | None = None):
        path, name = await call(store.original, identity, index, revision)
        return FileResponse(path, filename=name, content_disposition_type='inline')
    return routes
