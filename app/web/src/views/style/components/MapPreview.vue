<template>
  <div class="map-preview-wrap">
    <div ref="container" class="map-preview"></div>
    <FeatureInspect />
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import { useStyleEditorStore } from '@/stores/styleEditor'
import { cloneStyle } from '@/views/style/lib/emptyStyle'
import FeatureInspect from './FeatureInspect.vue'

mapboxgl.baseApiUrl = ''

const store = useStyleEditorStore()
const container = ref<HTMLDivElement | null>(null)
let map: mapboxgl.Map | null = null
let applying = false

onMounted(() => {
  const style = cloneStyle(store.style)
  map = new mapboxgl.Map({
    container: container.value as HTMLDivElement,
    style: style as any,
    center: style.center || [114.285, 30.575],
    zoom: style.zoom ?? 12,
    pitch: style.pitch ?? 0,
    bearing: style.bearing ?? 0,
    attributionControl: false,
  })
  map.addControl(new mapboxgl.NavigationControl(), 'top-right')
  map.on('load', () => map?.resize())
  setTimeout(() => map?.resize(), 200)
  map.getCanvas().style.cursor = 'pointer'
  map.on('click', (e) => {
    if (!map) return
    const features = map.queryRenderedFeatures(e.point)
    const styleLayerIds = new Set(store.style.layers.map((l: any) => l.id))
    const picked = features
      .filter((f) => f.layer?.id && styleLayerIds.has(f.layer.id))
      .map((f) => ({
        layerId: f.layer.id,
        source: (f.layer as any).source,
        sourceLayer: f.sourceLayer,
        properties: { ...(f.properties || {}) },
      }))
    const unique: typeof picked = []
    const seen = new Set<string>()
    for (const item of picked) {
      const key = `${item.layerId}|${item.sourceLayer || ''}|${JSON.stringify(item.properties)}`
      if (seen.has(key)) continue
      seen.add(key)
      unique.push(item)
    }
    if (!unique.length) {
      store.clearPickedFeatures()
      return
    }
    store.setPickedFeatures(unique)
  })
  map.on('moveend', () => {
    if (!map || applying) return
    applying = true
    const c = map.getCenter()
    store.updateRoot(
      {
        center: [Number(c.lng.toFixed(6)), Number(c.lat.toFixed(6))],
        zoom: Number(map.getZoom().toFixed(2)),
        pitch: Number(map.getPitch().toFixed(1)),
        bearing: Number(map.getBearing().toFixed(1)),
      },
      { silent: true },
    )
    requestAnimationFrame(() => {
      applying = false
    })
  })
})

watch(
  () => store.revision,
  () => {
    if (!map) return
    applying = true
    try {
      map.setStyle(cloneStyle(store.style) as any, { diff: true })
    } catch {
      map.setStyle(cloneStyle(store.style) as any)
    }
    requestAnimationFrame(() => {
      applying = false
    })
  },
)

watch(
  () => [store.style.center, store.style.zoom, store.style.pitch, store.style.bearing],
  () => {
    if (!map || applying) return
    const center = store.style.center
    if (!center) return
    applying = true
    map.jumpTo({
      center,
      zoom: store.style.zoom,
      pitch: store.style.pitch,
      bearing: store.style.bearing,
    })
    requestAnimationFrame(() => {
      applying = false
    })
  },
)

onBeforeUnmount(() => {
  map?.remove()
  map = null
})
</script>

<style scoped>
.map-preview-wrap {
  width: 100%;
  height: 100%;
  position: relative;
}
.map-preview {
  width: 100%;
  height: 100%;
}
</style>
