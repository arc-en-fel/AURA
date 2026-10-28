import { CRMConfiguration, CRMField, FieldType } from '@/types/crm';

/**
 * Validate a complete CRM configuration.
 */
export function validateCRMConfiguration(config: CRMConfiguration): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  if (!config.name || config.name.trim().length === 0) {
    errors.push('CRM name is required');
  }

  if (!config.entities || config.entities.length === 0) {
    errors.push('At least one entity is required');
  }

  config.entities?.forEach((entity, idx) => {
    if (!entity.name || entity.name.trim().length === 0) {
      errors.push(`Entity ${idx + 1}: name is required`);
    }
    if (!entity.label || entity.label.trim().length === 0) {
      errors.push(`Entity ${idx + 1}: label is required`);
    }
    if (!entity.fields || entity.fields.length === 0) {
      errors.push(`Entity ${idx + 1}: at least one field is required`);
    }

    entity.fields?.forEach((field, fieldIdx) => {
      const fieldValidation = validateField(field);
      if (!fieldValidation.valid) {
        errors.push(
          `Entity ${idx + 1}, Field ${fieldIdx + 1}: ${fieldValidation.errors.join(', ')}`
        );
      }
    });
  });

  if (config.pipeline_stages && config.pipeline_stages.length > 0) {
    const uniqueStages = new Set(config.pipeline_stages);
    if (uniqueStages.size !== config.pipeline_stages.length) {
      errors.push('Pipeline stages must be unique');
    }
  }

  return { valid: errors.length === 0, errors };
}

/**
 * Validate a single field.
 */
export function validateField(field: CRMField): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  if (!field.label || field.label.trim().length === 0) {
    errors.push('Field label is required');
  }

  if (!field.name || field.name.trim().length === 0) {
    errors.push('Field name is required');
  }

  if (!isValidFieldType(field.type)) {
    errors.push(`Invalid field type: ${field.type}`);
  }

  // Validate select/multi_select fields must have options
  if ((field.type === 'select' || field.type === 'multi_select') && (!field.options || field.options.length === 0)) {
    errors.push(`${field.type} fields require at least one option`);
  }

  // Validate options if present
  if (field.options) {
    const validationResult = validateSelectOptions(field.options);
    if (!validationResult.valid) {
      errors.push(...validationResult.errors);
    }
  }

  return { valid: errors.length === 0, errors };
}

/**
 * Validate options for select/multi_select fields.
 */
export function validateSelectOptions(
  options: string[]
): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  if (!options || options.length === 0) {
    errors.push('Options cannot be empty');
    return { valid: false, errors };
  }

  const nonEmptyOptions = options.filter((opt) => opt.trim().length > 0);
  if (nonEmptyOptions.length !== options.length) {
    errors.push('Options cannot be empty strings');
  }

  const uniqueOptions = new Set(nonEmptyOptions);
  if (uniqueOptions.size !== nonEmptyOptions.length) {
    errors.push('Options must be unique');
  }

  return { valid: errors.length === 0, errors };
}

/**
 * Check if a field type is valid.
 */
export function isValidFieldType(type: unknown): type is FieldType {
  const validTypes: FieldType[] = [
    'text',
    'textarea',
    'email',
    'number',
    'date',
    'datetime',
    'boolean',
    'select',
    'multi_select',
    'phone',
    'url',
  ];
  return typeof type === 'string' && (validTypes as string[]).includes(type);
}

/**
 * Normalize a label to a machine-friendly name (lowercase, underscores).
 * E.g., "Customer Name" -> "customer_name"
 */
export function normalizeLabelToKey(label: string): string {
  return label
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_') // Replace non-alphanumeric with underscore
    .replace(/^_+|_+$/g, '') // Remove leading/trailing underscores
    .slice(0, 64); // Limit to 64 chars
}

/**
 * Check if a field name is reserved or invalid.
 */
export function isReservedFieldName(name: string): boolean {
  const reserved = ['id', 'crm_id', 'created_at', 'updated_at', 'deleted_at', 'entity_name', 'source'];
  return reserved.includes(name.toLowerCase());
}

/**
 * Sanitize user input to prevent injection attacks.
 */
export function sanitizeInput(input: string): string {
  return input.replace(/[<>]/g, '');
}

/**
 * Get the display name for a field type.
 */
export function getFieldTypeLabel(type: FieldType): string {
  const labels: Record<FieldType, string> = {
    text: 'Text',
    textarea: 'Text Area',
    email: 'Email',
    number: 'Number',
    date: 'Date',
    datetime: 'Date & Time',
    boolean: 'Yes/No',
    select: 'Dropdown',
    multi_select: 'Multi-Select',
    phone: 'Phone',
    url: 'URL',
  };
  return labels[type] || type;
}
