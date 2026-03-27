<template>
  <div v-if="loading" class="loading-container">
    <el-skeleton :rows="6" animated />
  </div>
  <el-form v-else-if="schema" label-width="120px" label-position="right">
    <template v-for="group in visibleGroups" :key="group.id">
      <el-divider content-position="left">{{ group.label }}</el-divider>
      <el-row :gutter="16">
        <el-col
          v-for="field in group.fields"
          :key="field.key"
          :span="field.ui.span"
        >
          <FieldRenderer
            :field="field"
            :model-value="formData[field.key]"
            :error="errors[field.key]"
            @update:model-value="formData[field.key] = $event"
          />
        </el-col>
      </el-row>
    </template>
  </el-form>
  <el-empty v-else description="请先选择项目类型以加载表单" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ClinicalFormSchema } from '@/api/clinical'
import FieldRenderer from './FieldRenderer.vue'

const props = defineProps<{
  schema: ClinicalFormSchema | null
  formData: Record<string, any>
  errors: Record<string, string>
  loading: boolean
}>()

// Hide the "computed" group by default (collapsible in future)
const visibleGroups = computed(() => {
  if (!props.schema) return []
  return props.schema.groups.filter((g) => g.id !== 'computed')
})
</script>

<style scoped>
.loading-container {
  padding: 20px;
}
</style>
