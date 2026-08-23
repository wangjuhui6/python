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

// 保存文件路径 保存文件名
export async function selectSavePathAndFileName(data: any): Promise<string> {
  return await service({
    url: '/tkinter/save_path_and_file_name',
    method: 'post',
    data
  })
}