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

export async function runLlmTransform(data: {
  instruction: string
  paths?: string[]
  dry_run?: boolean
  plan?: any
}): Promise<any> {
  return await service({
    url: '/llm/run',
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

export async function autoGeoref(formData: FormData): Promise<any> {
  return await service({
    url: '/llm/georef-auto',
    method: 'post',
    data: formData,
  })
}

export async function getTrainLegendDataset(): Promise<any> {
  return await service({
    url: '/llm/train-legend/dataset',
    method: 'get',
  })
}

export async function listTrainLegendSamples(status?: string): Promise<any> {
  return await service({
    url: '/llm/train-legend/samples',
    method: 'get',
    params: status ? { status } : undefined,
  })
}

export async function importTrainLegendSamples(formData: FormData): Promise<any> {
  return await service({
    url: '/llm/train-legend/samples',
    method: 'post',
    data: formData,
  })
}

export async function getTrainLegendSample(id: string): Promise<any> {
  return await service({
    url: `/llm/train-legend/samples/${id}`,
    method: 'get',
  })
}

export async function saveTrainLegendSample(id: string, data: any): Promise<any> {
  return await service({
    url: `/llm/train-legend/samples/${id}`,
    method: 'post',
    data,
  })
}

export async function prelabelTrainLegendSample(id: string, instruction?: string): Promise<any> {
  return await service({
    url: `/llm/train-legend/samples/${id}/prelabel`,
    method: 'post',
    data: { instruction },
  })
}

export async function deleteTrainLegendSample(id: string): Promise<any> {
  return await service({
    url: `/llm/train-legend/samples/${id}`,
    method: 'delete',
  })
}

export async function exportTrainLegend(statuses?: string[]): Promise<any> {
  return await service({
    url: '/llm/train-legend/export',
    method: 'post',
    data: { statuses },
  })
}

export async function addTrainLegendRun(data: {
  export_path?: string
  base_model?: string
  output_path?: string
  sample_count?: number
  notes?: string
}): Promise<any> {
  return await service({
    url: '/llm/train-legend/runs',
    method: 'post',
    data,
  })
}

export async function getSynthLegendConfig(): Promise<any> {
  return await service({
    url: '/llm/train-legend/synth-config',
    method: 'get',
  })
}

export async function saveSynthLegendConfig(data: any): Promise<any> {
  return await service({
    url: '/llm/train-legend/synth-config',
    method: 'post',
    data,
  })
}
