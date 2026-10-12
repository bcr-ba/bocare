"""OpenTelemetry tracing: one trace per patient message, one span per pipeline stage.

Privacy rule: span attributes hold numbers, codes and model names, never the patient's text or
the generated answer. tests/unit/test_tracing.py enforces it.

Exporters (settings.yml `tracing_exporter`): "none", "console" (prints spans) or "otlp" (sends
them to a collector such as Jaeger, see docker-compose.yml).
"""
from contextlib import contextmanager
from typing import Any, Iterator, Optional

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.trace import Span

from app.core.settings import Settings

tracer = trace.get_tracer("bocare")
_configured = False


def configure_tracing(settings: Settings) -> None:
    """Install the exporter chosen in settings. Without it, spans are no-ops that cost nothing."""
    global _configured
    if _configured or settings.tracing_exporter == "none":
        return
    provider = TracerProvider(resource=Resource.create({"service.name": settings.tracing_service_name}))
    if settings.tracing_exporter == "console":
        exporter = ConsoleSpanExporter()
    else:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        exporter = OTLPSpanExporter(endpoint=settings.tracing_otlp_endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _configured = True


def set_attributes(target: Span, **attributes: Any) -> None:
    """Set attributes, skipping None. Lists must hold one type (OpenTelemetry's rule)."""
    for key, value in attributes.items():
        if value is not None:
            target.set_attribute(key, list(value) if isinstance(value, (list, tuple, set)) else value)


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[Span]:
    """A child of the current span. Exceptions are recorded on it automatically."""
    with tracer.start_as_current_span(name) as current:
        set_attributes(current, **attributes)
        yield current


def start_root(name: str, **attributes: Any) -> Span:
    """A span that is passed around explicitly instead of through the context. Used by the
    streaming endpoint, whose steps run on different threads between events."""
    root = tracer.start_span(name)
    set_attributes(root, **attributes)
    return root


@contextmanager
def within(root: Optional[Span]) -> Iterator[None]:
    """Make `root` the current span for one synchronous step, so the spans it opens become its
    children. Never keep this open across a `yield`."""
    if root is None:
        yield
        return
    with trace.use_span(root, end_on_exit=False):
        yield
