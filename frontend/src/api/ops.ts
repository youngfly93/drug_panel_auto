import client from './client'

export interface OpsStatusBlock {
  status: string
  last_at: string | null
}

export interface OpsStatusPayload {
  schema_version: string
  generated_at: string
  deployment: {
    release: string | null
    revision_short: string | null
    revision: string | null
  }
  runtime: {
    runtime_dir_present: boolean
    libreoffice_listener: {
      checked: boolean
      running: boolean | null
    }
    watchdog: {
      log_present: boolean
      last_event_at: string | null
      web: OpsStatusBlock
      tunnel: OpsStatusBlock
      libreoffice: OpsStatusBlock
      disk: OpsStatusBlock
    }
    maintenance: {
      log_present: boolean
      last_event_at: string | null
      last_backup_at: string | null
      last_verify_at: string | null
      last_cleanup_at: string | null
      last_lock_notice_at: string | null
    }
  }
  storage: {
    disk: {
      available: boolean
      total_bytes?: number
      used_bytes?: number
      free_bytes?: number
      used_percent?: number | null
    }
    buckets: Record<string, {
      exists: boolean
      top_level_entries: number | null
    }>
  }
  tasks: {
    counts: {
      total: number
      by_status: Record<string, number>
      failed_total: number
    }
    recent: Array<{
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
    }>
  }
  downloads: {
    log_present: boolean
    summary: {
      events: number
      started: number
      terminal: number
      completed: number
      slow: number
      failed: number
      avg_duration_ms: number | null
      max_duration_ms: number | null
      largest_file_mb: number | null
    }
    recent_terminal_events: Array<{
      timestamp: string | null
      event_type: string
      task_id: string | null
      task_type: string | null
      task_status: string | null
      project_type: string | null
      download_kind: string | null
      file_size_bytes: number | null
      file_size_mb: number | null
      duration_ms: number | null
      throughput_mbps: number | null
      range_request: boolean
      cf_ray_present: boolean
      error_type: string | null
    }>
  }
  backups: {
    backup_dir_present: boolean
    latest: OpsBackupItem | null
    items: OpsBackupItem[]
  }
}

export interface OpsBackupItem {
  filename: string
  size_bytes: number
  modified_at: string
  sha256_prefix: string | null
  manifest: {
    present: boolean
    created_at: string | null
    revision_short: string | null
    included_storage_roots: string[]
    storage_stats: Record<string, {
      exists: boolean
      files?: number
      dirs?: number
      bytes?: number
    }>
    db_backup: {
      exists?: boolean
      files?: number
      dirs?: number
      bytes?: number
    }
  }
}

export const opsApi = {
  async getStatus(params: { recent_task_limit?: number; download_event_limit?: number } = {}): Promise<OpsStatusPayload> {
    const { data } = await client.get('/admin/ops/status', { params })
    return data.data
  },
}
