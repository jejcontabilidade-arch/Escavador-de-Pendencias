const express = require('express');
const { Client, LocalAuth, MessageMedia } = require('whatsapp-web.js');
const qrcode = require('qrcode');
const axios = require('axios');
const fs = require('fs');
const path = require('path');
const bodyParser = require('body-parser');

const app = express();
app.use(bodyParser.json({ limit: '50mb' }));

// Captura de exceções globais para evitar que o processo Node caia abruptamente
process.on('unhandledRejection', (reason, promise) => {
    const timestamp = new Date().toISOString().replace('T', ' ').substring(0, 19);
    console.error(`[${timestamp}] [FATAL_REJECTION] Unhandled Rejection em:`, promise, `motivo:`, reason);
});

process.on('uncaughtException', (error) => {
    const timestamp = new Date().toISOString().replace('T', ' ').substring(0, 19);
    console.error(`[${timestamp}] [FATAL_EXCEPTION] Uncaught Exception: ${error.message}\nStack: ${error.stack}`);
});

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

let jidToPhoneMap = {}; // Maps: '69668748431583@lid' -> '5561986221356'
let phoneToJidMap = {}; // Maps: '5561986221356' -> '69668748431583@lid'

const csvPath = path.join(__dirname, '..', 'autorizados.csv');

// Carrega números autorizados do CSV
function loadAuthorizedNumbersFromCsv() {
    const list = [];
    try {
        if (fs.existsSync(csvPath)) {
            const data = fs.readFileSync(csvPath, 'utf-8');
            const lines = data.split('\n');
            for (let i = 1; i < lines.length; i++) {
                const line = lines[i].trim();
                if (!line) continue;
                const parts = line.split(',');
                if (parts.length >= 3) {
                    const number = parts[0].replace(/\D/g, '');
                    const name = parts[1].trim();
                    const permission = parts[2].trim().toLowerCase();
                    if (number) {
                        list.push({ number, name, permission });
                    }
                }
            }
        }
    } catch (err) {
        log(`Erro ao ler autorizados.csv no gateway: ${err.message}`, 'ERROR');
    }
    return list;
}

// Atualiza o cache bidirecional JID <-> Telefone para contatos autorizados
async function updateJidCache() {
    if (!client) return;
    
    log('Atualizando cache de JIDs dos contatos autorizados...', 'INFO');
    const csvContacts = loadAuthorizedNumbersFromCsv();
    
    // Adiciona o número padrão do config_private se existir
    if (authorizedNumber) {
        const cleanAuth = authorizedNumber.replace(/\D/g, '');
        if (!csvContacts.some(c => c.number === cleanAuth)) {
            csvContacts.push({ number: cleanAuth, name: 'Willian Administrador', permission: 'admin' });
        }
    }
    
    for (const contact of csvContacts) {
        let phone = contact.number;
        if (phone.length === 10 || phone.length === 11) {
            phone = '55' + phone;
        }
        
        try {
            if (phoneToJidMap[phone]) continue; // Se já está no cache, pula
            
            const jid = await resolveJid(phone);
            // Se resolveJid retornou um JID válido (não fallback simples)
            if (jid && (!jid.endsWith('@c.us') || jid.includes('@lid') || jid.split('@')[0] !== phone)) {
                phoneToJidMap[phone] = jid;
                jidToPhoneMap[jid] = phone;
            }
        } catch (err) {
            log(`Erro ao resolver cache para ${phone}: ${err.message}`, 'WARNING');
        }
    }
    log(`Cache de JIDs atualizado. ${Object.keys(jidToPhoneMap).length} JIDs mapeados.`, 'SUCCESS');
}

// Resolver JID (ID interno do WhatsApp) a partir de um número de telefone
async function resolveJid(to) {
    if (!client) return `${to}@c.us`;
    
    // Limpar o número de destino
    let cleanTo = to.replace(/\D/g, '');
    
    // Se já termina com @c.us, @g.us ou @lid, retornar como está
    if (to.endsWith('@c.us') || to.endsWith('@g.us') || to.endsWith('@lid')) {
        return to;
    }
    
    // Adicionar código do país (Brasil) se parecer estar faltando (DDDs brasileiros têm 2 dígitos)
    if (cleanTo.length === 10 || cleanTo.length === 11) {
        cleanTo = '55' + cleanTo;
    }
    
    // Verificar cache primeiro
    if (phoneToJidMap[cleanTo]) {
        return phoneToJidMap[cleanTo];
    }
    
    try {
        log(`Resolvendo JID para o número: ${cleanTo}...`);
        
        // Tenta obter o ID registrado no WhatsApp
        let jid = await client.getNumberId(cleanTo);
        
        // Se for brasileiro (começa com 55) e tem o 9º dígito (13 dígitos no total, ex: 5561986221356)
        // O WhatsApp pode ter cadastrado com ou sem o 9º dígito. Vamos tentar ambos!
        if (!jid && cleanTo.startsWith('55') && cleanTo.length === 13) {
            const ddd = cleanTo.slice(2, 4);
            const rest = cleanTo.slice(5);
            const withoutNine = `55${ddd}${rest}`;
            log(`JID não encontrado com 9 dígitos. Tentando sem o 9º dígito: ${withoutNine}...`);
            jid = await client.getNumberId(withoutNine);
        }
        
        if (jid && jid._serialized) {
            log(`JID resolvido com sucesso: ${jid._serialized}`);
            phoneToJidMap[cleanTo] = jid._serialized;
            jidToPhoneMap[jid._serialized] = cleanTo;
            return jid._serialized;
        }
        
        log(`Aviso: getNumberId falhou para ${cleanTo}. Usando formato fallback @c.us`, 'WARNING');
        return `${cleanTo}@c.us`;
    } catch (err) {
        log(`Erro ao resolver JID para ${cleanTo}: ${err.message}. Usando fallback @c.us`, 'ERROR');
        return `${cleanTo}@c.us`;
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
let isInitializing = false;
let retryTimeout = null;
let debugScreenshotInterval = null;

// Inicializar o cliente WhatsApp Web de forma segura e assíncrona
async function initWhatsAppClient() {
    if (isInitializing) {
        log('Uma tentativa de inicialização já está em andamento. Ignorando...', 'INFO');
        return;
    }

    isInitializing = true;
    log('Inicializando cliente WhatsApp Web...', 'INFO');
    currentStatus = 'authenticating';
    latestQr = null;

    if (retryTimeout) {
        clearTimeout(retryTimeout);
        retryTimeout = null;
    }

    if (debugScreenshotInterval) {
        clearInterval(debugScreenshotInterval);
        debugScreenshotInterval = null;
    }

    if (client) {
        try {
            log('Destruindo instância anterior do cliente...');
            await client.destroy();
        } catch (e) {
            log(`Erro ao destruir cliente anterior: ${e.message}`, 'WARNING');
        }
        client = null;
    }

    client = new Client({
        authStrategy: new LocalAuth({
            dataPath: path.join(__dirname, '..', 'temp'),
            clientId: 'wwebjs_session'
        }),
        puppeteer: {
            headless: true,
            protocolTimeout: 180000, // Aumentado para 3 minutos para evitar timeout de protocolo
            args: [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding',
                '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
            ]
        }
    });

    // Iniciar captura periódica de tela para depuração (a cada 15 segundos)
    debugScreenshotInterval = setInterval(async () => {
        if (client && client.pupPage) {
            try {
                const logsDir = path.join(__dirname, '..', 'logs');
                if (!fs.existsSync(logsDir)) {
                    fs.mkdirSync(logsDir, { recursive: true });
                }
                const screenshotPath = path.join(logsDir, 'whatsapp_debug.png');
                await client.pupPage.screenshot({ path: screenshotPath });
                log(`Print da tela do WhatsApp salvo para depuração em: ${screenshotPath}`, 'DEBUG');
            } catch (err) {
                log(`Não foi possível tirar print da tela do WhatsApp: ${err.message}`, 'DEBUG_ERROR');
            }
        }
    }, 15000);

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
        if (debugScreenshotInterval) {
            clearInterval(debugScreenshotInterval);
            debugScreenshotInterval = null;
        }
    });

    client.on('ready', async () => {
        log('O cliente do WhatsApp Web está PRONTO para enviar/receber mensagens!', 'SUCCESS');
        currentStatus = 'connected';
        latestQr = null;
        isInitializing = false;
        
        // Limpar o print de depuração pois já conectou com sucesso
        if (debugScreenshotInterval) {
            clearInterval(debugScreenshotInterval);
            debugScreenshotInterval = null;
        }

        // Atualizar o cache de JIDs assim que conectar
        try {
            await updateJidCache();
        } catch (e) {
            log(`Erro ao inicializar cache de JIDs: ${e.message}`, 'WARNING');
        }
    });

    client.on('disconnected', (reason) => {
        log(`Desconectado do WhatsApp: ${reason}`, 'WARNING');
        currentStatus = 'disconnected';
        latestQr = null;
        isInitializing = false;
        
        if (debugScreenshotInterval) {
            clearInterval(debugScreenshotInterval);
            debugScreenshotInterval = null;
        }
        
        clearSessionFolder();
        
        // Agendar reinicialização se não houver outra agendada
        if (!retryTimeout) {
            log('Agendando reinicialização em 5 segundos...', 'INFO');
            retryTimeout = setTimeout(() => {
                retryTimeout = null;
                initWhatsAppClient();
            }, 5000);
        }
    });

    // Evento de recepção de mensagens
    client.on('message', async (msg) => {
        log(`Mensagem recebida de ${msg.from}: "${msg.body}"`);

        let fromJid = msg.from;
        
        // Se for de um grupo ou status broadcast, ignorar
        if (fromJid.endsWith('@g.us') || fromJid === 'status@broadcast') {
            return;
        }

        // Verificar se o JID está no cache. Se não estiver, atualiza o cache para ver se foi adicionado recentemente
        if (!jidToPhoneMap[fromJid]) {
            log(`JID ${fromJid} não encontrado no cache de autorizados. Atualizando cache...`, 'INFO');
            try {
                await updateJidCache();
            } catch (e) {}
        }

        let senderPhoneNumber = jidToPhoneMap[fromJid];
        
        // Se ainda não estiver mapeado no cache, tenta obter o número pelo método tradicional msg.getContact()
        if (!senderPhoneNumber) {
            log(`JID ${fromJid} não está mapeado como autorizado. Tentando obter número via getContact...`, 'INFO');
            try {
                const contact = await msg.getContact();
                senderPhoneNumber = contact.number || '';
            } catch (err) {
                log(`Erro ao obter contato para verificar número: ${err.message}`, 'WARNING');
            }
        }

        // Fallback final para a parte do ID
        if (!senderPhoneNumber) {
            senderPhoneNumber = fromJid.split('@')[0];
        }

        const senderClean = senderPhoneNumber.replace(/\D/g, '');

        log(`Repassando mensagem de ${senderClean} (JID: ${fromJid}) para o webhook Flask...`, 'INFO');
        
        // Monta o payload no formato esperado por agente_escavador.py (Z-API Mock)
        const webhookPayload = {
            phone: senderClean,
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
    });

    try {
        log('Chamando client.initialize()...', 'INFO');
        await client.initialize();
    } catch (err) {
        log(`Erro assíncrono capturado no client.initialize(): ${err.message || err}`, 'ERROR');
        currentStatus = 'disconnected';
        latestQr = null;
        isInitializing = false;
        
        if (debugScreenshotInterval) {
            clearInterval(debugScreenshotInterval);
            debugScreenshotInterval = null;
        }
        
        clearSessionFolder();
        
        if (!retryTimeout) {
            log('Agendando reinicialização em 5 segundos devido a erro...', 'INFO');
            retryTimeout = setTimeout(() => {
                retryTimeout = null;
                initWhatsAppClient();
            }, 5000);
        }
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

    try {
        const resolvedTo = await resolveJid(to);
        log(`Enviando mensagem de texto para ${resolvedTo}...`);
        const sentMsg = await client.sendMessage(resolvedTo, message);
        res.json({ success: true, messageId: sentMsg.id.id });
    } catch (err) {
        log(`Erro ao enviar mensagem para ${to}: ${err.message}`, 'ERROR');
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

    try {
        const resolvedTo = await resolveJid(to);
        log(`Enviando documento "${fileName}" para ${resolvedTo}...`);
        
        // Decodificar base64 e mimetype do payload
        const parts = document.split(';base64,');
        const mimetype = parts[0].replace('data:', '');
        const base64Data = parts[1];

        const media = new MessageMedia(mimetype, base64Data, fileName);
        const sentMsg = await client.sendMessage(resolvedTo, media);
        
        res.json({ success: true, messageId: sentMsg.id.id });
    } catch (err) {
        log(`Erro ao enviar documento para ${to}: ${err.message}`, 'ERROR');
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
