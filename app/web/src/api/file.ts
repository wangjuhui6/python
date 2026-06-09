import service from './index'

// 选择文件
export async function selectFile(data: any): Promise<string> {
  return await service({
    url: '/tkinter/file',
    method: 'post',
    data
  })
}

// 选择文件夹
export async function selectFolder(data: any): Promise<string> {
  return await service({
    url: '/tkinter/folder',
    method: 'post',
    data
  })
}

// 选择要保存的文件路径
export async function selectSavePath(data: any): Promise<string> {
  return await service({
    url: '/tkinter/save_path',
    method: 'post',
    data
  })
}