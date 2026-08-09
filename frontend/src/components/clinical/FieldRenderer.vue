<template>
  <el-form-item
    :label="field.label"
    :required="field.required"
    :error="error"
  >
    <!-- String input -->
    <el-input
      v-if="field.ui.component === 'input'"
      v-model="model"
      :placeholder="field.ui.placeholder || ''"
      :disabled="field.computed"
      clearable
    />

    <!-- Number input -->
    <el-input-number
      v-else-if="field.ui.component === 'input-number'"
      v-model="model"
      :step="field.type === 'int' ? 1 : 0.1"
      :precision="field.type === 'int' ? 0 : undefined"
      :disabled="field.computed"
      controls-position="right"
      style="width: 100%"
    />

    <!-- Date picker -->
    <el-date-picker
      v-else-if="field.ui.component === 'date-picker'"
      v-model="model"
      type="date"
      :placeholder="field.ui.placeholder || '选择日期'"
      :disabled="field.computed"
      value-format="YYYY-MM-DD"
      style="width: 100%"
    />

    <!-- Switch (bool) -->
    <el-switch
      v-else-if="field.ui.component === 'switch'"
      v-model="model"
      :disabled="field.computed"
      active-text="是"
      inactive-text="否"
    />

    <!-- Select -->
    <el-select
      v-else-if="field.ui.component === 'select'"
      v-model="model"
      :placeholder="field.ui.placeholder || '请选择'"
      :disabled="field.computed"
      :allow-create="field.ui.allow_create"
      :default-first-option="field.ui.allow_create"
      filterable
      clearable
      style="width: 100%"
    >
      <el-option
        v-for="opt in field.ui.options || []"
        :key="opt"
        :label="opt"
        :value="opt"
      />
    </el-select>

    <!-- File upload -->
    <div
      v-else-if="field.ui.component === 'file-upload' || field.ui.component === 'pdl1-image-upload'"
      style="display: flex; gap: 8px; width: 100%; align-items: center"
    >
      <el-input
        :model-value="uploadDisplayValue"
        :placeholder="field.ui.placeholder || ''"
        readonly
        style="flex: 1"
      />
      <el-upload
        :show-file-list="false"
        :http-request="handleFileUpload"
        :accept="field.ui.accept || 'image/*'"
        :disabled="field.computed"
      >
        <el-button :disabled="field.computed">选择图片</el-button>
      </el-upload>
      <el-button v-if="model" :disabled="field.computed" @click="clearUpload">清空</el-button>
    </div>

    <!-- Fallback -->
    <el-input v-else v-model="model" :disabled="field.computed" />

    <template #label>
      <span>{{ field.label }}</span>
      <el-tooltip v-if="field.description" :content="field.description" placement="top">
        <el-icon style="margin-left: 4px; cursor: help;"><QuestionFilled /></el-icon>
      </el-tooltip>
    </template>
  </el-form-item>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage, type UploadRequestOptions } from 'element-plus'
import { QuestionFilled } from '@element-plus/icons-vue'
import { clinicalApi, type FieldSchema } from '@/api/clinical'

const props = defineProps<{
  field: FieldSchema
  modelValue: any
  error?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: any]
}>()

const model = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const uploadDisplayValue = computed(() => {
  if (!model.value) return ''
  if (props.field.ui.component === 'pdl1-image-upload') {
    return '已上传并校验病例专属PD-L1图片'
  }
  return String(model.value)
})

async function handleFileUpload(options: UploadRequestOptions) {
  const isPdl1Image = props.field.ui.component === 'pdl1-image-upload'
  try {
    const result = isPdl1Image
      ? await clinicalApi.uploadPdl1Image(options.file as File)
      : await clinicalApi.uploadSignature(options.file as File)
    model.value = result.stored_path
    ElMessage.success(isPdl1Image ? 'PD-L1病例图片已上传并完成校验' : '签名图片已上传')
    options.onSuccess?.(result)
  } catch (error: any) {
    const message = error?.response?.data?.detail
      || (isPdl1Image ? 'PD-L1病例图片上传失败' : '签名图片上传失败')
    ElMessage.error(message)
    options.onError?.(error)
  }
}

function clearUpload() {
  model.value = ''
}
</script>
