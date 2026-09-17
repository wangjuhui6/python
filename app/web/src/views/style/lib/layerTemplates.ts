import type { LayerType } from './types'
import { SOURCELESS_TYPES } from './types'

export function defaultLayer(type: LayerType, id: string, source?: string, sourceLayer?: string): any {
  const layer: any = { id, type }
  if (!SOURCELESS_TYPES.has(type)) {
    if (source) layer.source = source
    if (sourceLayer) layer['source-layer'] = sourceLayer
  }

  if (type === 'background') {
    layer.paint = { 'background-color': '#e8e4dc' }
  } else if (type === 'fill') {
    layer.paint = { 'fill-color': '#088', 'fill-opacity': 0.6 }
  } else if (type === 'line') {
    layer.paint = { 'line-color': '#000', 'line-width': 1.5 }
  } else if (type === 'circle') {
    layer.paint = { 'circle-color': '#088', 'circle-radius': 4 }
  } else if (type === 'symbol') {
    layer.layout = {
      'text-field': ['get', 'name'],
      'text-size': 12,
      'text-font': ['Open Sans Regular', 'Arial Unicode MS Regular'],
    }
    layer.paint = { 'text-color': '#333' }
  } else if (type === 'heatmap') {
    layer.paint = { 'heatmap-radius': 20, 'heatmap-opacity': 0.8 }
  } else if (type === 'fill-extrusion') {
    layer.minzoom = 14
    layer.paint = {
      'fill-extrusion-color': '#aaa',
      'fill-extrusion-opacity': 0.85,
      'fill-extrusion-height': ['interpolate', ['linear'], ['zoom'], 15, 0, 16, ['get', 'height']],
      'fill-extrusion-base': ['coalesce', ['get', 'min_height'], 0],
      'fill-extrusion-vertical-gradient': true,
    }
  } else if (type === 'building') {
    if (!layer['source-layer']) layer['source-layer'] = 'building'
    layer.minzoom = 14
    layer.layout = {
      'building-height': ['get', 'height'],
      'building-base': ['coalesce', ['get', 'min_height'], 0],
      'building-roof-shape': 'flat',
    }
    layer.paint = {
      'building-color': '#d9d0c9',
      'building-opacity': 1,
      'building-vertical-scale': 1,
      'building-cast-shadows': true,
    }
  } else if (type === 'raster') {
    layer.paint = { 'raster-opacity': 1 }
  } else if (type === 'hillshade') {
    layer.paint = { 'hillshade-exaggeration': 0.5 }
  } else if (type === 'sky') {
    layer.paint = { 'sky-type': 'atmosphere' }
  }

  return layer
}

export function buildingGrowPaint(heightField: string, baseField: string, zoomFrom = 15, zoomTo = 16) {
  const height = heightField.trim() || 'height'
  const base = baseField.trim()
  const z0 = Number(zoomFrom)
  const z1 = Number(zoomTo)
  return {
    'fill-extrusion-height': ['interpolate', ['linear'], ['zoom'], z0, 0, z1, ['get', height]],
    'fill-extrusion-base': base
      ? ['interpolate', ['linear'], ['zoom'], z0, 0, z1, ['coalesce', ['get', base], 0]]
      : 0,
  }
}

export function buildingGrowLayout(heightField: string, baseField: string, zoomFrom = 15, zoomTo = 16) {
  const height = heightField.trim() || 'height'
  const base = baseField.trim()
  const z0 = Number(zoomFrom)
  const z1 = Number(zoomTo)
  return {
    'building-height': ['interpolate', ['linear'], ['zoom'], z0, 0, z1, ['get', height]],
    'building-base': base ? ['interpolate', ['linear'], ['zoom'], z0, 0, z1, ['coalesce', ['get', base], 0]] : 0,
  }
}

export function transitionValue(duration: number, delay: number) {
  return { duration: Math.max(0, Number(duration) || 0), delay: Math.max(0, Number(delay) || 0) }
}

export function extractZoomStops(value: unknown): { from: number; to: number } | null {
  if (!Array.isArray(value) || value[0] !== 'interpolate') return null
  const stops: number[] = []
  for (let i = 3; i < value.length; i += 2) {
    const z = Number(value[i])
    if (!Number.isNaN(z)) stops.push(z)
  }
  if (stops.length < 2) return null
  return { from: stops[0], to: stops[stops.length - 1] }
}

export function extractGetName(value: unknown): string {
  if (!Array.isArray(value)) return ''
  if (value[0] === 'get' && value[1] != null) return String(value[1])
  for (let i = 1; i < value.length; i++) {
    const found = extractGetName(value[i])
    if (found) return found
  }
  return ''
}

export function replaceGetName(value: unknown, field: string): unknown {
  const name = field.trim()
  if (!name) return value
  if (!Array.isArray(value)) return value
  if (value[0] === 'get') return ['get', name]
  return value.map((item, index) => (index === 0 ? item : replaceGetName(item, name)))
}
