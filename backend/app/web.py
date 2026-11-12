"""Loopback-only musical timeline review and correction API."""
from pathlib import Path
from urllib.parse import urlsplit
from urllib.parse import unquote
from contextlib import asynccontextmanager
import json
from uuid import uuid4
from starlette.concurrency import run_in_threadpool
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .config import Settings
from .timelines import TimelineStore
from .playback import PlaybackLibrary
from .reference_review import ReferenceReviewStore
from .workflow import Workflow
from .workflow_manager import WorkflowManager
from .audio.probe import probe
from .library import EXTENSIONS
from scripts.setup_timeline import sha256

ASSETS = Path(__file__).with_name('web_assets')


def create_app(settings=None):
    settings = settings or Settings.from_env()
    store = TimelineStore(settings.data_root)
    listening = PlaybackLibrary(settings.data_root)
    references = ReferenceReviewStore(settings)
    workflow=Workflow(settings)
    @asynccontextmanager
    async def lifespan(app):
        manager=WorkflowManager(settings)
        manager.start()
        try:yield
        finally:manager.stop()
    app = FastAPI(title='AI-DJ local mixing', docs_url=None, redoc_url=None, lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]'])

    @app.middleware('http')
    async def local_requests(request: Request, call_next):
        origin = request.headers.get('origin')
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and origin:
            parsed = urlsplit(origin)
            if parsed.netloc != request.headers.get('host') or parsed.scheme != request.url.scheme:
                return JSONResponse({'detail': 'Cross-origin changes are not allowed'}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self'; img-src 'self' data:; font-src 'self'; frame-ancestors 'none'"
        return response

    @app.get('/')
    def home():
        return FileResponse(ASSETS/'mixes.html')

    @app.get('/mixes')
    def mixes_page():
        return FileResponse(ASSETS/'mixes.html')

    @app.get('/timelines')
    def timelines_page():
        return FileResponse(ASSETS/'index.html')

    @app.get('/references')
    def references_page():
        return FileResponse(ASSETS/'references.html')

    @app.get('/learning')
    def learning_page():
        return FileResponse(ASSETS/'learning.html')

    @app.get('/compare')
    def compare_page():
        return FileResponse(ASSETS/'compare.html')

    @app.get('/transition-review/{identity}')
    def transition_review_page(identity:str):
        return FileResponse(ASSETS/'transition-review.html')

    @app.get('/api/v1/comparisons')
    def comparisons_state():
        from .pair_comparisons import preferences,preference_model
        prefs=preferences(workflow)
        with workflow.db.connection() as c:
            identities=[r[0] for r in c.execute("SELECT id FROM workflow_jobs WHERE kind='pair_audition' ORDER BY rowid DESC LIMIT 30")]
        jobs=[workflow.job(identity) for identity in identities]
        for job in jobs:
            if job['payload'].get('pipeline')=='improved-transitions-1':
                from .transition_review import listening_state
                job['review']=listening_state(workflow,job['id'])
            else: job['review']=prefs.review_state(job['id'])
        from .transition_review import pipeline
        return {'library':workflow.catalog(),'jobs':jobs,'model':preference_model(workflow),'default_pipeline':pipeline(workflow)}

    @app.post('/api/v1/comparisons')
    async def enqueue_comparison(request:Request):
        from .pair_comparisons import enqueue_pair
        try:
            payload=await workflow_payload(request)
            return enqueue_pair(workflow,payload.get('track_ids'),payload.get('use_preferences',False),payload.get('pipeline'))
        except (ValueError,TypeError,KeyError) as exc:raise HTTPException(422,str(exc))

    @app.get('/api/v1/comparisons/{identity}/audio/{slot}')
    def comparison_audio(identity:str,slot:str,download:bool=False):
        from .pair_comparisons import comparison_audio
        try:
            path=comparison_audio(workflow,identity,slot)
            return FileResponse(path,media_type='audio/mpeg',filename=path.name,
                content_disposition_type='attachment' if download else 'inline')
        except (KeyError,OSError):raise HTTPException(404,'Comparison audio unavailable')
        except ValueError as exc:raise HTTPException(409,str(exc))

    @app.post('/api/v1/comparisons/{identity}/feedback')
    async def comparison_feedback(identity:str,request:Request):
        from .pair_comparisons import save_feedback
        try:
            payload=await workflow_payload(request)
            return await run_in_threadpool(save_feedback,workflow,identity,payload.get('choice'),
                payload.get('expected_revision'),payload.get('notes',''))
        except (KeyError,OSError):raise HTTPException(404,'Completed comparison unavailable')
        except (ValueError,TypeError) as exc:raise HTTPException(409 if 'reload' in str(exc) else 422,str(exc))

    @app.get('/api/v1/learning/state')
    def learning_state(draft_id: str | None = None):
        try:
            library=workflow.reviews.list()
            chosen=draft_id or next((r['draft_id'] for r in library if r['draft_id']),None)
            songs=workflow.catalog()
            defaults=[]
            if chosen:
                for track in workflow.reviews.batch(chosen)['tracks'][:2]:
                    digest=track.get('source_hash') or (track['sources'][0]['content_hash'] if track['sources'] else None)
                    source=next((s for s in songs if s['content_hash']==digest),None)
                    if source:defaults.append(source['id'])
            from .transition_review import pipeline
            return {'references':library,'readiness':workflow.readiness(chosen) if chosen else None,'default_pipeline':pipeline(workflow),
                    'models':workflow.models(),'jobs':workflow.jobs(),'library':songs,'default_track_ids':defaults}
        except KeyError:
            raise HTTPException(404,'Reference draft not found')

    async def workflow_payload(request):
        if len(await request.body())>64*1024:raise HTTPException(413,'Request is too large')
        payload=await request.json()
        if not isinstance(payload,dict):raise ValueError('Expected a workflow request')
        return payload

    @app.post('/api/v1/learning/train')
    async def train_from_reviews(request:Request):
        try:
            payload=await workflow_payload(request)
            return workflow.enqueue_train(payload.get('draft_id'))
        except KeyError:raise HTTPException(404,'Reference draft not found')
        except (ValueError,TypeError) as exc:raise HTTPException(422,str(exc))

    @app.post('/api/v1/learning/test-mixes')
    async def generate_test_mix(request:Request):
        try:
            payload=await workflow_payload(request)
            return workflow.enqueue_test(payload.get('model_id'),payload.get('track_ids'),
                                         payload.get('seconds',72),payload.get('baseline',False),payload.get('pipeline'))
        except KeyError:raise HTTPException(404,'Selected model or song is unavailable')
        except (ValueError,TypeError) as exc:raise HTTPException(422,str(exc))

    @app.get('/api/v1/learning/jobs/{identity}/transition-review')
    def transition_review_state(identity:str):
        from .transition_review import state
        try: return state(workflow,identity)
        except KeyError: raise HTTPException(404,'Review unavailable')
        except ValueError as exc: raise HTTPException(409,str(exc))

    @app.post('/api/v1/learning/jobs/{identity}/transition-review/{action}')
    async def transition_review_action(identity:str,action:str,request:Request):
        from .transition_review import save,enqueue,choose_default
        try:
            payload=await workflow_payload(request)
            if action=='save': return save(workflow,identity,payload.get('expected_revision'),payload.get('corrections'))
            if action=='preview':
                if type(payload.get('join_index')) is not int: raise ValueError('Choose a valid transition')
                return enqueue(workflow,identity,payload.get('expected_revision'),join_index=payload['join_index'])
            if action=='resume': return enqueue(workflow,identity,payload.get('expected_revision'))
            if action=='make-default': return choose_default(workflow,identity,payload.get('approved'))
            raise HTTPException(404,'Review action unavailable')
        except KeyError: raise HTTPException(404,'Review unavailable')
        except (ValueError,TypeError) as exc: raise HTTPException(409 if 'reload' in str(exc) else 422,str(exc))

    @app.get('/api/v1/learning/jobs/{identity}/transition-review/sources/{index}/audio')
    def transition_original(identity:str,index:int):
        from .transition_review import source_audio
        try: return FileResponse(source_audio(workflow,identity,index))
        except (KeyError,OSError): raise HTTPException(404,'Original unavailable')
        except ValueError as exc: raise HTTPException(409,str(exc))

    @app.get('/api/v1/learning/jobs/{identity}/audio/{slot}')
    def improved_job_audio(identity:str,slot:str,download:bool=False):
        from .transition_review import media
        try:
            path=media(workflow,identity,slot)
            return FileResponse(path,media_type='audio/mpeg',filename=path.name,
                                content_disposition_type='attachment' if download else 'inline')
        except (KeyError,OSError): raise HTTPException(404,'Validated audio unavailable')
        except ValueError as exc: raise HTTPException(409,str(exc))

    @app.post('/api/v1/learning/library')
    async def import_learning_song(request:Request):
        destination=None
        try:
            name=Path(unquote(request.headers.get('x-file-name',''),errors='strict').replace('\\','/')).name
            if not name or len(name)>240 or any(ord(c)<32 for c in name) or Path(name).suffix.lower() not in EXTENSIONS:
                raise ValueError('Choose a supported MP3, WAV, FLAC, M4A, AIFF or OGG song')
            length=int(request.headers.get('content-length','0'))
            if not 0<=length<=settings.max_upload_bytes:raise HTTPException(413,'Song exceeds the upload size limit')
            workflow.storage.require_space(length,settings.min_free_bytes)
            destination=workflow.storage.new_upload_path();size=0
            with destination.open('wb') as stream:
                async for chunk in request.stream():
                    size+=len(chunk)
                    if size>settings.max_upload_bytes:raise HTTPException(413,'Song exceeds the upload size limit')
                    stream.write(chunk)
            def register():
                info=probe(destination,settings)
                if not 2<=info.duration<=1200:raise ValueError('Choose an original song between 2 seconds and 20 minutes')
                digest=sha256(destination);identity='upload-'+uuid4().hex
                with workflow.db.connection() as c:
                    c.execute('INSERT INTO tracks(id,content_hash,original_name,storage_name,metadata_json) VALUES (?,?,?,?,?)',
                        (identity,digest,name,'external:'+identity,json.dumps({'external_path':str(destination)})))
                import hashlib
                catalog_id=hashlib.sha256((digest+':'+str(destination.resolve())).encode()).hexdigest()[:24]
                return {'id':catalog_id,'imported':name,'duration_seconds':info.duration}
            result=await run_in_threadpool(register)
            destination=None
            return result
        except (ValueError,OSError,RuntimeError) as exc:raise HTTPException(422,str(exc))
        finally:
            if destination is not None:destination.unlink(missing_ok=True)

    @app.post('/api/v1/learning/jobs/{identity}/cancel')
    def cancel_workflow(identity:str):
        try:return workflow.cancel(identity)
        except KeyError:raise HTTPException(404,'Job not found')

    @app.post('/api/v1/learning/jobs/{identity}/retry')
    def retry_workflow(identity:str):
        try:return workflow.retry(identity)
        except KeyError:raise HTTPException(404,'Job not found')
        except ValueError as exc:raise HTTPException(422,str(exc))

    @app.get('/api/v1/learning/jobs/{identity}/log')
    def workflow_log(identity:str):
        try:
            workflow.job(identity)
            path=settings.data_root/'tmp'/('workflow-'+identity)/'job.log'
            if not path.is_file():raise KeyError(identity)
            return FileResponse(path,media_type='text/plain',filename='mixing-job.log')
        except KeyError:raise HTTPException(404,'Job log is not available yet')

    @app.get('/api/v1/references')
    def reference_list():
        return {'references': references.list()}

    @app.get('/api/v1/reference-drafts/{draft_id}')
    def reference_batch(draft_id: str):
        try:
            return references.batch(draft_id)
        except KeyError:
            raise HTTPException(404, 'Reference draft not found')

    @app.post('/api/v1/reference-drafts/{draft_id}/transitions/{position}/reviews')
    async def reference_review(draft_id: str, position: int, request: Request):
        if len(await request.body()) > 128*1024:
            raise HTTPException(413, 'Review is too large')
        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                raise ValueError('Expected a review object')
            return references.save(draft_id, position, payload.get('expected_revision'), payload.get('review'))
        except KeyError:
            raise HTTPException(404, 'Reference draft or transition not found')
        except (ValueError, TypeError) as exc:
            raise HTTPException(409 if 'reload' in str(exc) else 422, str(exc))

    @app.get('/api/v1/reference-drafts/{draft_id}/analysis')
    def transition_analysis_state(draft_id: str):
        try:return workflow.analysis_state(draft_id)
        except KeyError:raise HTTPException(404,'Reference draft not found')

    @app.post('/api/v1/reference-drafts/{draft_id}/analysis')
    async def analyze_transitions(draft_id: str, request: Request):
        try:
            payload=await workflow_payload(request)
            return workflow.enqueue_analysis(draft_id,payload.get('position'),payload.get('expected_revision'))
        except KeyError:raise HTTPException(404,'Reference draft not found')
        except (ValueError,TypeError) as exc:
            raise HTTPException(409 if 'reload' in str(exc) else 422,str(exc))

    @app.get('/api/v1/reference-drafts/{draft_id}/training-examples')
    def reference_examples(draft_id: str):
        try:
            return JSONResponse(references.export(draft_id), headers={
                'Content-Disposition': 'attachment; filename="reviewed-reference-decisions.json"'})
        except KeyError:
            raise HTTPException(404, 'Reference draft not found')

    @app.get('/api/v1/references/{reference_id}/audio')
    def reference_recording(reference_id: str):
        try:
            return FileResponse(references.audio(reference_id))
        except (KeyError, OSError):
            raise HTTPException(404, 'Reference recording is unavailable')
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    @app.get('/api/v1/references/{reference_id}/sources/{position}/{digest}/audio')
    def reference_source(reference_id: str, position: int, digest: str):
        try:
            return FileResponse(references.audio(reference_id, position, digest))
        except (KeyError, OSError):
            raise HTTPException(404, 'Reference source is unavailable')
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    @app.get('/api/v1/mixes')
    def mixes():
        return {'mixes': listening.mixes()}

    @app.get('/api/v1/auditions')
    def auditions():
        return {'auditions': listening.auditions()}

    @app.get('/api/v1/mixes/{mix_id}/audio')
    def mix_audio(mix_id: str, download: bool = False, revision: int | None = None):
        try:
            path = listening.mix_audio(mix_id, revision)
            return FileResponse(path, media_type='audio/mpeg', filename=path.name,
                                content_disposition_type='attachment' if download else 'inline')
        except (KeyError, OSError):
            raise HTTPException(404, 'Rendered mix is unavailable')

    @app.get('/api/v1/auditions/{event_id}/audio')
    def audition_audio(event_id: int, download: bool = False):
        try:
            path = listening.audition_audio(event_id)
            return FileResponse(path, media_type='audio/mpeg', filename=path.name,
                                content_disposition_type='attachment' if download else 'inline')
        except (KeyError, OSError):
            raise HTTPException(404, 'Audition is unavailable')

    @app.get('/api/v1/tracks')
    def tracks():
        return {'tracks': store.tracks()}

    @app.get('/api/v1/tracks/{track_id}/timelines/{timeline_id}')
    def timeline(track_id: str, timeline_id: str):
        try:
            return store.get(track_id, timeline_id)
        except KeyError:
            raise HTTPException(404, 'Timeline not found')

    @app.post('/api/v1/tracks/{track_id}/timelines/{timeline_id}/corrections')
    async def correct(track_id: str, timeline_id: str, request: Request):
        body = await request.body()
        if len(body) > 1024*1024:
            raise HTTPException(413, 'Correction is too large')
        try:
            payload = await request.json()
            return store.correct(track_id, timeline_id, payload['expected_revision'], payload['changes'], payload.get('note', ''))
        except KeyError:
            raise HTTPException(404, 'Timeline or required field not found')
        except (ValueError, TypeError) as exc:
            raise HTTPException(409 if 'reload' in str(exc) else 422, str(exc))

    @app.get('/api/v1/tracks/{track_id}/audio')
    def audio(track_id: str):
        try:
            source, digest = store.source(track_id)
            if sha256(source) != digest:
                raise HTTPException(409, 'Source audio changed; analyze it again')
            return FileResponse(source)
        except (KeyError, OSError):
            raise HTTPException(404, 'Source audio is unavailable')

    app.mount('/assets', StaticFiles(directory=ASSETS), name='assets')
    return app
