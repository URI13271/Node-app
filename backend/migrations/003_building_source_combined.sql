-- 003_building_source_combined.sql : 건물 출처에 두 출처를 + 로 이은 값 허용
-- 바닥 모양은 OSM, 층수는 건축물대장인 건물을 'osm+public_data' 로 적는다 (scripts/fill_floors.py).
-- 화면 표기는 app/domain/attribution.py 가 + 로 나눠 출처마다 표기한다. 001 의 제약은 한 값만 받아 적재가 막혔다.
ALTER TABLE building DROP CONSTRAINT ck_building_source;
ALTER TABLE building ADD CONSTRAINT ck_building_source CHECK (
    source ~ '^(osm|public_data|vworld|manual)(\+(osm|public_data|vworld|manual))*$'
);
