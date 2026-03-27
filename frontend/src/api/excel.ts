import client from './client'

export interface UploadResult {
  upload_id: string
  original_filename: string
  file_size_bytes: number
  sheet_names: string[]
  detected_project_type: string | null
  detected_project_name: string | null
  detection_confidence: number | null
}

export interface SheetInfo {
  name: string
  rows: number
  columns: number
}

export interface SheetData {
  name: string
  columns: string[]
  rows: Record<string, any>[]
  total_rows: number
  page: number
  page_size: number
}

export const excelApi = {
  async upload(file: File): Promise<UploadResult> {
    const form = new FormData()
    form.append('file', file)
    const { data } = await client.post('/excel/upload', form)
    return data.data
  },

  async getSheets(uploadId: string): Promise<SheetInfo[]> {
    const { data } = await client.get(`/excel/${uploadId}/sheets`)
    return data.data
  },

  async getSheetData(
    uploadId: string,
    sheetName: string,
    page = 1,
    pageSize = 50,
  ): Promise<SheetData> {
    const { data } = await client.get(
      `/excel/${uploadId}/sheets/${encodeURIComponent(sheetName)}`,
      { params: { page, page_size: pageSize } },
    )
    return data.data
  },

  async getSingleValues(uploadId: string): Promise<Record<string, any>> {
    const { data } = await client.get(`/excel/${uploadId}/single-values`)
    return data.data.fields
  },

  async detect(uploadId: string) {
    const { data } = await client.get(`/excel/${uploadId}/detect`)
    return data.data
  },
}
