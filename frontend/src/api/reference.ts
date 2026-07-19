import client from './client'

export interface ReferenceReport {
  id: string
  panel_id: string
  case_id: string
  name: string
  original_filename: string
  checksum_sha256: string
  active: boolean
  formal_golden_verified: boolean
  notes?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface ReferenceReportList {
  items: ReferenceReport[]
  total: number
}

export const referenceApi = {
  async list(params: { panel_id?: string; case_id?: string; active?: boolean } = {}): Promise<ReferenceReportList> {
    const { data } = await client.get('/reference-reports', { params })
    return data.data
  },

  async upload(payload: {
    panel_id: string
    case_id: string
    name?: string
    notes?: string
    active?: boolean
    file: File
  }): Promise<ReferenceReport> {
    const formData = new FormData()
    formData.append('panel_id', payload.panel_id)
    formData.append('case_id', payload.case_id)
    if (payload.name) formData.append('name', payload.name)
    if (payload.notes) formData.append('notes', payload.notes)
    formData.append('active', String(payload.active ?? true))
    formData.append('file', payload.file)
    const { data } = await client.post('/reference-reports', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data.data
  },

  async activate(referenceId: string): Promise<ReferenceReport> {
    const { data } = await client.post(`/reference-reports/${referenceId}/activate`)
    return data.data
  },

  async delete(referenceId: string): Promise<void> {
    await client.delete(`/reference-reports/${referenceId}`)
  },

  getDownloadUrl(referenceId: string): string {
    return `/api/v1/reference-reports/${referenceId}/download`
  },
}
