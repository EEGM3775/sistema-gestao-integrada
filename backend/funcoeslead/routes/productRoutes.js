// backend/funcoeslead/routes/productRoutes.js
const express = require('express');
const router = express.Router();
const { 
    searchProductsController,
    getOpportunityProductsController,
    addOpportunityProductController,
    updateOpportunityProductController,
    deleteOpportunityProductController
} = require('../controllers/productController');

/**
 * @swagger
 * /api/products/search:
 *   get:
 *     summary: Search for products in the catalog.
 *     tags: [Products]
 *     parameters:
 *       - in: query
 *         name: q
 *         schema:
 *           type: string
 *         required: true
 *         description: The search query.
 *     responses:
 *       200:
 *         description: A list of products.
 *         content:
 *           application/json:
 *             schema:
 *               type: array
 *               items:
 *                 type: object
 *       400:
 *         description: Missing query parameter.
 *       500:
 *         description: Internal server error.
 */
router.get('/search', searchProductsController);

router.get('/opportunities/:opportunityId/products', getOpportunityProductsController);
router.post('/opportunities/:opportunityId/products', addOpportunityProductController);
router.patch('/opportunity-products/:opportunityProductId', updateOpportunityProductController);
router.delete('/opportunity-products/:opportunityProductId', deleteOpportunityProductController);

module.exports = router;
