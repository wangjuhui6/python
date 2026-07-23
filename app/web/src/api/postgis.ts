import service from './index'

// 查询数据源列表
export async function getDatasets(params: any): Promise<string> {
  return await service({
    url: '/postgis/datasets',
    method: 'get',
    params
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