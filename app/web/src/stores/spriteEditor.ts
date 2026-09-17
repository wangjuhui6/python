import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  iconImages,
  layoutIcons,
  type SpriteIconMeta,
  type SpriteJson,
  uniqueIconName,
} from '@/views/style/lib/spritePack'

export const useSpriteEditorStore = defineStore('spriteEditor', () => {
  const icons = ref<SpriteIconMeta[]>([])
  const selectedUid = ref<string | null>(null)
  const padding = ref(2)
  const maxWidth = ref(1024)
  const dirty = ref(false)
  const keyword = ref('')

  const selected = computed(() => icons.value.find((i) => i.uid === selectedUid.value) || null)
  const layout = computed(() => layoutIcons(icons.value, padding.value, maxWidth.value))
  const filtered = computed(() => {
    const q = keyword.value.trim().toLowerCase()
    if (!q) return icons.value
    return icons.value.filter((i) => i.name.toLowerCase().includes(q))
  })

  function touch() {
    dirty.value = true
  }

  function clearImages() {
    iconImages.clear()
  }

  function reset() {
    icons.value = []
    selectedUid.value = null
    clearImages()
    dirty.value = false
    keyword.value = ''
  }

  function names() {
    return icons.value.map((i) => i.name)
  }

  function addFromCanvas(canvas: HTMLCanvasElement, rawName: string, extra?: Partial<SpriteIconMeta>) {
    const uid = crypto.randomUUID()
    iconImages.set(uid, canvas)
    const name = uniqueIconName(names(), extra?.name || rawName)
    const icon: SpriteIconMeta = {
      uid,
      name,
      width: canvas.width,
      height: canvas.height,
      pixelRatio: extra?.pixelRatio || 1,
      sdf: extra?.sdf || false,
      content: extra?.content,
      stretchX: extra?.stretchX,
      stretchY: extra?.stretchY,
    }
    icons.value = [...icons.value, icon]
    selectedUid.value = uid
    touch()
    return icon
  }

  function importFromAtlas(source: HTMLCanvasElement, json: SpriteJson) {
    reset()
    const next: SpriteIconMeta[] = []
    for (const [name, meta] of Object.entries(json)) {
      const canvas = document.createElement('canvas')
      canvas.width = meta.width
      canvas.height = meta.height
      const ctx = canvas.getContext('2d')
      if (!ctx) continue
      ctx.drawImage(source, meta.x, meta.y, meta.width, meta.height, 0, 0, meta.width, meta.height)
      const uid = crypto.randomUUID()
      iconImages.set(uid, canvas)
      next.push({
        uid,
        name,
        width: meta.width,
        height: meta.height,
        pixelRatio: meta.pixelRatio || 1,
        sdf: Boolean(meta.sdf),
        content: meta.content,
        stretchX: meta.stretchX,
        stretchY: meta.stretchY,
      })
    }
    icons.value = next
    selectedUid.value = next[0]?.uid || null
    dirty.value = false
  }

  function remove(uid: string) {
    iconImages.delete(uid)
    icons.value = icons.value.filter((i) => i.uid !== uid)
    if (selectedUid.value === uid) selectedUid.value = icons.value[0]?.uid || null
    touch()
  }

  function updateIcon(uid: string, patch: Partial<SpriteIconMeta>) {
    icons.value = icons.value.map((icon) => {
      if (icon.uid !== uid) return icon
      const next = { ...icon, ...patch, uid }
      if (patch.name && patch.name !== icon.name) {
        next.name = uniqueIconName(
          icons.value.filter((i) => i.uid !== uid).map((i) => i.name),
          patch.name,
        )
      }
      return next
    })
    touch()
  }

  function replaceImage(uid: string, canvas: HTMLCanvasElement) {
    iconImages.set(uid, canvas)
    updateIcon(uid, { width: canvas.width, height: canvas.height })
  }

  function select(uid: string | null) {
    selectedUid.value = uid
  }

  function markClean() {
    dirty.value = false
  }

  function hitTest(px: number, py: number) {
    const found = layout.value.items.find(
      (item) => px >= item.x && py >= item.y && px < item.x + item.width && py < item.y + item.height,
    )
    return found?.uid || null
  }

  return {
    icons,
    selectedUid,
    selected,
    padding,
    maxWidth,
    dirty,
    keyword,
    layout,
    filtered,
    reset,
    addFromCanvas,
    importFromAtlas,
    remove,
    updateIcon,
    replaceImage,
    select,
    hitTest,
    touch,
    markClean,
  }
})
