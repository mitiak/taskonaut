from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class EchoInput(BaseModel):
    model_config = ConfigDict(strict=True)
    text: str


class EchoOutput(BaseModel):
    model_config = ConfigDict(strict=True)
    text: str


class AddInput(BaseModel):
    model_config = ConfigDict(strict=True)
    a: int
    b: int


class AddOutput(BaseModel):
    model_config = ConfigDict(strict=True)
    sum: int


def echo(payload: EchoInput) -> EchoOutput:
    return EchoOutput(text=payload.text)


def add(payload: AddInput) -> AddOutput:
    return AddOutput(sum=payload.a + payload.b)
