import service from './index'

// geoJSON转Shapefile
export async function geojsonToShp(data: any): Promise<string> {
  return await service({
    url: '/gdal/geojsonToShp',
    method: 'post',
    data
  })
}

// osm pbf转mbtiles
export async function osmPbfToMbtiles(data: any): Promise<string> {
  return await service({
    url: '/gdal/osmPbfToMbtiles',
    method: 'post',
    data
  })
}
