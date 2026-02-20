from __future__ import annotations

import logging
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.orm import Session

from taskrunner.db import get_db
from taskrunner.log_config import configure_logging
from taskrunner.schemas import TaskCreateRequest, TaskResponse
from taskrunner.service import TaskNotFoundError, TaskRunnerService

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Task Runner", version="0.1.0")


@app.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(request: TaskCreateRequest, db: Session = Depends(get_db)) -> TaskResponse:
    logger.info(
        "create_task.started",
        extra={"text": request.text, "a": request.a, "b": request.b},
    )
    service = TaskRunnerService(db)
    task = service.run_predefined_flow(request)
    logger.info("create_task.succeeded", extra={"task_id": str(task.id)})
    return TaskResponse.model_validate(task)


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: UUID, db: Session = Depends(get_db)) -> TaskResponse:
    service = TaskRunnerService(db)
    try:
        task = service.get_task(task_id)
    except TaskNotFoundError as exc:
        logger.warning("get_task.not_found", extra={"task_id": str(task_id)})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    logger.info("get_task.succeeded", extra={"task_id": str(task_id)})
    return TaskResponse.model_validate(task)
