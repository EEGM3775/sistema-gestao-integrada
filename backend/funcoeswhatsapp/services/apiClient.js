// backend/funcoeswhatsapp/services/apiClient.js
const axios = require('axios');
const config = require('../config');

const djangoApi = axios.create({
  baseURL: config.django.apiUrl,
  headers: { 'Authorization': `Token ${config.django.apiToken}` }
});

module.exports = djangoApi;
