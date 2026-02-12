"""Tests for site model data structures."""

import pytest

from src.models.site_model import (
    APIEndpoint,
    AuthFlow,
    ElementModel,
    FormField,
    FormModel,
    NetworkRequest,
    PageModel,
    SiteModel,
)


class TestElementModel:
    """Tests for ElementModel."""

    def test_minimal_element(self):
        """Test ElementModel with minimal required fields."""
        element = ElementModel(
            element_id="btn-1",
            tag="button",
            selector="button#submit",
        )
        assert element.element_id == "btn-1"
        assert element.tag == "button"
        assert element.selector == "button#submit"
        assert element.role == ""
        assert element.text_content == ""
        assert element.is_interactive is False
        assert element.element_type == ""
        assert element.attributes == {}

    def test_full_element(self):
        """Test ElementModel with all fields."""
        element = ElementModel(
            element_id="btn-submit",
            tag="button",
            selector="button#submit",
            role="button",
            text_content="Submit Form",
            is_interactive=True,
            element_type="button",
            attributes={"id": "submit", "class": "btn btn-primary"},
        )
        assert element.element_id == "btn-submit"
        assert element.is_interactive is True
        assert element.text_content == "Submit Form"
        assert element.attributes["class"] == "btn btn-primary"

    def test_serialization(self):
        """Test ElementModel serialization."""
        element = ElementModel(
            element_id="link-1",
            tag="a",
            selector="a.nav-link",
            text_content="Home",
        )
        data = element.model_dump()
        assert data["element_id"] == "link-1"
        assert data["tag"] == "a"


class TestFormField:
    """Tests for FormField."""

    def test_minimal_field(self):
        """Test FormField with minimal required fields."""
        field = FormField(name="email", field_type="email")
        assert field.name == "email"
        assert field.field_type == "email"
        assert field.required is False
        assert field.validation_pattern is None
        assert field.options is None
        assert field.selector == ""

    def test_required_field(self):
        """Test FormField with required flag."""
        field = FormField(
            name="password",
            field_type="password",
            required=True,
            selector="input[name='password']",
        )
        assert field.required is True
        assert field.selector == "input[name='password']"

    def test_field_with_validation(self):
        """Test FormField with validation pattern."""
        field = FormField(
            name="email",
            field_type="email",
            validation_pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
        )
        assert field.validation_pattern is not None
        assert "@" in field.validation_pattern

    def test_select_field_with_options(self):
        """Test FormField for select with options."""
        field = FormField(
            name="country",
            field_type="select",
            options=["USA", "Canada", "Mexico"],
        )
        assert field.options == ["USA", "Canada", "Mexico"]
        assert len(field.options) == 3


class TestFormModel:
    """Tests for FormModel."""

    def test_minimal_form(self):
        """Test FormModel with minimal fields."""
        form = FormModel(form_id="form-1")
        assert form.form_id == "form-1"
        assert form.action == ""
        assert form.method == "GET"
        assert form.fields == []
        assert form.submit_selector == ""

    def test_form_with_fields(self):
        """Test FormModel with fields."""
        fields = [
            FormField(name="email", field_type="email", required=True),
            FormField(name="password", field_type="password", required=True),
        ]
        form = FormModel(
            form_id="login-form",
            action="/api/login",
            method="POST",
            fields=fields,
            submit_selector="button[type='submit']",
        )
        assert form.form_id == "login-form"
        assert form.action == "/api/login"
        assert form.method == "POST"
        assert len(form.fields) == 2
        assert form.fields[0].name == "email"


class TestNetworkRequest:
    """Tests for NetworkRequest."""

    def test_minimal_request(self):
        """Test NetworkRequest with minimal fields."""
        request = NetworkRequest(url="/api/users")
        assert request.url == "/api/users"
        assert request.method == "GET"
        assert request.resource_type == ""
        assert request.status is None
        assert request.content_type is None

    def test_full_request(self):
        """Test NetworkRequest with all fields."""
        request = NetworkRequest(
            url="/api/users",
            method="POST",
            resource_type="xhr",
            status=201,
            content_type="application/json",
        )
        assert request.method == "POST"
        assert request.status == 201
        assert request.content_type == "application/json"


class TestAPIEndpoint:
    """Tests for APIEndpoint."""

    def test_minimal_endpoint(self):
        """Test APIEndpoint with minimal fields."""
        endpoint = APIEndpoint(url="/api/users", method="GET")
        assert endpoint.url == "/api/users"
        assert endpoint.method == "GET"
        assert endpoint.request_content_type is None
        assert endpoint.response_content_type is None
        assert endpoint.status_codes_seen == []

    def test_endpoint_with_status_codes(self):
        """Test APIEndpoint with observed status codes."""
        endpoint = APIEndpoint(
            url="/api/login",
            method="POST",
            request_content_type="application/json",
            response_content_type="application/json",
            status_codes_seen=[200, 401, 400],
        )
        assert len(endpoint.status_codes_seen) == 3
        assert 401 in endpoint.status_codes_seen


class TestAuthFlow:
    """Tests for AuthFlow."""

    def test_minimal_auth_flow(self):
        """Test AuthFlow with minimal fields."""
        auth = AuthFlow(login_url="https://example.com/login")
        assert auth.login_url == "https://example.com/login"
        assert auth.login_method == "form"
        assert auth.requires_credentials is True

    def test_oauth_auth_flow(self):
        """Test AuthFlow for OAuth."""
        auth = AuthFlow(
            login_url="https://example.com/oauth",
            login_method="oauth",
            requires_credentials=False,
        )
        assert auth.login_method == "oauth"
        assert auth.requires_credentials is False


class TestPageModel:
    """Tests for PageModel."""

    def test_minimal_page(self):
        """Test PageModel with minimal fields."""
        page = PageModel(page_id="page-1", url="https://example.com")
        assert page.page_id == "page-1"
        assert page.url == "https://example.com"
        assert page.page_type == "static"
        assert page.title == ""
        assert page.elements == []
        assert page.forms == []
        assert page.network_requests == []
        assert page.screenshot_path == ""
        assert page.dom_snapshot_path == ""

    def test_page_with_elements(self):
        """Test PageModel with elements."""
        elements = [
            ElementModel(element_id="btn-1", tag="button", selector="#btn"),
            ElementModel(element_id="link-1", tag="a", selector="a.nav"),
        ]
        page = PageModel(
            page_id="page-home",
            url="https://example.com/home",
            page_type="dashboard",
            title="Dashboard",
            elements=elements,
        )
        assert len(page.elements) == 2
        assert page.title == "Dashboard"
        assert page.page_type == "dashboard"

    def test_page_with_forms(self):
        """Test PageModel with forms."""
        form = FormModel(
            form_id="contact-form",
            fields=[FormField(name="message", field_type="text")],
        )
        page = PageModel(
            page_id="page-contact",
            url="https://example.com/contact",
            page_type="form",
            forms=[form],
        )
        assert len(page.forms) == 1
        assert page.forms[0].form_id == "contact-form"

    def test_page_with_network_requests(self):
        """Test PageModel with network requests."""
        requests = [
            NetworkRequest(url="/api/data", method="GET"),
            NetworkRequest(url="/api/save", method="POST"),
        ]
        page = PageModel(
            page_id="page-app",
            url="https://example.com/app",
            network_requests=requests,
        )
        assert len(page.network_requests) == 2


class TestSiteModel:
    """Tests for SiteModel."""

    def test_minimal_site(self):
        """Test SiteModel with minimal fields."""
        site = SiteModel(base_url="https://example.com")
        assert site.base_url == "https://example.com"
        assert site.pages == []
        assert site.navigation_graph == {}
        assert site.api_endpoints == []
        assert site.auth_flow is None
        assert site.crawl_metadata == {}

    def test_site_with_pages(self):
        """Test SiteModel with pages."""
        pages = [
            PageModel(page_id="page-1", url="https://example.com/"),
            PageModel(page_id="page-2", url="https://example.com/about"),
        ]
        site = SiteModel(base_url="https://example.com", pages=pages)
        assert len(site.pages) == 2
        assert site.pages[1].page_id == "page-2"

    def test_site_with_navigation_graph(self):
        """Test SiteModel with navigation graph."""
        navigation = {
            "page-home": ["page-about", "page-contact"],
            "page-about": ["page-home"],
        }
        site = SiteModel(
            base_url="https://example.com",
            navigation_graph=navigation,
        )
        assert len(site.navigation_graph["page-home"]) == 2
        assert "page-contact" in site.navigation_graph["page-home"]

    def test_site_with_api_endpoints(self):
        """Test SiteModel with API endpoints."""
        endpoints = [
            APIEndpoint(url="/api/users", method="GET"),
            APIEndpoint(url="/api/users", method="POST"),
        ]
        site = SiteModel(
            base_url="https://example.com",
            api_endpoints=endpoints,
        )
        assert len(site.api_endpoints) == 2

    def test_site_with_auth_flow(self):
        """Test SiteModel with auth flow."""
        auth = AuthFlow(
            login_url="https://example.com/login",
            login_method="form",
        )
        site = SiteModel(
            base_url="https://example.com",
            auth_flow=auth,
        )
        assert site.auth_flow is not None
        assert site.auth_flow.login_url == "https://example.com/login"

    def test_site_with_metadata(self):
        """Test SiteModel with crawl metadata."""
        metadata = {
            "crawl_duration": 300,
            "pages_crawled": 15,
            "errors": 2,
        }
        site = SiteModel(
            base_url="https://example.com",
            crawl_metadata=metadata,
        )
        assert site.crawl_metadata["pages_crawled"] == 15
        assert "errors" in site.crawl_metadata

    def test_serialization(self):
        """Test SiteModel serialization."""
        site = SiteModel(
            base_url="https://example.com",
            pages=[PageModel(page_id="p1", url="https://example.com/")],
            navigation_graph={"p1": []},
        )
        data = site.model_dump()
        assert data["base_url"] == "https://example.com"
        assert len(data["pages"]) == 1
        assert "p1" in data["navigation_graph"]
