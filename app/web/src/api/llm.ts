import service from './index'

export async function getLlmConfig(): Promise<any> {
  return await service({
    url: '/llm/config',
    method: 'get',
  })
}

export async function saveLlmConfig(data: any): Promise<any> {
  return await service({
    url: '/llm/config',
    method: 'post',
    data,
  })
}

export async function listLlmModels(model_dir?: string): Promise<any> {
  return await service({
    url: '/llm/models',
    method: 'get',
    params: { model_dir },
  })
}

export async function loadLlm(model_path?: string, mmproj_path?: string): Promise<any> {
  return await service({
    url: '/llm/load',
    method: 'post',
    data: { model_path, mmproj_path },
  })
}

export async function unloadLlm(): Promise<any> {
  return await service({
    url: '/llm/unload',
    method: 'post',
  })
}

export async function chatLlm(data: { prompt: string; system?: string }): Promise<any> {
  return await service({
    url: '/llm/chat',
    method: 'post',
    data,
  })
}

export async function previewLlmSource(path: string): Promise<any> {
  return await service({
    url: '/llm/preview',
    method: 'post',
    data: { path },
  })
}

export async function planLlmTransform(data: {
  instruction: string
  paths?: string[]
  path?: string
  mapping_path?: string
  save_path?: string
}): Promise<any> {
  return await service({
    url: '/llm/plan',
    method: 'post',
    data,
  })
}

export async function applyLlmTransform(data: {
  path?: string
  save_path?: string
  plan: any
  dry_run?: boolean
  mapping_path?: string
}): Promise<any> {
  return await service({
    url: '/llm/apply',
    method: 'post',
    data,
  })
}

export async function recognizeMapLegend(formData: FormData): Promise<any> {
  return await service({
    url: '/llm/map-legend',
    method: 'post',
    data: formData,
  })
}
