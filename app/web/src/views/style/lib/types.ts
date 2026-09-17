export type LayerType =
  | 'fill'
  | 'line'
  | 'symbol'
  | 'circle'
  | 'heatmap'
  | 'fill-extrusion'
  | 'building'
  | 'raster'
  | 'raster-particle'
  | 'hillshade'
  | 'background'
  | 'sky'
  | 'slot'
  | 'clip'
  | 'model'

export interface StyleJSON {
  version: 8
  name?: string
  metadata?: Record<string, unknown>
  center?: [number, number]
  zoom?: number
  bearing?: number
  pitch?: number
  sources: Record<string, any>
  sprite?: string | Array<{ id: string; url: string }>
  glyphs?: string
  layers: any[]
  lights?: any[]
  light?: any
  terrain?: any
  fog?: any
  projection?: any
  transition?: { duration?: number; delay?: number }
  [key: string]: unknown
}

export type FieldType =
  | 'number'
  | 'color'
  | 'boolean'
  | 'enum'
  | 'string'
  | 'array'
  | 'formatted'
  | 'resolvedImage'
  | 'padding'
  | 'json'

export type FieldGroup = 'base' | '3d' | 'transition' | 'other'

export interface SpecField {
  name: string
  type: FieldType
  label?: string
  default?: unknown
  doc?: string
  values?: string[]
  minimum?: number
  maximum?: number
  transition?: boolean
  group: FieldGroup
}

export const LAYER_TYPE_LABELS: Record<string, string> = {
  fill: '填充',
  line: '线',
  symbol: '符号',
  circle: '圆点',
  heatmap: '热力',
  'fill-extrusion': '拉伸 3D',
  building: '建筑 3D',
  raster: '栅格',
  'raster-particle': '粒子',
  hillshade: '山体阴影',
  background: '背景',
  sky: '天空',
  slot: '插槽',
  clip: '裁剪',
  model: '模型',
}

export const LAYER_TYPES: LayerType[] = [
  'background',
  'fill',
  'line',
  'symbol',
  'circle',
  'heatmap',
  'fill-extrusion',
  'building',
  'raster',
  'hillshade',
  'sky',
  'slot',
  'clip',
  'model',
  'raster-particle',
]

export const SOURCELESS_TYPES = new Set(['background', 'sky', 'slot'])
