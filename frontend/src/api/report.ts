import client from './client'

export interface GenerateRequest {
  upload_id?: string
  clinical_info: Record<string, any>
  project_type?: string | null
  project_name?: string | null
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
  output_filename?: string | null
  output_file_base64?: string | null
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

  async generateFromFile(file: File, req: Omit<GenerateRequest, 'upload_id'>): Promise<GenerateResult> {
    const form = new FormData()
    form.append('file', file)
    form.append('clinical_info', JSON.stringify(req.clinical_info || {}))
    if (req.project_type) form.append('project_type', req.project_type)
    if (req.project_name) form.append('project_name', req.project_name)
    if (req.template_name) form.append('template_name', req.template_name)
    if (req.strict_mode !== undefined) form.append('strict_mode', String(req.strict_mode))
    if (req.template_contract_mode) {
      form.append('template_contract_mode', req.template_contract_mode)
    }
    if (req.qa_visual_render) form.append('qa_visual_render', req.qa_visual_render)
    if (req.qa_visual_render_required !== undefined && req.qa_visual_render_required !== null) {
      form.append('qa_visual_render_required', String(req.qa_visual_render_required))
    }
    if (req.qa_visual_render_dpi !== undefined && req.qa_visual_render_dpi !== null) {
      form.append('qa_visual_render_dpi', String(req.qa_visual_render_dpi))
    }
    if (
      req.qa_visual_render_timeout_seconds !== undefined
      && req.qa_visual_render_timeout_seconds !== null
    ) {
      form.append(
        'qa_visual_render_timeout_seconds',
        String(req.qa_visual_render_timeout_seconds),
      )
    }
    const { data } = await client.post('/reports/generate-file', form)
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

  async download(taskId: string): Promise<void> {
    const response = await client.get(`/reports/${taskId}/download`, {
      responseType: 'blob',
    })
    const disposition = String(response.headers['content-disposition'] || '')
    const match = disposition.match(/filename\*=UTF-8''([^;]+)|filename="?([^"]+)"?/)
    const filename = decodeURIComponent(match?.[1] || match?.[2] || `${taskId}.docx`)
    const url = window.URL.createObjectURL(response.data)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  },

  downloadInline(result: GenerateResult): void {
    if (!result.output_file_base64) {
      throw new Error('报告内容不存在')
    }
    const binary = window.atob(result.output_file_base64)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i += 1) {
      bytes[i] = binary.charCodeAt(i)
    }
    const blob = new Blob([bytes], {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = result.output_filename || `${result.task_id}.docx`
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.URL.revokeObjectURL(url)
  },
}
