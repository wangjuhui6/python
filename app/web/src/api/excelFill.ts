import service from './index'

export function openExcelFill(): Promise<{ already: boolean }> {
  return service({
    url: '/excel-fill/open',
    method: 'post',
  })
}

export function arrayToTable(data: { rows: unknown[][], path: string }): Promise<{ path: string, rows: number, columns: number }> {
  return service({
    url: '/excel-fill/array-table',
    method: 'post',
    data,
  })
}
