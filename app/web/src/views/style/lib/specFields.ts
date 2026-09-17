import type { FieldGroup, FieldType, SpecField } from './types'
import { fieldDoc, fieldLabel } from './fieldLabels'

function groupOf(name: string): FieldGroup {
  if (name.endsWith('-transition')) return 'transition'
  if (
    /building|extrusion|ambient-occlusion|flood-light|vertical-scale|edge-radius|rounded-roof|emissive|cast-shadows|cutoff|roof-shape|facade/.test(
      name,
    )
  ) {
    return '3d'
  }
  return 'base'
}

function f(
  name: string,
  type: FieldType,
  extra: Partial<SpecField> = {},
): SpecField {
  return {
    name,
    type,
    group: extra.group || groupOf(name),
    transition: extra.transition ?? false,
    ...extra,
    label: extra.label || fieldLabel(name),
    doc: fieldDoc(name) || extra.doc,
  }
}

const vis: SpecField = f('visibility', 'enum', { values: ['visible', 'none'], default: 'visible', group: 'base' })

const COMMON_FILL: SpecField[] = [
  vis,
  f('fill-sort-key', 'number'),
]

const PAINT_FILL: SpecField[] = [
  f('fill-antialias', 'boolean', { default: true }),
  f('fill-opacity', 'number', { default: 1, minimum: 0, maximum: 1, transition: true }),
  f('fill-color', 'color', { default: '#000000', transition: true }),
  f('fill-outline-color', 'color', { transition: true }),
  f('fill-translate', 'array', { default: [0, 0], transition: true }),
  f('fill-translate-anchor', 'enum', { values: ['map', 'viewport'], default: 'map' }),
  f('fill-pattern', 'resolvedImage', { transition: true }),
  f('fill-emissive-strength', 'number', { default: 0, minimum: 0, transition: true, group: '3d' }),
  f('fill-z-offset', 'number', { default: 0, transition: true }),
]

const LAYOUT_LINE: SpecField[] = [
  vis,
  f('line-cap', 'enum', { values: ['butt', 'round', 'square'], default: 'butt' }),
  f('line-join', 'enum', { values: ['bevel', 'round', 'miter', 'none'], default: 'miter' }),
  f('line-miter-limit', 'number', { default: 2 }),
  f('line-round-limit', 'number', { default: 1.05 }),
  f('line-sort-key', 'number'),
  f('line-z-offset', 'number', { default: 0 }),
  f('line-elevation-reference', 'enum', { values: ['none', 'sea', 'ground', 'hd-road-markup'] }),
  f('line-cross-slope', 'number'),
]

const PAINT_LINE: SpecField[] = [
  f('line-opacity', 'number', { default: 1, minimum: 0, maximum: 1, transition: true }),
  f('line-color', 'color', { default: '#000000', transition: true }),
  f('line-translate', 'array', { default: [0, 0], transition: true }),
  f('line-translate-anchor', 'enum', { values: ['map', 'viewport'], default: 'map' }),
  f('line-width', 'number', { default: 1, minimum: 0, transition: true }),
  f('line-gap-width', 'number', { default: 0, minimum: 0, transition: true }),
  f('line-offset', 'number', { default: 0, transition: true }),
  f('line-blur', 'number', { default: 0, minimum: 0, transition: true }),
  f('line-dasharray', 'array'),
  f('line-pattern', 'resolvedImage', { transition: true }),
  f('line-gradient', 'json'),
  f('line-emissive-strength', 'number', { default: 0, minimum: 0, transition: true, group: '3d' }),
  f('line-occlusion-opacity', 'number', { default: 0, minimum: 0, maximum: 1, transition: true }),
  f('line-border-width', 'number', { default: 0, minimum: 0, transition: true }),
  f('line-border-color', 'color', { transition: true }),
]

const LAYOUT_SYMBOL: SpecField[] = [
  vis,
  f('symbol-placement', 'enum', { values: ['point', 'line', 'line-center'], default: 'point' }),
  f('symbol-spacing', 'number', { default: 250, minimum: 1 }),
  f('symbol-avoid-edges', 'boolean', { default: false }),
  f('symbol-sort-key', 'number'),
  f('symbol-z-elevate', 'boolean', { default: false, group: '3d' }),
  f('icon-allow-overlap', 'boolean', { default: false }),
  f('icon-ignore-placement', 'boolean', { default: false }),
  f('icon-optional', 'boolean', { default: false }),
  f('icon-rotation-alignment', 'enum', { values: ['map', 'viewport', 'auto'], default: 'auto' }),
  f('icon-size', 'number', { default: 1, minimum: 0 }),
  f('icon-text-fit', 'enum', { values: ['none', 'width', 'height', 'both'], default: 'none' }),
  f('icon-image', 'resolvedImage'),
  f('icon-rotate', 'number', { default: 0 }),
  f('icon-padding', 'padding', { default: 2 }),
  f('icon-keep-upright', 'boolean', { default: false }),
  f('icon-offset', 'array', { default: [0, 0] }),
  f('icon-anchor', 'enum', {
    values: ['center', 'left', 'right', 'top', 'bottom', 'top-left', 'top-right', 'bottom-left', 'bottom-right'],
    default: 'center',
  }),
  f('icon-pitch-alignment', 'enum', { values: ['map', 'viewport', 'auto'], default: 'auto' }),
  f('text-pitch-alignment', 'enum', { values: ['map', 'viewport', 'auto'], default: 'auto' }),
  f('text-rotation-alignment', 'enum', { values: ['map', 'viewport', 'viewport-glyph', 'auto'], default: 'auto' }),
  f('text-field', 'formatted', { default: '' }),
  f('text-font', 'array', { default: ['Open Sans Regular', 'Arial Unicode MS Regular'] }),
  f('text-size', 'number', { default: 16, minimum: 0 }),
  f('text-max-width', 'number', { default: 10, minimum: 0 }),
  f('text-line-height', 'number', { default: 1.2 }),
  f('text-letter-spacing', 'number', { default: 0 }),
  f('text-justify', 'enum', { values: ['auto', 'left', 'center', 'right'], default: 'center' }),
  f('text-radial-offset', 'number', { default: 0 }),
  f('text-variable-anchor', 'array'),
  f('text-anchor', 'enum', {
    values: ['center', 'left', 'right', 'top', 'bottom', 'top-left', 'top-right', 'bottom-left', 'bottom-right'],
    default: 'center',
  }),
  f('text-max-angle', 'number', { default: 45 }),
  f('text-writing-mode', 'array'),
  f('text-rotate', 'number', { default: 0 }),
  f('text-padding', 'number', { default: 2, minimum: 0 }),
  f('text-keep-upright', 'boolean', { default: true }),
  f('text-transform', 'enum', { values: ['none', 'uppercase', 'lowercase'], default: 'none' }),
  f('text-offset', 'array', { default: [0, 0] }),
  f('text-allow-overlap', 'boolean', { default: false }),
  f('text-ignore-placement', 'boolean', { default: false }),
  f('text-optional', 'boolean', { default: false }),
]

const PAINT_SYMBOL: SpecField[] = [
  f('icon-opacity', 'number', { default: 1, minimum: 0, maximum: 1, transition: true }),
  f('icon-color', 'color', { default: '#000000', transition: true }),
  f('icon-halo-color', 'color', { default: 'rgba(0,0,0,0)', transition: true }),
  f('icon-halo-width', 'number', { default: 0, minimum: 0, transition: true }),
  f('icon-halo-blur', 'number', { default: 0, minimum: 0, transition: true }),
  f('icon-translate', 'array', { default: [0, 0], transition: true }),
  f('icon-translate-anchor', 'enum', { values: ['map', 'viewport'], default: 'map' }),
  f('icon-emissive-strength', 'number', { default: 1, minimum: 0, transition: true, group: '3d' }),
  f('text-opacity', 'number', { default: 1, minimum: 0, maximum: 1, transition: true }),
  f('text-color', 'color', { default: '#000000', transition: true }),
  f('text-halo-color', 'color', { default: 'rgba(0,0,0,0)', transition: true }),
  f('text-halo-width', 'number', { default: 0, minimum: 0, transition: true }),
  f('text-halo-blur', 'number', { default: 0, minimum: 0, transition: true }),
  f('text-translate', 'array', { default: [0, 0], transition: true }),
  f('text-translate-anchor', 'enum', { values: ['map', 'viewport'], default: 'map' }),
  f('text-emissive-strength', 'number', { default: 1, minimum: 0, transition: true, group: '3d' }),
]

const LAYOUT_CIRCLE: SpecField[] = [
  vis,
  f('circle-sort-key', 'number'),
  f('circle-elevation-reference', 'enum', { values: ['none', 'sea', 'ground', 'hd-road-markup'] }),
]

const PAINT_CIRCLE: SpecField[] = [
  f('circle-radius', 'number', { default: 5, minimum: 0, transition: true }),
  f('circle-color', 'color', { default: '#000000', transition: true }),
  f('circle-blur', 'number', { default: 0, minimum: 0, transition: true }),
  f('circle-opacity', 'number', { default: 1, minimum: 0, maximum: 1, transition: true }),
  f('circle-translate', 'array', { default: [0, 0], transition: true }),
  f('circle-translate-anchor', 'enum', { values: ['map', 'viewport'], default: 'map' }),
  f('circle-pitch-scale', 'enum', { values: ['map', 'viewport'], default: 'map' }),
  f('circle-pitch-alignment', 'enum', { values: ['map', 'viewport'], default: 'viewport' }),
  f('circle-stroke-width', 'number', { default: 0, minimum: 0, transition: true }),
  f('circle-stroke-color', 'color', { default: '#000000', transition: true }),
  f('circle-stroke-opacity', 'number', { default: 1, minimum: 0, maximum: 1, transition: true }),
  f('circle-emissive-strength', 'number', { default: 0, minimum: 0, transition: true, group: '3d' }),
]

const PAINT_HEATMAP: SpecField[] = [
  f('heatmap-radius', 'number', { default: 30, minimum: 1, transition: true }),
  f('heatmap-weight', 'number', { default: 1, minimum: 0 }),
  f('heatmap-intensity', 'number', { default: 1, minimum: 0, transition: true }),
  f('heatmap-color', 'json'),
  f('heatmap-opacity', 'number', { default: 1, minimum: 0, maximum: 1, transition: true }),
]

const PAINT_FILL_EXTRUSION: SpecField[] = [
  f('fill-extrusion-opacity', 'number', { default: 1, minimum: 0, maximum: 1, transition: true }),
  f('fill-extrusion-color', 'color', { default: '#000000', transition: true }),
  f('fill-extrusion-translate', 'array', { default: [0, 0], transition: true }),
  f('fill-extrusion-translate-anchor', 'enum', { values: ['map', 'viewport'], default: 'map' }),
  f('fill-extrusion-pattern', 'resolvedImage', { transition: true }),
  f('fill-extrusion-height', 'number', { default: 0, minimum: 0, transition: true, group: '3d' }),
  f('fill-extrusion-base', 'number', { default: 0, minimum: 0, transition: true, group: '3d' }),
  f('fill-extrusion-height-alignment', 'enum', { values: ['terrain', 'flat'], default: 'flat', group: '3d' }),
  f('fill-extrusion-base-alignment', 'enum', { values: ['terrain', 'flat'], default: 'flat', group: '3d' }),
  f('fill-extrusion-vertical-gradient', 'boolean', { default: true, group: '3d' }),
  f('fill-extrusion-vertical-scale', 'number', { default: 1, minimum: 0, transition: true, group: '3d' }),
  f('fill-extrusion-rounded-roof', 'boolean', { default: true, group: '3d' }),
  f('fill-extrusion-edge-radius', 'number', { default: 0, minimum: 0, group: '3d' }),
  f('fill-extrusion-line-width', 'number', { default: 0, minimum: 0, transition: true, group: '3d' }),
  f('fill-extrusion-ambient-occlusion-intensity', 'number', { default: 0, minimum: 0, maximum: 1, transition: true, group: '3d' }),
  f('fill-extrusion-ambient-occlusion-radius', 'number', { default: 3, minimum: 0, transition: true, group: '3d' }),
  f('fill-extrusion-ambient-occlusion-wall-radius', 'number', { default: 3, minimum: 0, transition: true, group: '3d' }),
  f('fill-extrusion-ambient-occlusion-ground-radius', 'number', { default: 3, minimum: 0, transition: true, group: '3d' }),
  f('fill-extrusion-ambient-occlusion-ground-attenuation', 'number', { default: 0.69, minimum: 0, maximum: 1, transition: true, group: '3d' }),
  f('fill-extrusion-ambient-occlusion-ground-intensity', 'number', { default: 0, minimum: 0, maximum: 1, transition: true, group: '3d' }),
  f('fill-extrusion-flood-light-color', 'color', { default: '#ffffff', transition: true, group: '3d' }),
  f('fill-extrusion-flood-light-intensity', 'number', { default: 0, minimum: 0, maximum: 1, transition: true, group: '3d' }),
  f('fill-extrusion-flood-light-wall-radius', 'number', { default: 0, minimum: 0, transition: true, group: '3d' }),
  f('fill-extrusion-flood-light-ground-radius', 'number', { default: 0, minimum: 0, transition: true, group: '3d' }),
  f('fill-extrusion-flood-light-ground-attenuation', 'number', { default: 0.69, minimum: 0, maximum: 1, transition: true, group: '3d' }),
  f('fill-extrusion-cutoff-fade-range', 'number', { default: 0, minimum: 0, maximum: 1, group: '3d' }),
  f('fill-extrusion-cast-shadows', 'boolean', { default: true, group: '3d' }),
  f('fill-extrusion-emissive-strength', 'number', { default: 0, minimum: 0, transition: true, group: '3d' }),
]

const LAYOUT_BUILDING: SpecField[] = [
  vis,
  f('building-height', 'number', { default: 0, minimum: 0, transition: true, group: '3d' }),
  f('building-base', 'number', { default: 0, minimum: 0, transition: true, group: '3d' }),
  f('building-roof-shape', 'enum', {
    values: ['flat', 'hipped', 'gabled', 'parapet', 'mansard', 'skillion', 'pyramidal'],
    default: 'flat',
    group: '3d',
  }),
  f('building-facade', 'boolean', { default: false, group: '3d' }),
  f('building-facade-floors', 'number', { default: 0, minimum: 0, group: '3d' }),
  f('building-facade-unit-width', 'number', { default: 0, minimum: 0, group: '3d' }),
  f('building-facade-window', 'array', { group: '3d' }),
  f('building-flood-light-wall-radius', 'number', { default: 0, minimum: 0, transition: true, group: '3d' }),
  f('building-flood-light-ground-radius', 'number', { default: 0, minimum: 0, transition: true, group: '3d' }),
  f('building-flip-roof-orientation', 'boolean', { default: false, group: '3d' }),
]

const PAINT_BUILDING: SpecField[] = [
  f('building-opacity', 'number', { default: 1, minimum: 0, maximum: 1, transition: true, group: '3d' }),
  f('building-color', 'color', { default: '#ffffff', transition: true, group: '3d' }),
  f('building-vertical-scale', 'number', { default: 1, minimum: 0, transition: true, group: '3d' }),
  f('building-cast-shadows', 'boolean', { default: true, group: '3d' }),
  f('building-ambient-occlusion-intensity', 'number', { default: 0.3, minimum: 0, maximum: 1, transition: true, group: '3d' }),
  f('building-ambient-occlusion-ground-intensity', 'number', { default: 0, minimum: 0, maximum: 1, transition: true, group: '3d' }),
  f('building-ambient-occlusion-ground-radius', 'number', { default: 3, minimum: 0, transition: true, group: '3d' }),
  f('building-ambient-occlusion-ground-attenuation', 'number', { default: 0.69, minimum: 0, maximum: 1, transition: true, group: '3d' }),
  f('building-emissive-strength', 'number', { default: 0, minimum: 0, transition: true, group: '3d' }),
  f('building-facade-emissive-chance', 'number', { default: 0, minimum: 0, maximum: 1, group: '3d' }),
  f('building-cutoff-fade-range', 'number', { default: 0, minimum: 0, maximum: 1, group: '3d' }),
  f('building-front-cutoff', 'array', { group: '3d' }),
  f('building-flood-light-color', 'color', { default: '#ffffff', transition: true, group: '3d' }),
  f('building-flood-light-intensity', 'number', { default: 0, minimum: 0, maximum: 1, transition: true, group: '3d' }),
  f('building-flood-light-ground-attenuation', 'number', { default: 0.69, minimum: 0, maximum: 1, transition: true, group: '3d' }),
]

const PAINT_RASTER: SpecField[] = [
  f('raster-opacity', 'number', { default: 1, minimum: 0, maximum: 1, transition: true }),
  f('raster-hue-rotate', 'number', { default: 0, transition: true }),
  f('raster-brightness-min', 'number', { default: 0, minimum: 0, maximum: 1, transition: true }),
  f('raster-brightness-max', 'number', { default: 1, minimum: 0, maximum: 1, transition: true }),
  f('raster-saturation', 'number', { default: 0, minimum: -1, maximum: 1, transition: true }),
  f('raster-contrast', 'number', { default: 0, minimum: -1, maximum: 1, transition: true }),
  f('raster-resampling', 'enum', { values: ['linear', 'nearest'], default: 'linear' }),
  f('raster-fade-duration', 'number', { default: 300, minimum: 0 }),
  f('raster-emissive-strength', 'number', { default: 0, minimum: 0, transition: true, group: '3d' }),
]

const PAINT_HILLSHADE: SpecField[] = [
  f('hillshade-illumination-direction', 'number', { default: 335, minimum: 0, maximum: 359 }),
  f('hillshade-illumination-anchor', 'enum', { values: ['map', 'viewport'], default: 'viewport' }),
  f('hillshade-exaggeration', 'number', { default: 0.5, minimum: 0, maximum: 1, transition: true }),
  f('hillshade-shadow-color', 'color', { default: '#000000', transition: true }),
  f('hillshade-highlight-color', 'color', { default: '#FFFFFF', transition: true }),
  f('hillshade-accent-color', 'color', { default: '#000000', transition: true }),
  f('hillshade-emissive-strength', 'number', { default: 0, minimum: 0, transition: true, group: '3d' }),
]

const PAINT_BACKGROUND: SpecField[] = [
  f('background-color', 'color', { default: '#000000', transition: true }),
  f('background-pattern', 'resolvedImage', { transition: true }),
  f('background-opacity', 'number', { default: 1, minimum: 0, maximum: 1, transition: true }),
  f('background-emissive-strength', 'number', { default: 0, minimum: 0, transition: true, group: '3d' }),
  f('background-pitch-alignment', 'enum', { values: ['map', 'viewport'] }),
]

const PAINT_SKY: SpecField[] = [
  f('sky-type', 'enum', { values: ['gradient', 'atmosphere'], default: 'atmosphere' }),
  f('sky-atmosphere-sun', 'array'),
  f('sky-atmosphere-sun-intensity', 'number', { default: 10, minimum: 0, maximum: 100 }),
  f('sky-gradient', 'json'),
  f('sky-atmosphere-halo-color', 'color', { default: 'white' }),
  f('sky-atmosphere-color', 'color', { default: 'white' }),
  f('sky-opacity', 'number', { default: 1, minimum: 0, maximum: 1, transition: true }),
]

const LAYOUT_CLIP: SpecField[] = [
  vis,
  f('clip-layer-types', 'array'),
  f('clip-layer-scope', 'array'),
]

const PAINT_RASTER_PARTICLE: SpecField[] = [
  f('raster-particle-array-band', 'string'),
  f('raster-particle-count', 'number', { default: 512 }),
  f('raster-particle-color', 'json'),
  f('raster-particle-max-speed', 'number', { default: 1 }),
  f('raster-particle-speed-factor', 'number', { default: 0.18, transition: true }),
  f('raster-particle-fade-opacity-factor', 'number', { default: 0.98, transition: true }),
  f('raster-particle-reset-rate-factor', 'number', { default: 0.4 }),
  f('raster-particle-elevation-reference', 'enum', { values: ['sea', 'ground'] }),
]

const LAYOUT_MODEL: SpecField[] = [
  vis,
  f('model-id', 'string'),
]

const PAINT_MODEL: SpecField[] = [
  f('model-opacity', 'number', { default: 1, minimum: 0, maximum: 1, transition: true }),
  f('model-rotation', 'array', { default: [0, 0, 0], transition: true }),
  f('model-scale', 'array', { default: [1, 1, 1] }),
  f('model-translation', 'array', { default: [0, 0, 0] }),
  f('model-color', 'color', { default: '#ffffff', transition: true }),
  f('model-color-mix-intensity', 'number', { default: 0, transition: true }),
  f('model-type', 'enum', { values: ['common-3d', 'location-indicator'] }),
  f('model-cast-shadows', 'boolean', { default: true, group: '3d' }),
  f('model-emissive-strength', 'number', { default: 0, minimum: 0, transition: true, group: '3d' }),
  f('model-roughness', 'number', { default: 1, minimum: 0, maximum: 1, transition: true }),
  f('model-height-based-emissive-strength-multiplier', 'array', { group: '3d' }),
  f('model-cutoff-fade-range', 'number', { default: 0, group: '3d' }),
]

const catalog: Record<string, { layout: SpecField[]; paint: SpecField[] }> = {
  fill: { layout: COMMON_FILL, paint: PAINT_FILL },
  line: { layout: LAYOUT_LINE, paint: PAINT_LINE },
  symbol: { layout: LAYOUT_SYMBOL, paint: PAINT_SYMBOL },
  circle: { layout: LAYOUT_CIRCLE, paint: PAINT_CIRCLE },
  heatmap: { layout: [vis], paint: PAINT_HEATMAP },
  'fill-extrusion': { layout: [vis], paint: PAINT_FILL_EXTRUSION },
  building: { layout: LAYOUT_BUILDING, paint: PAINT_BUILDING },
  raster: { layout: [vis], paint: PAINT_RASTER },
  hillshade: { layout: [vis], paint: PAINT_HILLSHADE },
  background: { layout: [vis], paint: PAINT_BACKGROUND },
  sky: { layout: [vis], paint: PAINT_SKY },
  slot: { layout: [vis], paint: [] },
  clip: { layout: LAYOUT_CLIP, paint: [] },
  model: { layout: LAYOUT_MODEL, paint: PAINT_MODEL },
  'raster-particle': { layout: [vis], paint: PAINT_RASTER_PARTICLE },
}

function withTransitions(fields: SpecField[]): SpecField[] {
  const extra: SpecField[] = []
  for (const field of fields) {
    if (field.transition) {
      extra.push(
        f(`${field.name}-transition`, 'json', {
          default: { duration: 300, delay: 0 },
          group: 'transition',
        }),
      )
    }
  }
  return [...fields, ...extra]
}

export function getLayerFields(type: string): { layout: SpecField[]; paint: SpecField[] } {
  const item = catalog[type] || { layout: [vis], paint: [] }
  return {
    layout: withTransitions(item.layout),
    paint: withTransitions(item.paint),
  }
}

export function mergeOfficialSpec(latest: Record<string, any>) {
  for (const [key, value] of Object.entries(latest)) {
    if (!key.startsWith('paint_') && !key.startsWith('layout_')) continue
    const kind = key.startsWith('paint_') ? 'paint' : 'layout'
    const type = key.replace(/^paint_/, '').replace(/^layout_/, '').replace(/_/g, '-')
    if (!catalog[type]) catalog[type] = { layout: [vis], paint: [] }
    if (!value || typeof value !== 'object') continue
    const list: SpecField[] = []
    for (const [name, meta] of Object.entries(value as Record<string, any>)) {
      if (!meta || typeof meta !== 'object') continue
      const rawType = meta.type as string
      let fieldType: FieldType = 'json'
      if (rawType === 'number' || rawType === 'color' || rawType === 'boolean' || rawType === 'string') {
        fieldType = rawType
      } else if (rawType === 'enum') {
        fieldType = 'enum'
      } else if (rawType === 'array') {
        fieldType = 'array'
      } else if (rawType === 'formatted') {
        fieldType = 'formatted'
      } else if (rawType === 'resolvedImage') {
        fieldType = 'resolvedImage'
      } else if (rawType === 'padding') {
        fieldType = 'padding'
      }
      list.push(
        f(name, fieldType, {
          default: meta.default,
          doc: meta.doc,
          values: meta.values ? Object.keys(meta.values) : undefined,
          minimum: meta.minimum,
          maximum: meta.maximum,
          transition: Boolean(meta.transition),
        }),
      )
    }
    catalog[type][kind] = list
  }
}

export async function tryLoadOfficialSpec() {
  // 内置字段表已覆盖 building / fill-extrusion 3.0；若后续安装官方包可在此 mergeOfficialSpec
}
