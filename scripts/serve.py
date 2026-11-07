"""Serve the local musical timeline editor."""
import uvicorn
from backend.app.config import Settings
from backend.app.web import create_app


def main():
    settings = Settings.from_env()
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == '__main__':
    main()
