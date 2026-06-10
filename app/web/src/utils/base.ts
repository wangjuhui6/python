import {
  selectFile as selectFileApi,
  selectFolder as selectFolderApi,
  selectSavePath as selectSavePathApi,
} from '@/api/file'

// 数据类型对应表
export const dataTypes = {
  shapefile: [['Shapefile', '*.shp']],
  geopackage: [['GeoPackage', '*.gpkg']],
  json: [['JSON', '*.json']],
  csv: [['CSV', '*.csv']],
  tsv: [['TSV', '*.tsv']],
  psv: [['PSV', '*.psv']],
  xlsx: [['XLSX', '*.xlsx']],
  xls: [['XLS', '*.xls']],
  pdf: [['PDF', '*.pdf']],
  geoJSON: [['GeoJSON', '*.geojson']],
  topoJSON: [['TopoJSON', '*.topojson']],
  gpx: [['GPX', '*.gpx']],
  kml: [['KML', '*.kml']],
  kmz: [['KMZ', '*.kmz']],
  gdb: [['GDB', '*.gdb']],
  dbf: [['DBF', '*.dbf']],
  shp: [['SHP', '*.shp']],
  shx: [['SHX', '*.shx']],
  prj: [['PRJ', '*.prj']],
  geotiff: [['GeoTIFF', '*.tif']],
  zip: [['ZIP', '*.zip']],
  rar: [['RAR', '*.rar']],
  tar: [['TAR', '*.tar']],
  gzip: [['GZIP', '*.gz']],
  bzip2: [['BZIP2', '*.bz2']],
  xz: [['XZ', '*.xz']],
  lzma: [['LZMA', '*.lzma']],
  lz4: [['LZ4', '*.lz4']],
  mbtiles: [['MBTiles', '*.mbtiles']],
  osmPbf: [['OSM PBF', '*.pbf']],
}

// 选择文件
export async function selectFile(dataType?: string) {
  const res = await selectFileApi({
    filetypes: dataTypes[dataType as keyof typeof dataTypes],
  })
  return res
}

// 选择文件夹
export async function selectFolder(dataType?: string) {
  const res = await selectFolderApi({
    filetypes: dataTypes[dataType as keyof typeof dataTypes],
  })
  return res
}

// 选择要保存的文件路径
export async function selectSavePath(dataType?: string) {
  const res = await selectSavePathApi({
    filetypes: dataTypes[dataType as keyof typeof dataTypes],
  })
  return res
}