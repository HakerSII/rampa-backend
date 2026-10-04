import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.adapters.inbound.http.deps import UC, CurrentUser, OptionalUser
from app.adapters.inbound.http.errors import error_body
from app.domain.errors import DomainError
from app.domain.enums import LABELS_PL, CurrentState, FeatureKey, NeedsProfile, ObservationValue, Severity

router = APIRouter(tags=["ai"])


class ExpectedIn(BaseModel):
    element: str
    current_state: str | None = None


class ImageTagsIn(BaseModel):
    photo_ids: list[str]
    place_id: str | None = None
    expected: ExpectedIn | None = None  # F45: else the photos' upload metadata


class ImageAnalysisOut(BaseModel):
    real_place: bool
    barrier_detected: bool
    barrier_type: str
    affected_disabilities: list[str]
    description: str
    confidence: float


class TagOut(BaseModel):
    label: str
    feature: FeatureKey | None
    confidence: float


class SuggestedOut(BaseModel):
    element: FeatureKey
    current_state: CurrentState
    severity: Severity


class ImageTagsOut(BaseModel):
    analysis: ImageAnalysisOut
    tags: list[TagOut]
    detected: str
    suggested: SuggestedOut | None
    model: str


class ParseTextIn(BaseModel):
    text: str


class TextSuggestionOut(BaseModel):
    feature: FeatureKey
    label: str
    value: ObservationValue
    temporary: bool
    confidence: float


class ParseTextOut(BaseModel):
    suggestions: list[TextSuggestionOut]
    model: str


@router.post("/ai/parse-text", response_model=ParseTextOut)
async def parse_text(body: ParseTextIn, uc: UC, user: CurrentUser):
    """Description → suggested observations (rules, PL + EN, offline). Suggestion only."""
    return ParseTextOut(model="rules", suggestions=[
        TextSuggestionOut(feature=s.feature, label=LABELS_PL[s.feature], value=s.value, temporary=s.temporary,
                          confidence=s.confidence) for s in uc.parse_text(user, body.text)])


def _image_tags_out(r) -> ImageTagsOut:
    a = r.analysis
    return ImageTagsOut(
        analysis=ImageAnalysisOut(real_place=a.real_place, barrier_detected=a.barrier_detected,
                                  barrier_type=a.barrier_type, affected_disabilities=a.affected_disabilities,
                                  description=a.description, confidence=a.confidence),
        tags=[TagOut(label=t.label, feature=t.feature, confidence=t.confidence) for t in r.tags],
        detected=r.detected,
        suggested=SuggestedOut(element=r.suggested.element, current_state=r.suggested.current_state,
                               severity=r.suggested.severity) if r.suggested else None,
        model=r.model,
    )


@router.post("/ai/image-tags", response_model=ImageTagsOut)
async def image_tags(body: ImageTagsIn, uc: UC, user: CurrentUser):
    return _image_tags_out(await uc.analyze_image(user, body.photo_ids, body.place_id, expected=_expected(body)))


# ---------------------------------------------------------------- F44 streamed image check
KEEPALIVE_S = 10.0


def _expected(body: ImageTagsIn) -> dict | None:
    return body.expected.model_dump() if body.expected else None


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _event_stream(run) -> StreamingResponse:
    """SSE response: run(emit) emits (event, data) pairs and may return a last pair; keepalive comments while
    it works; any error after the start becomes an `error` event (the stream is never cut)."""
    queue: asyncio.Queue = asyncio.Queue()

    async def guarded():
        try:
            return await run(queue.put_nowait)
        except DomainError as e:
            error = {"code": e.code, "message": str(e)}
            if e.details:
                error["details"] = e.details
            return "error", {"error": error}
        except Exception:  # noqa: BLE001 — the stream already started: report, never cut it
            return "error", {"error": {"code": "INTERNAL_ERROR", "message": "request failed"}}

    async def events():
        task = asyncio.create_task(guarded())
        try:
            while True:
                getter = asyncio.create_task(queue.get())
                done, _ = await asyncio.wait({task, getter}, timeout=KEEPALIVE_S,
                                             return_when=asyncio.FIRST_COMPLETED)
                if getter in done:
                    yield _sse(*getter.result())
                    continue
                getter.cancel()
                if task in done:
                    while not queue.empty():
                        yield _sse(*queue.get_nowait())
                    last = task.result()
                    if last:
                        yield _sse(*last)
                    return
                yield ": keepalive\n\n"
        finally:
            task.cancel()

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/ai/image-tags/stream")
async def image_tags_stream(body: ImageTagsIn, uc: UC, user: CurrentUser):
    """Same check as /ai/image-tags, as Server-Sent Events: status (received, analyzing, fallback),
    keepalive comments while a slow model works, then result or error."""

    async def run(emit):
        emit(("status", {"stage": "received"}))
        r = await uc.analyze_image(user, body.photo_ids, body.place_id, on_step=lambda s: emit(("status", s)),
                                   expected=_expected(body))
        return "result", _image_tags_out(r).model_dump(mode="json")

    return _event_stream(run)


# ---------------------------------------------------------------- F46 chat assistant
class ChatIn(BaseModel):
    question: str = Field(min_length=1, max_length=500)


def _chat_disabled(request: Request) -> JSONResponse | None:
    if request.app.state.settings.chat_mode == "off":
        return JSONResponse(error_body("CHAT_DISABLED", "chat is disabled (CHAT_MODE=off)"), 503)
    return None


@router.get("/ai/chat/status")
async def chat_status(request: Request):
    """Chat model state: rules (no model) | loading | ready | error | off."""
    mode = request.app.state.settings.chat_mode
    status = request.app.state.chat.status()
    if mode == "off":
        status = {**status, "state": "off"}
    return {"mode": mode, **status}


@router.post("/ai/chat/stream")
async def chat_stream(body: ChatIn, request: Request, user: OptionalUser):
    """Ask the assistant (guest allowed): status, tool_call, tool_result, token events, then done or error."""
    disabled = _chat_disabled(request)
    if disabled:
        return disabled
    chat = request.app.state.chat

    async def run(emit):
        await chat.ask(body.question.strip(), emit)

    return _event_stream(run)


# ---------------------------------------------------------------- F30 recommendations
class RecommendIn(BaseModel):
    query: str
    profile: NeedsProfile | None = None
    lat: float | None = None
    lon: float | None = None
    limit: int = 5


class IntentOut(BaseModel):
    profiles: list[NeedsProfile]
    features: list[FeatureKey]
    categories: list[str]
    area: str | None


class RecReasonOut(BaseModel):
    feature: FeatureKey
    label: str
    state: str
    source: str | None
    last_verified: str | None


class RecPlaceOut(BaseModel):
    id: str
    name: str
    category: str
    address: str | None
    location: dict


class RecItemOut(BaseModel):
    place: RecPlaceOut
    match: str
    distance_m: int | None
    reasons: list[RecReasonOut]
    missing: list[FeatureKey]


class RecommendOut(BaseModel):
    intent: IntentOut
    items: list[RecItemOut]
    model: str
    note: str


@router.post("/ai/recommend", response_model=RecommendOut)
async def recommend(body: RecommendIn, uc: UC, user: OptionalUser):
    """Natural-language query → places from the database only, with reasons and missing data (guest allowed)."""
    r = await uc.recommend(user, body.query, body.profile, body.lat, body.lon, body.limit)
    i = r.intent
    return RecommendOut(
        intent=IntentOut(profiles=i.profiles, features=i.features, categories=i.categories, area=i.area),
        items=[RecItemOut(
            place=RecPlaceOut(id=x.place.id, name=x.place.name, category=x.place.category, address=x.place.address,
                              location={"lat": x.place.location.lat, "lon": x.place.location.lon}),
            match=x.match, distance_m=x.distance_m,
            reasons=[RecReasonOut(feature=c.feature, label=LABELS_PL[c.feature], state=str(c.state), source=c.source,
                                  last_verified=c.last_verified.isoformat() if c.last_verified else None)
                     for c in x.reasons],
            missing=x.missing) for x in r.items],
        model=r.model, note=r.note)
