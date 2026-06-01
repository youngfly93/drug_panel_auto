import client from './client'

export interface OpsStatusBlock {
  status: string
  last_at: string | null
}

export interface OpsStatusPayload {
  schema_version: string
  generated_at: string
  alerts: OpsAlert[]
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
    generation_queue: {
      max_workers: number
      queued: number
      active: number
      submitted_total: number
      finished_total: number
    }
    generation_limits: {
      process_isolation: boolean
      timeout_seconds: number
    }
    task_recovery: {
      ran: boolean
      checked_at: string | null
      scanned: number
      requeued: number
      failed: number
      skipped: number
      errors: Array<{
        task_id?: string
        error_type?: string
        message?: string
      }>
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
  retention: {
    backup_keep_days: number
    release_keep_count: number
    preview_keep_days: number
    log_keep_days: number
    upload_keep_days: number
    report_keep_days: number
    zip_keep_days: number
    audit_log_keep_days: number
  }
  backups: {
    backup_dir_present: boolean
    latest: OpsBackupItem | null
    items: OpsBackupItem[]
  }
}

export interface OpsAlert {
  id: string
  severity: 'success' | 'warning' | 'danger' | 'info' | string
  label: string
  title: string
  message: string
  threshold?: string | null
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
