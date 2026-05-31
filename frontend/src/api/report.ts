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
  report_summary_file?: string | null
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

export interface BatchGenerateResult {
  task_id: string
  status: string
  total_files: number
  retry_files?: number
}

export interface TaskStatus {
  id: string
  task_type: string
  status: string
  project_type: string | null
  total_files: number
  completed_files: number
  failed_files: number
  cancelled_files?: number
  pending_files?: number
  running_files?: number
  status_counts?: Record<string, number>
  output_path: string | null
  field_provenance_file?: string | null
  qa_report_file?: string | null
  report_summary_file?: string | null
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
  started_at?: string | null
  completed_at?: string | null
  duration_seconds: number | null
  errors: string[]
  warnings: string[]
}

export interface BatchResultItem {
  index: number
  excel_filename: string
  status: string
  output_path?: string | null
  output_filename?: string | null
  download_url?: string | null
  report_summary_file?: string | null
  qa_status?: string | null
  project_type?: string | null
  project_name?: string | null
  clinical_info?: Record<string, any>
  duration_seconds?: number | null
  errors: string[]
  warnings: string[]
  validation?: Record<string, any>
}

export interface BatchResults {
  task_id: string
  status: string
  total_files: number
  completed_files: number
  failed_files: number
  cancelled_files?: number
  pending_files?: number
  running_files?: number
  status_counts?: Record<string, number>
  output_root?: string | null
  items: BatchResultItem[]
  batch_report?: Record<string, any> | null
}

export interface QualityGateIssue {
  level: 'blocker' | 'warning' | 'info' | string
  code: string
  message: string
  scope?: string
}

export interface ReviewState {
  schema_version?: string
  task_id: string
  status: 'draft' | 'reviewed' | 'delivered' | 'rejected' | string
  status_label?: string
  updated_at?: string | null
  updated_by?: string | null
  note?: string | null
  history?: Array<Record<string, any>>
}

export interface QualityGate {
  schema_version?: string
  task_id: string
  task_type: string
  status: 'PASS' | 'BLOCKED' | string
  passed: boolean
  generated_at?: string
  blockers: number
  warnings: number
  issues: QualityGateIssue[]
  metrics?: Record<string, any>
  diff?: Record<string, any>
  review?: ReviewState
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

export interface ReportSummary {
  schema_version?: string
  generation_id?: string | null
  project_type?: string | null
  project_name?: string | null
  output_file?: string | null
  generated_at?: string
  panel?: {
    status?: string | null
    template_status?: string | null
  }
  patient?: Record<string, any>
  biomarkers?: {
    tmb?: Record<string, any>
    msi?: Record<string, any>
    immune?: Record<string, any>
  }
  variants?: {
    total?: number | null
    drug_related?: number | null
    summary_count?: number | null
    by_class?: Record<string, number>
    key_rows?: Array<Record<string, any>>
    summary_rows?: Array<Record<string, any>>
  }
  drugs?: {
    targeted_count?: number | null
    chemotherapy_count?: number | null
    targeted_rows?: Array<Record<string, any>>
    chemotherapy_rows?: Array<Record<string, any>>
  }
  qa?: {
    status?: string | null
    issue_count?: number
    errors?: number
    warnings?: number
  }
  manual_review?: string[]
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

function buildReportFileForm(file: File, req: Omit<GenerateRequest, 'upload_id'>): FormData {
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
  return form
}

function parseContentDispositionFilename(disposition: string, fallback: string): string {
  const filenameStar = disposition.match(/(?:^|;)\s*filename\*=([^;]+)/i)?.[1]
  if (filenameStar) {
    const raw = filenameStar.trim().replace(/^"|"$/g, '')
    const encoded = raw.includes("''") ? raw.split("''").slice(1).join("''") : raw
    try {
      return decodeURIComponent(encoded)
    } catch {
      return encoded || fallback
    }
  }

  const filename = disposition.match(/(?:^|;)\s*filename="?([^";]+)"?/i)?.[1]
  if (filename) {
    try {
      return decodeURIComponent(filename.trim())
    } catch {
      return filename.trim() || fallback
    }
  }

  return fallback
}

async function parseErrorPayload(data: any): Promise<string | null> {
  if (!data) return null
  if (typeof data === 'string') {
    try {
      const parsed = JSON.parse(data)
      return parsed.detail || parsed.error || parsed.message || data
    } catch {
      return data
    }
  }
  if (data instanceof Blob) {
    const text = await data.text()
    if (!text) return null
    try {
      const parsed = JSON.parse(text)
      return parsed.detail || parsed.error || parsed.message || text
    } catch {
      return text
    }
  }
  if (typeof data === 'object') {
    return data.detail || data.error || data.message || null
  }
  return null
}

async function buildApiErrorMessage(error: any, fallback: string): Promise<string> {
  const status = error?.response?.status
  const payloadMessage = await parseErrorPayload(error?.response?.data)
  if (payloadMessage) return payloadMessage
  if (status === 401) return '登录已过期，请重新登录'
  if (status === 404) return '报告文件不存在或已过期，请重新生成后下载'
  if (error?.code === 'ECONNABORTED') return '请求超时，请稍后重试'
  if (error?.message === 'Network Error') return '网络连接失败，请检查服务是否在线'
  return error?.message || fallback
}

export const reportApi = {
  async generate(req: GenerateRequest): Promise<GenerateResult> {
    const { data } = await client.post('/reports/generate', req)
    return data.data
  },

  buildFileForm(file: File, req: Omit<GenerateRequest, 'upload_id'>): FormData {
    return buildReportFileForm(file, req)
  },

  async generateFromFile(file: File, req: Omit<GenerateRequest, 'upload_id'>): Promise<GenerateResult> {
    const form = buildReportFileForm(file, req)
    const { data } = await client.post('/reports/generate-file', form, {
      timeout: 180000,
    })
    return data.data
  },

  async generateFromFileAsync(file: File, req: Omit<GenerateRequest, 'upload_id'>): Promise<GenerateResult> {
    const form = buildReportFileForm(file, req)
    const { data } = await client.post('/reports/generate-file-async', form)
    return data.data
  },

  async generateBatchFromFiles(files: File[], req: Omit<GenerateRequest, 'upload_id'>): Promise<BatchGenerateResult> {
    const form = new FormData()
    files.forEach((file) => form.append('files', file))
    form.append('clinical_info', JSON.stringify(req.clinical_info || {}))
    if (req.project_type) form.append('project_type', req.project_type)
    if (req.project_name) form.append('project_name', req.project_name)
    if (req.template_name) form.append('template_name', req.template_name)
    if (req.template_contract_mode) {
      form.append('template_contract_mode', req.template_contract_mode)
    }
    const { data } = await client.post('/reports/batch-files', form)
    return data.data
  },

  async getTaskStatus(taskId: string): Promise<TaskStatus> {
    const { data } = await client.get(`/reports/${taskId}`)
    return data.data
  },

  async getBatchResults(taskId: string): Promise<BatchResults> {
    const { data } = await client.get(`/reports/${taskId}/batch-results`)
    return data.data
  },

  async retryBatchFailed(taskId: string, includeCancelled = false): Promise<BatchGenerateResult> {
    const { data } = await client.post(`/reports/${taskId}/batch/retry-failed`, null, {
      params: { include_cancelled: includeCancelled },
    })
    return data.data
  },

  async cancelTask(taskId: string): Promise<void> {
    await client.delete(`/tasks/${taskId}`)
  },

  async getQualityGate(taskId: string): Promise<QualityGate> {
    const { data } = await client.get(`/reports/${taskId}/quality-gate`)
    return data.data
  },

  async getReviewState(taskId: string): Promise<ReviewState> {
    const { data } = await client.get(`/reports/${taskId}/review-state`)
    return data.data
  },

  async updateReviewState(
    taskId: string,
    req: {
      status: 'draft' | 'reviewed' | 'delivered' | 'rejected' | string
      operator?: string | null
      note?: string | null
      override_gate?: boolean
    },
  ): Promise<ReviewState> {
    const { data } = await client.post(`/reports/${taskId}/review-state`, req)
    return data.data
  },

  async getQaReport(taskId: string): Promise<Record<string, any>> {
    const { data } = await client.get(`/reports/${taskId}/qa`)
    return data.data
  },

  async getReportSummary(taskId: string): Promise<ReportSummary> {
    const { data } = await client.get(`/reports/${taskId}/summary`)
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

  getBatchDownloadUrl(taskId: string, qaPassOnly = false): string {
    return qaPassOnly
      ? `/api/v1/reports/${taskId}/batch/download?qa=pass`
      : `/api/v1/reports/${taskId}/batch/download`
  },

  getAuditPackageUrl(taskId: string, includeFailed = true): string {
    return includeFailed
      ? `/api/v1/reports/${taskId}/audit-package`
      : `/api/v1/reports/${taskId}/audit-package?include_failed=false`
  },

  async download(taskId: string): Promise<void> {
    try {
      const response = await client.get(`/reports/${taskId}/download`, {
        responseType: 'blob',
        timeout: 120000,
      })
      const disposition = String(response.headers['content-disposition'] || '')
      const filename = parseContentDispositionFilename(disposition, `${taskId}.docx`)
      const url = window.URL.createObjectURL(response.data)
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.appendChild(link)
      link.click()
      link.remove()
      window.URL.revokeObjectURL(url)
    } catch (error: any) {
      throw new Error(await buildApiErrorMessage(error, '报告下载失败'))
    }
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
