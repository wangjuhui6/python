import { ref, type Ref } from 'vue'
import { onMounted } from 'vue'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'

mapboxgl.baseApiUrl = ''; // 不做权限验证
export interface useMapOptions {
  mapRef: Ref<HTMLDivElement | null>
  onMap?: (map: any) => void
}
export interface useMapReturn {
  map: any
  getMapBounds: () => any
}

const emptyCollection = {
  type: 'FeatureCollection',
  features: [],
}

export function useMap(props: useMapOptions): useMapReturn {

  let map: any = null

  onMounted(async () => {
    let dataChina: any = emptyCollection
    try {
      const china = await fetch('/map/json/china.geojson')
      if (china.ok) {
        dataChina = await china.json()
      }
    } catch {
      dataChina = emptyCollection
    }

    map = new mapboxgl.Map({
      container: props.mapRef.value as HTMLDivElement,
      style: {
        version: 8,
        sources: {
          'geojson-source': {
            type: 'geojson',
            data: emptyCollection,
          },
          'china-source': {
            type: 'geojson',
            data: dataChina,
          },
        },
        layers: [
          {
            id: 'background',
            type: 'background',
            paint: {
              'background-color': '#f4f1ea',
            },
          },
          {
            id: 'china-layer',
            type: 'fill',
            source: 'china-source',
            paint: {
              'fill-color': '#d6d3d1',
              'fill-opacity': 0.45,
              'fill-outline-color': '#a8a29e',
            },
          },
          {
            id: 'geojson-layer',
            type: 'fill',
            source: 'geojson-source',
            filter: ['match', ['geometry-type'], ['Polygon', 'MultiPolygon'], true, false],
            paint: {
              'fill-color': '#2563eb',
              'fill-opacity': 0.35,
              'fill-outline-color': '#1d4ed8',
            },
          },
          {
            id: 'geojson-line-layer',
            type: 'line',
            source: 'geojson-source',
            filter: ['match', ['geometry-type'], ['LineString', 'MultiLineString'], true, false],
            paint: {
              'line-color': '#1d4ed8',
              'line-width': 2,
            },
          },
          {
            id: 'geojson-circle-layer',
            type: 'circle',
            source: 'geojson-source',
            filter: ['match', ['geometry-type'], ['Point', 'MultiPoint'], true, false],
            paint: {
              'circle-color': '#dc2626',
              'circle-radius': 4,
              'circle-stroke-width': 1,
              'circle-stroke-color': '#fff',
            },
          },
        ],
      },
      center: [104.2, 35.6],
      zoom: 4,
    })

    map.on('load', () => {
      map.resize()
      props.onMap?.(map)
    })
  })

  function getMapBounds() {
    if (!map) return
    return map.getBounds()
  }

  return {
    map,
    getMapBounds,
  }
}
