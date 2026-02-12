"""Site model data structures produced by the crawler."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ElementModel(BaseModel):
    element_id: str
    tag: str
    selector: str
    role: str = ""
    text_content: str = ""
    is_interactive: bool = False
    element_type: str = ""  # button, link, input, dropdown, etc.
    attributes: dict[str, str] = Field(default_factory=dict)


class FormField(BaseModel):
    name: str
    field_type: str  # text, email, password, select, checkbox, etc.
    required: bool = False
    validation_pattern: Optional[str] = None
    options: Optional[list[str]] = None
    selector: str = ""


class FormModel(BaseModel):
    form_id: str
    action: str = ""
    method: str = "GET"
    fields: list[FormField] = Field(default_factory=list)
    submit_selector: str = ""


class NetworkRequest(BaseModel):
    url: str
    method: str = "GET"
    resource_type: str = ""
    status: Optional[int] = None
    content_type: Optional[str] = None


class APIEndpoint(BaseModel):
    url: str
    method: str
    request_content_type: Optional[str] = None
    response_content_type: Optional[str] = None
    status_codes_seen: list[int] = Field(default_factory=list)


class AuthFlow(BaseModel):
    login_url: str
    login_method: str = "form"  # form, oauth, etc.
    requires_credentials: bool = True


class PageModel(BaseModel):
    page_id: str
    url: str
    page_type: str = "static"  # listing, detail, form, dashboard, static, error
    title: str = ""
    elements: list[ElementModel] = Field(default_factory=list)
    forms: list[FormModel] = Field(default_factory=list)
    network_requests: list[NetworkRequest] = Field(default_factory=list)
    screenshot_path: str = ""
    dom_snapshot_path: str = ""


class SiteModel(BaseModel):
    base_url: str
    pages: list[PageModel] = Field(default_factory=list)
    navigation_graph: dict[str, list[str]] = Field(default_factory=dict)
    api_endpoints: list[APIEndpoint] = Field(default_factory=list)
    auth_flow: Optional[AuthFlow] = None
    crawl_metadata: dict[str, Any] = Field(default_factory=dict)
