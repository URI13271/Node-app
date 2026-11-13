"""scripts/build_walk_routes.py 단위 테스트 (DB 없이, shapely 필요). build_walk_routes 담당자가 채운다.

"""
# TODO: 보행망 위 최단 경로가 건물을 통과하지 않음 (건물 통과 0m)
# TODO: 차도는 횡단보도에서만 건넘 (횡단보도 밖 횡단 0곳)
# TODO: manual_crossings.json 의 횡단보도를 경로에 포함
# TODO: --check 는 파일을 바꾸지 않음
