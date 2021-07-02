# Copyright 2021 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import contextlib
import os
from dataclasses import dataclass
from typing import Callable, Iterator, Mapping

import pydantic
from google.rpc import code_pb2
from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
from opentelemetry.propagators.cloud_trace_propagator import (
    CloudTraceFormatPropagator,
)
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ALWAYS_ON
from opentelemetry.trace import SpanKind, Tracer

from .constants import INSTRUMENTING_MODULE_NAME, TEST_ID


class Request(pydantic.BaseModel):
    test_id: str
    headers: Mapping[str, str]
    data: bytes


@dataclass
class Response:
    status_code: code_pb2.Code
    data: bytes = bytes()


@contextlib.contextmanager
def _tracer_setup() -> Iterator[Tracer]:
    """\
    Context manager with common setup for tracing endpoints

    Yields a tracer (from a fresh SDK with new exporter) then finally flushes
    spans created during the test after.
    """

    tracer_provider = TracerProvider(
        sampler=ALWAYS_ON,
        active_span_processor=BatchSpanProcessor(
            CloudTraceSpanExporter(project_id=os.environ.get("PROJECT_ID"))
        ),
    )
    tracer = tracer_provider.get_tracer(INSTRUMENTING_MODULE_NAME)

    try:
        yield tracer
    finally:
        tracer_provider.shutdown()


def health(request: Request) -> Response:
    return Response(status_code=code_pb2.OK)


def basic_trace(request: Request) -> Response:
    """Create a basic trace"""

    with _tracer_setup() as tracer:
        with tracer.start_span(
            "basicTrace", attributes={TEST_ID: request.test_id}
        ):
            pass

    return Response(status_code=code_pb2.OK)


def complex_trace(request: Request) -> Response:
    """Create a complex trace"""

    with _tracer_setup() as tracer:
        with tracer.start_as_current_span(
            "complexTrace/root", attributes={TEST_ID: request.test_id}
        ):
            with tracer.start_as_current_span(
                "complexTrace/child1",
                attributes={TEST_ID: request.test_id},
                kind=SpanKind.SERVER,
            ):
                with tracer.start_as_current_span(
                    "complexTrace/child2",
                    attributes={TEST_ID: request.test_id},
                    kind=SpanKind.CLIENT,
                ):
                    pass
            with tracer.start_as_current_span(
                "complexTrace/child3",
                attributes={TEST_ID: request.test_id},
            ):
                pass

    return Response(status_code=code_pb2.OK)


def basic_propagator(request: Request) -> Response:
    """Create a trace, using the Cloud Trace format propagator"""

    with _tracer_setup() as tracer:
        propagator = CloudTraceFormatPropagator()
        context = propagator.extract(request.headers)
        with tracer.start_span(
            "basicPropagator",
            attributes={TEST_ID: request.test_id},
            context=context,
        ):
            pass

    return Response(status_code=code_pb2.OK)


def not_implemented_handler(_: Request) -> Response:
    return Response(status_code=str(code_pb2.UNIMPLEMENTED))


SCENARIO_TO_HANDLER: dict[str, Callable[[Request], Response]] = {
    "/health": health,
    "/basicTrace": basic_trace,
    "/complexTrace": complex_trace,
    "/basicPropagator": basic_propagator,
}
