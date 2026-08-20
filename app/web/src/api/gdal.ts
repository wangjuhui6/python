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

// shp 获取字段
export async function getShpFields(data: any): Promise<string> {
  return await service({
    url: '/gdal/getShpFields',
    method: 'post',
    data
  })
}

// shp 生成白膜
export async function generateGlb(data: any): Promise<string> {
  return await service({
    url: '/gdal/generateGlb',
    method: 'post',
    data
  })
}

// 3dtiles裁剪
export async function clip3dTiles(data: any): Promise<string> {
  return await service({
    url: '/gdal/clip3dTiles',
    method: 'post',
    data
  })
}
