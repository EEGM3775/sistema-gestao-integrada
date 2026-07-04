// backend/funcoeslead/services/productService.js
const djangoApi = require('./djangoApiService');
const logger = require('../logger');

/**
 * Search for products in the catalog.
 * @param {string} query The search query.
 * @returns {Promise<object>} The search results.
 */
async function searchProducts(query) {
    logger.info(`Searching for products with query: ${query}`);

    try {
        const response = await djangoApi.apiClient.get('/produtos-servicos-fornecedores/', {
            params: {
                search: query
            }
        });
        return response.data;
    } catch (error) {
        logger.error('Error searching for products:', error);
        throw error;
    }
}

/**
 * Get all products for a given opportunity.
 * @param {string} opportunityId The ID of the opportunity.
 * @returns {Promise<object>} The list of opportunity products.
 */
async function getOpportunityProducts(opportunityId) {
    logger.info(`Getting products for opportunity ${opportunityId}`);
    try {
        const response = await djangoApi.apiClient.get('/crm/opportunity-products/', {
            params: {
                opportunity_id: opportunityId
            }
        });
        return response.data;
    } catch (error) {
        logger.error(`Error getting products for opportunity ${opportunityId}:`, error);
        throw error;
    }
}

/**
 * Add a product to an opportunity.
 * @param {string} opportunityId The ID of the opportunity.
 * @param {string} productId The ID of the product.
 * @param {number} quantity The quantity of the product.
 * @param {number} unitPrice The unit price of the product.
 * @returns {Promise<object>} The created opportunity product.
 */
async function addOpportunityProduct(opportunityId, productId, quantity, unitPrice) {
    logger.info(`Adding product ${productId} to opportunity ${opportunityId}`);
    try {
        const response = await djangoApi.createObject('/crm/opportunity-products/', {
            opportunity: opportunityId,
            product: productId,
            quantity: quantity,
            unit_price: unitPrice
        });
        return response;
    } catch (error) {
        logger.error(`Error adding product ${productId} to opportunity ${opportunityId}:`, error);
        throw error;
    }
}

/**
 * Update a product in an opportunity.
 * @param {string} opportunityProductId The ID of the opportunity product.
 * @param {number} quantity The new quantity.
 * @param {number} unitPrice The new unit price.
 * @returns {Promise<object>} The updated opportunity product.
 */
async function updateOpportunityProduct(opportunityProductId, quantity, unitPrice) {
    logger.info(`Updating opportunity product ${opportunityProductId}`);
    try {
        const response = await djangoApi.updateObject(`/crm/opportunity-products/`, opportunityProductId, {
            quantity: quantity,
            unit_price: unitPrice
        });
        return response;
    } catch (error) {
        logger.error(`Error updating opportunity product ${opportunityProductId}:`, error);
        throw error;
    }
}

/**
 * Delete a product from an opportunity.
 * @param {string} opportunityProductId The ID of the opportunity product to delete.
 * @returns {Promise<void>}
 */
async function deleteOpportunityProduct(opportunityProductId) {
    logger.info(`Deleting opportunity product ${opportunityProductId}`);
    try {
        await djangoApi.deleteObject('/crm/opportunity-products/', opportunityProductId);
    } catch (error) {
        logger.error(`Error deleting opportunity product ${opportunityProductId}:`, error);
        throw error;
    }
}


module.exports = {
    searchProducts,
    getOpportunityProducts,
    addOpportunityProduct,
    updateOpportunityProduct,
    deleteOpportunityProduct
};
