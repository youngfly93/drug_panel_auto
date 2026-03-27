import { ref, reactive, watch, type Ref } from 'vue'
import { clinicalApi, type ClinicalFormSchema } from '@/api/clinical'

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

  // Fetch schema when project type changes
  watch(
    projectType,
    async (type) => {
      loading.value = true
      try {
        schema.value = await clinicalApi.getSchema(type)
        // Initialize form with defaults (don't overwrite existing values)
        if (schema.value) {
          for (const group of schema.value.groups) {
            for (const field of group.fields) {
              if (!(field.key in formData) || formData[field.key] === undefined) {
                formData[field.key] = field.default ?? ''
              }
            }
          }
          // Auto-fill report_date with today if not set (Fix Issue 3)
          if (!formData['report_date']) {
            formData['report_date'] = new Date().toISOString().slice(0, 10)
          }
        }
      } finally {
        loading.value = false
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
      if (value !== null && value !== undefined && value !== '' && value !== '-') {
        formData[key] = value
      }
    }
  }

  /**
   * Merge patient info from the patient database.
   */
  function mergePatientInfo(info: Record<string, any>) {
    for (const [key, value] of Object.entries(info)) {
      if (value && key !== 'sample_id') {
        formData[key] = value
      }
    }
  }

  /**
   * Validate required fields. Returns true if valid.
   */
  function validate(): boolean {
    errors.value = {}
    if (!schema.value) return true

    let valid = true
    for (const group of schema.value.groups) {
      for (const field of group.fields) {
        if (field.required && field.key !== 'report_date') {
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
    Object.keys(formData).forEach((k) => delete formData[k])
    errors.value = {}
  }

  return {
    schema,
    formData,
    loading,
    errors,
    mergeExcelValues,
    mergePatientInfo,
    validate,
    getCleanValues,
    reset,
  }
}
