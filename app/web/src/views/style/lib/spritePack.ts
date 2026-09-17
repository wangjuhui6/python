export interface SpriteMeta {
  width: number
  height: number
  x: number
  y: number
  pixelRatio?: number
  sdf?: boolean
  content?: number[]
  stretchX?: number[][]
  stretchY?: number[][]
}

export type SpriteJson = Record<string, SpriteMeta>

export interface SpriteIconMeta {
  uid: string
  name: string
  width: number
  height: number
  pixelRatio: number
  sdf: boolean
  content?: number[]
  stretchX?: number[][]
  stretchY?: number[][]
}

export interface PackedIcon extends SpriteIconMeta {
  x: number
  y: number
}

export interface PackResult {
  width: number
  height: number
  items: PackedIcon[]
}

export const iconImages = new Map<string, HTMLCanvasElement>()

export function cloneCanvas(source: CanvasImageSource, width: number, height: number): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('无法创建画布')
  ctx.drawImage(source, 0, 0, width, height)
  return canvas
}

export function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('图片无法读取'))
    img.src = src
  })
}

export async function blobToCanvas(blob: Blob): Promise<HTMLCanvasElement> {
  const url = URL.createObjectURL(blob)
  try {
    const img = await loadImage(url)
    return cloneCanvas(img, img.naturalWidth, img.naturalHeight)
  } finally {
    URL.revokeObjectURL(url)
  }
}

export async function fileToCanvas(file: File): Promise<HTMLCanvasElement> {
  return blobToCanvas(file)
}

export function sliceIcon(source: CanvasImageSource, meta: SpriteMeta): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.width = meta.width
  canvas.height = meta.height
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('无法创建画布')
  ctx.drawImage(source, meta.x, meta.y, meta.width, meta.height, 0, 0, meta.width, meta.height)
  return canvas
}

export function iconNameFromFile(filename: string): { name: string; pixelRatio: number } {
  const base = filename.replace(/\.[^.]+$/, '')
  const retina = /@2x$/i.test(base)
  return {
    name: retina ? base.replace(/@2x$/i, '') : base,
    pixelRatio: retina ? 2 : 1,
  }
}

export function uniqueIconName(existing: Iterable<string>, raw: string): string {
  const used = new Set(existing)
  const base = raw.trim() || 'icon'
  if (!used.has(base)) return base
  let i = 2
  while (used.has(`${base}-${i}`)) i += 1
  return `${base}-${i}`
}

export function parseSpriteJson(text: string): SpriteJson {
  const data = JSON.parse(text)
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    throw new Error('sprite.json 格式无效')
  }
  const out: SpriteJson = {}
  for (const [name, value] of Object.entries(data as Record<string, any>)) {
    if (!value || typeof value !== 'object') continue
    const width = Number(value.width)
    const height = Number(value.height)
    const x = Number(value.x)
    const y = Number(value.y)
    if (![width, height, x, y].every((n) => Number.isFinite(n))) {
      throw new Error(`图标 ${name} 缺少 x/y/width/height`)
    }
    const meta: SpriteMeta = { width, height, x, y }
    if (value.pixelRatio != null) meta.pixelRatio = Number(value.pixelRatio) || 1
    if (value.sdf) meta.sdf = true
    if (Array.isArray(value.content)) meta.content = value.content.map(Number)
    if (Array.isArray(value.stretchX)) meta.stretchX = value.stretchX
    if (Array.isArray(value.stretchY)) meta.stretchY = value.stretchY
    out[name] = meta
  }
  if (!Object.keys(out).length) throw new Error('sprite.json 中没有图标')
  return out
}

export function layoutIcons(icons: SpriteIconMeta[], padding: number, maxWidth: number): PackResult {
  const items = icons.map((icon) => ({ ...icon, x: 0, y: 0 }))
  items.sort((a, b) => b.height - a.height || b.width - a.width || a.name.localeCompare(b.name))
  const gap = Math.max(0, padding)
  const limit = Math.max(
    maxWidth,
    ...items.map((item) => item.width + gap * 2),
    gap * 2 + 1,
  )
  let x = gap
  let y = gap
  let rowH = 0
  let sheetW = gap
  let sheetH = gap
  for (const item of items) {
    if (x > gap && x + item.width + gap > limit) {
      x = gap
      y += rowH + gap
      rowH = 0
    }
    item.x = x
    item.y = y
    x += item.width + gap
    rowH = Math.max(rowH, item.height)
    sheetW = Math.max(sheetW, x)
    sheetH = Math.max(sheetH, y + item.height + gap)
  }
  return {
    width: Math.max(1, sheetW),
    height: Math.max(1, sheetH),
    items,
  }
}

export function drawPacked(layout: PackResult, scale = 1, background?: string): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.width = Math.max(1, Math.round(layout.width * scale))
  canvas.height = Math.max(1, Math.round(layout.height * scale))
  const ctx = canvas.getContext('2d')
  if (!ctx) throw new Error('无法创建画布')
  if (background) {
    ctx.fillStyle = background
    ctx.fillRect(0, 0, canvas.width, canvas.height)
  } else {
    ctx.clearRect(0, 0, canvas.width, canvas.height)
  }
  ctx.imageSmoothingEnabled = scale !== 1
  for (const item of layout.items) {
    const src = iconImages.get(item.uid)
    if (!src) continue
    ctx.drawImage(
      src,
      0,
      0,
      src.width,
      src.height,
      Math.round(item.x * scale),
      Math.round(item.y * scale),
      Math.round(item.width * scale),
      Math.round(item.height * scale),
    )
  }
  return canvas
}

export function toSpriteJson(layout: PackResult, scale = 1): SpriteJson {
  const json: SpriteJson = {}
  const sorted = [...layout.items].sort((a, b) => a.name.localeCompare(b.name))
  for (const item of sorted) {
    const meta: SpriteMeta = {
      x: Math.round(item.x * scale),
      y: Math.round(item.y * scale),
      width: Math.round(item.width * scale),
      height: Math.round(item.height * scale),
      pixelRatio: (item.pixelRatio || 1) * scale,
    }
    if (item.sdf) meta.sdf = true
    if (item.content?.length) {
      meta.content = item.content.map((n) => Math.round(n * scale))
    }
    if (item.stretchX?.length) {
      meta.stretchX = item.stretchX.map((pair) => pair.map((n) => Math.round(n * scale)))
    }
    if (item.stretchY?.length) {
      meta.stretchY = item.stretchY.map((pair) => pair.map((n) => Math.round(n * scale)))
    }
    json[item.name] = meta
  }
  return json
}

export function canvasToPngBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob) reject(new Error('PNG 导出失败'))
      else resolve(blob)
    }, 'image/png')
  })
}

export async function blobToBase64(blob: Blob): Promise<string> {
  const buf = await blob.arrayBuffer()
  const bytes = new Uint8Array(buf)
  let binary = ''
  const chunk = 0x8000
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunk))
  }
  return btoa(binary)
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function joinPath(dir: string, name: string) {
  const sep = dir.includes('\\') ? '\\' : '/'
  return `${dir.replace(/[\\/]+$/, '')}${sep}${name}`
}
