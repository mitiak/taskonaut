from __future__ import annotations

from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy.orm import Session

from taskrunner.db import get_db
from taskrunner.schemas import TaskCreateRequest, TaskResponse
from taskrunner.service import TaskNotFoundError, TaskRunnerService

app = FastAPI(title="Task Runner", version="0.1.0")


@app.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(request: TaskCreateRequest, db: Session = Depends(get_db)) -> TaskResponse:
    service = TaskRunnerService(db)
    task = service.run_predefined_flow(request)
    return TaskResponse.model_validate(task)


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: UUID, db: Session = Depends(get_db)) -> TaskResponse:
    service = TaskRunnerService(db)
    try:
        task = service.get_task(task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return TaskResponse.model_validate(task)
