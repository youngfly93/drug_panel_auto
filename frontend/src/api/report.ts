import client from './client'

export interface GenerateRequest {
  upload_id: string
  clinical_info: Record<string, any>
  project_type?: string | null
  template_name?: string | null
  strict_mode?: boolean
  template_contract_mode?: string
  qa_visual_render?: 'none' | 'first' | 'all' | null
  qa_visual_render_required?: boolean | null
  qa_visual_render_dpi?: number | null
  qa_visual_render_timeout_seconds?: number | null
}

export interface GenerateResult {
  task_id: string
  success: boolean
  output_file: string | null
  field_provenance_file?: string | null
  qa_report_file?: string | null
  qa_status?: string | null
  qa_issues?: Array<Record<string, any>>
  visual_render?: Record<string, any> | null
  generation_id?: string | null
  stage_results?: Array<Record<string, any>>
  stage_results_file?: string | null
  diff_status?: string | null
  diff_gate_passed?: boolean | null
  diff_reference_id?: string | null
  diff_reference_name?: string | null
  diff_auto_ran?: boolean
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
  generation_id?: string | null
  stage_results_file?: string | null
  stage_results?: Array<Record<string, any>>
  diff_report_file?: string | null
  diff_markdown_file?: string | null
  diff_status?: string | null
  diff_gate_passed?: boolean | null
  diff_reference_id?: string | null
  diff_reference_name?: string | null
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

export interface ReportDiffIssue {
  level: 'error' | 'warning' | string
  section?: string
  code: string
  message: string
}

export interface ReportDiffResult {
  status: 'PASS' | 'WARN' | 'FAIL' | string
  summary: {
    failures?: number
    warnings?: number
    text_similarity?: number | null
    table_count?: {
      reference?: number | null
      candidate?: number | null
    }
    total_reports?: number
    matched_references?: number
    pass?: number
    warn?: number
    fail?: number
    skip?: number
    blocked?: number
  }
  issues?: ReportDiffIssue[]
  sections?: Record<string, any>
  items?: Array<Record<string, any>>
  gate?: {
    fail_on: 'fail' | 'warn'
    passed: boolean
  }
  reference_report?: {
    id?: string
    panel_id?: string
    case_id?: string
    name?: string
    original_filename?: string
    active?: boolean
    source?: string
  }
  download_urls?: {
    json?: string
    markdown?: string
  }
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

  async getStageResults(taskId: string): Promise<Record<string, any>> {
    const { data } = await client.get(`/reports/${taskId}/stage-results`)
    return data.data
  },

  async renderVisual(
    taskId: string,
    params: { mode?: 'first' | 'all'; dpi?: number; timeout_seconds?: number } = {},
  ): Promise<VisualRenderResult> {
    const { data } = await client.post(`/reports/${taskId}/visual-render`, null, { params })
    return data.data
  },

  async compareReport(
    taskId: string,
    reference: File,
    params: { fail_on?: 'fail' | 'warn'; max_samples?: number } = {},
  ): Promise<ReportDiffResult> {
    const formData = new FormData()
    formData.append('reference', reference)
    const { data } = await client.post(`/reports/${taskId}/diff`, formData, {
      params,
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    return data.data
  },

  async compareReportWithRegisteredReference(
    taskId: string,
    params: { fail_on?: 'fail' | 'warn'; max_samples?: number } = {},
  ): Promise<ReportDiffResult> {
    const { data } = await client.post(`/reports/${taskId}/diff/auto`, null, { params })
    return data.data
  },

  async compareBatchWithRegisteredReferences(
    taskId: string,
    params: { fail_on?: 'fail' | 'warn'; max_samples?: number } = {},
  ): Promise<ReportDiffResult> {
    const { data } = await client.post(`/reports/${taskId}/diff/batch/auto`, null, { params })
    return data.data
  },

  async getReportDiff(taskId: string): Promise<ReportDiffResult> {
    const { data } = await client.get(`/reports/${taskId}/diff`)
    return data.data
  },

  getDiffDownloadUrl(taskId: string, artifact: 'report_diff.json' | 'report_diff.md'): string {
    return `/api/v1/reports/${taskId}/diff/download/${artifact}`
  },

  getBatchDiffDownloadUrl(taskId: string, artifact: 'batch_report_diff.json' | 'batch_report_diff.md'): string {
    return `/api/v1/reports/${taskId}/diff/batch/download/${artifact}`
  },

  getBatchDiffItemDownloadUrl(
    taskId: string,
    itemKey: string,
    artifact: 'report_diff.json' | 'report_diff.md',
  ): string {
    return `/api/v1/reports/${taskId}/diff/batch/items/${encodeURIComponent(itemKey)}/download/${artifact}`
  },

  getDownloadUrl(taskId: string): string {
    return `/api/v1/reports/${taskId}/download`
  },
}
