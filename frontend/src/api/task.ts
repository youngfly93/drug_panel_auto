import client from './client'

export interface TaskItem {
  id: string
  task_type: string
  status: string
  project_type: string | null
  qa_status?: string | null
  qa_report_file?: string | null
  generation_id?: string | null
  stage_results_file?: string | null
  diff_status?: string | null
  diff_gate_passed?: boolean | null
  diff_reference_id?: string | null
  diff_reference_name?: string | null
  review_status?: string | null
  review_status_label?: string | null
  review_updated_at?: string | null
  total_files: number
  completed_files: number
  failed_files: number
  cancelled_files?: number
  pending_files?: number
  running_files?: number
  status_counts?: Record<string, number>
  created_at: string | null
  started_at: string | null
  completed_at: string | null
  duration_seconds: number | null
  output_path?: string | null
  warnings?: string[]
  errors: string[]
}

export interface TaskListResponse {
  items: TaskItem[]
  total: number
  page: number
  page_size: number
}

export interface TaskStats {
  total: number
  completed: number
  failed: number
  running: number
  pending: number
  partial_failed?: number
  cancelled?: number
  today_total?: number
  needs_attention?: number
  awaiting_review?: number
  delivered?: number
}

export const taskApi = {
  async list(params: {
    status?: string
    task_type?: string
    project_type?: string
    qa_status?: string
    review_status?: string
    attention?: boolean
    q?: string
    created_from?: string
    created_to?: string
    page?: number
    page_size?: number
  } = {}): Promise<TaskListResponse> {
    const { data } = await client.get('/tasks', { params })
    return data.data
  },

  async getStats(): Promise<TaskStats> {
    const { data } = await client.get('/tasks/stats')
    return data.data
  },

  async get(taskId: string): Promise<TaskItem> {
    const { data } = await client.get(`/tasks/${taskId}`)
    return data.data
  },

  async cancel(taskId: string): Promise<void> {
    await client.delete(`/tasks/${taskId}`)
  },
}
