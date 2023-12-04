import os

import requests
import uvicorn
import yaml
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from llmstudio.engine.providers import *
from llmstudio.tracking import crud, models, schemas
from llmstudio.tracking.database import SessionLocal, engine

models.Base.metadata.create_all(bind=engine)

TRACKING_HEALTH_ENDPOINT = "/health"
TRACKING_TITLE = "LLMstudio Tracking API"
TRACKING_DESCRIPTION = "The tracking API for LLM interactions"
TRACKING_VERSION = "0.0.1"
TRACKING_HOST = os.getenv("TRACKING_HOST", "localhost")
TRACKING_PORT = int(os.getenv("TRACKING_PORT", 8080))
TRACKING_URL = f"http://{TRACKING_HOST}:{TRACKING_PORT}"
TRACKING_BASE_ENDPOINT = "/api/tracking"


## Tracking
def create_tracking_app() -> FastAPI:
    app = FastAPI(
        title=TRACKING_TITLE,
        description=TRACKING_DESCRIPTION,
        version=TRACKING_VERSION,
    )

    # Dependency
    def get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    @app.get(TRACKING_HEALTH_ENDPOINT)
    def health_check():
        """Health check endpoint to ensure the API is running."""
        return {"status": "healthy", "message": "Tracking is up and running"}

    @app.post(f"{TRACKING_BASE_ENDPOINT}/projects/", response_model=schemas.Project)
    def create_project(project: schemas.ProjectCreate, db: Session = Depends(get_db)):
        db_project = crud.get_project_by_name(db, name=project.name)
        if db_project:
            raise HTTPException(status_code=400, detail="Project already registered")
        return crud.create_project(db=db, project=project)

    @app.get(
        f"{TRACKING_BASE_ENDPOINT}/projects/", response_model=list[schemas.Project]
    )
    def read_projects(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
        projects = crud.get_projects(db, skip=skip, limit=limit)
        return projects

    @app.get(
        f"{TRACKING_BASE_ENDPOINT}/projects/{{project_id}}",
        response_model=schemas.Project,
    )
    def read_project(project_id: int, db: Session = Depends(get_db)):
        db_project = crud.get_project(db, project_id=project_id)
        if db_project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return db_project

    @app.post(
        f"{TRACKING_BASE_ENDPOINT}/projects/{{project_id}}/sessions/",
        response_model=schemas.Session,
    )
    def create_session(
        project_id: int, session: schemas.SessionCreate, db: Session = Depends(get_db)
    ):
        return crud.create_session(db=db, session=session, project_id=project_id)

    @app.get(
        f"{TRACKING_BASE_ENDPOINT}/sessions/", response_model=list[schemas.Session]
    )
    def read_sessions(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
        sessions = crud.get_sessions(db, skip=skip, limit=limit)
        return sessions

    @app.post(
        f"{TRACKING_BASE_ENDPOINT}/logs/",
        response_model=schemas.LogDefault,
    )
    def add_log(log: schemas.LogDefaultCreate, db: Session = Depends(get_db)):
        return crud.add_log(db=db, log=log)

    @app.get(f"{TRACKING_BASE_ENDPOINT}/logs/", response_model=list[schemas.LogDefault])
    def read_logs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
        logs = crud.get_logs(db, skip=skip, limit=limit)
        return logs

    return app


def is_api_running(url: str) -> bool:
    try:
        response = requests.get(url, timeout=5)
        return response.status_code == 200
    except requests.RequestException:
        return False


def run_tracking_app():
    print(f"Running Tracking on {TRACKING_HOST}:{TRACKING_PORT}")
    try:

        tracking = create_tracking_app()
        uvicorn.run(
            tracking,
            host=TRACKING_HOST,
            port=TRACKING_PORT,
        )
    except Exception as e:
        print(f"Error running the Tracking app: {e}")
