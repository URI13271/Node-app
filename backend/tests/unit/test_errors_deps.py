"""core/errors.py 의 invalid, not_found 와 api/deps.py 의 client_ip, request_id (BE-10). DB 없이 실행된다.

require_admin 은 관리자 키 잠금(BE-13) 이후에 구현하고 tests/unit/test_http_layer.py 로 확인한다.
"""

from starlette.requests import Request

from app.api.deps import client_ip, request_id
from app.core.errors import AppError, invalid, not_found


def _request(client=("10.0.0.7", 5555), state: dict | None = None) -> Request:
    req = Request({"type": "http", "method": "GET", "path": "/", "headers": [], "client": client})
    for k, v in (state or {}).items():
        setattr(req.state, k, v)
    return req


def test_invalid_is_400_with_one_detail():
    e = invalid("query.parking_lot_id", "not_in_place", "이 장소의 주차장이 아닙니다.")
    assert isinstance(e, AppError) and (e.code, e.status) == ("INVALID_INPUT", 400)
    assert e.details == [{"field": "query.parking_lot_id", "reason": "not_in_place", "message": "이 장소의 주차장이 아닙니다."}]


def test_not_found_is_404_with_target_name():
    e = not_found("장소")
    assert (e.code, e.status, e.message, e.details) == ("NOT_FOUND", 404, "장소을(를) 찾을 수 없습니다.", [])


def test_client_ip_uses_connection_address_only():
    assert client_ip(_request()) == "10.0.0.7"
    assert client_ip(_request(client=None)) == "unknown"
    forwarded = _request()
    forwarded.scope["headers"] = [(b"x-forwarded-for", b"1.2.3.4")]
    assert client_ip(forwarded) == "10.0.0.7"  # 헤더는 믿지 않는다


def test_request_id_from_state_or_dash():
    assert request_id(_request(state={"request_id": "abc"})) == "abc"
    assert request_id(_request()) == "-"

