export type Gcp = {
  x: number
  y: number
  lng: number
  lat: number
  note?: string
}

export type FitResult = {
  kind: 'similarity' | 'affine'
  count: number
  matrix: number[][]
  mean_error_m: number
  residuals: Array<{
    note: string
    x: number
    y: number
    input_lng: number
    input_lat: number
    fitted_lng: number
    fitted_lat: number
    error_m: number
  }>
}

export type ImageExtent = {
  width: number
  height: number
  corners: {
    topLeft: [number, number]
    topRight: [number, number]
    bottomRight: [number, number]
    bottomLeft: [number, number]
  }
  bbox: [number, number, number, number]
  west: number
  south: number
  east: number
  north: number
}

function finite(n: number) {
  return Number.isFinite(n)
}

function latToMerc(lat: number) {
  const clamped = Math.min(89.5, Math.max(-89.5, lat))
  return Math.log(Math.tan(Math.PI / 4 + (clamped * Math.PI) / 180 / 2))
}

function mercToLat(merc: number) {
  const v = Math.min(10, Math.max(-10, merc))
  return ((2 * Math.atan(Math.exp(v)) - Math.PI / 2) * 180) / Math.PI
}

function applyLinear(matrix: number[][], x: number, y: number): [number, number] {
  return [
    matrix[0][0] * x + matrix[0][1] * y + matrix[0][2],
    matrix[1][0] * x + matrix[1][1] * y + matrix[1][2],
  ]
}

export function applyMatrix(matrix: number[][], x: number, y: number): [number, number] {
  const [lng, merc] = applyLinear(matrix, x, y)
  return [lng, mercToLat(merc)]
}

export function haversineM(lng1: number, lat1: number, lng2: number, lat2: number) {
  const r = 6371000
  const p1 = (lat1 * Math.PI) / 180
  const p2 = (lat2 * Math.PI) / 180
  const dphi = ((lat2 - lat1) * Math.PI) / 180
  const dlmb = ((lng2 - lng1) * Math.PI) / 180
  const a = Math.sin(dphi / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dlmb / 2) ** 2
  return 2 * r * Math.asin(Math.min(1, Math.sqrt(a)))
}

function solve3(ata: number[][], atb: number[]) {
  const m = ata.map((row, i) => [...row, atb[i]])
  for (let col = 0; col < 3; col++) {
    let pivot = col
    for (let row = col + 1; row < 3; row++) {
      if (Math.abs(m[row][col]) > Math.abs(m[pivot][col])) {
        pivot = row
      }
    }
    if (Math.abs(m[pivot][col]) < 1e-12) {
      throw new Error('控制点共线或过于接近，请换更散开的位置')
    }
    if (pivot !== col) {
      const tmp = m[col]
      m[col] = m[pivot]
      m[pivot] = tmp
    }
    const div = m[col][col]
    for (let j = col; j < 4; j++) {
      m[col][j] /= div
    }
    for (let row = 0; row < 3; row++) {
      if (row === col) continue
      const f = m[row][col]
      for (let j = col; j < 4; j++) {
        m[row][j] -= f * m[col][j]
      }
    }
  }
  return [m[0][3], m[1][3], m[2][3]]
}

function leastSquares(xs: number[], ys: number[], values: number[]) {
  const ata = [
    [0, 0, 0],
    [0, 0, 0],
    [0, 0, 0],
  ]
  const atb = [0, 0, 0]
  for (let i = 0; i < xs.length; i++) {
    const row = [xs[i], ys[i], 1]
    for (let r = 0; r < 3; r++) {
      atb[r] += row[r] * values[i]
      for (let c = 0; c < 3; c++) {
        ata[r][c] += row[r] * row[c]
      }
    }
  }
  return solve3(ata, atb)
}

export function fitTransform(gcps: Gcp[]): FitResult {
  const points = gcps.filter((p) => finite(p.x) && finite(p.y) && finite(p.lng) && finite(p.lat))
  if (points.length < 2) {
    throw new Error('至少需要 2 个控制点（图上坐标 + 经纬度）')
  }

  let matrix: number[][]
  let kind: FitResult['kind']

  if (points.length === 2) {
    const dx = points[1].x - points[0].x
    const dy = points[1].y - points[0].y
    const dlng = points[1].lng - points[0].lng
    const dmerc = latToMerc(points[1].lat) - latToMerc(points[0].lat)
    const denom = dx * dx + dy * dy
    if (denom < 1e-9) {
      throw new Error('两个控制点在图上太近，请选更散开的位置')
    }
    const a = (dx * dlng + dy * dmerc) / denom
    const b = (dx * dmerc - dy * dlng) / denom
    const tx = points[0].lng - a * points[0].x + b * points[0].y
    const ty = latToMerc(points[0].lat) - b * points[0].x - a * points[0].y
    matrix = [
      [a, -b, tx],
      [b, a, ty],
    ]
    kind = 'similarity'
  } else {
    const xs = points.map((p) => p.x)
    const ys = points.map((p) => p.y)
    matrix = [leastSquares(xs, ys, points.map((p) => p.lng)), leastSquares(xs, ys, points.map((p) => latToMerc(p.lat)))]
    kind = 'affine'
  }

  const residuals = points.map((point) => {
    const [fittedLng, fittedLat] = applyMatrix(matrix, point.x, point.y)
    const error = haversineM(point.lng, point.lat, fittedLng, fittedLat)
    return {
      note: point.note || '',
      x: point.x,
      y: point.y,
      input_lng: point.lng,
      input_lat: point.lat,
      fitted_lng: Number(fittedLng.toFixed(8)),
      fitted_lat: Number(fittedLat.toFixed(8)),
      error_m: Number(error.toFixed(2)),
    }
  })
  const mean = residuals.reduce((sum, item) => sum + item.error_m, 0) / residuals.length
  return {
    kind,
    count: points.length,
    matrix,
    mean_error_m: Number(mean.toFixed(2)),
    residuals,
  }
}

export function imageExtent(width: number, height: number, matrix: number[][]): ImageExtent {
  const topLeft = applyMatrix(matrix, 0, 0)
  const topRight = applyMatrix(matrix, width, 0)
  const bottomRight = applyMatrix(matrix, width, height)
  const bottomLeft = applyMatrix(matrix, 0, height)
  const lngs = [topLeft[0], topRight[0], bottomRight[0], bottomLeft[0]]
  const lats = [topLeft[1], topRight[1], bottomRight[1], bottomLeft[1]]
  const west = Math.min(...lngs)
  const east = Math.max(...lngs)
  const south = Math.min(...lats)
  const north = Math.max(...lats)
  return {
    width,
    height,
    corners: { topLeft, topRight, bottomRight, bottomLeft },
    bbox: [west, south, east, north],
    west,
    south,
    east,
    north,
  }
}

export function invertAffine(matrix: number[][]): number[][] {
  const a = matrix[0][0]
  const b = matrix[0][1]
  const c = matrix[0][2]
  const d = matrix[1][0]
  const e = matrix[1][1]
  const f = matrix[1][2]
  const det = a * e - b * d
  if (Math.abs(det) < 1e-18) {
    throw new Error('变换不可逆')
  }
  return [
    [e / det, -b / det, (b * f - c * e) / det],
    [-d / det, a / det, (c * d - a * f) / det],
  ]
}

export function lngLatToPixel(inv: number[][], lng: number, lat: number): [number, number] {
  return applyLinear(inv, lng, latToMerc(lat))
}

export function boundsToGcps(
  width: number,
  height: number,
  west: number,
  south: number,
  east: number,
  north: number,
): Array<{ x: number; y: number; lng: number; lat: number; note: string }> {
  return [
    { x: 0, y: 0, lng: west, lat: north, note: '左上' },
    { x: width, y: 0, lng: east, lat: north, note: '右上' },
    { x: width, y: height, lng: east, lat: south, note: '右下' },
    { x: 0, y: height, lng: west, lat: south, note: '左下' },
  ]
}

export function roundLngLat(pair: [number, number], digits = 6): [number, number] {
  const f = 10 ** digits
  return [Math.round(pair[0] * f) / f, Math.round(pair[1] * f) / f]
}
