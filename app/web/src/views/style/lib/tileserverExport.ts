import type { StyleJSON } from './types'
import { normalizeStyle } from './emptyStyle'

export interface TileserverExportOptions {
  sprite?: string
  glyphs?: string
  mbtilesMap?: Record<string, string>
}

export function rewriteForTileserver(style: StyleJSON, options: TileserverExportOptions): StyleJSON {
  const next = normalizeStyle(style)
  if (options.sprite !== undefined && options.sprite !== '') {
    next.sprite = options.sprite
  }
  if (options.glyphs !== undefined && options.glyphs !== '') {
    next.glyphs = options.glyphs
  }
  if (options.mbtilesMap) {
    for (const [sourceId, file] of Object.entries(options.mbtilesMap)) {
      if (!next.sources[sourceId] || !file) continue
      const name = file.replace(/^mbtiles:\/\//, '')
      next.sources[sourceId] = {
        ...next.sources[sourceId],
        type: next.sources[sourceId].type || 'vector',
        url: `mbtiles://${name}`,
      }
      delete next.sources[sourceId].tiles
    }
  }
  return next
}

export function buildTileserverConfig(styleId: string, styleFile = `${styleId}/style.json`) {
  return {
    options: {
      paths: {
        root: '/data',
        fonts: 'fonts',
        sprites: 'sprites',
        styles: 'styles',
        mbtiles: 'data',
      },
    },
    styles: {
      [styleId]: {
        style: styleFile,
        tilejson: {
          format: 'png',
        },
      },
    },
  }
}
