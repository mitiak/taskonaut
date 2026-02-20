from __future__ import annotations

from pydantic import BaseModel


class EchoInput(BaseModel):
    text: str


class EchoOutput(BaseModel):
    text: str


class AddInput(BaseModel):
    a: int
    b: int


class AddOutput(BaseModel):
    sum: int


def echo(payload: EchoInput) -> EchoOutput:
    return EchoOutput(text=payload.text)


def add(payload: AddInput) -> AddOutput:
    return AddOutput(sum=payload.a + payload.b)
