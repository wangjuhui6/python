<template>
  <div class="map-wrapper">
    <div ref="mapContainer" class="map-container"></div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { listFeatures } from '@/api/postgis'
import { useMap } from '@/hooks/useMap'

const route = useRoute()
const id = route.params.id as string
const mapContainer = ref<HTMLDivElement | null>(null)

let _map: any = null

useMap({
  mapRef: mapContainer,
  onMap: (map) => {
    _map = map
    setData()
  }
})

let geojsonData: any = {
  type: 'FeatureCollection',
  features: []
}

function setData() {
  if (!_map) return
  // _map.addSource('geojson-source', {
  //   type: 'geojson',
  //   data: {
  //     type: 'FeatureCollection',
  //     features: []
  //   }
  // })
  _map.getSource('geojson-source').setData(geojsonData)
}

onMounted(async () => {
  const res: any = await listFeatures({ datasets_id: id, is_geojson: true, page_size: 10000 })
  geojsonData = {
    type: 'FeatureCollection',
    features: res.data
  }
  setData()
})
</script>

<style scoped>
.map-wrapper{
  width: 100%;
  height: 100%;
}
.map-container{
  width: 100%;
  height: 100%;
}
</style>