/**
 * Shared utility for loading and displaying OpenRouter models
 */

/**
 * Fetch available models from OpenRouter
 * @returns {Promise<Array>} Array of model objects
 */
async function fetchOpenRouterModels() {
    try {
        const res = await fetch('/debug/llm-playground/models');
        if (!res.ok) throw new Error('Failed to load models');
        return await res.json();
    } catch(e) {
        console.error('Error loading OpenRouter models:', e);
        throw e;
    }
}

/**
 * Populate a select element with OpenRouter models
 * @param {HTMLSelectElement} selectElement - The select element to populate
 * @param {Object} options - Configuration options
 * @param {boolean} options.includeTierInName - Whether to append [Free]/[Paid] to model name
 * @param {string} options.emptyMessage - Message to show when no models available
 * @param {Function} options.onLoad - Callback after models are loaded
 * @returns {Promise<Array>} The loaded models
 */
async function populateModelSelect(selectElement, options = {}) {
    const {
        includeTierInName = false,
        emptyMessage = 'No models available',
        onLoad = null
    } = options;

    try {
        const models = await fetchOpenRouterModels();

        selectElement.innerHTML = '';

        if (models.length === 0) {
            selectElement.innerHTML = `<option value="">${emptyMessage}</option>`;
            return models;
        }

        // Add models to dropdown
        models.forEach(model => {
            const option = document.createElement('option');
            option.value = model.id;
            option.textContent = includeTierInName ? `${model.name} [${model.tier}]` : model.name;

            // Store model data as data attributes
            option.dataset.tier = model.tier;
            option.dataset.isFree = model.is_free;
            option.dataset.contextLength = model.context_length;
            option.dataset.pricing = JSON.stringify(model.pricing);
            option.dataset.description = model.description || '';

            selectElement.appendChild(option);
        });

        // Call onLoad callback if provided
        if (onLoad && typeof onLoad === 'function') {
            onLoad(models);
        }

        return models;

    } catch(e) {
        selectElement.innerHTML = `<option value="">Error loading models</option>`;
        throw e;
    }
}

/**
 * Get the tier (free/paid) from a selected option
 * @param {HTMLSelectElement} selectElement - The select element
 * @returns {string} 'free' or 'paid'
 */
function getSelectedModelTier(selectElement) {
    const selectedOption = selectElement.options[selectElement.selectedIndex];
    return selectedOption?.dataset.tier?.toLowerCase() || 'paid';
}

/**
 * Get detailed info about the selected model
 * @param {HTMLSelectElement} selectElement - The select element
 * @returns {Object|null} Model info object or null if no selection
 */
function getSelectedModelInfo(selectElement) {
    const selectedOption = selectElement.options[selectElement.selectedIndex];
    if (!selectedOption || !selectedOption.value) return null;

    return {
        id: selectedOption.value,
        name: selectedOption.textContent,
        tier: selectedOption.dataset.tier,
        isFree: selectedOption.dataset.isFree === 'true',
        contextLength: parseInt(selectedOption.dataset.contextLength) || 0,
        pricing: JSON.parse(selectedOption.dataset.pricing || '{}'),
        description: selectedOption.dataset.description || ''
    };
}
