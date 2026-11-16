-- 001_init.down.sql : 001_init.sql 되돌림 (PostGIS 확장은 다른 DB 객체가 쓸 수 있어 남김)
DROP TABLE IF EXISTS walk_route_step;
DROP TABLE IF EXISTS walk_route;
DROP TABLE IF EXISTS landmark;
DROP TABLE IF EXISTS parking_lot;
DROP TABLE IF EXISTS entrance;
DROP TABLE IF EXISTS building;
DROP TABLE IF EXISTS place;
