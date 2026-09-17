import type { StyleJSON } from './types'

export function createEmptyStyle(): StyleJSON {
  return {
    version: 8,
    name: 'Untitled',
    center: [114.285, 30.575],
    zoom: 12,
    bearing: 0,
    pitch: 45,
    sources: {},
    sprite: 'sprite',
    glyphs: '{fontstack}/{range}.pbf',
    layers: [
      {
        id: 'background',
        type: 'background',
        paint: {
          'background-color': '#e8e4dc',
        },
      },
    ],
    transition: {
      duration: 300,
      delay: 0,
    },
  }
}

export function cloneStyle(style: StyleJSON): StyleJSON {
  return JSON.parse(JSON.stringify(style)) as StyleJSON
}

export function normalizeStyle(style: StyleJSON): StyleJSON {
  const next = cloneStyle(style)
  next.version = 8
  if (!next.sources) next.sources = {}
  if (!Array.isArray(next.layers)) next.layers = []
  next.layers = next.layers.map((layer: any) => {
    const copy = { ...layer }
    if (copy.paint && Object.keys(copy.paint).length === 0) delete copy.paint
    if (copy.layout && Object.keys(copy.layout).length === 0) delete copy.layout
    return copy
  })
  return next
}

export function uniqueLayerId(style: StyleJSON, base: string): string {
  let id = base
  let i = 1
  const ids = new Set(style.layers.map((l: any) => l.id))
  while (ids.has(id)) {
    id = `${base}-${i++}`
  }
  return id
}
