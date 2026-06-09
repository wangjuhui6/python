import service from './index'

// geoJSON转Shapefile
export async function geojsonToShp(data: any): Promise<string> {
  return await service({
    url: '/gdal/geojsonToShp',
    method: 'post',
    data
  })
}