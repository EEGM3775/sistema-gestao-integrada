
const express = require('express');
const router = express.Router();
const { getAgenda } = require('../controllers/agendaController');
const { redirectToGoogleAuth, handleGoogleCallback } = require('../controllers/googleController');

// Rotas da Agenda
router.get('/users/:userId/agenda', getAgenda);

// Rotas de Autenticação do Google Calendar
router.get('/google/auth', redirectToGoogleAuth);
router.get('/google/callback', handleGoogleCallback);

module.exports = router;
