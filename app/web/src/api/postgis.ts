import service from './index'

// 查询数据源列表
export async function getDatasets(params: any): Promise<string> {
  return await service({
    url: '/postgis/datasets',
    method: 'get',
    params
  })
}

export async function getDataset(id: number | string): Promise<any> {
  return await service({
    url: `/postgis/datasets/${id}`,
    method: 'get',
  })
}

export async function updateDatasetCategories(data: any): Promise<any> {
  return await service({
    url: '/postgis/datasets/categories',
    method: 'post',
    data,
  })
}

// 新增/编辑数据源
export async function addDataset(data: any): Promise<string> {
  return await service({
    url: '/postgis/datasets/add',
    method: 'post',
    data
  })
}

// 删除数据源
export async function deleteDataset(data: any): Promise<string> {
  return await service({
    url: '/postgis/datasets/delete',
    method: 'post',
    data
  })
}

// 导入数据
export async function importData(data: any): Promise<string> {
  return await service({
    url: '/postgis/features/import',
    method: 'post',
    data
  })
}

// 根据数据源id查询数据
export async function listFeatures(params: any): Promise<any> {
  return await service({
    url: '/postgis/features/list',
    method: 'get',
    params
  })
}

export async function listFeaturesAtPoint(params: any): Promise<any> {
  return await service({
    url: '/postgis/features/at-point',
    method: 'get',
    params,
  })
}

// 根据数据源id删除所有数据
export async function deleteFeatures(data: any): Promise<string> {
  return await service({
    url: '/postgis/features/delete',
    method: 'post',
    data
  })
}

// 根据dataset_id查询数据中properties中的key
export async function getFeaturePropertiesKeys(data: any): Promise<string> {
  return await service({
    url: '/postgis/features/properties/keys',
    method: 'get',
    params: data
  })
}

// 根据dataset_id和key查询数据中properties中的value
export async function getFeaturePropertiesValues(data: any): Promise<string> {
  return await service({
    url: '/postgis/features/properties/values',
    method: 'get',
    params: data
  })
}
