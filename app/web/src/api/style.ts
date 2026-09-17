import service from './index'

export async function readStyleFile(file_path: string): Promise<string> {
  return await service({
    url: '/style/read',
    method: 'post',
    data: { file_path },
  })
}

export async function writeStyleFile(file_path: string, content: string): Promise<void> {
  return await service({
    url: '/style/write',
    method: 'post',
    data: { file_path, content },
  })
}

export async function readStyleBinary(file_path: string): Promise<string> {
  return await service({
    url: '/style/read_binary',
    method: 'post',
    data: { file_path },
  })
}

export async function writeStyleBinary(file_path: string, content_b64: string): Promise<void> {
  return await service({
    url: '/style/write_binary',
    method: 'post',
    data: { file_path, content_b64 },
  })
}
