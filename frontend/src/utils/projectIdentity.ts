/** An IHC value/form source can select a sibling, never a different NGS panel. */
export function pdl1VariantForForm(type: string | null, values: Record<string, unknown>): string | null {
  const variants: Record<string, string> = { lung_62: 'lung_62_pdl1', lung_588: 'lung_588_pdl1' }
  const variant = variants[type || '']
  const supplied = ['pdl1_tps', 'pdl1_cps', 'pdl1_result', 'pdl1_image_path', 'pdl1_source_record_id']
    .some((key) => values[key] !== null && values[key] !== undefined && String(values[key]).trim() !== '')
  return variant && supplied ? variant : null
}
