import client from './client'

export interface GenerateRequest {
  upload_id: string
  clinical_info: Record<string, any>
  project_type?: string | null
  template_name?: string | null
  strict_mode?: boolean
  template_contract_mode?: string
}

export interface GenerateResult {
  task_id: string
  success: boolean
  output_file: string | null
  field_provenance_file?: string | null
  qa_report_file?: string | null
  qa_status?: string | null
  qa_issues?: Array<Record<string, any>>
  duration_seconds: number | null
  errors: string[]
  warnings: string[]
}

export interface TaskStatus {
  id: string
  task_type: string
  status: string
  project_type: string | null
  total_files: number
  completed_files: number
  failed_files: number
  output_path: string | null
  field_provenance_file?: string | null
  qa_report_file?: string | null
  qa_status?: string | null
  created_at: string | null
  duration_seconds: number | null
  errors: string[]
  warnings: string[]
}

export interface RenderedPage {
  filename: string
  url: string
}

export interface VisualRenderResult {
  requested: 'first' | 'all'
  status: 'PASS' | 'WARN' | 'FAIL' | string
  message: string
  rendered_pages: RenderedPage[]
  output_dir?: string | null
  error?: string | null
  stage?: string | null
  command?: string[]
  stdout_tail?: string
  stderr_tail?: string
}

export const reportApi = {
  async generate(req: GenerateRequest): Promise<GenerateResult> {
    const { data } = await client.post('/reports/generate', req)
    return data.data
  },

  async getTaskStatus(taskId: string): Promise<TaskStatus> {
    const { data } = await client.get(`/reports/${taskId}`)
    return data.data
  },

  async getQaReport(taskId: string): Promise<Record<string, any>> {
    const { data } = await client.get(`/reports/${taskId}/qa`)
    return data.data
  },

  async getFieldProvenance(taskId: string): Promise<Record<string, any>> {
    const { data } = await client.get(`/reports/${taskId}/field-provenance`)
    return data.data
  },

  async renderVisual(
    taskId: string,
    params: { mode?: 'first' | 'all'; dpi?: number; timeout_seconds?: number } = {},
  ): Promise<VisualRenderResult> {
    const { data } = await client.post(`/reports/${taskId}/visual-render`, null, { params })
    return data.data
  },

  getDownloadUrl(taskId: string): string {
    return `/api/v1/reports/${taskId}/download`
  },
}
