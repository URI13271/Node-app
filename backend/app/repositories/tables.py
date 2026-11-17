"""SQLAlchemy Table 메타데이터 (ADR-004: ORM 클래스 없이 Core 사용).

migrations/*.sql 과 칼럼이 같아야 한다 (테이블 정의서 v1.1).
칼럼 이름, 타입, NULL 허용, 기본 키, 외래 키만 적는다. CHECK 제약과 인덱스는 DB(migrations)가 지킨다.
실제 DB 와 같은지는 tests/integration/test_schema.py 가 확인한다.
"""

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    SmallInteger,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import DOUBLE_PRECISION

from app.db import metadata


def _geom(kind: str) -> Geometry:
    # 공간 인덱스는 migrations 에 있으므로 여기서는 만들지 않는다
    return Geometry(kind, srid=4326, spatial_index=False)


def _id() -> Column:
    return Column("id", BigInteger, Identity(), primary_key=True)


def _ts(name: str, nullable: bool = True, now: bool = False) -> Column:
    return Column(name, DateTime(timezone=True), nullable=nullable, server_default=func.now() if now else None)


place = Table(
    "place",
    metadata,
    _id(),
    Column("seed_key", String(50)),
    Column("name", String(100), nullable=False),
    Column("category", String(30), nullable=False),
    Column("address", String(200)),
    Column("location", _geom("POINT"), nullable=False),
    Column("description", Text),
    Column("cover_image_url", Text),
    Column("camera_bearing", DOUBLE_PRECISION),
    Column("camera_pitch", DOUBLE_PRECISION),
    Column("camera_zoom", DOUBLE_PRECISION),
    Column("arrival_radius_m", Integer, nullable=False, server_default="150"),
    _ts("last_verified_at"),
    _ts("created_at", nullable=False, now=True),
)

building = Table(
    "building",
    metadata,
    _id(),
    Column("place_id", BigInteger, ForeignKey("place.id", ondelete="CASCADE"), nullable=False),
    Column("name", String(100)),
    Column("footprint", _geom("POLYGON"), nullable=False),
    Column("height_m", DOUBLE_PRECISION),
    Column("floor_count", Integer),
    Column("description", Text),
    Column("is_target", Boolean, nullable=False, server_default="false"),
    Column("source", String(30), nullable=False),
)

entrance = Table(
    "entrance",
    metadata,
    _id(),
    Column("place_id", BigInteger, ForeignKey("place.id", ondelete="CASCADE"), nullable=False),
    Column("name", String(100), nullable=False),
    Column("location", _geom("POINT"), nullable=False),
    Column("description", Text),
    Column("is_main", Boolean, nullable=False, server_default="false"),
    _ts("last_verified_at"),
    _ts("updated_at", nullable=False, now=True),
)

parking_lot = Table(
    "parking_lot",
    metadata,
    _id(),
    Column("place_id", BigInteger, ForeignKey("place.id", ondelete="CASCADE"), nullable=False),
    Column("name", String(100), nullable=False),
    Column("location", _geom("POINT"), nullable=False),
    Column("capacity", Integer),
    Column("is_free", Boolean),
    Column("description", Text),
    Column("priority", SmallInteger, nullable=False, server_default="1"),
    Column("area", _geom("POLYGON")),
    Column("camera_bearing", DOUBLE_PRECISION),
    Column("camera_pitch", DOUBLE_PRECISION),
    Column("camera_zoom", DOUBLE_PRECISION),
    _ts("last_verified_at"),
)

landmark = Table(
    "landmark",
    metadata,
    _id(),
    Column("place_id", BigInteger, ForeignKey("place.id", ondelete="CASCADE"), nullable=False),
    Column("name", String(100), nullable=False),
    Column("location", _geom("POINT"), nullable=False),
    Column("description", Text),
    Column("image_url", Text),
)

walk_route = Table(
    "walk_route",
    metadata,
    _id(),
    Column("parking_lot_id", BigInteger, ForeignKey("parking_lot.id", ondelete="CASCADE"), nullable=False),
    Column("entrance_id", BigInteger, ForeignKey("entrance.id", ondelete="CASCADE"), nullable=False),
    Column("path", _geom("LINESTRING"), nullable=False),
    Column("distance_m", DOUBLE_PRECISION),
    Column("walk_time_min", Integer),
    Column("description", Text),
    _ts("updated_at", nullable=False, now=True),
)

walk_route_step = Table(
    "walk_route_step",
    metadata,
    _id(),
    Column("walk_route_id", BigInteger, ForeignKey("walk_route.id", ondelete="CASCADE"), nullable=False),
    Column("step_order", Integer, nullable=False),
    Column("landmark_id", BigInteger, ForeignKey("landmark.id", ondelete="SET NULL")),
    Column("instruction", Text, nullable=False),
    Column("location", _geom("POINT"), nullable=False),
    Column("camera_bearing", DOUBLE_PRECISION),
    Column("camera_pitch", DOUBLE_PRECISION),
    Column("camera_zoom", DOUBLE_PRECISION),
    _ts("updated_at", now=True),  # 001_init.sql 에서 NOT NULL 이 아님
    Column("updated_by", String(50)),
)

# 002_walk_network: 앱은 읽지 않는다. 시드 적재(load_seed)와 경로 생성 근거 보관용
walk_network_feature = Table(
    "walk_network_feature",
    metadata,
    _id(),
    Column("area_key", String(50), nullable=False),
    Column("kind", String(20), nullable=False),
    Column("geom", _geom("GEOMETRY"), nullable=False),
    Column("source", String(30), nullable=False, server_default="osm"),
    _ts("loaded_at", nullable=False, now=True),
)
