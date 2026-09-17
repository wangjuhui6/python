import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { StyleJSON } from '@/views/style/lib/types'
import { createEmptyStyle, normalizeStyle, uniqueLayerId } from '@/views/style/lib/emptyStyle'

export interface PickedFeature {
  layerId: string
  source?: string
  sourceLayer?: string
  properties: Record<string, unknown>
}

export const useStyleEditorStore = defineStore('styleEditor', () => {
  const style = ref<StyleJSON>(createEmptyStyle())
  const selectedLayerId = ref<string | null>(style.value.layers[0]?.id || null)
  const revision = ref(0)
  const dirty = ref(false)
  const leftTab = ref<'layers' | 'sources' | 'assets'>('layers')
  const pickedFeatures = ref<PickedFeature[]>([])
  const pickedIndex = ref(0)
  const suggestedHeightField = ref('')
  const suggestedBaseField = ref('')

  const selectedLayer = computed(() => style.value.layers.find((l: any) => l.id === selectedLayerId.value) || null)
  const sourceIds = computed(() => Object.keys(style.value.sources || {}))

  function touch() {
    revision.value += 1
    dirty.value = true
  }

  function setStyle(next: StyleJSON) {
    style.value = normalizeStyle(next)
    selectedLayerId.value = style.value.layers[0]?.id || null
    revision.value += 1
    dirty.value = false
  }

  function resetEmpty() {
    setStyle(createEmptyStyle())
  }

  function updateRoot(partial: Partial<StyleJSON>, opts?: { silent?: boolean }) {
    style.value = { ...style.value, ...partial }
    if (opts?.silent) {
      dirty.value = true
      return
    }
    touch()
  }

  function selectLayer(id: string | null) {
    selectedLayerId.value = id
  }

  function addLayer(layer: any, beforeId?: string) {
    const copy = { ...layer, id: uniqueLayerId(style.value, layer.id || layer.type) }
    const layers = [...style.value.layers]
    const idx = beforeId ? layers.findIndex((l: any) => l.id === beforeId) : -1
    if (idx >= 0) layers.splice(idx, 0, copy)
    else layers.push(copy)
    style.value = { ...style.value, layers }
    selectedLayerId.value = copy.id
    touch()
  }

  function updateLayer(id: string, patch: Record<string, unknown>) {
    style.value = {
      ...style.value,
      layers: style.value.layers.map((layer: any) => (layer.id === id ? { ...layer, ...patch } : layer)),
    }
    if (patch.id && patch.id !== id) selectedLayerId.value = String(patch.id)
    touch()
  }

  function setLayerPaint(id: string, key: string, value: unknown) {
    style.value = {
      ...style.value,
      layers: style.value.layers.map((layer: any) => {
        if (layer.id !== id) return layer
        const paint = { ...(layer.paint || {}) }
        if (value === undefined) delete paint[key]
        else paint[key] = value
        const next = { ...layer, paint }
        if (Object.keys(paint).length === 0) delete next.paint
        return next
      }),
    }
    touch()
  }

  function setLayerLayout(id: string, key: string, value: unknown) {
    style.value = {
      ...style.value,
      layers: style.value.layers.map((layer: any) => {
        if (layer.id !== id) return layer
        const layout = { ...(layer.layout || {}) }
        if (value === undefined) delete layout[key]
        else layout[key] = value
        const next = { ...layer, layout }
        if (Object.keys(layout).length === 0) delete next.layout
        return next
      }),
    }
    touch()
  }

  function removeLayer(id: string) {
    const layers = style.value.layers.filter((l: any) => l.id !== id)
    style.value = { ...style.value, layers }
    if (selectedLayerId.value === id) selectedLayerId.value = layers[layers.length - 1]?.id || null
    touch()
  }

  function duplicateLayer(id: string) {
    const layer = style.value.layers.find((l: any) => l.id === id)
    if (!layer) return
    addLayer(JSON.parse(JSON.stringify(layer)))
  }

  function moveLayer(from: number, to: number) {
    if (from === to || from < 0 || to < 0) return
    const layers = [...style.value.layers]
    if (from >= layers.length || to >= layers.length) return
    const [item] = layers.splice(from, 1)
    layers.splice(to, 0, item)
    style.value = { ...style.value, layers }
    touch()
  }

  function addSource(id: string, source: any) {
    style.value = { ...style.value, sources: { ...style.value.sources, [id]: source } }
    touch()
  }

  function updateSource(id: string, source: any, nextId?: string) {
    const sources = { ...style.value.sources }
    if (nextId && nextId !== id) {
      delete sources[id]
      sources[nextId] = source
      style.value = {
        ...style.value,
        sources,
        layers: style.value.layers.map((layer: any) => (layer.source === id ? { ...layer, source: nextId } : layer)),
      }
    } else {
      sources[id] = source
      style.value = { ...style.value, sources }
    }
    touch()
  }

  function removeSource(id: string) {
    const sources = { ...style.value.sources }
    delete sources[id]
    style.value = { ...style.value, sources }
    touch()
  }

  function setPickedFeatures(list: PickedFeature[]) {
    pickedFeatures.value = list
    pickedIndex.value = 0
    if (list[0]?.layerId) selectedLayerId.value = list[0].layerId
  }

  function usePickedField(kind: 'height' | 'base', key: string) {
    if (kind === 'height') suggestedHeightField.value = key
    else suggestedBaseField.value = key
  }

  function clearPickedFeatures() {
    pickedFeatures.value = []
    pickedIndex.value = 0
  }

  function exportStyle() {
    return normalizeStyle(style.value)
  }

  return {
    style,
    selectedLayerId,
    selectedLayer,
    sourceIds,
    revision,
    dirty,
    leftTab,
    pickedFeatures,
    pickedIndex,
    suggestedHeightField,
    suggestedBaseField,
    setPickedFeatures,
    clearPickedFeatures,
    usePickedField,
    setStyle,
    resetEmpty,
    updateRoot,
    selectLayer,
    addLayer,
    updateLayer,
    setLayerPaint,
    setLayerLayout,
    removeLayer,
    duplicateLayer,
    moveLayer,
    addSource,
    updateSource,
    removeSource,
    exportStyle,
  }
})
