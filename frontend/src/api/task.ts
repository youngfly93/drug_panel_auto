import client from './client'

export interface TaskItem {
  id: string
  task_type: string
  status: string
  project_type: string | null
  total_files: number
  completed_files: number
  failed_files: number
  created_at: string | null
  started_at: string | null
  completed_at: string | null
  duration_seconds: number | null
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
}

export const taskApi = {
  async list(params: { status?: string; task_type?: string; page?: number; page_size?: number } = {}): Promise<TaskListResponse> {
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
