// 단말 안에서만 쓰는 거리 계산. 위치는 서버로 보내지 않는다 (ADR-006, N-03).
// 좌표는 항상 [경도, 위도] 순서 배열이다. 예: [128.0985, 35.1534]
import { todo } from './util.js'

/** 두 점 사이 거리(m) */
export function distanceM(a, b) { return todo('distanceM') }
/** 경로에서 p 에 가장 가까운 꼭짓점 번호 */
export function nearestVertex(path, p) { return todo('nearestVertex') }
/** 경로 전체 길이(m) */
export function pathLengthM(path) { return todo('pathLengthM') }
/** 경로 위 비율 t(0~1) 지점 */
export function pointAlong(path, t) { return todo('pointAlong') }
/** p 가 경로의 몇 % 지점인지 (0~1) */
export function fractionOnPath(path, p) { return todo('fractionOnPath') }
/** 경로 처음부터 비율 t 까지 자른 선 */
export function pathUntil(path, t) { return todo('pathUntil') }
