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
  created_at: string | null
  duration_seconds: number | null
  errors: string[]
  warnings: string[]
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

  getDownloadUrl(taskId: string): string {
    return `/api/v1/reports/${taskId}/download`
  },
}
