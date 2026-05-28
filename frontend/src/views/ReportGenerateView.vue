<template>
  <div>
    <h2>生成报告</h2>

    <!-- Step 1: Upload Excel -->
    <el-card shadow="hover" style="margin-bottom: 20px">
      <template #header><strong>1. 上传 Excel 文件</strong></template>
      <el-upload
        drag
        accept=".xlsx"
        v-loading="excelStore.loading"
        element-loading-text="正在上传并解析 Excel，请稍候..."
        :disabled="excelStore.loading"
        :auto-upload="false"
        :show-file-list="false"
        @change="handleFileChange"
      >
        <el-icon class="el-icon--upload" :size="40"><UploadFilled /></el-icon>
        <div class="el-upload__text">
          <template v-if="excelStore.loading">
            正在解析 Excel，请稍候...
          </template>
          <template v-else>
            拖拽文件到此处，或<em>点击上传</em>
          </template>
        </div>
        <template #tip>
          <div class="el-upload__tip">仅支持 .xlsx 格式的基因检测 Excel 文件</div>
        </template>
      </el-upload>

      <el-alert
        v-if="uploadStatusMessage"
        :title="uploadStatusMessage"
        :type="uploadStatusType"
        show-icon
        :closable="false"
        style="margin-top: 12px"
      />

      <div v-if="excelStore.upload" style="margin-top: 16px">
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="文件名">{{ excelStore.upload.original_filename }}</el-descriptions-item>
          <el-descriptions-item label="大小">{{ (excelStore.upload.file_size_bytes / 1024).toFixed(1) }} KB</el-descriptions-item>
          <el-descriptions-item label="Sheet 数量">{{ excelStore.upload.sheet_names.length }}</el-descriptions-item>
          <el-descriptions-item label="检测项目类型">
            <el-tag v-if="excelStore.upload.detected_project_type" type="success">
              {{ excelStore.upload.detected_project_name || excelStore.upload.detected_project_type }}
            </el-tag>
            <el-tag v-else type="warning">未识别</el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <!-- Validation warnings -->
        <div v-if="excelStore.upload.validation_warnings?.length" style="margin-top: 12px">
          <el-alert
            v-for="(w, i) in excelStore.upload.validation_warnings"
            :key="i"
            :title="w.message"
            :type="w.level === 'error' ? 'error' : w.level === 'warning' ? 'warning' : 'info'"
            show-icon
            :closable="false"
            style="margin-bottom: 4px"
          />
        </div>

        <!-- Sheet tabs preview -->
        <el-tabs
          v-if="excelStore.sheets.length > 0 && excelStore.isPersistentUpload"
          style="margin-top: 12px"
        >
          <el-tab-pane
            v-for="sheet in excelStore.sheets"
            :key="sheet.name"
            :label="`${sheet.name} (${sheet.rows}行)`"
            :name="sheet.name"
            lazy
          >
            <SheetPreview :upload-id="excelStore.upload!.upload_id" :sheet-name="sheet.name" />
          </el-tab-pane>
        </el-tabs>
        <el-alert
          v-else-if="excelStore.sheets.length > 0"
          type="info"
          show-icon
          :closable="false"
          style="margin-top: 12px"
          :title="`已识别 ${excelStore.sheets.length} 个 Sheet。当前使用${generationMode === 'async' ? '后台异步' : '无状态'}生成模式。`"
        />
      </div>
    </el-card>

    <!-- Step 2: Clinical Info Form -->
    <el-card v-if="excelStore.upload" shadow="hover" style="margin-bottom: 20px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <strong>2. 临床信息</strong>
          <div style="display: flex; gap: 12px; align-items: center">
            <el-select
              v-model="projectType"
              placeholder="项目类型"
              style="width: 250px"
              clearable
            >
              <el-option label="结直肠癌301基因+MSI" value="crc_301_msi" />
              <el-option label="结直肠癌358基因+MSI" value="crc_358_msi" />
              <el-option label="MLF基因检测" value="mlf_result" />
              <el-option label="肺癌甲基化" value="lung_methylation" />
            </el-select>
            <el-select
              v-if="templateOptions.length"
              v-model="templateName"
              placeholder="报告模板"
              style="width: 270px"
              clearable
            >
              <el-option
                v-for="option in templateOptions"
                :key="option.value"
                :label="option.label"
                :value="option.value"
              />
            </el-select>
          </div>
        </div>
      </template>
      <DynamicClinicalForm
        :schema="form.schema.value"
        :form-data="form.formData"
        :errors="form.errors.value"
        :loading="form.loading.value"
      />
      <el-alert
        v-if="enrichmentMessage"
        :title="enrichmentMessage"
        :type="excelStore.patientEnrichment?.found ? 'success' : 'warning'"
        show-icon
        :closable="false"
        style="margin-top: 12px"
      />
      <el-alert
        v-for="(warning, i) in excelStore.patientEnrichment?.warnings || []"
        :key="`enrichment-warning-${i}`"
        :title="warning"
        type="warning"
        show-icon
        :closable="false"
        style="margin-top: 8px"
      />
    </el-card>

    <!-- Step 3: Generate -->
    <el-card v-if="excelStore.upload" shadow="hover">
      <template #header><strong>3. 生成报告</strong></template>
      <el-button type="primary" size="large" :loading="generating" @click="handleGenerate">
        生成报告
      </el-button>

      <!-- Result -->
      <div v-if="result" style="margin-top: 16px">
        <el-result
          :icon="result.success ? 'success' : 'error'"
          :title="result.success ? '报告生成成功' : '报告生成失败'"
          :sub-title="result.duration_seconds ? `耗时 ${result.duration_seconds.toFixed(1)} 秒` : ''"
        >
          <template #extra>
            <el-button
              v-if="result.success && result.task_id"
              type="primary"
              @click="downloadGenerated(result)"
            >
              下载报告
            </el-button>
            <el-button
              v-if="result.task_id"
              @click="$router.push(`/tasks/${result.task_id}`)"
            >
              查看质控详情
            </el-button>
          </template>
        </el-result>
        <el-alert
          v-if="result.qa_status"
          :title="`QA 状态：${result.qa_status}`"
          :type="result.qa_status === 'PASS' ? 'success' : result.qa_status === 'FAIL' ? 'error' : 'warning'"
          show-icon
          :closable="false"
          style="margin-bottom: 8px"
        />
        <el-alert
          v-if="result.diff_auto_ran"
          :title="`自动 Diff：${result.diff_status || '-'}，基准：${result.diff_reference_name || result.diff_reference_id || '-'}`"
          :type="result.diff_gate_passed === false ? 'error' : result.diff_status === 'WARN' ? 'warning' : 'success'"
          show-icon
          :closable="false"
          style="margin-bottom: 8px"
        />
        <el-alert
          v-for="(err, i) in result.errors"
          :key="i"
          :title="err"
          type="error"
          show-icon
          :closable="false"
          style="margin-bottom: 4px"
        />
        <el-alert
          v-for="(warn, i) in result.warnings"
          :key="'w' + i"
          :title="warn"
          type="warning"
          show-icon
          :closable="false"
          style="margin-bottom: 4px"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useExcelStore } from '@/stores/excel'
import { useDynamicForm } from '@/composables/useDynamicForm'
import { reportApi, type GenerateResult } from '@/api/report'
import DynamicClinicalForm from '@/components/clinical/DynamicClinicalForm.vue'
import SheetPreview from '@/components/excel/SheetPreview.vue'

const excelStore = useExcelStore()

const projectType = ref<string | null>(null)
const templateName = ref<string | null>(null)
const generating = ref(false)
const result = ref<GenerateResult | null>(null)
const uploadError = ref('')
const selectedFileName = ref('')
const generationMode = import.meta.env.VITE_REPORT_GENERATION_MODE || 'async'

const templateOptions = computed(() => {
  if (projectType.value === 'crc_358_msi') {
    return [
      {
        label: '结直肠癌358+MSI Golden 模板（内测）',
        value: 'crc_358_msi_golden_template_v0',
      },
      {
        label: '结直肠癌358+MSI Legacy 模板',
        value: 'crc_358_msi_standard_v1',
      },
    ]
  }
  return []
})

const enrichmentMessage = computed(() => {
  const enrichment = excelStore.patientEnrichment
  const sampleId = excelStore.singleValues?.sample_id
  if (!sampleId) return ''
  if (enrichment?.found) {
    const source = enrichment.source || '患者信息源'
    const keys = Object.keys(enrichment.fields || {})
    return `已根据样本号 ${sampleId} 从 ${source} 补全 ${keys.length} 个临床字段`
  }
  if (excelStore.upload && !form.formData.patient_name) {
    return `Excel 未提供患者姓名，且未在患者信息库/运营系统中查到样本号 ${sampleId}。请手动填写或接入运营系统。`
  }
  return ''
})

const uploadStatusMessage = computed(() => {
  if (excelStore.loading && selectedFileName.value) {
    return `正在解析 ${selectedFileName.value}，请不要重复点击上传`
  }
  if (uploadError.value) {
    return uploadError.value
  }
  if (excelStore.upload?.original_filename) {
    return `已完成上传解析：${excelStore.upload.original_filename}`
  }
  return ''
})

const uploadStatusType = computed(() => {
  if (uploadError.value) return 'error'
  if (excelStore.upload) return 'success'
  return 'info'
})

// Initialize projectType from detection
watch(
  () => excelStore.upload?.detected_project_type,
  (type) => {
    if (type) projectType.value = type
  },
)

watch(
  templateOptions,
  (options) => {
    if (!options.length) {
      templateName.value = null
      return
    }
    const current = templateName.value
    if (!current || !options.some((option) => option.value === current)) {
      templateName.value = options[0].value
    }
  },
  { immediate: true },
)

// Dynamic form driven by project type
const form = useDynamicForm(projectType)

// Auto-merge Excel values when upload completes
watch(
  () => excelStore.singleValues,
  (vals) => {
    if (vals && Object.keys(vals).length > 0) {
      form.mergeExcelValues(vals)
    }
  },
)

watch(
  () => excelStore.patientEnrichment,
  (enrichment) => {
    if (enrichment?.found) {
      form.mergePatientInfo(enrichment.fields)
    }
  },
)

async function handleFileChange(uploadFile: any) {
  const file = uploadFile.raw || uploadFile
  if (!file) return
  result.value = null
  uploadError.value = ''
  selectedFileName.value = file.name || ''
  try {
    await excelStore.uploadFile(file)
    ElMessage.success('Excel 上传成功')
  } catch (err: any) {
    uploadError.value = err.response?.data?.detail || err.message || 'Excel 上传失败'
    ElMessage.error(uploadError.value)
  }
}

async function handleGenerate() {
  if (!excelStore.upload) return
  if (!form.validate()) {
    ElMessage.warning('请填写必填字段')
    return
  }

  generating.value = true
  result.value = null
  try {
    const payload = {
      clinical_info: form.getCleanValues(),
      project_type: projectType.value,
      project_name: excelStore.upload.detected_project_name,
      template_name: templateName.value,
    }
    if (excelStore.sourceFile && generationMode === 'async') {
      const accepted = await reportApi.generateFromFileAsync(excelStore.sourceFile, payload)
      ElMessage.info('报告已进入后台生成，请稍候')
      result.value = await waitForReportTask(accepted.task_id)
    } else {
      result.value = excelStore.sourceFile
        ? await reportApi.generateFromFile(excelStore.sourceFile, payload)
        : await reportApi.generate({
            upload_id: excelStore.upload.upload_id,
            ...payload,
          })
    }
    if (result.value.success) {
      ElMessage.success('报告生成成功')
    } else {
      ElMessage.error('报告生成失败')
    }
  } catch (err: any) {
    ElMessage.error(err.response?.data?.error || err.response?.data?.detail || err.message || '报告生成异常')
  } finally {
    generating.value = false
  }
}

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function taskStatusToResult(task: Awaited<ReturnType<typeof reportApi.getTaskStatus>>): GenerateResult {
  return {
    task_id: task.id,
    success: task.status === 'completed',
    output_file: task.output_path,
    field_provenance_file: task.field_provenance_file,
    qa_report_file: task.qa_report_file,
    qa_status: task.qa_status,
    generation_id: task.generation_id,
    stage_results: task.stage_results,
    stage_results_file: task.stage_results_file,
    diff_status: task.diff_status,
    diff_gate_passed: task.diff_gate_passed,
    diff_reference_id: task.diff_reference_id,
    diff_reference_name: task.diff_reference_name,
    diff_auto_ran: Boolean(task.diff_status),
    duration_seconds: task.duration_seconds,
    errors: task.errors,
    warnings: task.warnings,
  }
}

async function waitForReportTask(taskId: string): Promise<GenerateResult> {
  for (let i = 0; i < 180; i += 1) {
    const task = await reportApi.getTaskStatus(taskId)
    if (task.status === 'completed' || task.status === 'failed') {
      return taskStatusToResult(task)
    }
    await sleep(2000)
  }
  throw new Error('报告生成超时，请稍后到任务详情页查看')
}

async function downloadReport(taskId: string) {
  try {
    const task = await reportApi.getTaskStatus(taskId)
    if (task.status !== 'completed') {
      ElMessage.warning('报告仍在生成中，请稍后再下载')
      return
    }
    if (!task.output_path) {
      ElMessage.error('报告文件不存在，请重新生成后下载')
      return
    }
    const link = document.createElement('a')
    link.href = reportApi.getDownloadUrl(taskId)
    link.target = '_blank'
    link.rel = 'noopener'
    document.body.appendChild(link)
    link.click()
    link.remove()
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || err.message || '报告下载失败')
  }
}

async function downloadGenerated(generated: GenerateResult) {
  // 优先走 /download 流式接口（快、不占内存、不经 base64 膨胀）；
  // 只有缺 task_id 时才 fallback 到 base64 内联。
  try {
    if (generated.task_id) {
      await downloadReport(generated.task_id)
      return
    }
    if (generated.output_file_base64) {
      reportApi.downloadInline(generated)
      return
    }
    throw new Error('报告没有可下载的内容')
  } catch (err: any) {
    ElMessage.error(err.message || '下载失败')
  }
}
</script>
