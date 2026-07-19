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
    instance_lock: {
      enabled: boolean
      lock_file: string
      acquired: boolean
      pid: number | null
    }
    libreoffice_listener: {
      checked: boolean
      running: boolean | null
    }
    renderer_fingerprint: {
      available: boolean
      error?: string
      platform?: string
      machine?: string
      engine?: string
      engine_version?: string
      profile_mode?: string
      pdf_renderer?: string
      pdf_renderer_version?: string
      font_substitution_profile?: string
      font_substitution_profile_sha256?: string
      zh_font_match?: string
      zh_font_match_sha256?: string
    }
    alert_delivery: {
      configured: boolean
      source: string | null
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
    restore_drill: {
      available: boolean
      status: string
      modified_at: string | null
      age_hours?: number
      full_extract?: boolean
      sqlite_integrity?: string
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
      failed_recent_24h: number
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

export interface LoadTestGateCheck {
  id: string
  label: string
  status: 'pass' | 'warning' | 'block' | string
  value: string
  threshold: string
}

export interface LoadTestSummaryPayload {
  schema_version: string
  generated_at: string
  window_hours: number
  since: string
  gate: {
    status: 'pass' | 'warning' | 'block' | string
    title: string
    checks: LoadTestGateCheck[]
  }
  totals: {
    tasks_total: number
    single_tasks: number
    batch_tasks: number
    units_total: number
    units_completed: number
    units_failed: number
    units_cancelled: number
    units_pending: number
    units_running: number
    completion_rate: number | null
    success_rate: number | null
    task_status_counts: Record<string, number>
  }
  qa: {
    pass: number
    warn: number
    fail: number
    missing: number
  }
  durations: {
    avg_task_seconds: number | null
    p95_task_seconds: number | null
    avg_file_seconds: number | null
    p95_file_seconds: number | null
  }
  downloads: OpsStatusPayload['downloads']
  failure_reasons: Array<{
    severity: string
    reason: string
    count: number
  }>
  project_breakdown: Array<{
    project_type: string
    tasks: number
    units_total: number
    units_completed: number
    units_failed: number
    qa_warn: number
    qa_fail: number
    success_rate: number | null
    avg_task_seconds: number | null
  }>
  recent_batches: Array<{
    task_id: string
    status: string
    project_type: string | null
    created_at: string | null
    completed_at: string | null
    duration_seconds: number | null
    total_files: number
    completed_files: number
    failed_files: number
    cancelled_files: number
    pending_files: number
    running_files: number
  }>
}

export const opsApi = {
  async getStatus(params: { recent_task_limit?: number; download_event_limit?: number } = {}): Promise<OpsStatusPayload> {
    const { data } = await client.get('/admin/ops/status', { params })
    return data.data
  },

  async getLoadTestSummary(params: { window_hours?: number; recent_batch_limit?: number } = {}): Promise<LoadTestSummaryPayload> {
    const { data } = await client.get('/admin/ops/load-test-summary', { params })
    return data.data
  },
}
