// backend/funcoeslead/controllers/productController.js
const productService = require('../services/productService');
const logger = require('../logger');

/**
 * Controller to search for products.
 */
async function searchProductsController(req, res) {
    const { q } = req.query;

    if (!q) {
        return res.status(400).json({ error: 'Query parameter \'q\' is required.' });
    }

    try {
        logger.info(`Received request to search for products with query: ${q}`);
        const results = await productService.searchProducts(q);
        res.status(200).json(results);
    } catch (error) {
        logger.error(`Error in controller while searching for products with query ${q}:`, error);
        const statusCode = error.response?.status || 500;
        const errorMessage = error.message || 'An internal server error occurred.';
        res.status(statusCode).json({ error: errorMessage, details: error.response?.data });
    }
}

/**
 * Controller to get opportunity products.
 */
async function getOpportunityProductsController(req, res) {
    const { opportunityId } = req.params;

    try {
        logger.info(`Received request to get products for opportunity ${opportunityId}`);
        const results = await productService.getOpportunityProducts(opportunityId);
        res.status(200).json(results);
    } catch (error) {
        logger.error(`Error in controller while getting products for opportunity ${opportunityId}:`, error);
        const statusCode = error.response?.status || 500;
        const errorMessage = error.message || 'An internal server error occurred.';
        res.status(statusCode).json({ error: errorMessage, details: error.response?.data });
    }
}

/**
 * Controller to add a product to an opportunity.
 */
async function addOpportunityProductController(req, res) {
    const { opportunityId } = req.params;
    const { productId, quantity, unitPrice } = req.body;

    if (!productId || !quantity || !unitPrice) {
        return res.status(400).json({ error: 'productId, quantity, and unitPrice are required.' });
    }

    try {
        logger.info(`Received request to add product ${productId} to opportunity ${opportunityId}`);
        const result = await productService.addOpportunityProduct(opportunityId, productId, quantity, unitPrice);
        res.status(201).json(result);
    } catch (error) {
        logger.error(`Error in controller while adding product ${productId} to opportunity ${opportunityId}:`, error);
        const statusCode = error.response?.status || 500;
        const errorMessage = error.message || 'An internal server error occurred.';
        res.status(statusCode).json({ error: errorMessage, details: error.response?.data });
    }
}

/**
 * Controller to update a product in an opportunity.
 */
async function updateOpportunityProductController(req, res) {
    const { opportunityProductId } = req.params;
    const { quantity, unitPrice } = req.body;

    if (!quantity && !unitPrice) {
        return res.status(400).json({ error: 'Either quantity or unitPrice is required.' });
    }

    try {
        logger.info(`Received request to update opportunity product ${opportunityProductId}`);
        const result = await productService.updateOpportunityProduct(opportunityProductId, quantity, unitPrice);
        res.status(200).json(result);
    } catch (error) {
        logger.error(`Error in controller while updating opportunity product ${opportunityProductId}:`, error);
        const statusCode = error.response?.status || 500;
        const errorMessage = error.message || 'An internal server error occurred.';
        res.status(statusCode).json({ error: errorMessage, details: error.response?.data });
    }
}

/**
 * Controller to delete a product from an opportunity.
 */
async function deleteOpportunityProductController(req, res) {
    const { opportunityProductId } = req.params;

    try {
        logger.info(`Received request to delete opportunity product ${opportunityProductId}`);
        await productService.deleteOpportunityProduct(opportunityProductId);
        res.status(204).send();
    } catch (error) {
        logger.error(`Error in controller while deleting opportunity product ${opportunityProductId}:`, error);
        const statusCode = error.response?.status || 500;
        const errorMessage = error.message || 'An internal server error occurred.';
        res.status(statusCode).json({ error: errorMessage, details: error.response?.data });
    }
}


module.exports = {
    searchProductsController,
    getOpportunityProductsController,
    addOpportunityProductController,
    updateOpportunityProductController,
    deleteOpportunityProductController
};

