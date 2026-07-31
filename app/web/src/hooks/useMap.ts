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

export function useMap(props: useMapOptions): useMapReturn {

  let map: any = null

  onMounted(async () => {
    
    const china = await fetch('/map/json/china.geojson')
    const dataChina = await china.json()
    
    map = new mapboxgl.Map({
      container: props.mapRef.value as HTMLDivElement,
      style: {
        version: 8,
        sources: {
          'geojson-source': {
            type: 'geojson',
            data: {
              type: 'FeatureCollection',
              features: []
            }
          },
          'china-source': {
            type: 'geojson',
            data: dataChina
          }
        },
        layers: [
          {
            id: 'china-layer',
            type: 'fill',
            source: 'china-source',
            paint: {
              'fill-color': '#000000',
              'fill-opacity': 0.1,
              'fill-outline-color': '#000000',
            }
          },
          {
            id: 'geojson-layer',
            type: 'fill',
            source: 'geojson-source',
            // filter: ['==', 'type', 'Polygon'],
            paint: {
              'fill-color': '#000000',
              'fill-opacity': 0.5
            }
          },
          {
            id: 'geojson-line-layer',
            type: 'line',
            source: 'geojson-source',
            // filter: ['==', 'type', 'LineString'],
            paint: {
              'line-color': '#000000',
              'line-width': 2
            }
          },
          {
            id: 'geojson-circle-layer',
            type: 'circle',
            source: 'geojson-source',
            // filter: ['==', 'type', 'Point'],
            paint: {
              'circle-color': '#000000',
              'circle-radius': 2
            }
          }
        ]
      },
      center: [114.285, 30.575],
      zoom: 12
    })

    map.on('load', () => {
      console.log('map loaded')
      props.onMap?.(map)
    })

    // 监听地图范围变化
    map.on('move', () => {
      // const bounds = getMapBounds()
      // console.log(bounds)
    })
  })

  // 获取地图范围
  function getMapBounds() {
    if (!map) return
    const bounds = map.getBounds()
    return bounds
  }

  return {
    map,
    getMapBounds
  }
}
