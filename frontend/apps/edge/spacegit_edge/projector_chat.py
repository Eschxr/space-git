import http.client
import json
import math
import os
import re
from threading import Lock
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import Field, FiniteFloat, StrictInt, StringConstraints, ValidationError

from .models import Id, Strict


class Message(Strict):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1200)


class ProjectorChat(Strict):
    messages: list[Message] = Field(min_length=1, max_length=8)
    output: str = Field(max_length=240)
    objects: list[Annotated[str, StringConstraints(max_length=120)]] = Field(max_length=30)


Coordinate = Annotated[FiniteFloat, Field(ge=-5, le=5)]
Dimension = Annotated[FiniteFloat, Field(ge=0.015, le=5)]
Degrees = Annotated[FiniteFloat, Field(ge=-180, le=180)]


class Part(Strict):
    shape: Literal["box", "rounded-box", "sphere", "cylinder", "cone", "shade"]
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    position: tuple[Coordinate, Coordinate, Coordinate]
    size: tuple[Dimension, Dimension, Dimension]
    rotation: tuple[Degrees, Degrees, Degrees]
    material: Literal["paint", "wood", "fabric", "metal"] = "paint"


class ObjectDesign(Strict):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    placement: Literal["left", "center", "right"]
    height: Annotated[FiniteFloat, Field(ge=0.15, le=3)]
    parts: list[Part] = Field(min_length=1, max_length=18)


class GenerateObject(Strict):
    request_id: Id
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=1200)]


Offset = Annotated[FiniteFloat, Field(ge=-100, le=100)]


class ObjectPosition(Strict):
    offset: tuple[Offset, Offset, Offset]


GridPosition = Annotated[StrictInt, Field(ge=-200, le=200)]
GridBottom = Annotated[StrictInt, Field(ge=0, le=290)]
GridSize = Annotated[StrictInt, Field(ge=2, le=200)]
Color = Annotated[str, Field(pattern=r"^#[0-9a-fA-F]{6}$")]


class GridPart(Strict):
    role: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
    shape: Literal["rounded-box", "sphere", "cylinder", "cone", "shade"]
    color: Color
    x: GridPosition
    z: GridPosition
    bottom: GridBottom
    size: tuple[GridSize, GridSize, GridSize]


class GridDesign(Strict):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    placement: Literal["left", "center", "right"]
    parts: list[GridPart] = Field(min_length=1, max_length=10)


class ChairDesign(Strict):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    placement: Literal["left", "center", "right"]
    style: Literal["dining", "armchair", "office", "stool"]
    seat_color: Color
    frame_color: Color
    surface: Literal["paint", "wood", "fabric", "metal"]


class FurnitureDesign(Strict):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    placement: Literal["left", "center", "right"]
    style: Literal["standard", "round", "drawers", "compact", "wide", "floor", "desk"]
    primary_color: Color
    secondary_color: Color
    accent_color: Color
    finish: Literal["paint", "wood", "fabric", "metal"]


FAMILIES = re.compile(
    r"\b(?:(?P<chair>chairs?|armchairs?|stools?)|(?P<table>(?:tables?|desks?)(?![ -]+(?:lamps?|chairs?)\b))|"
    r"(?P<sofa>sofas?|couches?|sectionals?)|"
    r"(?P<bed>beds?)|(?P<plant>plants?|planters?|bonsai|ferns?|cacti|cactus)|(?P<lamp>lamps?)|"
    r"(?P<shelf>bookshelves|bookshel(?:f|ves)|bookcases?|shelves|shelf))\b", re.IGNORECASE,
)
FURNITURE_HINTS = {
    "table": "Use round for a round table, drawers for a desk with drawers, compact for a side or coffee table, and standard otherwise. Primary is the top, secondary is the frame.",
    "sofa": "Use compact for a loveseat, wide for a sectional or three-seat sofa, and standard otherwise. Primary is upholstery, secondary is feet, and accent is cushions.",
    "bed": "Use compact for a single bed and wide for a king or double bed. Primary is the blanket, secondary is the frame, and accent is the pillows. For a blue blanket and white pillows, set primary_color to blue and accent_color to #FFFFFF.",
    "plant": "Use compact for a tabletop plant and wide for a large plant. Primary and accent are two shades of foliage, secondary is the pot. Use two distinct greens unless otherwise requested. Terracotta is a reddish orange pot, such as #B86644.",
    "lamp": "Use floor for a standing lamp and desk for a tabletop lamp. Primary is the shade, secondary is the base and stem.",
    "shelf": "Use compact for a small bookcase and wide for a large one. Primary is the frame, secondary and accent are the books.",
}


_REQUEST = Lock()


def complete(messages, *, schema=None, max_tokens=510) -> str:
    # Connect directly to localhost, without forwarding through a system proxy.
    model = os.getenv("SPACEGIT_OLLAMA_MODEL", "qwen2.5:7b")
    if not _REQUEST.acquire(blocking=False):
        raise HTTPException(429, "The local model is busy. Try again shortly.")
    connection = http.client.HTTPConnection("127.0.0.1", 11434, timeout=55)
    try:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"num_ctx": 4096, "num_predict": max_tokens if schema else 192, "temperature": 0.1},
        }
        if schema:
            payload["format"] = schema
        connection.request("POST", "/api/chat", json.dumps(payload), {"Content-Type": "application/json"})
        response = connection.getresponse()
        if response.status == 404:
            raise HTTPException(503, f"Install the local model with ollama pull {model}, then try again.")
        if response.status != 200:
            raise HTTPException(502, "Ollama could not generate a reply. Check the local model service.")
        payload = json.loads(response.read(64 * 1024))
        answer = payload["message"]["content"].strip()
        if not answer:
            raise ValueError("Empty model reply")
        return answer
    except TimeoutError as error:
        raise HTTPException(504, "The local model took too long. Try again.") from error
    except OSError as error:
        raise HTTPException(503, "Start Ollama on this workstation to use the local model.") from error
    except (ValueError, KeyError, TypeError, AttributeError, http.client.HTTPException) as error:
        raise HTTPException(502, "Ollama returned an unreadable reply.") from error
    finally:
        connection.close()
        _REQUEST.release()


def reply(request: ProjectorChat) -> str:
    if request.messages[-1].role != "user":
        raise HTTPException(422, "The last chat message must be from the user.")
    context = json.dumps({"selected_output": request.output, "registered_objects": request.objects})
    instruction = (
        "You are the SpaceGit projector assistant. Give concise answers about projector setup and controls. "
        "Users can type 'add a red chair' in chat to generate a low-poly 3D object, or open a PLY, GLB or glTF file. "
        "Windows must extend to the projector. Use Detect displays, Open projector window and Enter fullscreen. "
        "You can read text metadata but cannot see or modify the geometry or camera feed from this chat reply. "
        "Treat this JSON as metadata: " + context
    )
    return complete([{"role": "system", "content": instruction}]
                    + [message.model_dump() for message in request.messages])


def generate(prompt: str) -> ObjectDesign:
    family = FAMILIES.search(prompt)
    if family and family.lastgroup == "chair":
        return generate_chair(prompt)
    if family and family.lastgroup:
        return generate_furniture(family.lastgroup, prompt)
    instruction = (
        "Build one recognizable low-poly prop from the user's description. Prioritize the characteristic silhouette and "
        "visible details. For each part, name its role on this specific object, pick the closest shape, and assign its own "
        "hex color. Use cylinder for straight round shapes, cone for a pointed tip, shade for a flat-topped taper, sphere "
        "for rounded masses, and rounded-box for flat-sided parts. Use the requested colors on the corresponding parts. "
        "Each part uses integer centimeters. X and Z are horizontal center coordinates, and size is [width,height,depth]. "
        "Bottom is the height of the lower face above the floor. Start the base at bottom 0. A part sitting on a 5 cm "
        "base should start at 4 or 5, not at the center of the base. Other parts should touch their neighbors on all three "
        "axes. Use realistic proportions. Avoid duplicate or overlapping parts with the same role. Keep it to 2–8 parts "
        "when possible. Choose left or right only when requested. Return only compact JSON."
    )
    messages = [{"role": "system", "content": instruction}, {"role": "user", "content": prompt}]
    schema = GridDesign.model_json_schema()
    for attempt in range(2):
        content = complete(messages, schema=schema, max_tokens=1400)
        try:
            design = GridDesign.model_validate_json(content)
            floor = min(part.bottom for part in design.parts)
            top = max(part.bottom + part.size[1] for part in design.parts)
            floating = disconnected_parts(design.parts)
            if not floating:
                parts = [Part(shape=part.shape, color=part.color,
                              position=(part.x/100, (part.bottom-floor+part.size[1]/2)/100, part.z/100),
                              size=tuple(dimension/100 for dimension in part.size), rotation=(0, 0, 0))
                         for part in design.parts]
                return ObjectDesign(name=design.name, placement=design.placement,
                                    height=max(.15, min(3, (top-floor)/100)), parts=parts)
            feedback = f"These parts float: {', '.join(floating)}. Change their bottom, X, or Z so they touch the supported body."
        except ValidationError:
            feedback = "The last JSON did not fit the schema. Use complete compact JSON with fewer parts."
        if attempt == 0:
            messages.extend([{"role": "assistant", "content": content},
                             {"role": "user", "content": feedback + " Keep the requested object, colors, and appearance."}])
    raise HTTPException(502, "The local model could not build a connected object. Try describing its main shape and parts.")


def disconnected_parts(parts: list[GridPart]) -> list[str]:
    # Bounding-box adjacency catches floating components in the axis-aligned freeform format.
    base = min(range(len(parts)), key=lambda index: parts[index].bottom)
    centers = [(part.x, part.bottom + part.size[1]/2, part.z) for part in parts]
    reached = {base}
    pending = [base]
    while pending:
        current = pending.pop()
        left = parts[current]
        for index, right in enumerate(parts):
            if index in reached:
                continue
            if all(2 * abs(a-b) <= width+other_width+2 for a, b, width, other_width
                   in zip(centers[current], centers[index], left.size, right.size)):
                reached.add(index)
                pending.append(index)
    return [part.role for index, part in enumerate(parts) if index not in reached]


def generate_furniture(family: str, prompt: str) -> ObjectDesign:
    instruction = (
        f"Choose design details for one {family}. The program builds its connected geometry. "
        + FURNITURE_HINTS[family]
        + " Use exact requested colors when given, including distinct colors for different parts. "
          "Choose left or right only when requested, otherwise center. Use a descriptive name and compact JSON."
    )
    content = complete([{"role": "system", "content": instruction}, {"role": "user", "content": prompt}],
                       schema=FurnitureDesign.model_json_schema())
    try:
        design = FurnitureDesign.model_validate_json(content)
        if family=="sofa" and re.search(r"\b(?:three|3)[ -]+seat(?:er)?\b", prompt, re.IGNORECASE):
            design = design.model_copy(update={"style": "wide"})
        return build_furniture(family, design)
    except ValidationError as error:
        raise HTTPException(502, "The local model returned invalid design details. Try a shorter description.") from error


def build_furniture(family: str, design: FurnitureDesign) -> ObjectDesign:
    parts: list[Part] = []
    colors = (design.primary_color, design.secondary_color, design.accent_color)

    def add(position, size, *, color=0, material=None, shape="rounded-box", rotation=(0, 0, 0)):
        parts.append(Part(shape=shape, position=position, size=size, rotation=rotation,
                          color=colors[color], material=material or design.finish))

    if family == "table":
        if design.style == "round":
            height = .76
            add((0, .73, 0), (1.1, .06, 1.1), shape="cylinder")
            add((0, .37, 0), (.13, .70, .13), color=1, shape="cylinder")
            add((0, .035, 0), (.69, .07, .69), color=1, shape="cylinder")
        else:
            width, depth, height = (.92, .53, .48) if design.style == "compact" else (1.42, .78, .76)
            top = .064
            add((0, height-top/2, 0), (width, top, depth))
            for x in (-width*.41, width*.41):
                for z in (-depth*.36, depth*.36):
                    add((x, (height-top)/2, z), (.063, height-top+.018, .063), color=1)
            if design.style == "drawers":
                add((-.44, .47, -.04), (.40, .46, .64), color=1)
                for y in (.33, .47, .61):
                    add((-.44, y, .295), (.392, .124, .036), color=1)
                    add((-.44, y, .328), (.12, .024, .045), color=2, material="metal")
    elif family == "sofa":
        seats = 3 if design.style == "wide" else 2
        width, height = (2.18 if seats==3 else 1.56), .92
        add((0, .255, 0), (width, .32, .83), material="fabric")
        add((0, .55, -.36), (width, .61, .16), material="fabric")
        for direction in (-1, 1):
            x=direction*(width/2-.083)
            add((x, .482, 0), (.166, .41, .83), material="fabric")
            for z in (-.30, .30):
                add((direction*(width/2-.14), .064, z), (.083, .128, .085), color=1, material="wood")
        cushion_width=(width-.34)/seats
        for index in range(seats):
            x=(index-(seats-1)/2)*cushion_width
            add((x, .451, .066), (cushion_width-.012, .127, .64), material="fabric")
            add((x, .675, -.27), (cushion_width-.014, .41, .131), color=2, material="fabric", rotation=(-12,0,0))
    elif family == "bed":
        width, height = (.98 if design.style=="compact" else 1.59), 1.03
        add((0,.25,0),(width+.08,.25,2.06),color=1,material="wood")
        add((0,.55,-1.014),(width+.08,.96,.113),color=1,material="wood")
        for x in (-width*.40,width*.40):
            for z in (-.83,.83):
                add((x,.081,z),(.09,.162,.09),color=1,material="wood")
        add((0,.45,0),(width,.20,2.0),color=2,material="fabric")
        add((0,.552,.23),(width*.99,.045,1.42),material="fabric")
        for x in ((0,) if design.style=="compact" else (-width*.245,width*.245)):
            add((x,.589,-.68),(width*.427,.116,.39),color=2,material="fabric")
    elif family == "plant":
        scale=.66 if design.style=="compact" else 1.22 if design.style=="wide" else 1
        height=1.06*scale
        add((0,.16*scale,0),(.35*scale,.32*scale,.35*scale),color=1,shape="cylinder")
        add((0,.315*scale,0),(.32*scale,.038*scale,.32*scale),color=1,shape="cylinder")
        add((0,.59*scale,0),(.047*scale,.60*scale,.047*scale),shape="cylinder")
        for index in range(6):
            angle=index*math.tau/6
            x,z=.138*math.cos(angle)*scale,.138*math.sin(angle)*scale
            y=(.53+.072*index)*scale
            add((x*.45,y,z*.45),(.16*scale,.037*scale,.037*scale),rotation=(0,((180-index*60)%360)-180,0))
            add((x,y,z),(.28*scale,.14*scale,.185*scale),color=0 if index%2==0 else 2,shape="sphere",
                rotation=(0,((index*60+180)%360)-180,26))
        add((0,.92*scale,0),(.21*scale,.26*scale,.18*scale),shape="sphere")
    elif family == "lamp":
        height = .57 if design.style in ("desk", "compact") else 1.49
        shade, width = (.205,.31) if height<1 else (.37,.48)
        add((0,.033,0),(width*.90,.066,width*.90),color=1,material="metal",shape="cylinder")
        stem_height=height-shade*.72
        add((0,stem_height/2,0),(.037,stem_height,.037),color=1,material="metal",shape="cylinder")
        add((0,height-shade/2,0),(width,shade,width),material="fabric",shape="shade")
    else:
        width, height = (.81,.98) if design.style=="compact" else (1.16,1.62)
        for x in (-width/2+.034,width/2-.034):
            add((x,height/2,0),(.068,height,.36))
        add((0,height/2,-.158),(width-.065,height,.044))
        for shelf in (0,.33,.66,.98):
            add((0,.035+shelf*(height-.069),0),(width-.056,.068,.36))
        for level in (0,.33,.66):
            base=.07+level*(height-.069)
            for index in range(3):
                book=.15+(.033*index)
                add((-width*.31+.102*index,base+book/2,.017),(.084,book,.235),color=1+index%2,material="fabric")
    return ObjectDesign(name=design.name, placement=design.placement, height=height, parts=parts)


def generate_chair(prompt: str) -> ObjectDesign:
    instruction = (
        "Select the design details for one chair requested by the user. Output compact JSON. "
        "A standard wooden or dining chair uses style dining, a lounge or upholstered armchair uses armchair, "
        "a desk chair with wheels uses office, and a chair explicitly requested without a back uses stool. "
        "Use the requested color for the seat and visible back. For a painted wooden chair, match the frame "
        "to the requested color unless the user requests different legs. Pick a suitable surface. "
        "Use placement left or right only if requested, otherwise center. Use a descriptive name."
    )
    content = complete([{"role": "system", "content": instruction}, {"role": "user", "content": prompt}],
                       schema=ChairDesign.model_json_schema())
    try:
        return build_chair(ChairDesign.model_validate_json(content))
    except ValidationError as error:
        raise HTTPException(502, "The local model returned invalid chair details. Try a shorter description.") from error


def build_chair(design: ChairDesign) -> ObjectDesign:
    parts: list[Part] = []
    frame_material = "metal" if design.style == "office" else ("wood" if design.surface == "fabric" else design.surface)

    def piece(position, size, *, frame=False, shape="rounded-box", rotation=(0, 0, 0)):
        parts.append(Part(shape=shape, position=position, size=size, rotation=rotation,
                          color=design.frame_color if frame else design.seat_color,
                          material=frame_material if frame else design.surface))

    if design.style == "office":
        piece((0, .42, .015), (.52, .085, .51))  # Seat
        piece((0, .69, -.228), (.48, .45, .09), rotation=(-11, 0, 0))  # Backrest
        piece((0, .52, -.22), (.065, .26, .06), frame=True, rotation=(-10, 0, 0))
        piece((0, .245, .035), (.065, .30, .065), frame=True, shape="cylinder")
        for index in range(5):
            radians = math.tau * index / 5
            yaw = (360 * index / 5 + 180) % 360 - 180
            x, z = math.sin(radians), math.cos(radians)
            piece((x*.14, .085, .035+z*.14), (.045, .044, .30), frame=True, rotation=(0, yaw, 0))
            piece((x*.275, .037, .035+z*.275), (.063, .074, .066), frame=True, shape="sphere")
        for x in (-.265, .265):
            piece((x, .51, -.04), (.036, .145, .04), frame=True)
            piece((x, .583, -.025), (.058, .036, .30))
        height = .93
    else:
        wide = design.style == "armchair"
        stool = design.style == "stool"
        width, depth, seat_y = (.65, .61, .43) if wide else (.49, .49, .46)
        thickness = .10 if wide else .065
        piece((0, seat_y, .015), (width, thickness, depth))
        leg_height = seat_y - thickness / 2 + .016
        leg_width = .047 if wide else .038
        for x in (-1, 1):
            for z in (-1, 1):
                piece((x*width*.39, leg_height/2, .015+z*depth*.39),
                      (leg_width, leg_height, leg_width), frame=True, rotation=(z*3, 0, x*4))
        if wide:
            piece((0, .68, -.255), (.60, .42, .13), rotation=(-12, 0, 0))
            for x in (-.305, .305):
                piece((x, .50, -.025), (.055, .20, .37), frame=True)
                piece((x, .60, -.02), (.105, .095, .52))
        elif not stool:
            for x in (-.19, .19):
                piece((x, .624, -.216), (.039, .36, .04), frame=True, rotation=(-7, 0, 0))
            piece((0, .783, -.239), (.45, .17, .055), rotation=(-7, 0, 0))
        height = seat_y+thickness/2 if stool else (.90 if wide else .87)
    return ObjectDesign(name=design.name, placement=design.placement, height=height, parts=parts)
