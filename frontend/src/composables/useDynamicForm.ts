import { computed, ref, reactive, watch, type Ref } from 'vue'
import { clinicalApi, type ClinicalFormSchema } from '@/api/clinical'

const PROJECT_DISPLAY_NAMES: Record<string, string> = {
  crc_301_msi: '结直肠癌301基因+MSI',
  crc_358_msi: '结直肠癌358基因+MSI',
  lung_329_pdl1: '肺癌329基因+PD-L1',
  lung_588_pdl1: '肺癌588基因+PD-L1',
  mlf_result: 'MLF基因检测结果',
  lung_methylation: '肺癌甲基化',
}

const PROJECT_SCOPED_FIELDS = new Set([
  'pdl1_tps',
  'pdl1_cps',
  'pdl1_result',
  'pdl1_image_path',
  'pdl1_assay_profile_id',
  'pdl1_source_record_id',
  'pdl1_source_record_date',
  'pdl1_specimen_id',
  'pdl1_image_disposition',
  'methylation_result',
  'lung_histology',
  'disease_extent',
  'prior_systemic_therapy',
  'companion_diagnostic_status',
])
const PROJECT_IDENTITY_FIELDS = new Set(['project_name', '项目名称', '检测项目'])

export function projectDisplayName(projectType: string | null | undefined): string | null {
  return projectType ? PROJECT_DISPLAY_NAMES[projectType] || null : null
}

/**
 * Core composable for the dynamic clinical info form.
 * Fetches schema from backend (driven by mapping.yaml),
 * initializes form data with defaults, and provides
 * merge/validate utilities.
 */
export function useDynamicForm(projectType: Ref<string | null>) {
  const schema = ref<ClinicalFormSchema | null>(null)
  const formData = reactive<Record<string, any>>({})
  const loading = ref(false)
  const errors = ref<Record<string, string>>({})
  let schemaRequestId = 0

  // Fetch schema when project type changes
  watch(
    projectType,
    async (type) => {
      const requestId = ++schemaRequestId
      errors.value = {}
      if (!type) {
        schema.value = null
        loading.value = false
        return
      }
      loading.value = true
      try {
        const nextSchema = await clinicalApi.getSchema(type)
        if (requestId !== schemaRequestId || projectType.value !== type) return
        schema.value = nextSchema
        // Initialize form with defaults (don't overwrite existing values)
        if (schema.value) {
          const schemaFields = new Set(
            schema.value.groups.flatMap((group) => group.fields.map((field) => field.key)),
          )
          for (const field of PROJECT_SCOPED_FIELDS) {
            if (!schemaFields.has(field)) delete formData[field]
          }
          for (const group of schema.value.groups) {
            for (const field of group.fields) {
              if (!(field.key in formData) || formData[field.key] === undefined) {
                formData[field.key] = field.default ?? ''
              }
            }
          }
          const canonicalName = projectDisplayName(type)
          if (canonicalName) formData.project_name = canonicalName
        }
      } finally {
        if (requestId === schemaRequestId) loading.value = false
      }
    },
    { immediate: true },
  )

  /**
   * Merge Excel-extracted single values into the form.
   * Only overwrites if the value is non-empty.
   */
  function mergeExcelValues(values: Record<string, any>) {
    for (const [key, value] of Object.entries(values)) {
      if (PROJECT_IDENTITY_FIELDS.has(key)) continue
      if (value !== null && value !== undefined && value !== '' && value !== '-') {
        formData[key] = value
        delete errors.value[key]
      }
    }
  }

  /**
   * Merge patient info from the patient database.
   */
  function mergePatientInfo(info: Record<string, any>) {
    for (const [key, value] of Object.entries(info)) {
      if (value && key !== 'sample_id' && !PROJECT_IDENTITY_FIELDS.has(key)) {
        formData[key] = value
        delete errors.value[key]
      }
    }
  }

  /**
   * Validate required fields. Returns true if valid.
   */
  function validate(): boolean {
    errors.value = {}
    if (
      loading.value
      || !projectType.value
      || !schema.value
      || schema.value.project_type !== projectType.value
    ) {
      return false
    }

    let valid = true
    for (const group of schema.value.groups) {
      for (const field of group.fields) {
        if (field.required) {
          const val = formData[field.key]
          if (val === null || val === undefined || val === '') {
            errors.value[field.key] = `${field.label}不能为空`
            valid = false
          }
        }
      }
    }
    return valid
  }

  function setValue(key: string, value: unknown) {
    formData[key] = value
    delete errors.value[key]
  }

  /**
   * Get all non-empty form values as a clean dict for submission.
   */
  function getCleanValues(): Record<string, any> {
    const result: Record<string, any> = {}
    for (const [key, value] of Object.entries(formData)) {
      if (value !== null && value !== undefined && value !== '') {
        result[key] = value
      }
    }
    return result
  }

  function reset() {
    schemaRequestId += 1
    Object.keys(formData).forEach((k) => delete formData[k])
    errors.value = {}
    schema.value = null
    loading.value = false
  }

  const ready = computed(
    () => Boolean(
      projectType.value
      && !loading.value
      && schema.value
      && schema.value.project_type === projectType.value,
    ),
  )

  return {
    schema,
    formData,
    loading,
    errors,
    ready,
    mergeExcelValues,
    mergePatientInfo,
    validate,
    setValue,
    getCleanValues,
    reset,
  }
}
