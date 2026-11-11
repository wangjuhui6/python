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
export async function osmPbfToMbtiles(data: any): Promise<any> {
  return await service({
    url: '/gdal/osmPbfToMbtiles',
    method: 'post',
    data
  })
}

export async function osmPbfToMbtilesEnv(): Promise<any> {
  return await service({
    url: '/gdal/osmPbfToMbtiles/env',
    method: 'get'
  })
}

export async function osmPbfToMbtilesStatus(): Promise<any> {
  return await service({
    url: '/gdal/osmPbfToMbtiles/status',
    method: 'get'
  })
}

export async function osmPbfToMbtilesStop(): Promise<any> {
  return await service({
    url: '/gdal/osmPbfToMbtiles/stop',
    method: 'post'
  })
}

export async function imageToMbtiles(data: any): Promise<any> {
  return await service({
    url: '/gdal/imageToMbtiles',
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

// 识别 shp 里的建筑
export async function inspectBuildingShp(data: any): Promise<any> {
  return await service({
    url: '/gdal/inspectBuildingShp',
    method: 'post',
    data
  })
}

// 字段取值
export async function buildingFieldValues(data: any): Promise<any> {
  return await service({
    url: '/gdal/buildingFieldValues',
    method: 'post',
    data
  })
}

// 导出建筑 shp
export async function exportBuildingShp(data: any): Promise<any> {
  return await service({
    url: '/gdal/exportBuildingShp',
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

// 线去重
export async function lineDeduplication(data: any): Promise<string> {
  return await service({
    url: '/gdal/lineDeduplication',
    method: 'post',
    data
  })
}

// 读取多个文件的内容
export async function readMultipleFiles(data: any): Promise<string> {
  return await service({
    url: '/tkinter/read_multiple_files',
    method: 'post',
    data
  })
}

// 生成文件
export async function generateFile(data: any): Promise<string> {
  return await service({
    url: '/tkinter/generate_file',
    method: 'post',
    data
  })
}