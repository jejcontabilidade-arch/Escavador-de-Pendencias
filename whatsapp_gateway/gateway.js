const express = require('express');
const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');
const qrcode = require('qrcode');
const axios = require('axios');
const fs = require('fs');
const path = require('path');
const bodyParser = require('body-parser');

const app = express();
app.use(bodyParser.json({ limit: '50mb' }));

const PORT = 3000;
const SESSION_PATH = path.join(__dirname, '..', 'temp', 'session-wwebjs_session');
const CONFIG_PATH = path.join(__dirname, '..', 'config_private.json');

let client = null;
let currentStatus = 'disconnected'; // 'disconnected', 'authenticating', 'qr_ready', 'connected'
let latestQr = null;
let authorizedNumber = '';

// Função para logar mensagens no console com timestamp
function log(msg, level = 'GATEWAY') {
    const timestamp = new Date().toISOString().replace('T', ' ').substring(0, 19);
    console.log(`[${timestamp}] [${level}] ${msg}`);
}

// Carregar número autorizado do config_private.json
function loadAuthorizedNumber() {
    try {
        if (fs.existsSync(CONFIG_PATH)) {
            const config = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf-8'));
            authorizedNumber = config.whatsapp_number || '';
            log(`Número autorizado carregado: ${authorizedNumber}`, 'CONFIG');
        } else {
            log('Arquivo config_private.json não encontrado. Webhook de recebimento pode não funcionar corretamente.', 'WARNING');
        }
    } catch (err) {
        log(`Erro ao carregar config_private.json: ${err.message}`, 'ERROR');
    }
}

// Limpar pasta de sessão antiga para forçar logout completo
function clearSessionFolder() {
    try {
        if (fs.existsSync(SESSION_PATH)) {
            fs.rmSync(SESSION_PATH, { recursive: true, force: true });
            log('Diretório de sessão do WhatsApp Web apagado.', 'SUCCESS');
        }
    } catch (err) {
        log(`Erro ao apagar diretório de sessão: ${err.message}`, 'WARNING');
    }
}

// Inicializar o cliente WhatsApp Web
function initWhatsAppClient() {
    log('Inicializando cliente WhatsApp Web...', 'INFO');
    currentStatus = 'authenticating';
    latestQr = null;

    client = new Client({
        authStrategy: new LocalAuth({
            dataPath: path.join(__dirname, '..', 'temp'),
            clientId: 'wwebjs_session'
        }),
        webVersionCache: {
            type: 'remote',
            remotePath: 'https://raw.githubusercontent.com/wppconnect-team/wa-version/main/html/{version}.html',
            strict: false
        },
        puppeteer: {
            headless: true,
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
            ]
        }
    });

    client.on('qr', (qr) => {
        log('Novo QR Code gerado pelo WhatsApp Web.', 'QR');
        latestQr = qr;
        currentStatus = 'qr_ready';
    });

    client.on('authenticated', () => {
        log('Autenticação no WhatsApp efetuada com sucesso!', 'AUTH');
    });

    client.on('auth_failure', (msg) => {
        log(`Falha na autenticação do WhatsApp Web: ${msg}`, 'ERROR');
        currentStatus = 'disconnected';
        latestQr = null;
    });

    client.on('ready', () => {
        log('O cliente do WhatsApp Web está PRONTO para enviar/receber mensagens!', 'SUCCESS');
        currentStatus = 'connected';
        latestQr = null;
    });

    client.on('disconnected', (reason) => {
        log(`Desconectado do WhatsApp: ${reason}`, 'WARNING');
        currentStatus = 'disconnected';
        latestQr = null;
        
        // Destrói o cliente e limpa a sessão para poder receber um novo QR Code
        try {
            client.destroy();
        } catch (e) {}
        clearSessionFolder();
        
        // Reinicializa em 5 segundos
        setTimeout(initWhatsAppClient, 5000);
    });

    // Evento de recepção de mensagens
    client.on('message', async (msg) => {
        log(`Mensagem recebida de ${msg.from}: "${msg.body}"`);

        // Recarregar configurações para ter o número autorizado mais recente
        loadAuthorizedNumber();

        if (!authorizedNumber) {
            log('Mensagem ignorada: Nenhum número autorizado configurado.', 'SECURITY');
            return;
        }

        const senderClean = msg.from.replace(/\D/g, '');
        const authClean = authorizedNumber.replace(/\D/g, '');

        let isAuthorized = (senderClean === authClean) || senderClean.endsWith(authClean) || authClean.endsWith(senderClean);
        if (!isAuthorized && senderClean.length >= 8 && authClean.length >= 8) {
            isAuthorized = (senderClean.slice(-8) === authClean.slice(-8));
        }

        if (isAuthorized) {
            log('Mensagem vinda de número autorizado. Repassando para o webhook Flask...', 'INFO');
            
            // Monta o payload no formato esperado por agente_escavador.py (Z-API Mock)
            const webhookPayload = {
                phone: msg.from,
                text: {
                    message: msg.body
                }
            };

            try {
                const response = await axios.post('http://127.0.0.1:5000/api/webhook/whatsapp', webhookPayload, { timeout: 10000 });
                log(`Webhook Flask respondeu: ${response.status} ${JSON.stringify(response.data)}`, 'SUCCESS');
            } catch (err) {
                log(`Erro ao notificar webhook Flask: ${err.message}`, 'ERROR');
            }
        } else {
            log(`Mensagem de número não autorizado (${senderClean}). Ignorando por segurança.`, 'SECURITY');
        }
    });

    try {
        client.initialize();
    } catch (err) {
        log(`Erro ao inicializar cliente: ${err.message}`, 'ERROR');
        currentStatus = 'disconnected';
    }
}

// ----------------- EXPRESS ENDPOINTS -----------------

// Rota de status do WhatsApp
app.get('/api/status', (req, res) => {
    res.json({ status: currentStatus });
});

// Rota de obtenção do QR Code em imagem base64
app.get('/api/qr', async (req, res) => {
    if (currentStatus === 'qr_ready' && latestQr) {
        try {
            const qrImageBase64 = await qrcode.toDataURL(latestQr);
            res.json({ qr: qrImageBase64, status: currentStatus });
        } catch (err) {
            log(`Erro ao converter QR Code para base64: ${err.message}`, 'ERROR');
            res.status(500).json({ error: 'Erro ao gerar imagem do QR Code' });
        }
    } else {
        res.json({ qr: null, status: currentStatus });
    }
});

// Rota de envio de mensagem de texto simples
app.post('/api/send-message', async (req, res) => {
    if (currentStatus !== 'connected' || !client) {
        return res.status(400).json({ error: 'WhatsApp não está conectado' });
    }

    const { to, message } = req.body;
    if (!to || !message) {
        return res.status(400).json({ error: 'Parâmetros "to" e "message" são obrigatórios' });
    }

    // Limpar o número de destino e formatar para o padrão do WhatsApp Web (@c.us)
    let cleanTo = to.replace(/\D/g, '');
    if (!cleanTo.endsWith('@c.us') && !cleanTo.endsWith('@g.us')) {
        // WhatsApp Web exige o formato correto. Para números brasileiros de celular antigos:
        cleanTo = `${cleanTo}@c.us`;
    }

    try {
        log(`Enviando mensagem de texto para ${cleanTo}...`);
        const sentMsg = await client.sendMessage(cleanTo, message);
        res.json({ success: true, messageId: sentMsg.id.id });
    } catch (err) {
        log(`Erro ao enviar mensagem: ${err.message}`, 'ERROR');
        res.status(500).json({ error: `Erro ao enviar mensagem: ${err.message}` });
    }
});

// Rota de envio de documentos pesados (PDFs de certidões/relatórios)
app.post('/api/send-document', async (req, res) => {
    if (currentStatus !== 'connected' || !client) {
        return res.status(400).json({ error: 'WhatsApp não está conectado' });
    }

    const { to, fileName, document } = req.body;
    if (!to || !fileName || !document) {
        return res.status(400).json({ error: 'Parâmetros "to", "fileName" e "document" (base64) são obrigatórios' });
    }

    // Limpar o número de destino
    let cleanTo = to.replace(/\D/g, '');
    if (!cleanTo.endsWith('@c.us') && !cleanTo.endsWith('@g.us')) {
        cleanTo = `${cleanTo}@c.us`;
    }

    try {
        log(`Enviando documento "${fileName}" para ${cleanTo}...`);
        
        // Decodificar base64 e mimetype do payload
        // Formato esperado: "data:application/pdf;base64,JVBERi0xLjQK..."
        const parts = document.split(';base64,');
        const mimetype = parts[0].replace('data:', '');
        const base64Data = parts[1];

        const media = new MessageMedia(mimetype, base64Data, fileName);
        const sentMsg = await client.sendMessage(cleanTo, media);
        
        res.json({ success: true, messageId: sentMsg.id.id });
    } catch (err) {
        log(`Erro ao enviar documento: ${err.message}`, 'ERROR');
        res.status(500).json({ error: `Erro ao enviar documento: ${err.message}` });
    }
});

// Rota para forçar desconexão e exclusão de sessão
app.post('/api/disconnect', async (req, res) => {
    log('Solicitação de desconexão manual recebida.', 'ACTION');
    
    if (client) {
        try {
            await client.logout();
            log('Logout no WhatsApp efetuado com sucesso.');
        } catch (e) {
            log(`Aviso ao tentar efetuar logout: ${e.message}`, 'WARNING');
        }
        try {
            await client.destroy();
        } catch (e) {}
    }

    clearSessionFolder();
    
    // Reinicia o cliente em segundo plano para gerar novo QR Code
    setTimeout(initWhatsAppClient, 2000);
    
    res.json({ success: true, message: 'WhatsApp desconectado e sessão apagada com sucesso' });
});

// Iniciar servidor Express e WhatsApp
app.listen(PORT, '127.0.0.1', () => {
    log(`Servidor Gateway WhatsApp rodando localmente em http://127.0.0.1:${PORT}`, 'START');
    loadAuthorizedNumber();
    initWhatsAppClient();
});
