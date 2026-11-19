-- 003_building_source_combined.down.sql : 003 되돌림 (한 값만 허용)
-- + 로 이은 출처가 있는 행이 남아 있으면 실패한다. 먼저 시드를 다시 적재하거나 해당 행을 고친다.
ALTER TABLE building DROP CONSTRAINT ck_building_source;
ALTER TABLE building ADD CONSTRAINT ck_building_source CHECK (source IN ('osm','public_data','vworld','manual'));
