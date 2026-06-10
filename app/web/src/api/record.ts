import service from './index'

// 获取列表
export async function getRecordList(params: any): Promise<string> {
  return await service({
    url: '/record/list',
    method: 'get',
    params
  })
}