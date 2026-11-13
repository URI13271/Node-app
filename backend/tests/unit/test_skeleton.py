"""뼈대 확인: 앱이 뜨고, 라우터가 등록되어 있고, 미구현 엔드포인트는 501 을 돌려준다.

기능을 구현하면 이 파일의 501 검사는 지우고 실제 테스트로 바꾼다.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

client = TestClient(create_app())

ROUTES = [
    ("GET", "/api/v1/places"),
    ("GET", "/api/v1/places/1"),
    ("GET", "/api/v1/places/1/buildings"),
    ("GET", "/api/v1/places/1/walk-routes"),
    ("GET", "/api/v1/admin/me"),
    ("PUT", "/api/v1/admin/walk-routes/1/steps"),
    ("PATCH", "/api/v1/admin/walk-route-steps/1"),
]


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.parametrize("method,path", ROUTES)
def test_routes_registered_not_implemented(method, path):
    r = client.request(method, path, json={} if method in ("PUT", "PATCH") else None)
    assert r.status_code == 501
    assert r.json()["error"]["code"] == "NOT_IMPLEMENTED"


@pytest.mark.parametrize("path", ["/", "/place.html", "/guide.html", "/admin.html", "/about.html", "/css/style.css", "/js/api.js"])
def test_frontend_served(path):
    r = client.get(path)
    assert r.status_code == 200


def test_frontend_missing_file_is_404_page():
    r = client.get("/nope.html")
    assert r.status_code == 404
    assert "없는 화면입니다" in r.text


def test_api_unknown_path_is_json_404():
    r = client.get("/api/v1/nope")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_api_wrong_method_is_json_405():
    r = client.post("/api/v1/places")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_validation_error_is_400_invalid_input():
    r = client.get("/api/v1/places", params={"limit": 0})
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "INVALID_INPUT"
    assert err["details"][0] == {"field": "query.limit", "reason": "out_of_range", "message": err["details"][0]["message"]}


def test_frontend_headers():
    r = client.get("/guide.html")
    assert r.headers["cache-control"] == "no-cache"
    # 개발(ENV=local) 기본값은 Report-Only: 막지 않고 보고만
    assert "worker-src 'self' blob:" in r.headers["content-security-policy-report-only"]
    assert "content-security-policy" not in r.headers
    assert client.get("/js/api.js").headers["cache-control"] == "no-cache"


def _app_with(monkeypatch, **env):
    from app.config import get_settings

    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    try:
        return TestClient(create_app())
    finally:
        get_settings.cache_clear()


def test_csp_enforced_in_prod(monkeypatch):
    c = _app_with(monkeypatch, ENV="prod")
    r = c.get("/index.html")
    assert "content-security-policy" in r.headers
    assert "content-security-policy-report-only" not in r.headers


def test_csp_mode_override(monkeypatch):
    assert "content-security-policy" in _app_with(monkeypatch, CSP_MODE="enforce").get("/").headers
    off = _app_with(monkeypatch, CSP_MODE="off").get("/").headers
    assert "content-security-policy" not in off and "content-security-policy-report-only" not in off


def test_csp_report_is_logged(caplog):
    body = {
        "csp-report": {
            "document-uri": "http://localhost:8000/guide.html?id=1",
            "effective-directive": "img-src",
            "blocked-uri": "https://evil.example/x.png?token=1",
            "disposition": "report",
        }
    }
    with caplog.at_level("WARNING", logger="csp"):
        r = client.post("/csp-report", content=__import__("json").dumps(body), headers={"Content-Type": "application/csp-report"})
    assert r.status_code == 204
    rec = next(x for x in caplog.records if x.getMessage().startswith("csp_violation"))
    assert rec.directive == "img-src"
    assert rec.blocked == "https://evil.example/x.png"  # 쿼리 문자열은 남기지 않는다
    assert rec.page == "guide.html"


def test_csp_report_ignores_garbage():
    assert client.post("/csp-report", content=b"not json").status_code == 204
    assert client.post("/csp-report", content=b"x" * 20000).status_code == 204


def test_csp_report_cannot_forge_log_lines(caplog):
    body = {
        "csp-report": {
            "document-uri": "http://x/a.html",
            "effective-directive": "img-src\nINFO:fake",
            "blocked-uri": "https://e.example/x\r\nINFO:fake log line",
        }
    }
    with caplog.at_level("WARNING", logger="csp"):
        client.post("/csp-report", content=__import__("json").dumps(body))
    msg = next(x for x in caplog.records if x.getMessage().startswith("csp_violation")).getMessage()
    assert "\n" not in msg and "\r" not in msg


def test_csp_report_rejects_large_body_by_header(caplog):
    with caplog.at_level("WARNING", logger="csp"):
        r = client.post("/csp-report", content=b"{}", headers={"Content-Length": "999999"})
    assert r.status_code == 204
    assert not [x for x in caplog.records if x.getMessage().startswith("csp_violation")]


def test_http_exception_keeps_status():
    from fastapi import FastAPI, HTTPException

    from app.core.errors import install_handlers

    app = FastAPI()
    install_handlers(app)

    @app.get("/t/{status}")
    def raise_status(status: int):
        raise HTTPException(status)

    c = TestClient(app)
    for status, code in [(401, "UNAUTHORIZED"), (413, "PAYLOAD_TOO_LARGE"), (429, "RATE_LIMITED"), (418, "INTERNAL")]:
        r = c.get(f"/t/{status}")
        assert (r.status_code, r.json()["error"]["code"]) == (500 if status == 418 else status, code)


def test_head_requests():
    assert client.head("/health").status_code == 200
    assert client.head("/api/v1/places").status_code == 405
    assert client.head("/index.html").status_code == 200
