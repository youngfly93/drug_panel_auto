<template>
  <div>
    <h2>生成报告</h2>

    <!-- Step 1: Upload Excel -->
    <el-card shadow="hover" style="margin-bottom: 20px">
      <template #header><strong>1. 上传 Excel 文件</strong></template>
      <el-upload
        drag
        accept=".xlsx"
        :auto-upload="false"
        :show-file-list="false"
        @change="handleFileChange"
      >
        <el-icon class="el-icon--upload" :size="40"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖拽文件到此处，或<em>点击上传</em></div>
        <template #tip>
          <div class="el-upload__tip">仅支持 .xlsx 格式的基因检测 Excel 文件</div>
        </template>
      </el-upload>

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

        <!-- Sheet tabs preview -->
        <el-tabs v-if="excelStore.sheets.length > 0" style="margin-top: 12px">
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
      </div>
    </el-card>

    <!-- Step 2: Clinical Info Form -->
    <el-card v-if="excelStore.upload" shadow="hover" style="margin-bottom: 20px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <strong>2. 临床信息</strong>
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
        </div>
      </template>
      <DynamicClinicalForm
        :schema="form.schema.value"
        :form-data="form.formData"
        :errors="form.errors.value"
        :loading="form.loading.value"
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
              @click="downloadReport(result.task_id)"
            >
              下载报告
            </el-button>
          </template>
        </el-result>
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
const generating = ref(false)
const result = ref<GenerateResult | null>(null)

// Initialize projectType from detection
watch(
  () => excelStore.upload?.detected_project_type,
  (type) => {
    if (type) projectType.value = type
  },
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

async function handleFileChange(uploadFile: any) {
  const file = uploadFile.raw || uploadFile
  if (!file) return
  result.value = null
  try {
    await excelStore.uploadFile(file)
    ElMessage.success('Excel 上传成功')
  } catch (err: any) {
    ElMessage.error(err.response?.data?.detail || 'Excel 上传失败')
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
    result.value = await reportApi.generate({
      upload_id: excelStore.upload.upload_id,
      clinical_info: form.getCleanValues(),
      project_type: projectType.value,
    })
    if (result.value.success) {
      ElMessage.success('报告生成成功')
    } else {
      ElMessage.error('报告生成失败')
    }
  } catch (err: any) {
    ElMessage.error(err.response?.data?.error || '报告生成异常')
  } finally {
    generating.value = false
  }
}

function downloadReport(taskId: string) {
  const url = reportApi.getDownloadUrl(taskId)
  window.open(url, '_blank')
}
</script>
