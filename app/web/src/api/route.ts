import service from './index'

export interface RouteProfile {
  id: string
  label: string
}

export interface RouteStatus {
  phase: 'stopped' | 'starting' | 'ready' | 'failed'
  message: string
  pbf: string
  elevation: boolean
  port: number
  profiles: RouteProfile[]
  log: string[]
}

export interface RouteDefaults {
  basemap: string
  pbf_path: string
  profiles: RouteProfile[]
}

export interface RouteInstruction {
  text: string
  distance: number
  time: number
}

export interface RouteGeoJSON {
  type: 'FeatureCollection'
  features: Array<Record<string, unknown>>
}

export interface RoutePlace {
  query: string
  name: string
  lng: number
  lat: number
}

export interface RoutePlan {
  distance: number
  time: number
  coordinates: number[][]
  instructions: RouteInstruction[]
  geojson: RouteGeoJSON
  places?: RoutePlace[]
  missed?: string[]
}

export function getRouteDefaults(): Promise<RouteDefaults> {
  return service({ url: '/route/defaults', method: 'get' })
}

export function getRouteStatus(): Promise<RouteStatus> {
  return service({ url: '/route/status', method: 'get' })
}

export function startRoute(pbf_path: string, elevation = false): Promise<RouteStatus> {
  return service({ url: '/route/start', method: 'post', data: { pbf_path, elevation } })
}

export function stopRoute(): Promise<RouteStatus> {
  return service({ url: '/route/stop', method: 'post' })
}

export function planRoute(profile: string, points: number[][]): Promise<RoutePlan> {
  return service({ url: '/route/plan', method: 'post', data: { profile, points } })
}

export function describeRoute(data: {
  profile: string
  start: number[]
  end: number[]
  description: string
}): Promise<RoutePlan> {
  return service({ url: '/route/describe', method: 'post', data })
}

export function downloadGeoJSON(geojson: RouteGeoJSON, filename = 'route.geojson') {
  const blob = new Blob([JSON.stringify(geojson, null, 2)], { type: 'application/geo+json' })
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = filename
  link.click()
  URL.revokeObjectURL(link.href)
}
