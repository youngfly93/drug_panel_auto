<template>
  <div class="ops-page">
    <div class="ops-head">
      <div>
        <h2>生产状态</h2>
        <div class="ops-subline">
          <span>Release {{ status?.deployment.release || '-' }}</span>
          <span>更新 {{ formatDate(status?.generated_at) }}</span>
        </div>
      </div>
      <div class="ops-actions">
        <el-switch v-model="autoRefresh" active-text="自动刷新" />
        <el-button :icon="Refresh" :loading="loading" @click="fetchStatus">刷新</el-button>
      </div>
    </div>

    <el-alert
      v-if="error"
      class="ops-alert"
      type="error"
      :closable="false"
      :title="error"
      show-icon
    />

    <el-row :gutter="12" class="signal-grid" v-loading="loading && !status">
      <el-col v-for="signal in topSignals" :key="signal.label" :xs="24" :sm="12" :lg="8" :xl="4">
        <div :class="['signal-tile', `signal-${signal.tone}`]">
          <div class="signal-icon">
            <el-icon><component :is="signal.icon" /></el-icon>
          </div>
          <div class="signal-body">
            <span class="signal-label">{{ signal.label }}</span>
            <strong>{{ signal.value }}</strong>
            <small>{{ signal.meta }}</small>
          </div>
        </div>
      </el-col>
    </el-row>

    <section v-if="healthAlerts.length" class="ops-section alert-section">
      <div class="section-head">
        <div>
          <h3>当前告警</h3>
          <span>按后端阈值实时计算，优先处理红色项</span>
        </div>
      </div>
      <div class="alert-grid">
        <div
          v-for="alert in healthAlerts"
          :key="alert.id"
          :class="['alert-item', `alert-${alertTone(alert.severity)}`]"
        >
          <el-tag size="small" :type="alertTagType(alert.severity)">
            {{ alert.label }}
          </el-tag>
          <div>
            <strong>{{ alert.title }}</strong>
            <span>{{ alert.message }}</span>
            <small v-if="alert.threshold">阈值 {{ alert.threshold }}</small>
          </div>
        </div>
      </div>
    </section>

    <el-row :gutter="16">
      <el-col :xs="24" :xl="12">
        <section class="ops-section">
          <div class="section-head">
            <div>
              <h3>运行状态</h3>
              <span>Web、隧道、LibreOffice 与维护任务</span>
            </div>
          </div>
          <div class="status-list">
            <div v-for="item in runtimeRows" :key="item.label" class="status-row">
              <div>
                <strong>{{ item.label }}</strong>
                <span>{{ item.meta }}</span>
              </div>
              <el-tag :type="statusTagType(item.status)" size="small">{{ statusText(item.status) }}</el-tag>
            </div>
          </div>
        </section>
      </el-col>

      <el-col :xs="24" :xl="12">
        <section class="ops-section">
          <div class="section-head">
            <div>
              <h3>任务生产</h3>
              <span>当前队列与最近任务</span>
            </div>
          </div>
          <div class="metric-grid">
            <div v-for="metric in taskMetrics" :key="metric.label" class="metric-cell">
              <span>{{ metric.label }}</span>
              <strong>{{ metric.value }}</strong>
            </div>
          </div>
          <div class="status-bars">
            <div v-for="bar in taskBars" :key="bar.label" class="status-bar">
              <div>
                <span>{{ bar.label }}</span>
                <em>{{ bar.value }}</em>
              </div>
              <el-progress :percentage="bar.percent" :color="bar.color" :show-text="false" />
            </div>
          </div>
        </section>
      </el-col>
    </el-row>

    <el-row :gutter="16">
      <el-col :xs="24" :xl="12">
        <section class="ops-section">
          <div class="section-head">
            <div>
              <h3>下载质量</h3>
              <span>最近终态下载事件</span>
            </div>
          </div>
          <div class="metric-grid compact">
            <div v-for="metric in downloadMetrics" :key="metric.label" class="metric-cell">
              <span>{{ metric.label }}</span>
              <strong>{{ metric.value }}</strong>
            </div>
          </div>
          <el-table :data="status?.downloads.recent_terminal_events || []" size="small" stripe>
            <el-table-column label="任务" width="118">
              <template #default="{ row }">
                <el-button v-if="row.task_id" text type="primary" size="small" @click="openTask(row.task_id)">
                  {{ shortId(row.task_id) }}
                </el-button>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column label="状态" width="86">
              <template #default="{ row }">
                <el-tag :type="downloadTagType(row.event_type)" size="small">
                  {{ downloadEventText(row.event_type) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="文件" width="86">
              <template #default="{ row }">{{ formatMb(row.file_size_mb) }}</template>
            </el-table-column>
            <el-table-column label="耗时" width="86">
              <template #default="{ row }">{{ formatMs(row.duration_ms) }}</template>
            </el-table-column>
            <el-table-column label="速率" width="86">
              <template #default="{ row }">{{ formatSpeed(row.throughput_mbps) }}</template>
            </el-table-column>
            <el-table-column label="时间" min-width="150">
              <template #default="{ row }">{{ formatDate(row.timestamp) }}</template>
            </el-table-column>
          </el-table>
        </section>
      </el-col>

      <el-col :xs="24" :xl="12">
        <section class="ops-section">
          <div class="section-head">
            <div>
              <h3>备份与空间</h3>
              <span>备份、磁盘与存储桶水位</span>
            </div>
          </div>
          <div class="backup-main">
            <div>
              <span>最近备份</span>
              <strong>{{ status?.backups.latest?.filename || '-' }}</strong>
              <small>{{ formatBytes(status?.backups.latest?.size_bytes) }}</small>
            </div>
            <el-tag :type="backupTone === 'danger' ? 'danger' : backupTone === 'warning' ? 'warning' : 'success'">
              {{ backupLabel }}
            </el-tag>
          </div>
          <div class="maintenance-grid">
            <div>
              <span>备份完成</span>
              <strong>{{ formatDate(status?.runtime.maintenance.last_backup_at) }}</strong>
            </div>
            <div>
              <span>校验完成</span>
              <strong>{{ formatDate(status?.runtime.maintenance.last_verify_at) }}</strong>
            </div>
            <div>
              <span>清理完成</span>
              <strong>{{ formatDate(status?.runtime.maintenance.last_cleanup_at) }}</strong>
            </div>
          </div>
          <div class="retention-grid">
            <div v-for="item in retentionRows" :key="item.label">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
          <el-table :data="storageRows" size="small" stripe>
            <el-table-column prop="label" label="存储区" />
            <el-table-column prop="entries" label="一级条目" width="100" align="right" />
            <el-table-column label="状态" width="86">
              <template #default="{ row }">
                <el-tag :type="row.exists ? 'success' : 'info'" size="small">
                  {{ row.exists ? '存在' : '未创建' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </section>
      </el-col>
    </el-row>

    <section class="ops-section">
      <div class="section-head">
        <div>
          <h3>最近任务</h3>
          <span>不含文件名、报告路径和错误正文</span>
        </div>
        <el-button text type="primary" @click="$router.push('/tasks')">任务队列</el-button>
      </div>
      <el-table :data="status?.tasks.recent || []" size="small" stripe>
        <el-table-column label="任务ID" width="132">
          <template #default="{ row }">
            <el-button text type="primary" size="small" @click="openTask(row.id)">
              {{ shortId(row.id) }}
            </el-button>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="82">
          <template #default="{ row }">
            <el-tag :type="row.task_type === 'batch' ? 'warning' : 'primary'" size="small">
              {{ row.task_type === 'batch' ? '批量' : '单份' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="98">
          <template #default="{ row }">
            <el-tag :type="taskStatusTagType(row.status)" size="small">{{ taskStatusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="project_type" label="项目" min-width="140" show-overflow-tooltip />
        <el-table-column label="进度" width="110">
          <template #default="{ row }">{{ row.completed_files }}/{{ row.total_files }}</template>
        </el-table-column>
        <el-table-column label="失败" width="80">
          <template #default="{ row }">{{ row.failed_files }}</template>
        </el-table-column>
        <el-table-column label="耗时" width="96">
          <template #default="{ row }">{{ formatSeconds(row.duration_seconds) }}</template>
        </el-table-column>
        <el-table-column label="创建时间" min-width="160">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import type { Component } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  CircleCheckFilled,
  Cpu,
  DataLine,
  Download,
  Files,
  FolderChecked,
  Odometer,
  Refresh,
  Timer,
  TrendCharts,
  WarningFilled,
} from '@element-plus/icons-vue'
import { opsApi, type OpsAlert, type OpsStatusPayload } from '@/api/ops'

type Tone = 'success' | 'warning' | 'danger' | 'info'

const router = useRouter()
const status = ref<OpsStatusPayload | null>(null)
const loading = ref(false)
const error = ref('')
const autoRefresh = ref(false)
let refreshTimer: number | undefined

const taskCounts = computed(() => status.value?.tasks.counts.by_status || {})
const downloadSummary = computed(() => status.value?.downloads.summary)
const diskUsed = computed(() => status.value?.storage.disk.used_percent ?? null)
const healthAlerts = computed<OpsAlert[]>(() => status.value?.alerts || [])

const backupAgeHours = computed(() => {
  const lastBackup = parseDate(status.value?.runtime.maintenance.last_backup_at)
  if (!lastBackup) return null
  return (Date.now() - lastBackup.getTime()) / 1000 / 3600
})

const backupTone = computed<Tone>(() => {
  if (!status.value?.backups.latest) return 'danger'
  if (backupAgeHours.value == null) return 'warning'
  if (backupAgeHours.value > 48) return 'danger'
  if (backupAgeHours.value > 30) return 'warning'
  return 'success'
})

const backupLabel = computed(() => {
  if (!status.value?.backups.latest) return '无备份'
  if (backupTone.value === 'danger') return '过期'
  if (backupTone.value === 'warning') return '关注'
  return '正常'
})

const overall = computed<{ tone: Tone; label: string }>(() => {
  if (!status.value) return { tone: 'info', label: '未加载' }
  const watchdog = status.value.runtime.watchdog
  if (watchdog.web.status === 'fail' || watchdog.tunnel.status === 'fail') {
    return { tone: 'danger', label: '服务异常' }
  }
  if ((diskUsed.value ?? 0) >= 90 || backupTone.value === 'danger') {
    return { tone: 'danger', label: '需要处理' }
  }
  if (
    watchdog.web.status !== 'ok'
    || watchdog.tunnel.status !== 'ok'
    || watchdog.libreoffice.status !== 'ok'
    || backupTone.value === 'warning'
    || (diskUsed.value ?? 0) >= 80
    || (downloadSummary.value?.slow || 0) > 0
    || (downloadSummary.value?.failed || 0) > 0
  ) {
    return { tone: 'warning', label: '需要关注' }
  }
  return { tone: 'success', label: '运行正常' }
})

const topSignals = computed<Array<{ label: string; value: string; meta: string; tone: Tone; icon: Component }>>(() => [
  {
    label: '总体',
    value: overall.value.label,
    meta: `Web ${statusText(status.value?.runtime.watchdog.web.status)} · 隧道 ${statusText(status.value?.runtime.watchdog.tunnel.status)}`,
    tone: overall.value.tone,
    icon: overall.value.tone === 'success' ? CircleCheckFilled : WarningFilled,
  },
  {
    label: '版本',
    value: status.value?.deployment.release || '-',
    meta: status.value?.deployment.revision_short ? `Commit ${status.value.deployment.revision_short}` : 'Commit -',
    tone: 'info',
    icon: Odometer,
  },
  {
    label: '任务',
    value: `${status.value?.tasks.counts.total ?? 0}`,
    meta: `执行槽 ${queueStats.value.active}/${queueStats.value.max_workers} · 排队 ${queueStats.value.queued}`,
    tone: (queueStats.value.queued || 0) > 0 ? 'warning' : (status.value?.tasks.counts.failed_total || 0) > 0 ? 'warning' : 'success',
    icon: DataLine,
  },
  {
    label: '下载',
    value: `${downloadSummary.value?.completed ?? 0}`,
    meta: `慢 ${downloadSummary.value?.slow ?? 0} · 失败 ${downloadSummary.value?.failed ?? 0} · 最大 ${formatMs(downloadSummary.value?.max_duration_ms)}`,
    tone: (downloadSummary.value?.failed || 0) > 0 ? 'danger' : (downloadSummary.value?.slow || 0) > 0 ? 'warning' : 'success',
    icon: Download,
  },
  {
    label: '磁盘',
    value: diskUsed.value == null ? '-' : `${diskUsed.value.toFixed(1)}%`,
    meta: `可用 ${formatBytes(status.value?.storage.disk.free_bytes)}`,
    tone: (diskUsed.value ?? 0) >= 90 ? 'danger' : (diskUsed.value ?? 0) >= 80 ? 'warning' : 'success',
    icon: Files,
  },
  {
    label: '备份',
    value: backupLabel.value,
    meta: status.value?.runtime.maintenance.last_backup_at || '-',
    tone: backupTone.value,
    icon: FolderChecked,
  },
])

const runtimeRows = computed(() => {
  const runtime = status.value?.runtime
  return [
    {
      label: '生成队列',
      status: queueStats.value.queued > 0 ? 'warn' : 'ok',
      meta: `运行 ${queueStats.value.active}/${queueStats.value.max_workers}，排队 ${queueStats.value.queued}，超时 ${formatSeconds(generationLimits.value.timeout_seconds)}`,
    },
    {
      label: '任务恢复',
      status: recoveryStats.value.errors.length || recoveryStats.value.failed ? 'warn' : recoveryStats.value.ran ? 'ok' : 'unknown',
      meta: recoveryStats.value.ran
        ? `扫描 ${recoveryStats.value.scanned}，恢复 ${recoveryStats.value.requeued}，失败 ${recoveryStats.value.failed}`
        : '启动后尚未执行',
    },
    {
      label: 'Web 服务',
      status: runtime?.watchdog.web.status || 'unknown',
      meta: `最近 ${formatDate(runtime?.watchdog.web.last_at)}`,
    },
    {
      label: '公网隧道',
      status: runtime?.watchdog.tunnel.status || 'unknown',
      meta: `最近 ${formatDate(runtime?.watchdog.tunnel.last_at)}`,
    },
    {
      label: 'LibreOffice',
      status: runtime?.libreoffice_listener.running ? 'ok' : runtime?.watchdog.libreoffice.status || 'unknown',
      meta: runtime?.libreoffice_listener.checked ? `listener ${runtime.libreoffice_listener.running ? 'running' : 'missing'}` : '未检测',
    },
    {
      label: '磁盘巡检',
      status: runtime?.watchdog.disk.status || 'unknown',
      meta: `最近告警 ${formatDate(runtime?.watchdog.disk.last_at)}`,
    },
    {
      label: '维护脚本',
      status: runtime?.maintenance.last_backup_at && runtime?.maintenance.last_verify_at ? 'ok' : 'warn',
      meta: `最近事件 ${formatDate(runtime?.maintenance.last_event_at)}`,
    },
  ]
})

const taskMetrics = computed(() => [
  { label: '总任务', value: status.value?.tasks.counts.total ?? 0 },
  { label: '执行中', value: queueStats.value.active },
  { label: '队列中', value: queueStats.value.queued },
  { label: '失败', value: status.value?.tasks.counts.failed_total ?? 0 },
])

const queueStats = computed(() => status.value?.runtime.generation_queue || {
  max_workers: 0,
  queued: 0,
  active: 0,
  submitted_total: 0,
  finished_total: 0,
})

const recoveryStats = computed(() => status.value?.runtime.task_recovery || {
  ran: false,
  checked_at: null,
  scanned: 0,
  requeued: 0,
  failed: 0,
  skipped: 0,
  errors: [],
})

const generationLimits = computed(() => status.value?.runtime.generation_limits || {
  process_isolation: false,
  timeout_seconds: 0,
})

const taskBars = computed(() => {
  const total = Math.max(status.value?.tasks.counts.total || 0, 1)
  return [
    { label: '已完成', value: taskCounts.value.completed || 0, color: '#2f8f68' },
    { label: '运行中', value: taskCounts.value.running || 0, color: '#d9862a' },
    { label: '待执行', value: taskCounts.value.pending || 0, color: '#6b7280' },
    { label: '失败/部分失败', value: status.value?.tasks.counts.failed_total || 0, color: '#cf4b48' },
  ].map((item) => ({
    ...item,
    percent: Math.round((item.value / total) * 100),
  }))
})

const downloadMetrics = computed(() => [
  { label: '完成', value: downloadSummary.value?.completed ?? 0 },
  { label: '慢下载', value: downloadSummary.value?.slow ?? 0 },
  { label: '失败', value: downloadSummary.value?.failed ?? 0 },
  { label: '平均耗时', value: formatMs(downloadSummary.value?.avg_duration_ms) },
  { label: '最大耗时', value: formatMs(downloadSummary.value?.max_duration_ms) },
  { label: '最大文件', value: formatMb(downloadSummary.value?.largest_file_mb) },
])

const retentionRows = computed(() => [
  { label: '上传 Excel', value: formatDays(status.value?.retention.upload_keep_days) },
  { label: '报告产物', value: formatDays(status.value?.retention.report_keep_days) },
  { label: 'ZIP 包', value: formatDays(status.value?.retention.zip_keep_days) },
  { label: '审计日志', value: formatDays(status.value?.retention.audit_log_keep_days) },
  { label: '预览图', value: formatDays(status.value?.retention.preview_keep_days) },
  { label: '运行日志', value: formatDays(status.value?.retention.log_keep_days) },
])

const storageRows = computed(() => {
  const labels: Record<string, string> = {
    uploads: '上传 Excel',
    reports: '生成报告',
    previews: '预览图',
    signatures: '签名图',
    reference_reports: '基准报告',
  }
  return Object.entries(status.value?.storage.buckets || {}).map(([key, bucket]) => ({
    label: labels[key] || key,
    exists: bucket.exists,
    entries: bucket.top_level_entries ?? '-',
  }))
})

async function fetchStatus() {
  loading.value = true
  error.value = ''
  try {
    status.value = await opsApi.getStatus({ recent_task_limit: 8, download_event_limit: 12 })
  } catch (err: any) {
    error.value = err.response?.data?.detail || err.response?.data?.error || '生产状态读取失败'
    ElMessage.error(error.value)
  } finally {
    loading.value = false
  }
}

function openTask(taskId: string) {
  router.push(`/tasks/${taskId}`)
}

function statusText(value?: string | null) {
  const map: Record<string, string> = {
    ok: '正常',
    warn: '关注',
    fail: '异常',
    missing: '缺失',
    unknown: '未知',
  }
  return map[value || 'unknown'] || value || '未知'
}

function statusTagType(value?: string | null) {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
    ok: 'success',
    warn: 'warning',
    fail: 'danger',
    missing: 'warning',
    unknown: 'info',
  }
  return map[value || 'unknown'] || 'info'
}

function alertTone(value?: string | null): Tone {
  if (value === 'danger') return 'danger'
  if (value === 'warning') return 'warning'
  if (value === 'success') return 'success'
  return 'info'
}

function alertTagType(value?: string | null) {
  return alertTone(value)
}

function taskStatusText(value: string) {
  const map: Record<string, string> = {
    completed: '已完成',
    partial_failed: '部分失败',
    failed: '失败',
    queued: '已排队',
    preflight: '预检中',
    generating: '生成中',
    qa: '质控中',
    running: '运行中',
    pending: '待执行',
    cancelled: '已取消',
  }
  return map[value] || value
}

function taskStatusTagType(value: string) {
  const map: Record<string, 'success' | 'warning' | 'danger' | 'info'> = {
    completed: 'success',
    partial_failed: 'danger',
    failed: 'danger',
    queued: 'info',
    preflight: 'warning',
    generating: 'warning',
    qa: 'warning',
    running: 'warning',
    pending: 'info',
    cancelled: 'info',
  }
  return map[value] || 'info'
}

function downloadEventText(value: string) {
  const map: Record<string, string> = {
    report_download_completed: '完成',
    report_download_slow: '慢',
    report_download_failed: '失败',
  }
  return map[value] || value
}

function downloadTagType(value: string) {
  if (value === 'report_download_failed') return 'danger'
  if (value === 'report_download_slow') return 'warning'
  return 'success'
}

function shortId(value: string | null | undefined) {
  if (!value) return '-'
  return value.length > 12 ? `${value.slice(0, 8)}...${value.slice(-4)}` : value
}

function parseDate(value: string | null | undefined): Date | null {
  if (!value) return null
  const normalized = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(value)
    ? value.replace(' ', 'T')
    : value
  const date = new Date(normalized)
  return Number.isNaN(date.getTime()) ? null : date
}

function formatDate(value: string | null | undefined) {
  const date = parseDate(value)
  if (!date) return '-'
  return date.toLocaleString('zh-CN', { hour12: false })
}

function formatBytes(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '-'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let size = value
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit += 1
  }
  return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`
}

function formatMs(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '-'
  if (value < 1000) return `${value.toFixed(0)} ms`
  return `${(value / 1000).toFixed(1)} s`
}

function formatSeconds(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '-'
  if (value < 60) return `${value.toFixed(1)} s`
  return `${Math.floor(value / 60)}m ${Math.round(value % 60)}s`
}

function formatMb(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '-'
  return `${value.toFixed(1)} MB`
}

function formatSpeed(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '-'
  return `${value.toFixed(1)} Mbps`
}

function formatDays(value: number | null | undefined) {
  if (value == null || Number.isNaN(value)) return '-'
  if (value <= 0) return '不清理'
  return `${value} 天`
}

watch(autoRefresh, (enabled) => {
  if (refreshTimer) {
    window.clearInterval(refreshTimer)
    refreshTimer = undefined
  }
  if (enabled) {
    refreshTimer = window.setInterval(fetchStatus, 30000)
  }
})

onMounted(fetchStatus)
onUnmounted(() => {
  if (refreshTimer) window.clearInterval(refreshTimer)
})
</script>

<style scoped>
.ops-page {
  color: #222831;
}

.ops-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.ops-head h2 {
  margin: 0 0 6px;
  font-size: 24px;
  font-weight: 700;
}

.ops-subline {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: #667085;
  font-size: 13px;
}

.ops-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ops-alert {
  margin-bottom: 14px;
}

.signal-grid {
  margin-bottom: 16px;
}

.signal-tile {
  min-height: 112px;
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px;
  margin-bottom: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
}

.signal-icon {
  width: 42px;
  height: 42px;
  display: grid;
  place-items: center;
  flex: 0 0 auto;
  border-radius: 8px;
  font-size: 23px;
}

.signal-body {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.signal-label {
  color: #667085;
  font-size: 12px;
}

.signal-body strong {
  overflow: hidden;
  color: #111827;
  font-size: 22px;
  line-height: 1.1;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.signal-body small {
  overflow: hidden;
  color: #667085;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.signal-success {
  border-color: #d5e7dd;
}

.signal-success .signal-icon {
  background: #edf7f1;
  color: #2f8f68;
}

.signal-warning {
  border-color: #efd9b9;
}

.signal-warning .signal-icon {
  background: #fff6e8;
  color: #b86d1c;
}

.signal-danger {
  border-color: #edc7c5;
}

.signal-danger .signal-icon {
  background: #fff0ef;
  color: #c2413d;
}

.signal-info .signal-icon {
  background: #edf4fb;
  color: #2f6f9f;
}

.ops-section {
  margin-bottom: 16px;
  padding: 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
}

.alert-section {
  border-color: #d7dde6;
}

.alert-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.alert-item {
  min-height: 82px;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fafbfc;
}

.alert-item div {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.alert-item strong {
  font-size: 14px;
}

.alert-item span,
.alert-item small {
  color: #667085;
  font-size: 12px;
  line-height: 1.45;
}

.alert-danger {
  border-color: #efc4c1;
  background: #fff5f4;
}

.alert-warning {
  border-color: #f1d4a8;
  background: #fff8ed;
}

.alert-info {
  border-color: #cfddea;
  background: #f5f9fd;
}

.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.section-head h3 {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 700;
}

.section-head span {
  color: #667085;
  font-size: 12px;
}

.status-list {
  display: grid;
  gap: 10px;
}

.status-row {
  min-height: 54px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid #edf0f3;
  border-radius: 8px;
  background: #fafbfc;
}

.status-row div {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.status-row strong {
  font-size: 14px;
}

.status-row span {
  overflow: hidden;
  color: #667085;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.metric-grid.compact {
  grid-template-columns: repeat(6, minmax(0, 1fr));
}

.metric-cell {
  min-height: 70px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  padding: 10px 12px;
  border: 1px solid #edf0f3;
  border-radius: 8px;
  background: #fafbfc;
}

.metric-cell span {
  color: #667085;
  font-size: 12px;
}

.metric-cell strong {
  margin-top: 6px;
  font-size: 22px;
  line-height: 1;
}

.status-bars {
  display: grid;
  gap: 10px;
}

.status-bar div {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
  color: #667085;
  font-size: 12px;
}

.status-bar em {
  color: #111827;
  font-style: normal;
}

.backup-main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  padding: 12px;
  border: 1px solid #edf0f3;
  border-radius: 8px;
  background: #fafbfc;
}

.backup-main div {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.backup-main span,
.backup-main small {
  color: #667085;
  font-size: 12px;
}

.backup-main strong {
  overflow: hidden;
  font-size: 15px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.maintenance-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.maintenance-grid div,
.retention-grid div {
  min-height: 62px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 6px;
  padding: 10px;
  border: 1px solid #edf0f3;
  border-radius: 8px;
}

.retention-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.maintenance-grid span,
.retention-grid span {
  color: #667085;
  font-size: 12px;
}

.maintenance-grid strong,
.retention-grid strong {
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 1100px) {
  .alert-grid,
  .metric-grid,
  .metric-grid.compact {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .ops-head {
    flex-direction: column;
  }

  .ops-actions {
    width: 100%;
    justify-content: space-between;
  }

  .maintenance-grid,
  .retention-grid {
    grid-template-columns: 1fr;
  }

  .alert-grid {
    grid-template-columns: 1fr;
  }
}
</style>
