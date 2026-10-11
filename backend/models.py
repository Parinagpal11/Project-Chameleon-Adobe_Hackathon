from typing import Literal, Any
from pydantic import BaseModel, Field, ConfigDict, model_validator



class StrictModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)


class Relationship(StrictModel):
    source: str
    target: str
    type: str
    strength: float = 1.0


class Genome(StrictModel):
    role: str
    importance: float = Field(default=.5, ge=0, le=1)
    removable: bool = False
    scalable: bool = True
    reflow: bool = False
    relationships: list[Relationship] = Field(default_factory=list)


class Element(StrictModel):
    id: str = Field(min_length=1, max_length=100)
    type: Literal['text', 'image', 'logo', 'button', 'shape', 'decoration']
    x: float
    y: float
    width: float = Field(ge=0)
    height: float = Field(ge=0)
    text: str | None = Field(default=None, max_length=2000)
    fontSize: float | None = Field(default=None, gt=0)
    genome: Genome | None = None
    # Product additions: uploaded artwork, text alignment, and rule-driven visibility.
    src: str | None = Field(default=None, max_length=8_000_000)
    align: Literal['left', 'center', 'right'] | None = None
    hidden: bool = False
    pinned: str | None = None
    art: str | None = Field(default=None, max_length=20)   # placeholder illustration for templates


class Brand(StrictModel):
    background: str = Field(default='#e6b56e', pattern=r'^#[0-9a-fA-F]{6}$')
    text: str = Field(default='#2b1d14', pattern=r'^#[0-9a-fA-F]{6}$')
    primary: str = Field(default='#26402f', pattern=r'^#[0-9a-fA-F]{6}$')
    accent: str = Field(default='#cc874e', pattern=r'^#[0-9a-fA-F]{6}$')
    font: str = Field(default='Inter', max_length=60)


class Canvas(StrictModel):
    width: int = Field(ge=64, le=8192)
    height: int = Field(ge=64, le=8192)


class Design(StrictModel):
    canvas: Canvas
    elements: list[Element] = Field(min_length=1, max_length=100)
    brand: Brand | None = None

    @model_validator(mode='after')
    def unique_ids(self):
        if len({e.id for e in self.elements}) != len(self.elements):
            raise ValueError('Element IDs must be unique')
        return self


class Target(Canvas):
    name: str = Field(default='', max_length=60)


class ProjectSave(StrictModel):
    name: str = Field(default='', max_length=80)
    design: dict[str, Any]                                    # chameleon-graph/1 (or the older studio format)
    formats: list[Target] = Field(default_factory=list, max_length=30)
    assets: dict[str, str] = Field(default_factory=dict)      # uploaded images as data URLs, keyed by asset id
    state: dict[str, Any] = Field(default_factory=dict)       # UI state: per-format overrides, layout choices
