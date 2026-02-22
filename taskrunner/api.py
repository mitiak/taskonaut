from __future__ import annotations

import logging
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.orm import Session

from taskrunner.db import get_db
from taskrunner.log_config import configure_logging
from taskrunner.schemas import RunTaskRequest, TaskCreateRequest, TaskResponse
from taskrunner.service import (
    InvalidFlowError,
    MaxStepsExceededError,
    TaskNotFoundError,
    TaskRunnerService,
)

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
    try:
        task = service.create_task(request)
    except InvalidFlowError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    logger.info("create_task.succeeded", extra={"task_id": str(task.id)})
    return TaskResponse.model_validate(task)


@app.post("/tasks/{task_id}/advance", response_model=TaskResponse)
def advance_task(task_id: UUID, db: Session = Depends(get_db)) -> TaskResponse:
    service = TaskRunnerService(db)
    try:
        task = service.advance_task(task_id)
    except TaskNotFoundError as exc:
        logger.warning("advance_task.not_found", extra={"task_id": str(task_id)})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    logger.info(
        "advance_task.succeeded",
        extra={"task_id": str(task_id), "status": task.status.value},
    )
    return TaskResponse.model_validate(task)


@app.post("/tasks/{task_id}/run", response_model=TaskResponse)
def run_task(
    task_id: UUID,
    request: RunTaskRequest,
    db: Session = Depends(get_db),
) -> TaskResponse:
    service = TaskRunnerService(db)
    try:
        task = service.run_task(task_id, request.max_steps)
    except TaskNotFoundError as exc:
        logger.warning("run_task.not_found", extra={"task_id": str(task_id)})
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except MaxStepsExceededError as exc:
        logger.warning(
            "run_task.max_steps_exceeded",
            extra={"task_id": str(task_id), "max_steps": request.max_steps},
        )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    logger.info(
        "run_task.succeeded",
        extra={"task_id": str(task_id), "status": task.status.value},
    )
    return TaskResponse.model_validate(task)


@app.get("/tasks", response_model=list[TaskResponse])
def list_tasks(db: Session = Depends(get_db)) -> list[TaskResponse]:
    service = TaskRunnerService(db)
    tasks = service.list_tasks()
    logger.info("list_tasks.succeeded", extra={"count": len(tasks)})
    return [TaskResponse.model_validate(task) for task in tasks]


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
