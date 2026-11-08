import service from './index'

export async function basemapStatus(): Promise<any> {
  return await service({
    url: '/basemap/status',
    method: 'get',
  })
}

export async function basemapStart(data: { mbtiles: string; style: string }): Promise<any> {
  return await service({
    url: '/basemap/start',
    method: 'post',
    data,
  })
}

export async function basemapStop(): Promise<any> {
  return await service({
    url: '/basemap/stop',
    method: 'post',
  })
}
