"""Loopback-only musical timeline review and correction API."""
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .config import Settings
from .timelines import TimelineStore
from .playback import PlaybackLibrary
from scripts.setup_timeline import sha256

ASSETS = Path(__file__).with_name('web_assets')


def create_app(settings=None):
    settings = settings or Settings.from_env()
    store = TimelineStore(settings.data_root)
    listening = PlaybackLibrary(settings.data_root)
    app = FastAPI(title='AI-DJ timeline review', docs_url=None, redoc_url=None)
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
