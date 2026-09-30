const express = require('express');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');

const app = express();
app.use(express.json());

const NODEODM_DATA = process.env.NODEODM_DATA || '/nodeodm/data';
const POTREE_OUTPUT = process.env.POTREE_OUTPUT || '/potree/data';
const CONVERTER_BIN = path.join(__dirname, 'PotreeConverter');

function statusFile(taskUuid) {
  return path.join(POTREE_OUTPUT, taskUuid, '_status.json');
}

function readStatus(taskUuid) {
  const file = statusFile(taskUuid);
  if (!fs.existsSync(file)) return { status: 'not_started' };
  try {
    return JSON.parse(fs.readFileSync(file, 'utf-8'));
  } catch {
    return { status: 'not_started' };
  }
}

function writeStatus(taskUuid, data) {
  const dir = path.join(POTREE_OUTPUT, taskUuid);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(statusFile(taskUuid), JSON.stringify(data));
}

// GET /health
app.get('/health', (_req, res) => res.json({ status: 'ok' }));

// GET /status/:taskUuid
app.get('/status/:taskUuid', (req, res) => {
  res.json(readStatus(req.params.taskUuid));
});

// POST /convert  { taskUuid }
app.post('/convert', (req, res) => {
  const { taskUuid } = req.body;
  if (!taskUuid) return res.status(400).json({ error: 'taskUuid required' });

  const current = readStatus(taskUuid);
  if (current.status === 'converting') return res.json(current);
  if (current.status === 'ready') return res.json(current);

  const inputLaz = path.join(NODEODM_DATA, taskUuid, 'odm_georeferencing', 'odm_georeferenced_model.laz');
  if (!fs.existsSync(inputLaz)) {
    return res.status(404).json({ error: '[ERRO] LAZ nao encontrado: ' + inputLaz });
  }

  const outputDir = path.join(POTREE_OUTPUT, taskUuid);
  fs.mkdirSync(outputDir, { recursive: true });

  const started = new Date().toISOString();
  writeStatus(taskUuid, { status: 'converting', startedAt: started });

  res.json({ status: 'converting', startedAt: started });

  // Run PotreeConverter in background
  const proc = spawn(CONVERTER_BIN, [
    '--input', inputLaz,
    '--output', outputDir,
    '--overwrite'
  ]);

  let stderr = '';
  proc.stderr.on('data', d => { stderr += d.toString(); });

  proc.on('close', code => {
    if (code === 0) {
      writeStatus(taskUuid, { status: 'ready', startedAt: started, completedAt: new Date().toISOString() });
      console.log('[OK] Conversion complete:', taskUuid);
    } else {
      writeStatus(taskUuid, { status: 'failed', startedAt: started, error: stderr.slice(-500) });
      console.error('[ERRO] Conversion failed:', taskUuid, stderr.slice(-200));
    }
  });
});

const PORT = process.env.PORT || 5001;
app.listen(PORT, () => console.log('[INFO] potree-converter-service na porta ' + PORT));
