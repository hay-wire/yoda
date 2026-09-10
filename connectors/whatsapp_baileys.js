// Phase 2 WhatsApp ingestion. One shot: connect using the saved auth
// session, collect messages newer than the given timestamp, disconnect.
// Read/track only - this never sends a message.
//
// First run (no saved session yet) prints a QR code to scan with your
// phone; run it manually once before wiring it into the scheduler:
//   node connectors/whatsapp_baileys.js 0
//
// Usage: node whatsapp_baileys.js <sinceTimestampMs>
// Prints a JSON array of new messages to stdout, then exits.

const path = require('path')
const { default: makeWASocket, useMultiFileAuthState, DisconnectReason } = require('@whiskeysockets/baileys')

const AUTH_DIR = path.join(__dirname, '..', '.whatsapp-auth')
const sinceMs = Number(process.argv[2] || 0)
const SETTLE_MS = 8000 // window to receive queued/backlog messages after connecting

async function main() {
  const { state, saveCreds } = await useMultiFileAuthState(AUTH_DIR)
  const sock = makeWASocket({ auth: state, printQRInTerminal: true })

  const collected = []
  sock.ev.on('creds.update', saveCreds)

  sock.ev.on('messages.upsert', ({ messages }) => {
    for (const msg of messages) {
      if (!msg.message || msg.key.fromMe) continue

      const timestampMs = Number(msg.messageTimestamp) * 1000
      if (timestampMs <= sinceMs) continue

      const text =
        msg.message.conversation ||
        msg.message.extendedTextMessage?.text ||
        msg.message.imageMessage?.caption ||
        ''
      if (!text) continue

      collected.push({
        id: `${msg.key.remoteJid}:${msg.key.id}`,
        from: msg.pushName || msg.key.remoteJid,
        chat: msg.key.remoteJid,
        date: new Date(timestampMs).toISOString(),
        body: text,
        timestamp_ms: timestampMs,
      })
    }
  })

  await new Promise((resolve) => {
    sock.ev.on('connection.update', (update) => {
      if (update.connection === 'open') {
        setTimeout(resolve, SETTLE_MS)
      } else if (update.connection === 'close') {
        const loggedOut = update.lastDisconnect?.error?.output?.statusCode === DisconnectReason.loggedOut
        if (loggedOut) {
          process.stderr.write('Session logged out - delete .whatsapp-auth and re-scan the QR code.\n')
        }
        resolve()
      }
    })
  })

  await sock.end(undefined)
  process.stdout.write(JSON.stringify(collected))
}

main()
  .then(() => process.exit(0))
  .catch((err) => {
    process.stderr.write(String(err && err.stack ? err.stack : err) + '\n')
    process.exit(1)
  })
