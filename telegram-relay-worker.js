/**
 * Cloudflare Worker - Telegram API Relay
 * 
 * HF Spaces free tier blocks api.telegram.org outbound.
 * This worker relays Telegram API calls from HF Space → Telegram.
 * 
 * Deploy: https://dash.cloudflare.com → Workers → Create → paste this code
 * 
 * Usage from HF Space:
 *   Instead of: https://api.telegram.org/bot<TOKEN>/<method>
 *   Use:        https://<worker-name>.<your-subdomain>.workers.dev/relay/<method>
 *   And send header: X-Bot-Token: <TOKEN>
 */

const TELEGRAM_API = 'https://api.telegram.org';

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    
    // Health check
    if (url.pathname === '/' || url.pathname === '/health') {
      return new Response(JSON.stringify({ status: 'ok', service: 'telegram-relay' }), {
        headers: { 'Content-Type': 'application/json' }
      });
    }

    // Relay: /relay/<method>  OR  /bot<TOKEN>/<method>
    const token = request.headers.get('X-Bot-Token') || '';
    
    let method, botToken;
    if (url.pathname.startsWith('/relay/')) {
      method = url.pathname.replace('/relay/', '');
      botToken = token;
    } else if (url.pathname.startsWith('/bot')) {
      const parts = url.pathname.split('/');
      botToken = parts[1].replace('bot', '');
      method = parts.slice(2).join('/');
    } else {
      return new Response(JSON.stringify({ error: 'Not found' }), { status: 404 });
    }

    if (!botToken || !method) {
      return new Response(JSON.stringify({ error: 'Missing token or method' }), { status: 400 });
    }

    // Forward to Telegram
    const tgUrl = `${TELEGRAM_API}/bot${botToken}/${method}`;
    
    try {
      const init = {
        method: request.method,
        headers: { 'Content-Type': 'application/json' },
      };
      
      if (request.method === 'POST') {
        const body = await request.text();
        init.body = body;
      } else {
        // GET - pass query params
        const tgFullUrl = tgUrl + url.search;
        const resp = await fetch(tgFullUrl, init);
        const data = await resp.text();
        return new Response(data, {
          status: resp.status,
          headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
        });
      }
      
      const resp = await fetch(tgUrl, init);
      const data = await resp.text();
      
      return new Response(data, {
        status: resp.status,
        headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' }
      });
    } catch (e) {
      return new Response(JSON.stringify({ error: e.message }), {
        status: 502,
        headers: { 'Content-Type': 'application/json' }
      });
    }
  }
};
